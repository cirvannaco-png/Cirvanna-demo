# src/infrastructure/external/climate_service.py
import aiohttp
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import hashlib
import json
import logging
from dataclasses import dataclass

from config.config import config

logger = logging.getLogger(__name__)

@dataclass
class EnvironmentalSignalVector:
    thermal_index: float        # [-1,1]
    precipitation_index: float  # [0,1]
    humidity_index: float       # [0,1]
    uv_index: float            # [0,1]
    wind_index: float          # [0,1]
    climate_baseline: float    # [0,1]
    confidence: float          # [0,1]

    @classmethod
    def neutral(cls):
        return cls(
            thermal_index=0.0,
            precipitation_index=0.0,
            humidity_index=0.5,
            uv_index=0.0,
            wind_index=0.0,
            climate_baseline=0.5,
            confidence=0.0
        )

@dataclass
class WeatherData:
    temperature: float
    condition: str
    humidity: float
    wind_speed: float
    precipitation: float
    feels_like: float
    uv_index: float
    visibility: float
    timestamp: datetime

    @property
    def season(self) -> str:
        month = self.timestamp.month
        if month in [12, 1, 2]:
            return 'winter'
        elif month in [3, 4, 5]:
            return 'spring'
        elif month in [6, 7, 8]:
            return 'summer'
        else:
            return 'fall'

    @property
    def comfort_index(self) -> float:
        temp_score = 1 - abs(self.temperature - 21) / 15
        temp_score = max(0, min(1, temp_score))
        humidity_score = 1 - abs(self.humidity - 50) / 50
        humidity_score = max(0, min(1, humidity_score))
        wind_score = 1 - min(self.wind_speed / 30, 1)
        return temp_score * 0.5 + humidity_score * 0.3 + wind_score * 0.2

