# src/infrastructure/external/virtual_twin_service.py
import asyncio
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from src.core.domain.entities import UserProfile, Item
from config.config import config

logger = logging.getLogger(__name__)

@dataclass
class SimulationResult:
    user_id: str
    outfit_hash: str
    engagement_score: float
    satisfaction_score: float
    style_coherence: float
    fit_score: float
    color_harmony: float
    material_compatibility: float
    season_appropriateness: float
    confidence: float
    simulation_time: float
    timestamp: datetime

    @property
    def overall_score(self) -> float:
        weights = {
            'engagement': 0.25,
            'satisfaction': 0.20,
            'style_coherence': 0.15,
            'fit_score': 0.15,
            'color_harmony': 0.10,
            'material_compatibility': 0.10,
            'season_appropriateness': 0.05
        }
        return sum([
            self.engagement_score * weights['engagement'],
            self.satisfaction_score * weights['satisfaction'],
            self.style_coherence * weights['style_coherence'],
            self.fit_score * weights['fit_score'],
            self.color_harmony * weights['color_harmony'],
            self.material_compatibility * weights['material_compatibility'],
            self.season_appropriateness * weights['season_appropriateness']
        ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            'user_id': self.user_id,
            'outfit_hash': self.outfit_hash,
            'engagement_score': self.engagement_score,
            'satisfaction_score': self.satisfaction_score,
            'style_coherence': self.style_coherence,
            'fit_score': self.fit_score,
            'color_harmony': self.color_harmony,
            'material_compatibility': self.material_compatibility,
            'season_appropriateness': self.season_appropriateness,
            'overall_score': self.overall_score,
            'confidence': self.confidence,
            'simulation_time': self.simulation_time,
            'timestamp': self.timestamp.isoformat()
        }

class VirtualTwinService:
    def __init__(self, base_url: str = None, item_repo=None):
        self.base_url = base_url or config.virtual_twin_url
        self.item_repo = item_repo  # Injected repository for fetching items
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.simulation_cache: Dict[str, tuple[SimulationResult, datetime]] = {}
        self.cache_ttl = timedelta(hours=config.SIMULATION_CACHE_TTL_HOURS)
        self.max_simulations_per_request = 2
        self._simulation_semaphore = asyncio.Semaphore(self.max_simulations_per_request)
        self._load_models()

    def _load_models(self):
        self.style_model = StyleCompatibilityModel()
        self.fit_model = FitPredictionModel()
        self.color_model = ColorHarmonyModel()
        self.material_model = MaterialCompatibilityModel()
        logger.info('Virtual Twin models loaded')

    def set_deterministic(self, seed: int = 42):
        np.random.seed(seed)
        try:
            import torch
            torch.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
        except ImportError:
            pass
        logger.info(f'Deterministic mode enabled with seed {seed}')

    def _generate_cache_key(self,
                           user_id: str,
                           outfit_items: List[Item],
                           climate_bucket: str,
                           cultural_profile_hash: str) -> str:
        item_ids = sorted([str(it.item_id) for it in outfit_items])
        outfit_str = ':'.join(item_ids)
        outfit_hash = hashlib.md5(outfit_str.encode()).hexdigest()[:16]
        key = f'{user_id}:{outfit_hash}:{climate_bucket}:{cultural_profile_hash}'
        return hashlib.md5(key.encode()).hexdigest()

    def _delta_rendering_hint(self, cached_outfit: List[Item], new_outfit: List[Item]) -> bool:
        """Return True if only color/texture changed, reuse mesh physics."""
        cached_cats = {i.category for i in cached_outfit}
        new_cats = {i.category for i in new_outfit}
        if cached_cats != new_cats:
            return False
        return True

    async def _get_items(self, item_ids: List[str]) -> List[Item]:
        if not self.item_repo:
            logger.error('Item repository not injected')
            return []
        items = []
        for iid in item_ids:
            try:
                item = await self.item_repo.get_item(UUID(iid))
                if item:
                    items.append(item)
            except Exception as e:
                logger.warning(f'Failed to fetch item {iid}: {e}')
        return items

    async def simulate_outfit(self,
                              user_id: str,
                              item_ids: List[str],
                              user_profile: Optional[UserProfile] = None,
                              context: Optional[Dict] = None,
                              climate_bucket: str = 'temperate',
                              cultural_profile_hash: str = 'default') -> SimulationResult:
        items = await self._get_items(item_ids)
        if not items:
            raise ValueError('No items found for simulation')

        cache_key = self._generate_cache_key(user_id, items, climate_bucket, cultural_profile_hash)
        now = datetime.now()
        if cache_key in self.simulation_cache:
            result, ts = self.simulation_cache[cache_key]
            if now - ts < self.cache_ttl:
                logger.debug(f'Simulation cache hit: {cache_key}')
                return result

        async with self._simulation_semaphore:
            start = now
            style = await self._simulate_style_compatibility(user_profile, items) if user_profile else 0.5
            fit = await self._simulate_fit_prediction(user_id, items)
            color = await self._simulate_color_harmony(items)
            material = await self._simulate_material_compatibility(items)
            season = await self._simulate_season_appropriateness(items, context)
            engagement = 0.7  # placeholder
            satisfaction = self._calculate_satisfaction_score([style, fit, color, material, season])
            sim_time = (datetime.now() - start).total_seconds()
            result = SimulationResult(
                user_id=user_id,
                outfit_hash=cache_key[:16],
                engagement_score=engagement,
                satisfaction_score=satisfaction,
                style_coherence=style,
                fit_score=fit,
                color_harmony=color,
                material_compatibility=material,
                season_appropriateness=season,
                confidence=min(style, fit, color, material, season),
                simulation_time=sim_time,
                timestamp=now
            )

        self.simulation_cache[cache_key] = (result, now)
        if len(self.simulation_cache) > 10000:
            self._cleanup_cache()
        logger.info(f'Simulated outfit {cache_key[:8]} in {sim_time:.2f}s')
        return result

    async def simulate_multiple_outfits(self,
                                        user_id: str,
                                        outfit_combinations: List[List[str]],
                                        user_profile: Optional[UserProfile] = None,
                                        climate_bucket: str = 'temperate',
                                        cultural_profile_hash: str = 'default') -> List[SimulationResult]:
        sem = asyncio.Semaphore(self.max_simulations_per_request)
        async def throttled_sim(outfit):
            async with sem:
                return await self.simulate_outfit(user_id, outfit, user_profile, None, climate_bucket, cultural_profile_hash)
        tasks = [throttled_sim(outfit) for outfit in outfit_combinations]
        return await asyncio.gather(*tasks)

    def _cleanup_cache(self):
        now = datetime.now()
        to_remove = [k for k, (_, ts) in self.simulation_cache.items() if now - ts > self.cache_ttl]
        for k in to_remove:
            del self.simulation_cache[k]
        logger.info(f'Cleaned {len(to_remove)} cache entries')

    async def _simulate_style_compatibility(self, user_profile: UserProfile, items: List[Item]) -> float:
        if not user_profile or not items:
            return 0.5
        sims = []
        for item in items:
            if hasattr(item, 'embedding'):
                sim = user_profile.style_vector.cosine_similarity(item.embedding)
                sims.append(sim)
        return float(np.mean(sims)) if sims else 0.5

    async def _simulate_fit_prediction(self, user_id: str, items: List[Item]) -> float:
        cat_scores = {'top': 0.8, 'bottom': 0.7, 'dress': 0.75, 'outerwear': 0.85, 'footwear': 0.9, 'accessory': 1.0}
        scores = []
        for item in items:
            score = cat_scores.get(item.category, 0.7)
            if 'stretch' in item.features.style_tags:
                score *= 1.1
            if 'adjustable' in item.features.style_tags:
                score *= 1.05
            scores.append(min(1.0, score))
        return float(np.mean(scores)) if scores else 0.7

    async def _simulate_color_harmony(self, items: List[Item]) -> float:
        if len(items) < 2:
            return 0.7
        colors = [i.features.color.lower() for i in items]
        groups = {
            'neutral': ['black', 'white', 'gray', 'navy', 'beige', 'brown'],
            'warm': ['red', 'orange', 'yellow', 'pink', 'burgundy'],
            'cool': ['blue', 'green', 'purple', 'teal', 'turquoise']
        }
        group_counts = {g: 0 for g in groups}
        for c in colors:
            for g, gcols in groups.items():
                if c in gcols:
                    group_counts[g] += 1
                    break
        non_neutral = sum(v for k, v in group_counts.items() if k != 'neutral')
        if non_neutral > 2:
            return 0.5
        if group_counts['neutral'] < len(colors) // 3:
            return 0.5
        return 0.9

    async def _simulate_material_compatibility(self, items: List[Item]) -> float:
        if len(items) < 2:
            return 0.8
        mats = [i.features.material.lower() for i in items]
        compat = {
            'cotton': {'cotton': 1.0, 'linen': 0.9, 'denim': 0.8, 'wool': 0.7, 'silk': 0.6},
            'linen': {'cotton': 0.9, 'linen': 1.0, 'denim': 0.7, 'wool': 0.6, 'silk': 0.8},
            'denim': {'cotton': 0.8, 'linen': 0.7, 'denim': 1.0, 'wool': 0.5, 'silk': 0.4},
            'wool': {'cotton': 0.7, 'linen': 0.6, 'denim': 0.5, 'wool': 1.0, 'silk': 0.9},
            'silk': {'cotton': 0.6, 'linen': 0.8, 'denim': 0.4, 'wool': 0.9, 'silk': 1.0}
        }
        total, pairs = 0, 0
        for i in range(len(mats)):
            for j in range(i+1, len(mats)):
                m1, m2 = mats[i], mats[j]
                score = 0.5
                if m1 in compat and m2 in compat[m1]:
                    score = compat[m1][m2]
                elif m2 in compat and m1 in compat[m2]:
                    score = compat[m2][m1]
                total += score
                pairs += 1
        return total / pairs if pairs else 0.7

    async def _simulate_season_appropriateness(self, items: List[Item], context: Optional[Dict]) -> float:
        if not context or 'season' not in context:
            return 0.7
        season = context['season']
        scores = [0.9 if season in i.climate_compatibility else 0.4 for i in items]
        return float(np.mean(scores)) if scores else 0.7

    def _calculate_satisfaction_score(self, component_scores: List[float]) -> float:
        weights = [0.3, 0.3, 0.2, 0.1, 0.1]
        weighted = sum(w * s for w, s in zip(weights, component_scores))
        return 1 / (1 + np.exp(-weighted * 10 + 5))

# Placeholder ML models
class StyleCompatibilityModel: pass
class FitPredictionModel: pass
class ColorHarmonyModel: pass
class MaterialCompatibilityModel: pass
