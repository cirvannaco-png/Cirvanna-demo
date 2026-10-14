# src/core/eepl.py
import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import UUID

import numpy as np
import aiohttp
from aiobreaker import CircuitBreaker

from config.config import config
from src.core.domain.entities import (
    UserProfile, Item, FeedbackEvent, SegmentPrior, StyleSnapshot, Vector
)
from src.infrastructure.external.climate_service import (
    ClimateService, EnvironmentalSignalVector
)
from src.infrastructure.external.virtual_twin_service import VirtualTwinService
from src.infrastructure.external.cfrp_client import RealCFRPClient
from src.infrastructure.external.feedback_repository import PostgreSQLFeedbackRepository
from src.infrastructure.external.cultural_validator import CulturalValidator
from src.infrastructure.external.trend_service import TrendService
from src.infrastructure.caching.redis_cache import RedisCache
from src.infrastructure.database.postgres_repository import (
    PostgreSQLUserRepository, PostgreSQLItemRepository,
    PostgreSQLSegmentPriorRepository, PostgreSQLStyleSnapshotRepository
)
from src.monitoring.metrics import track_request, track_ranking
from src.ab_testing.ab_framework import ABFramework
from src.explainability.explainer import Explainer

logger = logging.getLogger(__name__)

CONF_THRESHOLD = config.CONF_THRESHOLD
HIGH_ENV_THRESHOLD = config.HIGH_ENV_THRESHOLD
MAX_ENV_INFLUENCE = config.MAX_ENVIRONMENTAL_INFLUENCE
MAX_SEGMENT_INFLUENCE = config.MAX_SEGMENT_INFLUENCE
MAX_REVIVAL_BOOST = config.MAX_REVIVAL_BOOST
MAX_TOTAL_BOOST = config.MAX_TOTAL_BOOST
CULTURAL_SEVERITY_CAP = config.CULTURAL_SEVERITY_CAP
MAX_SCORE = config.MAX_SCORE

@dataclass
class CandidateItem:
    item: Item
    base_score: float = 0.0
    blended_score: float = 0.0
    environmental_score: float = 0.0
    revival_boost: float = 0.0
    final_score: float = 0.0
    confidence: float = 0.0
    suppressed: bool = False
    needs_simulation: bool = False
    npl_vetoed: bool = False
    fci_score: Optional[float] = None
    friction_action: Optional[int] = None
    fci_confidence: Optional[float] = None
    explanation: Optional[str] = None