class OpenWeatherMapService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.api_keys.get('openweathermap')
        self.base_url = 'https://api.openweathermap.org/data/2.5'
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache: Dict[str, Dict] = {}
        self.cache_ttl = 1800  # 30 minutes

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    async def connect(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def disconnect(self):
        if self.session and not self.session.closed:
            await self.session.close()

    @staticmethod
    def sanitize_weather(data: Dict[str, Any]) -> Dict[str, Any]:
        """Discard physically impossible values."""
        main = data.get('main', {})
        if not -60 <= main.get('temp', 20) <= 60:
            main['temp'] = 20.0
        if not -60 <= main.get('feels_like', 20) <= 60:
            main['feels_like'] = 20.0
        if not 0 <= main.get('humidity', 50) <= 100:
            main['humidity'] = 50
        wind = data.get('wind', {})
        if not 0 <= wind.get('speed', 0) <= 100:
            wind['speed'] = 0
        if not 0 <= data.get('uvi', 0) <= 15:
            data['uvi'] = 0
        if not 0 <= data.get('visibility', 10000) <= 100000:
            data['visibility'] = 10000
        rain = data.get('rain', {})
        if not 0 <= rain.get('1h', 0) <= 500:
            rain['1h'] = 0
        return data

    @staticmethod
    def fallback_seasonal_profile(location: Dict[str, Any]) -> EnvironmentalSignalVector:
        """Latitude‑based fallback when API fails."""
        lat = location.get('lat', 40)
        if abs(lat) > 60:
            thermal = -0.6
            baseline = 0.2
        elif abs(lat) > 40:
            thermal = 0.0
            baseline = 0.5
        elif abs(lat) > 23.5:
            thermal = 0.4
            baseline = 0.7
        else:
            thermal = 0.8
            baseline = 0.9
        return EnvironmentalSignalVector(
            thermal_index=thermal,
            precipitation_index=0.5,
            humidity_index=0.7 if abs(lat) < 30 else 0.5,
            uv_index=0.7 if abs(lat) < 30 else 0.4,
            wind_index=0.3,
            climate_baseline=baseline,
            confidence=0.2
        )

    # ----- ENVIRONMENTAL SIGNAL VECTOR (FULL IMPLEMENTATION) -----
    async def get_environmental_signal(self, location: Dict[str, Any]) -> EnvironmentalSignalVector:
        """Build ESV with confidence, blending real‑time and seasonal normals."""
        # Try real‑time weather with timeout
        try:
            weather_task = self.get_current_weather(location)
            weather = await asyncio.wait_for(weather_task, timeout=0.3)
        except (asyncio.TimeoutError, Exception):
            logger.debug('ESV fetch failed – using fallback')
            weather = None

        # Get climate baseline
        normals = await self.get_climate_normals(location)
        baseline_temp = normals.get('avg_temp', 20)

        if weather is None:
            return self.fallback_seasonal_profile(location)

        # Normalisation
        thermal_idx = (weather.temperature - 15) / 30
        thermal_idx = max(-1.0, min(1.0, thermal_idx))

        precip_idx = min(1.0, weather.precipitation / 50)
        humid_idx = weather.humidity / 100.0
        uv_idx = min(1.0, weather.uv_index / 11)
        wind_idx = min(1.0, weather.wind_speed / 30)

        baseline_idx = (baseline_temp - 15) / 30
        baseline_idx = max(-1.0, min(1.0, baseline_idx))

        # Confidence
        confidence = 0.8
        if (datetime.now() - weather.timestamp).seconds > 3600:
            confidence *= 0.7

        # Anomaly blending
        if abs(thermal_idx - baseline_idx) > 0.5:
            thermal_idx = 0.7 * thermal_idx + 0.3 * baseline_idx
            confidence *= 0.9

        return EnvironmentalSignalVector(
            thermal_index=thermal_idx,
            precipitation_index=precip_idx,
            humidity_index=humid_idx,
            uv_index=uv_idx,
            wind_index=wind_idx,
            climate_baseline=baseline_idx,
            confidence=confidence
        )

    async def get_current_weather(self, location: Dict[str, Any]) -> Optional[WeatherData]:
        if not location or not self.api_key:
            return None
        cache_key = self._generate_cache_key('current', location)
        cached = self._get_cached(cache_key)
        if cached:
            return WeatherData(**cached)
        try:
            await self.connect()
            params = {
                'lat': location.get('lat'),
                'lon': location.get('lon'),
                'appid': self.api_key,
                'units': 'metric',
                'lang': 'en'
            }
            async with self.session.get(f'{self.base_url}/weather', params=params) as resp:
                if resp.status == 200:
                    raw = await resp.json()
                    sanitized = self.sanitize_weather(raw)
                    weather = self._parse_weather_response(sanitized)
                    self._set_cached(cache_key, weather.__dict__)
                    return weather
                else:
                    logger.error(f'Weather API error: {resp.status}')
                    return None
        except Exception as e:
            logger.error(f'Failed to get weather: {e}')
            return None

    # ----- Cache helpers with TTL -----
    def _generate_cache_key(self, prefix: str, location: Dict) -> str:
        lat = location.get('lat', 0)
        lon = location.get('lon', 0)
        key_str = f'{prefix}:{lat:.4f}:{lon:.4f}'
        return hashlib.md5(key_str.encode()).hexdigest()

    def _get_cached(self, cache_key: str) -> Optional[Any]:
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            if datetime.now() - entry['timestamp'] < timedelta(seconds=self.cache_ttl):
                return entry['data']
            else:
                del self.cache[cache_key]
        return None

    def _set_cached(self, cache_key: str, data: Any):
        self.cache[cache_key] = {'data': data, 'timestamp': datetime.now()}
        # LRU cleanup
        if len(self.cache) > 1000:
            oldest_key = min(self.cache.items(), key=lambda x: x[1]['timestamp'])[0]
            del self.cache[oldest_key]

    def _parse_weather_response(self, data: Dict) -> WeatherData:
        main = data.get('main', {})
        weather = data.get('weather', [{}])[0]
        wind = data.get('wind', {})
        return WeatherData(
            temperature=main.get('temp', 20),
            condition=weather.get('main', 'Clear').lower(),
            humidity=main.get('humidity', 50),
            wind_speed=wind.get('speed', 0),
            precipitation=data.get('rain', {}).get('1h', 0),
            feels_like=main.get('feels_like', main.get('temp', 20)),
            uv_index=data.get('uvi', 0),
            visibility=data.get('visibility', 10000) / 1000,
            timestamp=datetime.fromtimestamp(data.get('dt', 0))
        )

    async def get_climate_normals(self, location: Dict, month: Optional[int] = None) -> Dict[str, float]:
        lat = location.get('lat', 0)
        if abs(lat) > 60:
            return {'avg_temp': -5, 'avg_precipitation': 30, 'avg_humidity': 70, 'climate_zone': 'polar'}
        elif abs(lat) > 40:
            return {'avg_temp': 10, 'avg_precipitation': 60, 'avg_humidity': 65, 'climate_zone': 'temperate'}
        elif abs(lat) > 23.5:
            return {'avg_temp': 20, 'avg_precipitation': 80, 'avg_humidity': 70, 'climate_zone': 'subtropical'}
        else:
            return {'avg_temp': 27, 'avg_precipitation': 150, 'avg_humidity': 80, 'climate_zone': 'tropical'}

class ClimateService:
    def __init__(self):
        self.openweather = OpenWeatherMapService()
        self._esv_cache: Dict[str, tuple[EnvironmentalSignalVector, datetime]] = {}
        self._esv_ttl = timedelta(minutes=config.ESV_CACHE_TTL_MINUTES)

    async def get_environmental_signal(self, location: Dict[str, Any]) -> EnvironmentalSignalVector:
        if not location:
            return EnvironmentalSignalVector.neutral()

        cache_key = f'esv:{location.get("lat",0):.4f}:{location.get("lon",0):.4f}'
        now = datetime.now()
        if cache_key in self._esv_cache:
            esv, ts = self._esv_cache[cache_key]
            if now - ts < self._esv_ttl:
                return esv

        try:
            esv = await asyncio.wait_for(
                self.openweather.get_environmental_signal(location),
                timeout=0.3
            )
        except Exception:
            esv = self.openweather.fallback_seasonal_profile(location)

        self._esv_cache[cache_key] = (esv, now)
        # Cleanup old entries
        if len(self._esv_cache) > 100:
            to_del = [k for k, (_, ts) in self._esv_cache.items() if now - ts > self._esv_ttl]
            for k in to_del:
                del self._esv_cache[k]
        return esv
