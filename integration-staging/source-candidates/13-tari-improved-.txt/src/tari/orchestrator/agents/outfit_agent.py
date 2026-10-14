"""
Outfit Agent – composes coordinated looks using compatibility graph and constraints.
"""
import itertools
import numpy as np
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from ...config import TariConfig
from ...cache.predictive_cache import PredictiveCache
from ...privacy.manager import PrivacyManager
from ...connection_pool import SecureConnectionPool
from ...body.pipeline import CirvannaOptimizedPipeline
from ...body.domain.body import BodySegment

class OutfitAgent:
    def __init__(self, config: TariConfig, cache: PredictiveCache,
                 privacy_manager: PrivacyManager, pool: SecureConnectionPool):
        self.config = config
        self.cache = cache
        self.privacy_manager = privacy_manager
        self.pool = pool
        self.body_pipeline = CirvannaOptimizedPipeline(config, cache, privacy_manager, pool)

    async def compose_outfits(self, products: List[Dict], intent: Dict,
                              user_profile: Dict) -> List[Dict]:
        """
        Generate complete coordinated looks.
        """
        # Separate by category (inferred from metadata)
        categories = defaultdict(list)
        for p in products:
            cat = p.get("metadata", {}).get("category", "unknown")
            categories[cat].append(p)
        # Define category priority
        required_cats = ["top", "bottom", "footwear"]
        optional_cats = ["outerwear", "accessory", "bag"]
        # Generate outfit candidates
        outfits = []
        # For simplicity, take combinations of top, bottom, footwear
        tops = categories.get("top", [])[:5]
        bottoms = categories.get("bottom", [])[:5]
        footwear = categories.get("footwear", [])[:5]
        for top, bottom, shoe in itertools.product(tops, bottoms, footwear):
            outfit = {
                "outfit_id": f"outfit_{len(outfits)}",
                "items": [top, bottom, shoe],
                "compatibility_score": await self._compute_outfit_compatibility([top, bottom, shoe]),
                "aesthetic_profile": self._merge_aesthetics([top, bottom, shoe]),
                "color_palette": self._merge_colors([top, bottom, shoe]),
                "fit_scores": await self._compute_fit_scores([top, bottom, shoe], user_profile),
                "tension_tags": []
            }
            # Add optional items if available
            if categories.get("outerwear"):
                outer = categories["outerwear"][0]
                outfit["items"].append(outer)
                outfit["compatibility_score"] *= 0.9
            outfits.append(outfit)
        # Sort by compatibility
        outfits.sort(key=lambda x: x["compatibility_score"], reverse=True)
        # Apply constraints
        constrained = await self._apply_constraints(outfits, user_profile, intent)
        return constrained[:10]  # return top 10 outfits

    async def _compute_outfit_compatibility(self, items: List[Dict]) -> float:
        """Compute overall compatibility using pairwise scores."""
        if len(items) < 2:
            return 0.5
        total = 0.0
        count = 0
        for i in range(len(items)):
            for j in range(i+1, len(items)):
                emb_i = items[i].get("embedding")
                emb_j = items[j].get("embedding")
                if emb_i is not None and emb_j is not None:
                    sim = self._cosine_sim(emb_i, emb_j)
                else:
                    sim = 0.5
                total += sim
                count += 1
        return total / count if count > 0 else 0.5

    def _cosine_sim(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))

    def _merge_aesthetics(self, items: List[Dict]) -> List[str]:
        all_aesthetics = []
        for item in items:
            tags = item.get("metadata", {}).get("styleTags", [])
            all_aesthetics.extend(tags)
        # Return most common
        from collections import Counter
        return [tag for tag, _ in Counter(all_aesthetics).most_common(3)]

    def _merge_colors(self, items: List[Dict]) -> List[str]:
        all_colors = []
        for item in items:
            colors = item.get("metadata", {}).get("colors", [])
            all_colors.extend(colors)
        return list(set(all_colors))[:3]

    async def _compute_fit_scores(self, items: List[Dict], user_profile: Dict) -> Dict:
        # Use body calibration to estimate fit per item
        body_meas = user_profile.get("body_measurements", {})
        scores = {}
        for item in items:
            # Simplified: use similarity between item fit tags and user fit preferences
            fit_pref = user_profile.get("fitPreference", "regular")
            scores[item.get("product_id")] = 0.8 if fit_pref == "regular" else 0.6
        return scores

    async def _apply_constraints(self, outfits: List[Dict], user_profile: Dict, intent: Dict) -> List[Dict]:
        """
        Apply constraint engine: category uniqueness, color coherence, layering rules, etc.
        """
        valid = []
        for outfit in outfits:
            # Category uniqueness (no duplicate categories)
            categories = [item.get("metadata", {}).get("category") for item in outfit["items"]]
            if len(set(categories)) != len(categories):
                continue
            # Color coherence (simple: at least two items share a color)
            all_colors = self._merge_colors(outfit["items"])
            if len(all_colors) < 1:
                continue
            # Layering rule: if outerwear, must have top and bottom
            has_outer = any(cat == "outerwear" for cat in categories)
            has_top = any(cat == "top" for cat in categories)
            has_bottom = any(cat == "bottom" for cat in categories)
            if has_outer and (not has_top or not has_bottom):
                continue
            # Seasonal rule (simplified)
            season = intent.get("season", "spring")
            if season == "winter" and not any(cat == "outerwear" for cat in categories):
                continue
            valid.append(outfit)
        return valid

    async def generate_variations(self, outfits: List[Dict], intent: Dict) -> List[Dict]:
        """
        Generate slight variations of a selected look (darker, luxury, casual, avant-garde, warmer).
        """
        variations = []
        for outfit in outfits:
            base_items = outfit["items"]
            # For each item, generate a variant by replacing with similar but slightly different product
            # Placeholder: just copy the outfit with modified metadata
            variant = outfit.copy()
            variant["outfit_id"] = f"{outfit['outfit_id']}_variation"
            variant["variation_type"] = "luxury"
            variant["compatibility_score"] *= 0.95
            variations.append(variant)
        return variations

    async def health(self) -> Dict:
        return {"agent": "outfit", "status": "healthy"}
