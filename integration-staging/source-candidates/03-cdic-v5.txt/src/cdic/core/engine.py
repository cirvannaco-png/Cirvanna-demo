import asyncio
import time
import uuid
import pickle
import logging
from collections import defaultdict
from threading import Thread, Lock
from typing import Dict, List, Tuple, Optional, Any
from queue import Queue

from ..common.utils import lazy_import
from ..common.structs import DecisionContext, ClarificationQuestion, ClarificationResponse, WDLSSignal, AuditEntry
from ..common.enums import (
    QuestionType, ResponseType, DecisionState, HybridResolution,
    ModestyCompliance, TrendAuthority
)
from ..common.caches import LRUCache, _context_vector_cache
from ..engines import CTIFEngineGPU, WDLSEngineVectorized, ParallelOptionGenerator
from .supporting import SecureHasher, CircuitBreaker, ImmutableDoctrine
from .metrics import PerfMetrics

class CDICEngine:
    """Unified CDIC Engine v5.0 with all optimizations and production features."""
    def __init__(self, config):
        self.config = config
        self.np = lazy_import('numpy')
        self.ctif = CTIFEngineGPU(use_gpu=config.use_gpu)
        self.wdls = WDLSEngineVectorized(
            max_realtime=100,
            cold_store=self._init_redis(config.redis_url) if config.redis_url else None
        )
        self.option_gen = ParallelOptionGenerator(
            max_workers=config.max_workers,
            use_gpu=config.use_gpu
        )
        self.hasher = SecureHasher(config.secret_key.encode() if isinstance(config.secret_key, str) else config.secret_key)
        self.doctrine = ImmutableDoctrine()

        # Redis client for distributed state
        self.redis = self._init_redis(config.redis_url)
        # PostgreSQL connection for audit (optional)
        self.db_pool = self._init_postgres(config.postgres_url) if config.postgres_url else None

        # Logger
        self.logger = logging.getLogger("cdic")
        self.logger.setLevel(getattr(logging, config.log_level))
        if not self.logger.handlers:
            ch = logging.StreamHandler()
            ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(ch)

        # Local caches and state
        self.sessions = LRUCache(10000)
        self.session_data = defaultdict(dict)
        self.session_locks = defaultdict(Lock)
        self.session_timeout = config.max_session_age_hours * 3600

        # Precomputed tables
        self.precomputed = self._build_precomputed_tables()

        # Circuit breakers
        self.circuit_breakers = {
            'decision': CircuitBreaker(config.circuit_breaker_threshold, config.circuit_breaker_timeout),
            'clarification': CircuitBreaker(config.circuit_breaker_threshold, config.circuit_breaker_timeout),
            'generation': CircuitBreaker(config.circuit_breaker_threshold, config.circuit_breaker_timeout),
        }

        # Metrics
        self.metrics = PerfMetrics()
        self.stats = {
            'decisions_processed': 0,
            'clarifications_triggered': 0,
            'early_exits': 0,
            'errors_handled': 0
        }

        # Async queues
        self.task_queue = asyncio.Queue(maxsize=10000)
        self.audit_queue = Queue(maxsize=10000)

        # Background workers
        self._start_background_workers()
        self._warmup()

    def _init_redis(self, url):
        if not url:
            return None
        try:
            redis = lazy_import('redis')
            return redis.Redis.from_url(url, decode_responses=False)
        except Exception:
            return None

    def _init_postgres(self, url):
        # Simplified - in real app use asyncpg or SQLAlchemy
        pass

    def _build_precomputed_tables(self):
        np = self.np
        # Response mappings: [qtype][response][effect indices]
        response_mappings = np.zeros((8, 20, 4), dtype=np.int8)
        # Fill for each question type (simplified)
        response_mappings[0, ResponseType.YES.value] = [1, 1, 0, 0]   # coverage yes -> persistent
        response_mappings[0, ResponseType.FLEXIBLE.value] = [0, 0, 0, 0]
        response_mappings[0, ResponseType.ASK_LATER.value] = [0, 0, 1, 1]  # defer, session_bound

        # early exit matrix
        early_exit_matrix = np.array([
            [ModestyCompliance.FULL.value, 0, 1, 1],   # exit
            [ModestyCompliance.NONE.value, 0, 0, 1],   # exit
        ], dtype=np.int16)

        # priority matrix for triggers
        priority_matrix = np.array([5, 4, 3, 2, 1], dtype=np.int8)

        return {
            'response_mappings': response_mappings,
            'trend_caps': np.array([0.15, 0.15, 0.15, 0.15, 0.1, 0.2, 0.05, 0.1], dtype=np.float32),
            'silence_responses': np.array([0, 0, 6, 8, 11, 15, 16, 19], dtype=np.int8),
            'early_exit_matrix': early_exit_matrix,
            'priority_matrix': priority_matrix
        }

    def _start_background_workers(self):
        # Audit worker
        Thread(target=self._audit_worker, daemon=True).start()
        # Session cleanup
        Thread(target=self._session_cleanup_worker, daemon=True).start()
        # Metrics
        Thread(target=self._metrics_worker, daemon=True).start()

    def _warmup(self):
        """Pre-warm caches."""
        self.logger.info("Warming up CDIC engine...")
        warmup_contexts = [
            {'intent': 'recommendation', 'category': 'general'},
            {'intent': 'search', 'query': 'test'},
            {'intent': 'filter', 'criteria': 'default'}
        ]
        for ctx in warmup_contexts:
            self.ctif.compute_context_vector(ctx)
            self.ctif.get_contextual_influence(ctx)

    # ---------- Distributed Locking Helpers ----------
    def _acquire_session_lock(self, session_id: int, timeout: int = 5) -> bool:
        """Acquire a distributed lock for a session using Redis."""
        if not self.redis:
            return True  # no distributed locking, assume local only
        lock_key = f"lock:session:{session_id}"
        # Use SETNX with expiration
        acquired = self.redis.set(lock_key, "1", nx=True, ex=timeout)
        return bool(acquired)

    def _release_session_lock(self, session_id: int):
        if not self.redis:
            return
        lock_key = f"lock:session:{session_id}"
        self.redis.delete(lock_key)

    # ---------- Main Decision Pipeline ----------
    async def process_decision(self, context: DecisionContext, pipeline_state: Dict) -> Dict:
        timer = self.metrics.start_timer('decision_total')
        try:
            self._update_session_activity(context.session_id)

            if not self.circuit_breakers['decision'].allow_request():
                result = await self._circuit_breaker_fallback(context)
                timer.stop()
                return result

            # enrich pipeline state if missing
            self._compute_pipeline_state(pipeline_state, context)

            # early exit check (vectorized)
            if self._check_early_exit_vectorized(pipeline_state):
                self.stats['early_exits'] += 1
                result = await self._execute_early_exit(context, pipeline_state)
                timer.stop()
                return result

            # check clarification triggers
            triggers = await self._check_triggers_parallel(context, pipeline_state)
            if triggers:
                self.stats['clarifications_triggered'] += 1
                question = await self._generate_question_async(triggers[0], context)
                if question:
                    self._halt_pipeline(pipeline_state)
                    # store pending in Redis if distributed
                    if self.redis:
                        self.redis.setex(f"clarify:{question.question_id}", 300,
                                         pickle.dumps({'question': question, 'session': context.session_id}))
                    # else keep in local dict (not shown for simplicity)
                    asyncio.create_task(self._log_async('clarification_triggered', {
                        'question_id': question.question_id,
                        'context_id': context.request_id
                    }))
                    timer.stop()
                    return {
                        'state': DecisionState.CLARIFICATION_PENDING,
                        'question_id': question.question_id,
                        'pipeline_halted': True,
                        'timestamp': time.time()
                    }

            # generate options with n‑look pruning
            options = await self._generate_and_score_options(context, pipeline_state)
            best_option = await self._select_best_option_async(options, context)
            best_option = self._apply_hard_authority_caps(best_option, context)

            decision = self._create_final_decision(context, best_option, options)

            # background audit logging
            asyncio.create_task(self._log_decision_async(decision, context))

            self.circuit_breakers['decision'].record_success()
            self.stats['decisions_processed'] += 1
            timer.stop()
            return decision

        except Exception as e:
            self.stats['errors_handled'] += 1
            self.circuit_breakers['decision'].record_failure()
            self.logger.error(f"Decision failed: {e}", exc_info=True)
            return await self._safe_fallback(context, pipeline_state, str(e))

    def _update_session_activity(self, session_id: int):
        # acquire lock for session update
        locked = self._acquire_session_lock(session_id)
        try:
            with self.session_locks[session_id]:
                self.session_data[session_id]['last_activity'] = time.time()
        finally:
            if locked:
                self._release_session_lock(session_id)

    def _compute_pipeline_state(self, pipeline_state: Dict, context: DecisionContext):
        if 'confidence' not in pipeline_state:
            pipeline_state['confidence'] = 0.5
        if 'hybrid_resolution' not in pipeline_state:
            pipeline_state['hybrid_resolution'] = HybridResolution.UNDECIDED.value
        if 'user_override' not in pipeline_state:
            pipeline_state['user_override'] = False
        if 'modesty_compliance' not in pipeline_state:
            threshold = self._compute_threshold_sync(context)
            if pipeline_state['confidence'] >= threshold:
                pipeline_state['modesty_compliance'] = ModestyCompliance.FULL.value
            elif pipeline_state['confidence'] >= threshold * 0.7:
                pipeline_state['modesty_compliance'] = ModestyCompliance.PARTIAL.value
            else:
                pipeline_state['modesty_compliance'] = ModestyCompliance.NONE.value
        if 'coverage_deviation' not in pipeline_state:
            pipeline_state['coverage_deviation'] = 0.5 if not context.coverage_flag else 0.1
        if 'changes_possible' not in pipeline_state:
            pipeline_state['changes_possible'] = True

    def _check_early_exit_vectorized(self, pipeline_state: Dict) -> bool:
        mc = pipeline_state.get('modesty_compliance', 0)
        cd = pipeline_state.get('coverage_deviation', 1.0)
        cp = int(pipeline_state.get('changes_possible', True))
        # any circuit breaker open forces early exit
        if any(cb.state == "OPEN" for cb in self.circuit_breakers.values()):
            return True
        matrix = self.precomputed['early_exit_matrix']
        conditions = self.np.array([mc, cd, cp])
        matches = self.np.all(matrix[:, :3] == conditions, axis=1)
        return self.np.any(matches)

    async def _check_triggers_parallel(self, context: DecisionContext, pipeline_state: Dict) -> List[Tuple]:
        tasks = [
            self._check_humility_trigger(context, pipeline_state),
            self._check_coverage_trigger(pipeline_state),
            self._check_hybrid_trigger(pipeline_state),
            self._check_doctrine_trigger(context, pipeline_state)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        triggers = []
        for i, result in enumerate(results):
            if isinstance(result, tuple) and result[0]:
                priority = self.precomputed['priority_matrix'][i]
                triggers.append((priority, i, result[1], result[2]))
        triggers.sort(key=lambda x: x[0], reverse=True)
        return triggers

    async def _check_humility_trigger(self, context: DecisionContext, pipeline_state: Dict) -> Tuple[bool, str, Dict]:
        confidence = pipeline_state.get('confidence', 0.5)
        threshold = await self._compute_dynamic_threshold_async(context)
        if confidence < threshold:
            return (True, 'humility_threshold', {'confidence': confidence, 'threshold': threshold})
        return (False, '', {})

    async def _check_coverage_trigger(self, pipeline_state: Dict) -> Tuple[bool, str, Dict]:
        dev = pipeline_state.get('coverage_deviation', 0.0)
        if dev > 0.3:
            return (True, 'coverage_deviation', {'deviation': dev})
        return (False, '', {})

    async def _check_hybrid_trigger(self, pipeline_state: Dict) -> Tuple[bool, str, Dict]:
        res = pipeline_state.get('hybrid_resolution', HybridResolution.UNDECIDED.value)
        if res == HybridResolution.CONFLICT.value:
            return (True, 'hybrid_conflict', {})
        return (False, '', {})

    async def _check_doctrine_trigger(self, context: DecisionContext, pipeline_state: Dict) -> Tuple[bool, str, Dict]:
        if pipeline_state.get('user_override', False):
            # Check if any potential decision would violate doctrine (simplified)
            # For now, just trigger if user override is present
            return (True, 'doctrine_conflict', {})
        return (False, '', {})

    async def _compute_dynamic_threshold_async(self, context: DecisionContext) -> float:
        cache_key = f"threshold_{context.intent}_{int(time.time() // 3600)}"
        cached = self.sessions.get(cache_key)
        if cached:
            return cached
        loop = asyncio.get_event_loop()
        threshold = await loop.run_in_executor(None, self._compute_threshold_sync, context)
        self.sessions.put(cache_key, threshold)
        return threshold

    def _compute_threshold_sync(self, context: DecisionContext) -> float:
        intent_class = self._classify_intent_fast(context.intent)
        base = {'high_stakes': 0.5, 'medium_stakes': 0.35, 'low_stakes': 0.25}.get(intent_class, 0.3)
        # Add dynamic factors (simplified)
        return base

    def _classify_intent_fast(self, intent: str) -> str:
        intent_lower = intent.lower()
        if any(kw in intent_lower for kw in ['medical', 'safety', 'critical', 'emergency']):
            return 'high_stakes'
        elif any(kw in intent_lower for kw in ['financial', 'legal', 'important']):
            return 'medium_stakes'
        else:
            return 'low_stakes'

    async def _generate_question_async(self, trigger: Tuple, context: DecisionContext) -> Optional[ClarificationQuestion]:
        trigger_idx = trigger[1]
        qtype_map = {
            0: QuestionType.CONFIDENCE,
            1: QuestionType.COVERAGE,
            2: QuestionType.EXPLORATION,
            3: QuestionType.STAKEHOLDER
        }
        qtype = qtype_map.get(trigger_idx)
        if not qtype:
            return None
        loop = asyncio.get_event_loop()
        question = await loop.run_in_executor(None, self._generate_question_sync, qtype, context)
        return question

    def _generate_question_sync(self, qtype: QuestionType, context: DecisionContext) -> ClarificationQuestion:
        templates = {
            QuestionType.CONFIDENCE: ("Prefer fewer safe options or more variety?",
                                      [ResponseType.SAFE, ResponseType.VARIETY, ResponseType.DEFAULT], 0),
            QuestionType.COVERAGE: ("Is coverage important for this choice?",
                                    [ResponseType.YES, ResponseType.FLEXIBLE, ResponseType.ASK_LATER], 0),
            QuestionType.EXPLORATION: ("Would you like me to explore more freely or stay conservative?",
                                       [ResponseType.EXPLORE, ResponseType.CONSERVATIVE, ResponseType.DECIDE], 0),
            QuestionType.STAKEHOLDER: ("Will others be affected by this decision?",
                                       [ResponseType.AFFECTED, ResponseType.UNAFFECTED], 1),
        }
        prompt, responses, persistence = templates.get(qtype, ("", [], 0))
        return ClarificationQuestion.create(qtype, prompt, responses, persistence)

    async def _generate_and_score_options(self, context: DecisionContext, pipeline_state: Dict) -> List[Dict]:
        confidence = pipeline_state.get('confidence', 0.5)
        base_count = 5
        if confidence < 0.3:
            base_count = 8
        elif confidence > 0.7:
            base_count = 3
        ctif_influence = self.ctif.get_contextual_influence({'intent': context.intent, 'input_hash': context.input_hash})
        options = await self.option_gen.generate_options(context, base_count, self.ctif, self.wdls, ctif_influence)
        return options

    async def _select_best_option_async(self, options: List[Dict], context: DecisionContext) -> Dict:
        if not options:
            return {'decision': 'no_options_available', 'confidence': 0.0}
        # filter doctrine compliant
        compliant = []
        for opt in options:
            ok, violations = self.doctrine.check_compliance(opt)
            opt['doctrine_compliant'] = ok
            if ok:
                compliant.append(opt)
            else:
                opt['doctrine_violations'] = violations
        if not compliant:
            best = max(options, key=lambda x: x.get('final_score', 0))
            best['doctrine_warning'] = True
            return best
        best = max(compliant, key=lambda x: x.get('final_score', 0))
        return best

    def _apply_hard_authority_caps(self, option: Dict, context: DecisionContext) -> Dict:
        trend = abs(option.get('trend_influence', 0))
        ctif = abs(option.get('ctif_influence', 0))
        thresholds = {'doctrine': 1.0, 'user_override': 0.8, 'safety_critical': 0.9}
        for name, threshold in thresholds.items():
            if trend > threshold or ctif > threshold:
                reduction = max(trend - threshold, ctif - threshold)
                factor = 1.0 - reduction * 0.5
                if 'trend_influence' in option:
                    option['trend_influence'] *= factor
                if 'ctif_influence' in option:
                    option['ctif_influence'] *= factor
                option['authority_enforced'] = {'authority': name, 'reduction': factor}
        return option

    def _create_final_decision(self, context: DecisionContext, best_option: Dict, options: List[Dict]) -> Dict:
        decision = {
            'state': DecisionState.COMPLETED,
            'decision': best_option,
            'confidence': best_option.get('final_score', 0.5),
            'options_considered': len(options),
            'timestamp': time.time(),
            'request_id': context.request_id,
            'session_id': context.session_id,
            'coverage_used': context.coverage_flag,
            'exploration_used': context.exploration_flag
        }
        decision['audit_hash'] = self.hasher.compute_hash(decision)
        return decision

    def _halt_pipeline(self, pipeline_state: Dict):
        pipeline_state['execution_halted'] = True
        pipeline_state['halt_timestamp'] = time.time()

    async def _execute_early_exit(self, context: DecisionContext, pipeline_state: Dict) -> Dict:
        decision = {
            'state': DecisionState.COMPLETED,
            'decision': {'action': 'early_exit', 'confidence': pipeline_state.get('confidence', 0.5)},
            'early_exit': True,
            'exit_reason': 'coverage_deviation_zero' if pipeline_state.get('coverage_deviation', 1) == 0 else 'no_changes',
            'timestamp': time.time()
        }
        decision['audit_hash'] = self.hasher.compute_hash(decision)
        asyncio.create_task(self._log_async('early_exit_executed', {'context_id': context.request_id}))
        return decision

    async def _circuit_breaker_fallback(self, context: DecisionContext) -> Dict:
        return {
            'state': DecisionState.COMPLETED,
            'decision': {'action': 'circuit_breaker_fallback', 'confidence': 0.1},
            'circuit_breaker': True,
            'requires_human_review': True,
            'timestamp': time.time()
        }

    async def _safe_fallback(self, context: DecisionContext, pipeline_state: Dict, error: str) -> Dict:
        return {
            'state': DecisionState.COMPLETED,
            'decision': {'action': 'safe_fallback', 'confidence': 0.05},
            'error_handled': True,
            'original_error': error[:100],
            'timestamp': time.time()
        }

    # ---------- Background Workers ----------
    def _audit_worker(self):
        batch = []
        last_flush = time.time()
        while True:
            try:
                entry = self.audit_queue.get(timeout=1.0)
                batch.append(entry)
                if len(batch) >= 100 or (time.time() - last_flush) > 5.0:
                    self._flush_audit_batch(batch)
                    batch = []
                    last_flush = time.time()
            except:
                if batch:
                    self._flush_audit_batch(batch)
                    batch = []
                    last_flush = time.time()

    def _flush_audit_batch(self, batch: List):
        if not batch:
            return
        try:
            serialized = pickle.dumps(batch)
            if self.redis:
                key = f"audit_batch_{int(time.time())}_{uuid.uuid4().hex[:8]}"
                self.redis.setex(key, 86400 * 7, serialized)
            self.metrics.record_audit_batch(len(batch))
        except Exception as e:
            self.logger.error(f"Audit batch flush error: {e}")

    def _session_cleanup_worker(self):
        while True:
            time.sleep(300)
            current_time = time.time()
            expired = []
            for sid, data in list(self.session_data.items()):
                if current_time - data.get('last_activity', 0) > self.session_timeout:
                    expired.append(sid)
            for sid in expired:
                # acquire lock before removal
                locked = self._acquire_session_lock(sid)
                try:
                    with self.session_locks[sid]:
                        if sid in self.session_data:
                            del self.session_data[sid]
                        if sid in self.session_locks:
                            del self.session_locks[sid]
                finally:
                    if locked:
                        self._release_session_lock(sid)

    def _metrics_worker(self):
        while True:
            time.sleep(60)
            self.metrics.collect_system_metrics()
            self.metrics.update_gauge('decisions_processed', self.stats['decisions_processed'])
            self.metrics.update_gauge('early_exits', self.stats['early_exits'])

    async def _log_async(self, operation: str, data: Dict):
        try:
            await self.task_queue.put((operation, data, time.time()))
        except asyncio.QueueFull:
            pass

    async def _log_decision_async(self, decision: Dict, context: DecisionContext):
        log_entry = {
            'operation': 'decision_made',
            'decision_id': decision.get('audit_hash'),
            'context_id': context.request_id,
            'confidence': decision.get('confidence'),
            'timestamp': time.time()
        }
        await self._log_async('decision_audit', log_entry)

    def get_stats(self) -> Dict:
        return {
            **self.stats,
            'circuit_breakers': {k: v.get_stats() for k, v in self.circuit_breakers.items()},
            'ctif_stats': self.ctif.stats,
            'option_gen_stats': self.option_gen.stats,
            'metrics': self.metrics.get_summary(),
            'session_count': len(self.session_data)
        }
