"""
Main CDIC Engine v4.0
"""

import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Deque, Callable, Tuple
from dataclasses import asdict
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from logging.handlers import RotatingFileHandler

import structlog
import orjson
import numpy as np
from prometheus_client import Counter, Histogram

from .config import CDICConfig, VERSION, MAX_WORKERS
from .models import AuditEntry, WDLSignal, DecisionOption, DecisionContext, CDICResponse
from .enums import QuestionType, ResponseType, RiskLevel
from .utils.monitor import PerformanceMonitor
from .utils.hasher import SecureHasher
from .utils.doctrine import ImmutableDoctrine
from .utils.circuit_breaker import CircuitBreaker
from .utils.locking import DistributedLock
from .utils.cache import MultiLevelCache
from .utils.random import FastRandom

# Prometheus metrics
DECISION_REQUESTS = Counter('cdic_decisions_total', 'Total decision requests')
DECISION_ERRORS = Counter('cdic_decision_errors', 'Decision processing errors')
DECISION_LATENCY = Histogram('cdic_decision_latency_seconds', 'Decision latency')
CACHE_HITS = Counter('cdic_cache_hits', 'Cache hits')
CACHE_MISSES = Counter('cdic_cache_misses', 'Cache misses')
CLARIFICATION_BUDGET_EXCEEDED = Counter('cdic_clarification_budget_exceeded', 'Clarification budget exceeded')


