# src/infrastructure/external/marketplace_service.py
import aiohttp
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import json
import logging
from dataclasses import dataclass
import numpy as np
from uuid import UUID

from src.core.domain.entities import Item, ItemFeatures, Vector
from config.config import config

logger = logging.getLogger(__name__)

@dataclass
class MarketplaceItem:
    item_id: str
    title: str
    description: str
    category: str
    subcategory: str
    brand: str
    price: float
    original_price: float
    currency: str
    features: Dict[str, Any]
    images: List[str]
    stock: int
    seller_id: str
    seller_rating: float
    created_at: datetime
    updated_at: datetime
    popularity_score: float
    trend_score: float
    revival_score: float
    # Environmental attributes
    thermal_rating: float = 0.5
    water_resistance: float = 0.0
    uv_protection: float = 0.0
    breathability: float = 0.5
    wind_resistance: float = 0.0

    def to_item(self) -> Item:
        return Item(
            item_id=UUID(self.item_id),
            category=self.category,
            features=ItemFeatures(
                color=self.features.get('color', 'unknown'),
                material=self.features.get('material', 'unknown'),
                style_tags=self.features.get('style_tags', []),
                pattern=self.features.get('pattern'),
                silhouette=self.features.get('silhouette'),
                formality=self.features.get('formality', 0.5),
                trendiness=self.features.get('trendiness', 0.5),
                versatility=self.features.get('versatility', 0.5),
                thermal_rating=self.thermal_rating,
                water_resistance=self.water_resistance,
                uv_protection=self.uv_protection,
                breathability=self.breathability,
                wind_resistance=self.wind_resistance
            ),
            embedding=Vector(np.random.randn(config.vector_dimensions).astype(np.float32)),
            created_at=self.created_at,
            updated_at=self.updated_at,
            revival_score=self.revival_score,
            trend_score=self.trend_score,
            climate_compatibility=self._extract_climate_compatibility(),
            confidence=0.8,
            thermal_rating=self.thermal_rating,
            water_resistance=self.water_resistance,
            uv_protection=self.uv_protection,
            breathability=self.breathability,
            wind_resistance=self.wind_resistance
        )

    def _extract_climate_compatibility(self) -> List[str]:
        comp = []
        material = self.features.get('material', '').lower()
        if any(m in material for m in ['wool', 'cashmere', 'fleece']):
            comp.extend(['winter', 'cold'])
        if any(m in material for m in ['linen', 'cotton', 'seersucker']):
            comp.extend(['summer', 'warm'])
        if 'waterproof' in material or 'rain' in self.title.lower():
            comp.append('rainy')
        tags = self.features.get('style_tags', [])
        if any(tag in tags for tag in ['winter', 'ski', 'snow']):
            comp.append('winter')
        if any(tag in tags for tag in ['summer', 'beach', 'resort']):
            comp.append('summer')
        return list(set(comp))

class MarketplaceService:
    def __init__(self, base_url: str = None):
        self.base_url = base_url or config.marketplace_url
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache: Dict[str, tuple[Any, datetime]] = {}

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    async def connect(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def disconnect(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def _parse_item(self, data: Dict[str, Any]) -> MarketplaceItem:
        features = data.get('features', {})
        # Infer environmental attributes
        thermal = features.get('thermal_rating')
        if thermal is None:
            material = features.get('material', '').lower()
            if any(m in material for m in ['wool', 'cashmere', 'fleece']):
                thermal = 0.2
            elif any(m in material for m in ['linen', 'cotton', 'silk']):
                thermal = 0.8
            else:
                thermal = 0.5
        water_res = features.get('water_resistance', 0.0)
        if water_res == 0.0 and 'waterproof' in features.get('style_tags', []):
            water_res = 0.8
        uv = features.get('uv_protection', 0.0)
        if 'upf' in features.get('material', '').lower():
            uv = 0.7
        breath = features.get('breathability', 0.5)
        wind = features.get('wind_resistance', 0.0)

        return MarketplaceItem(
            item_id=data.get('id', ''),
            title=data.get('title', ''),
            description=data.get('description', ''),
            category=data.get('category', 'unknown'),
            subcategory=data.get('subcategory', ''),
            brand=data.get('brand', ''),
            price=data.get('price', 0.0),
            original_price=data.get('original_price', data.get('price', 0.0)),
            currency=data.get('currency', 'USD'),
            features=features,
            images=data.get('images', []),
            stock=data.get('stock', 0),
            seller_id=data.get('seller_id', ''),
            seller_rating=data.get('seller_rating', 0.0),
            created_at=datetime.fromisoformat(data.get('created_at', datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(data.get('updated_at', datetime.now().isoformat())),
            popularity_score=data.get('popularity_score', 0.5),
            trend_score=data.get('trend_score', 0.5),
            revival_score=data.get('revival_score', 0.5),
            thermal_rating=thermal,
            water_resistance=water_res,
            uv_protection=uv,
            breathability=breath,
            wind_resistance=wind
        )

    # ... other methods (search, get_item, etc.) remain similar, with caching and error handling ...