class EEPL:
    def __init__(self,
                 user_repo: PostgreSQLUserRepository,
                 item_repo: PostgreSQLItemRepository,
                 segment_repo: PostgreSQLSegmentPriorRepository,
                 snapshot_repo: PostgreSQLStyleSnapshotRepository,
                 feedback_repo: PostgreSQLFeedbackRepository,
                 climate_service: ClimateService,
                 virtual_twin: VirtualTwinService,
                 cfrp_client: RealCFRPClient,
                 fci_client: aiohttp.ClientSession,
                 cache: RedisCache,
                 cultural_validator: CulturalValidator,
                 trend_service: TrendService,
                 ab_framework: ABFramework,
                 explainer: Explainer):
        self.user_repo = user_repo
        self.item_repo = item_repo
        self.segment_repo = segment_repo
        self.snapshot_repo = snapshot_repo
        self.feedback_repo = feedback_repo
        self.climate = climate_service
        self.vt = virtual_twin
        self.cfrp = cfrp_client
        self.fci_client = fci_client
        self.cache = cache
        self.cultural_validator = cultural_validator
        self.trend_service = trend_service
        self.ab_framework = ab_framework
        self.explainer = explainer

        # Circuit breakers
        self.fci_cb = CircuitBreaker(
            failure_threshold=config.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=config.CIRCUIT_BREAKER_RECOVERY_TIMEOUT
        )
        self.vt_cb = CircuitBreaker(
            failure_threshold=config.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=config.CIRCUIT_BREAKER_RECOVERY_TIMEOUT
        )

        self.last_env_hash = None
        self.last_segment_hash = None
        self.last_cultural_hash = None
        self.last_sim_hash = None
        self.last_ranking_seed = None
        self._last_snapshot_time: Dict[UUID, datetime] = {}

    async def process(self,
                      user_id: UUID,
                      candidate_items: List[Item],
                      context: Dict[str, Any]) -> List[Item]:
        """Full pipeline with all improvements."""
        request_seed = config.RANKING_SEED + hash(user_id) % (2**32)
        np.random.seed(request_seed)
        self.vt.set_deterministic(request_seed)

        # 1. NPL veto
        user = await self.user_repo.get_user(user_id)
        if user and user.negative_preferences:
            candidate_items = self._apply_npl_veto(candidate_items, user.negative_preferences)

        # 2. Cultural validation
        if user and user.cultural_constraints:
            candidate_items = await self.cultural_validator.validate(candidate_items, user.cultural_constraints)

        # 3. Compute base score (CFRP)
        base_scored = await self._compute_base_scores(user_id, candidate_items, context)

        # 4. Cross-user priors
        blended = await self._apply_cross_user_priors(user_id, base_scored, context)

        # 5. Environmental weighting
        esv = await self.climate.get_environmental_signal(context.get('location'))
        env_scored = await self._apply_environmental_weighting(blended, esv, user)

        # 6. Revival-forward boost
        boosted = await self._apply_revival_boost(env_scored, user_id, context, user)

        # 7. FCI scoring
        fci_scored = await self._apply_fci(boosted, user_id, context)

        # 8. Confidence filter
        filtered = await self._confidence_filter(fci_scored, esv.confidence, context)

        # 9. Simulation (if needed)
        simulated = await self._handle_simulations(filtered, user_id, context, esv, user)

        # 10. A/B test assignment and ranking variation
        experiment = self.ab_framework.get_experiment(user_id)
        if experiment:
            variant = self.ab_framework.get_variant(user_id, experiment)
            if variant == "B":
                # Alternative ranking: e.g., boost diversity
                simulated = self._apply_diversity_boost(simulated)

        # 11. Final sort
        ranked = sorted(simulated, key=lambda x: x.final_score, reverse=True)

        # 12. Explainability
        for c in ranked[:10]:  # only top 10 for performance
            c.explanation = await self.explainer.explain(c, user, context, esv)

        # 13. Record snapshot
        await self._maybe_record_snapshot(user_id, ranked)

        # 14. Log determinism
        self._log_determinism(esv, context, request_seed)

        # 15. Track metrics
        track_ranking(user_id, ranked, experiment, variant if experiment else "control")

        # Invariants
        for c in ranked:
            assert 0 <= c.confidence <= 1
            assert 0 <= c.final_score <= MAX_SCORE
            env_weight = c.environmental_score * esv.confidence
            assert env_weight <= MAX_ENV_INFLUENCE + 1e-6

        return [c.item for c in ranked if not c.suppressed and not c.npl_vetoed]

    # ... (all the helper methods remain as before, with updates to use new components)

    def _apply_npl_veto(self, items: List[Item], negative_prefs: set) -> List[Item]:
        filtered = []
        for item in items:
            vetoed = False
            if item.category in negative_prefs:
                vetoed = True
            for tag in item.features.style_tags:
                if tag in negative_prefs:
                    vetoed = True
                    break
            if not vetoed:
                filtered.append(item)
        return filtered

    async def _compute_base_scores(self, user_id: UUID, items: List[Item], context: Dict) -> List[CandidateItem]:
        candidates = []
        for item in items:
            try:
                score = await self.cfrp.predict(user_id, item.item_id, context)
            except Exception:
                score = 0.5
            candidates.append(CandidateItem(item=item, base_score=score, confidence=item.confidence))
        return candidates

    async def _apply_cross_user_priors(self, user_id: UUID, candidates: List[CandidateItem], context: Dict) -> List[CandidateItem]:
        user = await self.user_repo.get_user(user_id)
        if not user:
            return candidates
        segment = await self.segment_repo.get_prior(user.archetype)
        if not segment or segment.confidence < 0.4:
            return candidates
        if segment.variance > config.SEGMENT_VARIANCE_THRESHOLD:
            segment.confidence *= 0.8
        alpha = max(0.6, 1.0 - segment.confidence * MAX_SEGMENT_INFLUENCE)
        beta = 1.0 - alpha
        blended_vec = alpha * user.style_vector.values + beta * segment.embedding
        norm_blended = np.linalg.norm(blended_vec)
        for cand in candidates:
            item_vec = cand.item.embedding.values
            norm_item = np.linalg.norm(item_vec)
            if norm_blended > 0 and norm_item > 0:
                sim = np.dot(blended_vec, item_vec) / (norm_blended * norm_item)
            else:
                sim = 0.0
            cand.blended_score = (1 - MAX_SEGMENT_INFLUENCE) * cand.base_score + MAX_SEGMENT_INFLUENCE * sim
            cand.confidence = min(cand.confidence, segment.confidence)
        return candidates

    def _compute_ecs(self, item: Item, esv: EnvironmentalSignalVector) -> float:
        thermal_fit = 1 - abs(item.thermal_rating - (esv.thermal_index + 1) / 2)
        precip_fit = 1 - abs(item.water_resistance - esv.precipitation_index)
        uv_fit = 1 - abs(item.uv_protection - esv.uv_index)
        raw = 0.4 * thermal_fit + 0.3 * precip_fit + 0.3 * uv_fit
        return max(0.0, min(1.0, raw))

    async def _apply_environmental_weighting(self, candidates: List[CandidateItem], esv: EnvironmentalSignalVector, user: Optional[UserProfile]) -> List[CandidateItem]:
        for cand in candidates:
            ecs = self._compute_ecs(cand.item, esv)
            cand.environmental_score = ecs
            env_weight = ecs * esv.confidence
            if user:
                severity = await self.cultural_validator.get_severity(user, cand.item)
                if severity > 0.8:
                    env_weight = min(env_weight, CULTURAL_SEVERITY_CAP)
            boost = min(MAX_ENV_INFLUENCE, 0.2 * env_weight)
            cand.final_score = cand.blended_score * (1 + boost)
        return candidates

    async def _apply_revival_boost(self, candidates: List[CandidateItem], user_id: UUID, context: Dict, user: Optional[UserProfile]) -> List[CandidateItem]:
        for cand in candidates:
            cross_trend = cand.item.trend_score
            env_align = cand.environmental_score
            wardrobe_relevance = 0.5
            if user and user.style_history:
                owned_embeddings = [Vector(np.array(h['embedding'])) for h in user.style_history if 'embedding' in h]
                if owned_embeddings:
                    sims = [cand.item.embedding.cosine_similarity(oe) for oe in owned_embeddings]
                    wardrobe_relevance = max(sims) if sims else 0.5
            raw_boost = cross_trend * env_align * wardrobe_relevance
            cand.revival_boost = min(MAX_REVIVAL_BOOST, raw_boost)
            total_boost = cand.final_score / (cand.blended_score + 1e-8) - 1
            if total_boost + cand.revival_boost > MAX_TOTAL_BOOST:
                cand.revival_boost = MAX_TOTAL_BOOST - total_boost
            cand.final_score += cand.revival_boost
        return candidates

    async def _apply_fci(self, candidates: List[CandidateItem], user_id: UUID, context: Dict) -> List[CandidateItem]:
        user = await self.user_repo.get_user(user_id)
        body_mesh_id = context.get('body_mesh_id', str(user_id))
        for cand in candidates:
            if cand.suppressed or cand.npl_vetoed:
                continue
            try:
                async with self.fci_cb:
                    async with self.fci_client.post(f"{config.fci_url}/predict", json={
                        "body_mesh_id": body_mesh_id,
                        "garment_id": str(cand.item.item_id),
                        "brand_id": cand.item.brand,
                        "user_id": str(user_id),
                        "category": cand.item.category,
                        "temperature": context.get('temperature', 20.0),
                        "humidity": context.get('humidity', 0.5)
                    }) as resp:
                        if resp.status == 200:
                            fci_result = await resp.json()
                            cand.fci_score = fci_result["fci_final"]
                            cand.friction_action = fci_result["friction_action"]
                            cand.fci_confidence = fci_result["confidence"]
                            cand.final_score = cand.fci_score
                        else:
                            logger.warning(f"FCI returned {resp.status} for {cand.item.item_id}")
            except Exception as e:
                logger.warning(f"FCI call failed for {cand.item.item_id}: {e}")
        return candidates

    async def _confidence_filter(self, candidates: List[CandidateItem], env_confidence: float, context: Dict) -> List[CandidateItem]:
        active = [c for c in candidates if not c.npl_vetoed]
        all_below = all(c.final_score < CONF_THRESHOLD for c in active)
        threshold = CONF_THRESHOLD * (0.95 if all_below else 1.0)
        for cand in active:
            if cand.confidence < threshold:
                if cand.environmental_score * env_confidence > HIGH_ENV_THRESHOLD:
                    cand.needs_simulation = True
                else:
                    cand.suppressed = True
        return candidates

    async def _handle_simulations(self, candidates: List[CandidateItem], user_id: UUID, context: Dict, esv: EnvironmentalSignalVector, user: Optional[UserProfile]) -> List[CandidateItem]:
        to_sim = [c for c in candidates if c.needs_simulation and not c.suppressed]
        if not to_sim:
            return candidates
        to_sim.sort(key=lambda c: (c.environmental_score, c.base_score), reverse=True)
        sim_count = 0
        for cand in to_sim:
            if sim_count >= self.vt.max_simulations_per_request:
                cand.suppressed = True
                logger.warning('Simulation throttle hit')
                continue
            climate_bucket = 'temperate'
            if esv.thermal_index < -0.3:
                climate_bucket = 'cold'
            elif esv.thermal_index > 0.3:
                climate_bucket = 'warm'
            cultural_hash = self._get_cultural_hash(user.cultural_constraints if user else {})
            try:
                async with self.vt_cb:
                    sim_result = await self.vt.simulate_outfit(
                        user_id=str(user_id),
                        item_ids=[str(cand.item.item_id)],
                        user_profile=user,
                        context=context,
                        climate_bucket=climate_bucket,
                        cultural_profile_hash=cultural_hash
                    )
                    if sim_result and sim_result.confidence > 0.6:
                        cand.confidence = max(cand.confidence, 0.8)
                        cand.suppressed = False
                    else:
                        cand.suppressed = True
            except Exception as e:
                logger.error(f'Simulation failed: {e}')
                cand.suppressed = True
            sim_count += 1
        return candidates

    async def ingest_feedback(self, event: FeedbackEvent) -> None:
        # Recency decay
        days_since = (datetime.now() - event.timestamp).days
        event.recency_weight = np.exp(-config.FEEDBACK_DECAY_LAMBDA * max(0, days_since))
        # Dampening for rapid identical events
        recent = await self.feedback_repo.get_recent_for_item(event.user_id, event.item_id, minutes=10)
        identical = sum(1 for e in recent if e.event_type == event.event_type)
        dampening = 0.2 ** identical
        event.effective_weight = event.base_weight * event.recency_weight * dampening
        event.engagement_weight = dampening
        # Store and update CFRP
        await self.feedback_repo.save_feedback(event)
        await self.cfrp.record_feedback(event)

    def _apply_diversity_boost(self, candidates: List[CandidateItem]) -> List[CandidateItem]:
        # Simple diversity: penalise items from the same category
        categories = {}
        for c in candidates:
            cat = c.item.category
            if cat not in categories:
                categories[cat] = 0
            categories[cat] += 1
        for c in candidates:
            if categories[c.item.category] > 2:
                c.final_score *= 0.95
        return candidates

    async def _maybe_record_snapshot(self, user_id: UUID, candidates: List[CandidateItem]):
        last = self._last_snapshot_time.get(user_id)
        now = datetime.now()
        if last and (now - last).days < 7:
            return
        self._last_snapshot_time[user_id] = now
        top = [c.item.embedding.values for c in sorted(candidates, key=lambda x: x.final_score, reverse=True)[:5]]
        dominant = np.mean(top, axis=0).tolist() if top else []
        conf = np.mean([c.confidence for c in candidates if not c.suppressed]) if candidates else 0.0
        rev = np.mean([c.revival_boost for c in candidates]) if candidates else 0.0
        snapshot = StyleSnapshot(
            user_id=user_id,
            timestamp=now,
            dominant_style_embedding=dominant,
            confidence_trend=float(conf),
            revival_trend=float(rev)
        )
        await self.snapshot_repo.save(snapshot)
        logger.info(f'Recorded style snapshot for user {user_id}')

    def _log_determinism(self, esv: EnvironmentalSignalVector, context: Dict, seed: int):
        self.last_env_hash = hashlib.md5(json.dumps(esv.__dict__, sort_keys=True).encode()).hexdigest()
        self.last_segment_hash = context.get('segment_hash', 'none')
        self.last_cultural_hash = context.get('cultural_hash', 'none')
        self.last_sim_hash = context.get('simulation_hash', 'none')
        self.last_ranking_seed = seed
        logger.info(json.dumps({
            'environment_hash': self.last_env_hash,
            'segment_hash': self.last_segment_hash,
            'cultural_hash': self.last_cultural_hash,
            'simulation_hash': self.last_sim_hash,
            'ranking_seed': self.last_ranking_seed
        }))

    @staticmethod
    def _get_cultural_hash(constraints: Dict) -> str:
        return hashlib.md5(json.dumps(constraints, sort_keys=True).encode()).hexdigest()[:16]