class CDICEngine:
    """Optimized CDIC Engine v4.0"""
    
    def __init__(self, config: CDICConfig):
        self.config = config
        self.logger = self._setup_logging()
        self.doctrine = ImmutableDoctrine()
        self.hasher = SecureHasher(config.secret_key)
        self.distributed_lock = DistributedLock(config.redis_url)
        self.cache = MultiLevelCache(maxsize=10000, ttl=config.cache_ttl)
        self.random = FastRandom()
        
        # Thread-safe state
        self.pending_clarifications: Dict[str, Any] = {}
        self.audit_log: List[AuditEntry] = []
        self.wdl_signals: Dict[str, WDLSignal] = {}
        self.session_data: Dict[str, Any] = {}
        self.session_expiry: Dict[str, datetime] = {}
        self.decision_queue: Deque = deque(maxlen=config.max_concurrent_decisions)
        
        # New: Clarification budget tracking
        self.clarification_budget: Dict[str, int] = {}
        
        # Thread locks
        self._state_locks = {
            "audit": threading.RLock(),
            "signals": threading.RLock(),
            "sessions": threading.RLock(),
            "pending": threading.RLock(),
            "queue": threading.RLock(),
            "clarification_budget": threading.RLock()
        }
        
        # Circuit breakers
        self.circuit_breakers = {
            "decision": CircuitBreaker(
                config.circuit_breaker_threshold,
                config.circuit_breaker_timeout
            ),
            "clarification": CircuitBreaker(
                config.circuit_breaker_threshold,
                config.circuit_breaker_timeout
            ),
            "wdls": CircuitBreaker(
                config.circuit_breaker_threshold,
                config.circuit_breaker_timeout
            )
        }
        
        # Precomputed tables (optimized for speed)
        self.precomputed_tables = self._precompute_tables()
        
        # Performance monitor
        self.monitor = PerformanceMonitor(self)
        
        # Background workers
        if config.enable_background_workers:
            self._start_background_workers()
        
        self.logger.info(
            "cdic_engine_initialized",
            version=VERSION,
            workers=MAX_WORKERS,
            config=config.dict(exclude={'secret_key'})
        )
    
    def _setup_logging(self):
        """Setup structured logging"""
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer()
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
        )
        
        logger = logging.getLogger("cdic")
        logger.setLevel(getattr(logging, self.config.log_level))
        
        # Console handler
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(console)
        
        # File handler with rotation
        file_handler = RotatingFileHandler(
            'cdic.log',
            maxBytes=10_000_000,
            backupCount=5
        )
        logger.addHandler(file_handler)
        
        return structlog.wrap_logger(logger)
    
    def _check_clarification_budget(self, session_id: str) -> Tuple[bool, int]:
        """
        Check if clarification budget is exceeded for session.
        Returns: (budget_exceeded, remaining_budget)
        """
        with self._state_locks["clarification_budget"]:
            budget = self.clarification_budget.get(session_id, self.config.clarification_budget_per_session)
            
            if budget <= 0:
                CLARIFICATION_BUDGET_EXCEEDED.inc()
                return True, 0
            
            return False, budget
    
    def _decrement_clarification_budget(self, session_id: str) -> int:
        """Decrement clarification budget and return remaining"""
        with self._state_locks["clarification_budget"]:
            current = self.clarification_budget.get(session_id, self.config.clarification_budget_per_session)
            new_budget = max(0, current - 1)
            self.clarification_budget[session_id] = new_budget
            return new_budget
    
    def _should_ask_clarification(self, context: DecisionContext, options: List[DecisionOption]) -> bool:
        """
        Determine if clarification is needed based on:
        1. Clarification budget
        2. Option confidence spread
        3. Risk level
        """
        # Check budget first
        budget_exceeded, remaining = self._check_clarification_budget(context.session_id)
        if budget_exceeded:
            self.logger.info(
                "clarification_budget_exceeded",
                session_id=context.session_id,
                remaining=remaining
            )
            return False
        
        # Calculate confidence spread
        if len(options) < 2:
            return False
        
        confidences = [opt.confidence for opt in options]
        confidence_spread = max(confidences) - min(confidences)
        
        # Determine if clarification is beneficial
        needs_clarification = (
            confidence_spread > 0.3 or  # High spread indicates uncertainty
            context.risk_tolerance == RiskLevel.LOW or  # Low risk tolerance requires more certainty
            any(not opt.doctrine_compliant for opt in options)  # Doctrine violations need clarification
        )
        
        if needs_clarification:
            self._decrement_clarification_budget(context.session_id)
        
        return needs_clarification
    
    def _precompute_tables(self) -> Dict[str, Any]:
        """Precompute optimized lookup tables"""
        return {
            "response_mappings": {
                QuestionType.COVERAGE: {
                    ResponseType.YES: {"coverage_required": True},
                    ResponseType.FLEXIBLE: {"coverage_required": False},
                    ResponseType.ASK_LATER: {"defer": True}
                },
                QuestionType.CULTURAL: {
                    ResponseType.YES: {"cultural_required": True},
                    ResponseType.NO: {"cultural_required": False},
                    ResponseType.DEPENDS: {"cultural_conditional": True}
                },
                QuestionType.EXPLORATION: {
                    ResponseType.EXPLORE: {"exploration_mode": "aggressive"},
                    ResponseType.CONSERVATIVE: {"exploration_mode": "conservative"},
                    ResponseType.DECIDE: {"exploration_mode": "manual"}
                },
                QuestionType.TEMPORAL: {
                    ResponseType.TODAY: {"temporal_scope": "session"},
                    ResponseType.REMEMBER: {"temporal_scope": "persistent"},
                    ResponseType.DONT_SAVE: {"temporal_scope": "ephemeral"}
                },
                QuestionType.CONFIDENCE: {
                    ResponseType.SAFE: {"confidence_mode": "conservative"},
                    ResponseType.VARIETY: {"confidence_mode": "exploratory"},
                    ResponseType.DEFAULT: {"confidence_mode": "balanced"}
                }
            },
            "risk_profiles": {
                RiskLevel.LOW: {"max_risk": 0.2, "confidence_boost": 0.1},
                RiskLevel.MEDIUM: {"max_risk": 0.5, "confidence_boost": 0.0},
                RiskLevel.HIGH: {"max_risk": 0.7, "confidence_boost": -0.1},
                RiskLevel.CRITICAL: {"max_risk": 0.9, "confidence_boost": -0.2}
            },
            "generation_templates": {
                "conservative": {
                    "risk_tolerance": 0.1,
                    "exploration": 0.0,
                    "diversity": 0.3
                },
                "balanced": {
                    "risk_tolerance": 0.4,
                    "exploration": 0.5,
                    "diversity": 0.5
                },
                "exploratory": {
                    "risk_tolerance": 0.7,
                    "exploration": 0.8,
                    "diversity": 0.8
                }
            }
        }
    
    @DECISION_LATENCY.time()
    def process_decision(self, context: DecisionContext,
                        pipeline_state: Dict[str, Any]) -> CDICResponse:
        """Optimized decision processing with caching and timeout"""
        DECISION_REQUESTS.inc()
        
        # Check cache first
        cache_key = f"decision:{context.request_id}"
        cached = self.cache.get(cache_key)
        if cached:
            CACHE_HITS.inc()
            return cached
        
        CACHE_MISSES.inc()
        
        try:
            # Validate context
            if not self._validate_context(context):
                raise ValueError("Invalid context")
            
            # Process with circuit breaker and timeout
            start_time = time.time()
            try:
                result = self.circuit_breakers["decision"].call(
                    self._process_decision_internal,
                    context,
                    pipeline_state
                )
            except Exception as e:
                # If circuit breaker is open or other error, we fallback
                self.logger.warning("circuit_breaker_open_or_error", error=str(e))
                result = self._create_fallback_response(context)
            
            # Check for timeout
            duration = (time.time() - start_time) * 1000
            if duration > self.config.decision_timeout_seconds * 1000:
                self.logger.warning("decision_timeout", 
                                   request_id=context.request_id,
                                   duration_ms=duration)
                result = self._create_fallback_response(context)
            
            # Log audit
            self._log_audit("decision_completed", {
                "request_id": context.request_id,
                "duration_ms": duration,
                "success": True,
                "intent": context.intent,
                "clarification_needed": result.clarification_needed
            })
            
            # Cache result
            self.cache.set(cache_key, result)
            return result
        
        except Exception as e:
            DECISION_ERRORS.inc()
            self.logger.error("decision_failed",
                            request_id=context.request_id,
                            error=str(e))
            # Fallback response on any error
            return self._create_fallback_response(context)
    
    def _process_decision_internal(self, context: DecisionContext,
                                  pipeline_state: Dict[str, Any]) -> CDICResponse:
        """Internal decision processing - only generates options"""
        # Generate options in parallel
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for i in range(5):  # Generate 5 options in parallel
                futures.append(
                    executor.submit(
                        self._generate_option,
                        context, pipeline_state, i
                    )
                )
            
            options = []
            for future in as_completed(futures):
                try:
                    options.append(future.result(timeout=1.0))
                except FutureTimeoutError:
                    continue
        
        # Determine if clarification is needed (ROLE SEPARATION: CDIC only suggests)
        clarification_needed = self._should_ask_clarification(context, options)
        
        # Calculate overall confidence (average of top 3 options)
        if options:
            sorted_options = sorted(options, key=lambda x: x.confidence, reverse=True)
            top_confidence = sorted_options[0].confidence
            avg_confidence = sum(opt.confidence for opt in sorted_options[:3]) / min(3, len(sorted_options))
            overall_confidence = (top_confidence + avg_confidence) / 2
        else:
            overall_confidence = 0.0
        
        # Return CDICResponse (NOT final decision)
        return CDICResponse(
            options=options,
            confidence=overall_confidence,
            clarification_needed=clarification_needed
        )
    
    def _generate_option(self, context: DecisionContext,
                        pipeline_state: Dict[str, Any],
                        iteration: int) -> DecisionOption:
        """Generate decision option with optimized parameters"""
        # Get appropriate template
        if context.exploration_allowed:
            template = self.precomputed_tables["generation_templates"]["exploratory"]
        elif context.risk_tolerance == RiskLevel.LOW:
            template = self.precomputed_tables["generation_templates"]["conservative"]
        else:
            template = self.precomputed_tables["generation_templates"]["balanced"]
        
        # Get thread-safe random generator
        rng = self.random.get_generator()
        
        # Create option
        option = DecisionOption(
            action=self._generate_action(context, iteration),
            confidence=self._calculate_confidence(context, pipeline_state, iteration),
            rationale=self._generate_rationale(context),
            risk_score=rng.beta(2, 5) * template["risk_tolerance"],
            diversity_score=1.0 - (iteration * 0.15),
            generation_cost=iteration * 0.05
        )
        
        # Check doctrine compliance
        compliant, violations = self.doctrine.check_compliance(asdict(option))
        option.doctrine_compliant = compliant
        if violations:
            option.doctrine_violations = violations
            option.confidence *= 0.8
        
        return option
    
    def _calculate_confidence(self, context: DecisionContext,
                             pipeline_state: Dict[str, Any],
                             iteration: int) -> float:
        """Fast confidence calculation"""
        base_confidence = pipeline_state.get("base_confidence", 0.5)
        
        # Apply iteration penalty
        iteration_penalty = 1.0 - (iteration * 0.05)
        
        # Apply risk profile boost
        risk_profile = self.precomputed_tables["risk_profiles"][context.risk_tolerance]
        risk_boost = risk_profile["confidence_boost"]
        
        confidence = base_confidence * iteration_penalty + risk_boost
        
        return min(0.99, max(0.1, confidence))
    
    def _generate_action(self, context: DecisionContext, iteration: int) -> str:
        """Generate action based on intent"""
        action_sets = {
            "medical": ["diagnose", "refer", "monitor", "treat", "advise"],
            "financial": ["invest", "hold", "divest", "analyze", "report"],
            "technical": ["implement", "test", "debug", "optimize", "document"],
            "general": ["proceed", "delay", "consult", "abort", "research"]
        }
        
        # Find matching category
        category = "general"
        intent_lower = context.intent.lower()
        for cat in action_sets:
            if cat in intent_lower:
                category = cat
                break
        
        actions = action_sets[category]
        rng = self.random.get_generator()
        return rng.choice(actions)
    
    def _generate_rationale(self, context: DecisionContext) -> str:
        """Generate concise rationale"""
        templates = [
            f"Based on {context.intent} analysis with risk tolerance {context.risk_tolerance.value}.",
            f"Considering historical patterns and current context for {context.intent}.",
            f"Optimizing for {context.intent} with balanced risk-reward assessment.",
            f"Decision framework applied to {context.intent} scenario."
        ]
        
        rng = self.random.get_generator()
        return rng.choice(templates)
    
    def _select_best_option(self, options: List[DecisionOption],
                           context: DecisionContext) -> DecisionOption:
        """Select best option using weighted scoring"""
        if not options:
            return self._create_fallback_option(context)
        
        best_score = -1.0
        best_option = None
        
        for option in options:
            score = self._score_option(option, context)
            if score > best_score:
                best_score = score
                best_option = option
        
        # Add selection metadata
        best_option.metadata["selection_score"] = best_score
        best_option.metadata["selection_method"] = "weighted_scoring"
        
        return best_option
    
    def _score_option(self, option: DecisionOption,
                     context: DecisionContext) -> float:
        """Calculate weighted score for option"""
        weights = {
            "confidence": 0.35,
            "risk_adjustment": 0.25,
            "doctrine_compliance": 0.20,
            "diversity": 0.15,
            "cost_efficiency": 0.05
        }
        
        scores = {
            "confidence": option.confidence,
            "risk_adjustment": 1.0 - min(1.0, option.risk_score),
            "doctrine_compliance": 1.0 if option.doctrine_compliant else 0.3,
            "diversity": option.diversity_score,
            "cost_efficiency": 1.0 - min(1.0, option.generation_cost)
        }
        
        # Apply penalties for violations
        if option.doctrine_violations:
            scores["doctrine_compliance"] *= 0.5
        
        # Calculate weighted score
        total_score = sum(scores[factor] * weight
                         for factor, weight in weights.items())
        
        return total_score
    
    def _create_fallback_option(self, context: DecisionContext) -> DecisionOption:
        """Create safe fallback option"""
        return DecisionOption(
            action="defer_decision",
            confidence=0.3,
            rationale="No viable options generated, deferring to user",
            risk_score=0.1,
            doctrine_compliant=True,
            metadata={"fallback": True}
        )
    
    def _create_fallback_response(self, context: DecisionContext) -> CDICResponse:
        """Create fallback response when CDIC fails"""
        fallback_option = self._create_fallback_option(context)
        
        return CDICResponse(
            options=[fallback_option],
            confidence=0.3,
            clarification_needed=False
        )
    
    def _get_wdls_influence(self, context: DecisionContext) -> float:
        """Calculate WDLS influence with caching"""
        cache_key = f"wdls_influence:{context.intent}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        with self._state_locks["signals"]:
            relevant_signals = [
                s for s in self.wdl_signals.values()
                if s.intent == context.intent and 
                s.timestamp > datetime.utcnow() - timedelta(hours=24)
            ]
        
        if not relevant_signals:
            influence = 0.0
        else:
            # Weighted average with decay
            total_weight = 0.0
            weighted_sum = 0.0
            
            for signal in relevant_signals:
                age_hours = (datetime.utcnow() - signal.timestamp).total_seconds() / 3600
                decay = np.exp(-signal.decay_rate * age_hours)
                weight = signal.weight * decay * signal.confidence
                total_weight += weight
                weighted_sum += signal.trend_impact * weight
            
            influence = weighted_sum / total_weight if total_weight > 0 else 0.0
        
        # Apply cap
        influence = max(-0.15, min(0.15, influence))
        
        # Cache for 5 minutes
        self.cache.set(cache_key, influence, ttl=300)
        return influence
    
    def _validate_context(self, context: DecisionContext) -> bool:
        """Fast context validation"""
        try:
            # Check required fields
            if not all([context.intent, context.user_id, context.session_id]):
                return False
            
            # Check session expiry
            with self._state_locks["sessions"]:
                expiry = self.session_expiry.get(context.session_id)
                if expiry and expiry < datetime.utcnow():
                    return False
            
            return True
        except Exception:
            return False
    
    def _log_audit(self, operation: str, data: Dict[str, Any]):
        """Thread-safe audit logging"""
        entry = AuditEntry(
            operation=operation,
            request_id=data.get("request_id", "system"),
            user_id=data.get("user_id", "system"),
            session_id=data.get("session_id", "system"),
            duration_ms=data.get("duration_ms", 0.0),
            success=data.get("success", True),
            error_message=data.get("error_message", ""),
            metadata=data
        )
        
        with self._state_locks["audit"]:
            self.audit_log.append(entry)
            
            # Auto-clean if too large
            if len(self.audit_log) > self.config.max_audit_log_size:
                self.audit_log = self.audit_log[-self.config.max_audit_log_size:]
    
    def _start_background_workers(self):
        """Start optimized background workers"""
        workers = [
            ("cleanup", self._background_cleanup, 3600),
            ("metrics", self._background_metrics, 300),
            ("audit_flush", self._background_audit_flush, 60)
        ]
        
        for name, func, interval in workers:
            thread = threading.Thread(
                target=self._worker_wrapper,
                args=(name, func, interval),
                daemon=True,
                name=f"cdic_{name}"
            )
            thread.start()
            self.logger.info("worker_started", worker=name)
    
    def _worker_wrapper(self, name: str, func: Callable, interval: int):
        """Worker wrapper with error handling"""
        while True:
            try:
                func()
            except Exception as e:
                self.logger.error("worker_failed", worker=name, error=str(e))
            time.sleep(interval)
    
    def _background_cleanup(self):
        """Cleanup stale data"""
        # Clean expired sessions
        cutoff = datetime.utcnow() - timedelta(hours=self.config.max_session_age_hours)
        
        with self._state_locks["sessions"]:
            expired = [
                sid for sid, expiry in self.session_expiry.items()
                if expiry < cutoff
            ]
            for sid in expired:
                self.session_data.pop(sid, None)
                self.session_expiry.pop(sid, None)
            
            if expired:
                self.logger.info("sessions_cleaned", count=len(expired))
        
        # Clean old WDLS signals
        with self._state_locks["signals"]:
            if len(self.wdl_signals) > self.config.max_wdls_signals:
                # Keep only recent signals
                sorted_signals = sorted(
                    self.wdl_signals.items(),
                    key=lambda x: x[1].timestamp,
                    reverse=True
                )[:self.config.max_wdls_signals]
                self.wdl_signals = dict(sorted_signals)
        
        # Clean old clarification budgets
        with self._state_locks["clarification_budget"]:
            old_sessions = [
                sid for sid in self.clarification_budget.keys()
                if sid not in self.session_expiry or 
                self.session_expiry[sid] < datetime.utcnow() - timedelta(hours=1)
            ]
            for sid in old_sessions:
                self.clarification_budget.pop(sid, None)
    
    def _background_metrics(self):
        """Collect and report metrics"""
        metrics = {
            "active_sessions": len(self.session_data),
            "wdls_signals": len(self.wdl_signals),
            "audit_entries": len(self.audit_log),
            "cache_hits": self.cache.stats["hits"],
            "cache_misses": self.cache.stats["misses"],
            "clarification_budgets": len(self.clarification_budget)
        }
        
        # Check SLA
        sla_check = self.monitor.check_sla_violations()
        self.logger.info("system_metrics", **metrics)
        
        if sla_check["requires_intervention"]:
            self.logger.warning("sla_violations",
                               violations=sla_check["violations"])
    
    def _background_audit_flush(self):
        """Flush audit logs to persistent storage"""
        if not self.audit_log:
            return
        
        # In production, this would write to database/object storage
        # For now, write to compressed JSON file
        try:
            import gzip
            import json
            
            filename = f"audit/audit_{datetime.utcnow().strftime('%Y%m%d_%H')}.json.gz"
            
            with gzip.open(filename, 'wt', encoding='utf-8') as f:
                json.dump([asdict(entry) for entry in self.audit_log[-1000:]], f)
            
            # Remove flushed entries
            with self._state_locks["audit"]:
                self.audit_log = self.audit_log[:-1000]
                
        except Exception as e:
            self.logger.error("audit_flush_failed", error=str(e))
    
    def _get_error_rate(self) -> float:
        """Calculate current error rate"""
        # Look at recent audit entries
        with self._state_locks["audit"]:
            recent = self.audit_log[-100:] if len(self.audit_log) > 100 else self.audit_log
            
            if not recent:
                return 0.0
            
            errors = sum(1 for entry in recent if not entry.success)
            return errors / len(recent)
    
    def _get_queue_depth(self) -> int:
        """Get current queue depth"""
        with self._state_locks["queue"]:
            return len(self.decision_queue)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics"""
        return {
            "version": VERSION,
            "uptime_seconds": time.time() - self.monitor.start_time,
            "active_sessions": len(self.session_data),
            "pending_clarifications": len(self.pending_clarifications),
            "wdls_signals": len(self.wdl_signals),
            "audit_log_size": len(self.audit_log),
            "cache_stats": self.cache.stats.copy(),
            "circuit_breakers": {
                name: cb.state for name, cb in self.circuit_breakers.items()
            },
            "clarification_budgets": len(self.clarification_budget),
            "performance": self.monitor.check_sla_violations()["metrics"]
        }
