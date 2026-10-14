"""Core domain models and business logic for Cirvanna.

This module is the single source of truth for:
  - Enumerations (ingestion methods, lifecycle states, categories, etc.)
  - Value objects (ColorVector, TemporalValue, ConfidenceEnvelope, RegretSignals)
  - Profile objects (GeometryProfile, SurfaceProperties)
  - Event objects (WearEvent)
  - The central aggregate: WardrobeObject

It has **no external service dependencies** (no DB, no HTTP, no messaging)
so it can be imported anywhere. All persistence is handled by adapters.
"""

from __future__ import annotations

import datetime as dt
import math
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Iterable

import numpy as np

from .config import settings

# ────────────────────────────────────────────────────────────────
# Enumerations
# ────────────────────────────────────────────────────────────────


class IngestionMethod(str, Enum):
    CAMERA = "camera"
    SKU_ASSISTED = "sku_assisted"
    MANUAL = "manual"
    CATALOG_IMPORT = "catalog_import"


class LifecycleState(str, Enum):
    PROVISIONAL = "provisional"
    ACTIVE_LEARNING = "active_learning"
    STABLE = "stable"
    DORMANT = "dormant"
    REVIVAL_CANDIDATE = "revival_candidate"
    RETIRED = "retired"


class SilhouetteClass(str, Enum):
    FITTED = "fitted"
    RELAXED = "relaxed"
    OVERSIZED = "oversized"
    STRUCTURED = "structured"
    FLUID = "fluid"


class TextureClass(str, Enum):
    SMOOTH = "smooth"
    COARSE = "coarse"
    KNIT = "knit"
    REFLECTIVE = "reflective"
    MATTE = "matte"


class MobilityTolerance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EventType(str, Enum):
    WEAR = "wear"
    TRYON = "tryon"
    PAIRING_TEST = "pairing_test"


class PrimaryCategory(str, Enum):
    TOP = "top"
    BOTTOM = "bottom"
    OUTERWEAR = "outerwear"
    FOOTWEAR = "footwear"
    ACCESSORY = "accessory"


class LayeringRole(str, Enum):
    BASE = "base"
    MID = "mid"
    SHELL = "shell"


class SecondaryRole(str, Enum):
    SLEEPWEAR = "sleepwear"
    ATHLETIC = "athletic"
    SWIMWEAR = "swimwear"
    FORMAL = "formal"
    RAIN_PROTECTION = "rain_protection"
    WARMTH = "warmth"
    SUN_PROTECTION = "sun_protection"
    WORKWEAR = "workwear"
    UNSPECIFIED = "unspecified"


class ActivityType(str, Enum):
    SEDENTARY = "sedentary"
    LIGHT_EXERCISE = "light_exercise"
    INTENSE_EXERCISE = "intense_exercise"
    WALKING = "walking"
    RUNNING = "running"
    CYCLING = "cycling"
    SWIMMING = "swimming"
    TRAVEL = "travel"
    OFFICE_WORK = "office_work"
    MANUAL_LABOR = "manual_labor"
    SOCIAL = "social"
    UNSPECIFIED = "unspecified"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ────────────────────────────────────────────────────────────────
# Business constants (derived from settings so they're configurable)
# ────────────────────────────────────────────────────────────────

CONFIDENCE_BASE: dict[IngestionMethod, float] = {
    IngestionMethod.CAMERA: settings.confidence_base_camera,
    IngestionMethod.SKU_ASSISTED: settings.confidence_base_sku_assisted,
    IngestionMethod.MANUAL: settings.confidence_base_manual,
    IngestionMethod.CATALOG_IMPORT: settings.confidence_base_catalog_import,
}

BOOTSTRAP_CONFIDENCE_RANGE: tuple[float, float] = (
    settings.bootstrap_confidence_min,
    settings.bootstrap_confidence_max,
)

MAX_ACTIVE_SLICE: int = settings.max_active_slice

# Category compatibility matrix (used by graph and recommendation)
CATEGORY_COMPATIBILITY: dict[str, set[str]] = {
    "top": {"bottom", "outerwear", "footwear", "accessory"},
    "bottom": {"top", "outerwear", "footwear", "accessory"},
    "outerwear": {"top", "bottom", "footwear", "accessory"},
    "footwear": {"top", "bottom", "outerwear", "accessory"},
    "accessory": {"top", "bottom", "outerwear", "footwear"},
}


# ────────────────────────────────────────────────────────────────
# Value objects
# ────────────────────────────────────────────────────────────────


@dataclass
class ColorVector:
    """CIELAB colour representation with bidirectional conversion.

    All conversions are cached; the object is immutable in practice.
    """

    l: float
    a: float
    b: float
    _rgb_cache: tuple[int, int, int] | None = field(default=None, repr=False)
    _hex_cache: str | None = field(default=None, repr=False)

    # ---------- Constructors ----------
    @classmethod
    def from_rgb(cls, r: int, g: int, b: int) -> "ColorVector":
        """Convert sRGB (0-255) to CIELAB using D65 illuminant."""
        if not all(0 <= v <= 255 for v in (r, g, b)):
            raise ValueError(f"RGB values must be in [0,255], got ({r},{g},{b})")

        def _linearize(c: float) -> float:
            c /= 255.0
            return c ** 2.2 if c > 0.04045 else c / 12.92

        rl, gl, bl = _linearize(r), _linearize(g), _linearize(b)

        x = rl * 0.4124 + gl * 0.3576 + bl * 0.1805
        y = rl * 0.2126 + gl * 0.7152 + bl * 0.0722
        z = rl * 0.0193 + gl * 0.1192 + bl * 0.9505

        xn, zn = x / 0.95047, z / 1.08883

        def _f(t: float) -> float:
            return t ** (1 / 3) if t > 0.008856 else (7.787 * t) + (16 / 116)

        fx, fy, fz = _f(xn), _f(y), _f(zn)

        return cls(
            l=max(0.0, min(100.0, 116 * fy - 16)),
            a=max(-128.0, min(127.0, 500 * (fx - fy))),
            b=max(-128.0, min(127.0, 200 * (fy - fz))),
        )

    @classmethod
    def from_hex(cls, hex_color: str) -> "ColorVector":
        """Parse '#RRGGBB' or '#RGB' into a ColorVector."""
        h = hex_color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            raise ValueError(f"Invalid hex color: {hex_color}")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        cv = cls.from_rgb(r, g, b)
        cv._hex_cache = f"#{h.lower()}"
        cv._rgb_cache = (r, g, b)
        return cv

    # ---------- Conversions ----------
    def to_rgb(self) -> tuple[int, int, int]:
        if self._rgb_cache is not None:
            return self._rgb_cache

        fy = (self.l + 16) / 116
        fx = fy + (self.a / 500)
        fz = fy - (self.b / 200)

        def _inv(t: float) -> float:
            return t ** 3 if t ** 3 > 0.008856 else (t - 16 / 116) / 7.787

        x = _inv(fx) * 0.95047
        y = ((self.l + 16) / 116) ** 3 if self.l > 7.9996 else self.l / 903.3
        z = _inv(fz) * 1.08883

        rl = x * 3.2406 + y * -1.5372 + z * -0.4986
        gl = x * -0.9689 + y * 1.8758 + z * 0.0415
        bl = x * 0.0557 + y * -0.2040 + z * 1.0570

        def _gamma(c: float) -> int:
            v = c ** (1 / 2.2) if c > 0.0031308 else 12.92 * c
            return int(max(0, min(255, 255 * v)))

        self._rgb_cache = (_gamma(rl), _gamma(gl), _gamma(bl))
        return self._rgb_cache

    def to_hex(self) -> str:
        if self._hex_cache is not None:
            return self._hex_cache
        r, g, b = self.to_rgb()
        self._hex_cache = f"#{r:02x}{g:02x}{b:02x}"
        return self._hex_cache

    # ---------- Operations ----------
    def distance_to(self, other: "ColorVector") -> float:
        """Euclidean distance in CIELAB (delta-E 1976)."""
        return math.sqrt(
            (self.l - other.l) ** 2 + (self.a - other.a) ** 2 + (self.b - other.b) ** 2
        )

    def to_dict(self) -> dict[str, float]:
        return {"l": self.l, "a": self.a, "b": self.b}

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> "ColorVector":
        return cls(l=float(data["l"]), a=float(data["a"]), b=float(data["b"]))


@dataclass
class TemporalValue:
    """Exponentially-smoothed scalar with a bounded history buffer.

    Used for confidence, regret, and edge weights. `get_trend` performs
    a linear regression over the last N days and returns the slope/day.
    """

    current: float = 0.0
    history: Deque[tuple[dt.datetime, float]] = field(
        default_factory=lambda: deque(maxlen=100)
    )
    smoothing_factor: float = 0.7

    def update(self, new_value: float, timestamp: dt.datetime | None = None) -> None:
        ts = timestamp or dt.datetime.now(dt.timezone.utc)
        self.history.append((ts, float(new_value)))
        if len(self.history) == 1:
            self.current = float(new_value)
        else:
            self.current = (
                self.smoothing_factor * new_value
                + (1 - self.smoothing_factor) * self.current
            )

    def apply_decay(self, decay_factor: float) -> None:
        """Multiply current and history by a decay factor."""
        if not 0 < decay_factor <= 1:
            raise ValueError(f"decay_factor must be in (0,1], got {decay_factor}")
        self.current *= decay_factor
        self.history = deque(
            [(ts, v * decay_factor) for ts, v in self.history], maxlen=self.history.maxlen
        )

    def get_trend(self, days: int = 30) -> float:
        """Slope per day over the last `days`. Returns 0 if insufficient data."""
        if len(self.history) < 2:
            return 0.0
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        relevant = [(ts, v) for ts, v in self.history if ts > cutoff]
        if len(relevant) < 2:
            return 0.0
        times = [(ts - relevant[0][0]).total_seconds() for ts, _ in relevant]
        values = [v for _, v in relevant]
        if len(set(times)) < 2:
            return 0.0
        slope = float(np.polyfit(times, values, 1)[0])
        return slope / 86400.0  # per day

    def to_dict(self) -> dict[str, Any]:
        return {
            "current": self.current,
            "history": [(ts.isoformat(), v) for ts, v in self.history],
            "smoothing_factor": self.smoothing_factor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TemporalValue":
        obj = cls(
            current=float(data["current"]),
            smoothing_factor=float(data.get("smoothing_factor", 0.7)),
        )
        obj.history = deque(
            [(dt.datetime.fromisoformat(ts), float(v)) for ts, v in data.get("history", [])],
            maxlen=100,
        )
        return obj


@dataclass
class GeometryProfile:
    """Physical shape of a garment."""

    silhouette_class: SilhouetteClass
    length_profile: str
    volume_distribution: list[float]
    stretch_behavior: str
    confidence: TemporalValue = field(default_factory=TemporalValue)

    def validate(self) -> bool:
        if not math.isclose(sum(self.volume_distribution), 1.0, abs_tol=0.01):
            return False
        return all(0.0 <= v <= 1.0 for v in self.volume_distribution)

    def to_dict(self) -> dict[str, Any]:
        return {
            "silhouette_class": self.silhouette_class.value,
            "length_profile": self.length_profile,
            "volume_distribution": list(self.volume_distribution),
            "stretch_behavior": self.stretch_behavior,
            "confidence": self.confidence.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GeometryProfile":
        obj = cls(
            silhouette_class=SilhouetteClass(data["silhouette_class"]),
            length_profile=data["length_profile"],
            volume_distribution=list(data["volume_distribution"]),
            stretch_behavior=data["stretch_behavior"],
        )
        obj.confidence = TemporalValue.from_dict(data["confidence"])
        return obj


@dataclass
class SurfaceProperties:
    """Visual surface properties of a garment."""

    dominant_color: ColorVector
    color_variance: float
    texture_class: TextureClass
    pattern_density: float
    lighting_risk: float = 0.0

    def is_update_allowed(self) -> bool:
        return self.lighting_risk < 0.8

    def get_visual_complexity(self) -> float:
        texture_penalty = 0.0 if self.texture_class == TextureClass.SMOOTH else 1.0
        return (
            self.color_variance * 0.4
            + self.pattern_density * 0.4
            + texture_penalty * 0.2
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dominant_color": self.dominant_color.to_dict(),
            "color_variance": self.color_variance,
            "texture_class": self.texture_class.value,
            "pattern_density": self.pattern_density,
            "lighting_risk": self.lighting_risk,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurfaceProperties":
        return cls(
            dominant_color=ColorVector.from_dict(data["dominant_color"]),
            color_variance=float(data["color_variance"]),
            texture_class=TextureClass(data["texture_class"]),
            pattern_density=float(data["pattern_density"]),
            lighting_risk=float(data.get("lighting_risk", 0.0)),
        )


@dataclass
class WearEvent:
    """An individual interaction with a garment."""

    timestamp: dt.datetime
    context_snapshot_id: str
    accepted: bool
    duration_estimate: float
    event_type: EventType

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "context_snapshot_id": self.context_snapshot_id,
            "accepted": self.accepted,
            "duration_estimate": self.duration_estimate,
            "event_type": self.event_type.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WearEvent":
        return cls(
            timestamp=dt.datetime.fromisoformat(data["timestamp"]),
            context_snapshot_id=data["context_snapshot_id"],
            accepted=bool(data["accepted"]),
            duration_estimate=float(data["duration_estimate"]),
            event_type=EventType(data["event_type"]),
        )


@dataclass
class RegretSignals:
    """Explicit + implicit signals of purchase/usage regret."""

    explicit: str = "none"
    implicit: dict[str, TemporalValue] = field(default_factory=dict)

    def update_implicit(self, signal_type: str, strength: float) -> None:
        if signal_type not in self.implicit:
            self.implicit[signal_type] = TemporalValue()
        self.implicit[signal_type].update(strength)

    def get_weighted_regret(self) -> float:
        base = {"none": 0.0, "mild": 0.3, "strong": 0.7}.get(self.explicit, 0.0)
        implicit_total = sum(tv.current * 0.5 for tv in self.implicit.values())
        return min(1.0, base + implicit_total)

    def get_strongest_signal(self) -> tuple[str | None, float]:
        if not self.implicit:
            return None, 0.0
        strongest = max(self.implicit.items(), key=lambda kv: kv[1].current)
        return strongest[0], strongest[1].current

    def to_dict(self) -> dict[str, Any]:
        return {
            "explicit": self.explicit,
            "implicit": {k: v.to_dict() for k, v in self.implicit.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegretSignals":
        obj = cls(explicit=data["explicit"])
        obj.implicit = {k: TemporalValue.from_dict(v) for k, v in data.get("implicit", {}).items()}
        return obj


@dataclass
class ConfidenceEnvelope:
    """Per-dimension confidence capped by the ingestion method ceiling."""

    geometry_confidence: float = 0.0
    surface_confidence: float = 0.0
    category_confidence: float = 0.0
    context_confidence: float = 0.0
    ingestion_method: IngestionMethod | None = None

    @property
    def _ceiling(self) -> float:
        if self.ingestion_method is not None:
            return CONFIDENCE_BASE[self.ingestion_method]
        return 1.0

    @property
    def overall_confidence(self) -> float:
        """Bottleneck: lowest dimension after applying the ceiling."""
        return min(
            min(self.geometry_confidence, self._ceiling),
            min(self.surface_confidence, self._ceiling),
            min(self.category_confidence, self._ceiling),
            min(self.context_confidence, self._ceiling),
        )

    def update(self, **kwargs: float) -> None:
        ceiling = self._ceiling
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, max(0.0, min(ceiling, float(value))))

    def decay(self, days_inactive: int) -> None:
        factor = 0.95 ** (days_inactive / 30.0)
        self.geometry_confidence *= factor
        self.surface_confidence *= factor
        self.category_confidence = min(self.category_confidence, 0.9)
        self.context_confidence *= factor * 0.8

    def to_dict(self) -> dict[str, Any]:
        return {
            "geometry_confidence": self.geometry_confidence,
            "surface_confidence": self.surface_confidence,
            "category_confidence": self.category_confidence,
            "context_confidence": self.context_confidence,
            "ingestion_method": self.ingestion_method.value if self.ingestion_method else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfidenceEnvelope":
        obj = cls(
            geometry_confidence=float(data["geometry_confidence"]),
            surface_confidence=float(data["surface_confidence"]),
            category_confidence=float(data["category_confidence"]),
            context_confidence=float(data["context_confidence"]),
        )
        if data.get("ingestion_method"):
            obj.ingestion_method = IngestionMethod(data["ingestion_method"])
        return obj


# ────────────────────────────────────────────────────────────────
# The aggregate: WardrobeObject
# ────────────────────────────────────────────────────────────────


class WardrobeObject:
    """Aggregate root for a single garment.

    Encapsulates every piece of per-item state and every rule that mutates it:
      * Confidence envelope updates on wear/tryon/rejection
      * Regret signal accumulation
      * Lifecycle state transitions (provisional → stable → dormant → revived)
      * Wearability context expansion based on long-duration wears

    This class performs no I/O. Persistence is handled by adapter layers.
    """

    __slots__ = (
        "id",
        "owner_id",
        "created_at",
        "last_updated",
        "ingestion_method",
        "lifecycle_state",
        "bootstrap_confidence",
        "geometry_profile",
        "surface_properties",
        "category_constraints",
        "wearability_context",
        "confidence_envelope",
        "usage_history",
        "regret_signals",
        "graph_hooks",
        "last_worn",
        "total_wears",
        "successful_wears",
        "adaptive_slice_weight",
        "pending_decay_days",
        "_catalog_metadata",
    )

    def __init__(
        self,
        owner_id: str,
        ingestion_method: IngestionMethod,
        primary_category: PrimaryCategory,
        bootstrap_confidence: float | None = None,
    ) -> None:
        if not owner_id:
            raise ValueError("owner_id is required")

        self.id: str = str(uuid.uuid4())
        self.owner_id: str = owner_id
        self.created_at: dt.datetime = dt.datetime.now(dt.timezone.utc)
        self.last_updated: dt.datetime = self.created_at
        self.ingestion_method: IngestionMethod = ingestion_method
        self.lifecycle_state: LifecycleState = LifecycleState.PROVISIONAL

        if bootstrap_confidence is not None:
            lo, hi = BOOTSTRAP_CONFIDENCE_RANGE
            self.bootstrap_confidence: float = max(lo, min(hi, bootstrap_confidence))
        else:
            self.bootstrap_confidence = CONFIDENCE_BASE[ingestion_method] * 0.3

        self.geometry_profile: GeometryProfile | None = None
        self.surface_properties: SurfaceProperties | None = None

        self.category_constraints: dict[str, Any] = {
            "primary_category": primary_category.value,
            "secondary_roles": [],
            "layering_role": LayeringRole.BASE.value,
        }
        self.wearability_context: dict[str, Any] = {
            "climate_range": [10.0, 25.0],
            "activity_affinity": [],
            "mobility_tolerance": MobilityTolerance.MEDIUM.value,
        }

        self.confidence_envelope = ConfidenceEnvelope(ingestion_method=ingestion_method)
        self._init_confidence()

        self.usage_history: list[WearEvent] = []
        self.regret_signals = RegretSignals()

        self.graph_hooks: dict[str, Any] = {
            "node_id": str(uuid.uuid4()),
            "last_graph_update": self.created_at,
        }

        self.last_worn: dt.datetime | None = None
        self.total_wears: int = 0
        self.successful_wears: int = 0
        self.adaptive_slice_weight: float = 0.0
        self.pending_decay_days: int = 0
        self._catalog_metadata: dict[str, Any] = {}

    # ── Catalog metadata with size guard ────────────────────────
    @property
    def catalog_metadata(self) -> dict[str, Any]:
        return self._catalog_metadata

    @catalog_metadata.setter
    def catalog_metadata(self, value: dict[str, Any]) -> None:
        import json

        serialized = json.dumps(value, default=str)
        if len(serialized) > 100_000:
            raise ValueError("catalog_metadata exceeds 100 KB")
        self._catalog_metadata = value

    # ── Confidence initialization ───────────────────────────────
    def _init_confidence(self) -> None:
        base = CONFIDENCE_BASE[self.ingestion_method]
        self.confidence_envelope.update(
            geometry_confidence=base * 0.6,
            surface_confidence=base * 0.7,
            category_confidence=base * 0.8,
            context_confidence=self.bootstrap_confidence,
        )

    # ── Wear event handling ─────────────────────────────────────
    def record_wear_event(
        self,
        accepted: bool,
        duration_estimate: float,
        event_type: EventType = EventType.WEAR,
        context_snapshot_id: str | None = None,
    ) -> WearEvent:
        """Atomically record a wear event and update all derived state."""
        now = dt.datetime.now(dt.timezone.utc)
        cid = context_snapshot_id or f"ctx_{int(now.timestamp())}"

        event = WearEvent(
            timestamp=now,
            context_snapshot_id=cid,
            accepted=accepted,
            duration_estimate=duration_estimate,
            event_type=event_type,
        )

        # Prepare derived counters BEFORE mutating anything
        new_total = self.total_wears + 1
        new_successful = self.successful_wears + (1 if accepted else 0)
        new_last_worn = now if accepted else self.last_worn

        # Commit
        self.usage_history.append(event)
        self.total_wears = new_total
        self.successful_wears = new_successful
        self.last_worn = new_last_worn
        self.last_updated = now

        if accepted:
            self._apply_acceptance(event)
        else:
            self._apply_rejection(event)

        self._transition_lifecycle()
        return event

    def _apply_acceptance(self, event: WearEvent) -> None:
        if event.event_type == EventType.WEAR:
            self.confidence_envelope.update(
                geometry_confidence=self.confidence_envelope.geometry_confidence + 0.05,
                surface_confidence=self.confidence_envelope.surface_confidence + 0.04,
                context_confidence=self.confidence_envelope.context_confidence + 0.05,
            )
            self.adaptive_slice_weight = min(1.0, self.adaptive_slice_weight + 0.1)
        elif event.event_type == EventType.TRYON:
            self.confidence_envelope.update(
                geometry_confidence=self.confidence_envelope.geometry_confidence + 0.02,
                context_confidence=self.confidence_envelope.context_confidence + 0.01,
            )

        if event.duration_estimate > 120:
            self._expand_climate_range()

    def _apply_rejection(self, event: WearEvent) -> None:
        if event.duration_estimate < 30:
            self.regret_signals.update_implicit("early_change", 0.7)
        self.confidence_envelope.geometry_confidence *= 0.9
        self.confidence_envelope.context_confidence *= 0.9
        self.adaptive_slice_weight = max(0.0, self.adaptive_slice_weight - 0.15)

    def _expand_climate_range(self) -> None:
        lo, hi = self.wearability_context["climate_range"]
        size = hi - lo
        expansion = size * 0.1
        self.wearability_context["climate_range"] = [lo - expansion, hi + expansion]

    # ── Lifecycle transitions ───────────────────────────────────
    def _transition_lifecycle(self) -> None:
        conf = self.confidence_envelope.overall_confidence
        days_inactive = (
            (dt.datetime.now(dt.timezone.utc) - self.last_worn).days
            if self.last_worn
            else 10**9
        )

        if conf < 0.2:
            self.lifecycle_state = LifecycleState.PROVISIONAL
        elif self.lifecycle_state == LifecycleState.PROVISIONAL and conf >= 0.3:
            self.lifecycle_state = LifecycleState.ACTIVE_LEARNING
        elif (
            self.lifecycle_state == LifecycleState.ACTIVE_LEARNING
            and conf >= 0.7
            and self.total_wears >= 3
        ):
            self.lifecycle_state = LifecycleState.STABLE
        elif self.lifecycle_state == LifecycleState.STABLE and days_inactive > 90:
            self.lifecycle_state = LifecycleState.DORMANT
        elif self.lifecycle_state == LifecycleState.DORMANT:
            regret = self.regret_signals.get_weighted_regret()
            if regret < 0.3 and conf > 0.5:
                self.lifecycle_state = LifecycleState.REVIVAL_CANDIDATE
        elif (
            self.lifecycle_state == LifecycleState.REVIVAL_CANDIDATE and self.total_wears > 0
        ):
            self.lifecycle_state = LifecycleState.ACTIVE_LEARNING

    # ── Query helpers ───────────────────────────────────────────
    def get_safe_for_exploration(self) -> bool:
        if self.lifecycle_state in (LifecycleState.DORMANT, LifecycleState.RETIRED):
            return False
        return (
            self.regret_signals.get_weighted_regret() < 0.4
            and self.confidence_envelope.overall_confidence > 0.4
            and self.total_wears < 10
        )

    def queue_decay(self, days: int) -> None:
        self.pending_decay_days += days

    def apply_queue_decay(self) -> None:
        if self.pending_decay_days > 0:
            self.confidence_envelope.decay(self.pending_decay_days)
            self.pending_decay_days = 0
            self._transition_lifecycle()

    def retire(self) -> None:
        self.lifecycle_state = LifecycleState.RETIRED
        self.last_updated = dt.datetime.now(dt.timezone.utc)

    # ── Serialization ───────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "ingestion_method": self.ingestion_method.value,
            "lifecycle_state": self.lifecycle_state.value,
            "bootstrap_confidence": self.bootstrap_confidence,
            "geometry_profile": self.geometry_profile.to_dict()
            if self.geometry_profile
            else None,
            "surface_properties": self.surface_properties.to_dict()
            if self.surface_properties
            else None,
            "category_constraints": self.category_constraints,
            "wearability_context": self.wearability_context,
            "confidence_envelope": self.confidence_envelope.to_dict(),
            "regret_signals": self.regret_signals.to_dict(),
            "usage_history": [e.to_dict() for e in self.usage_history],
            "total_wears": self.total_wears,
            "successful_wears": self.successful_wears,
            "adaptive_slice_weight": self.adaptive_slice_weight,
            "pending_decay_days": self.pending_decay_days,
            "catalog_metadata": self._catalog_metadata,
            "last_worn": self.last_worn.isoformat() if self.last_worn else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WardrobeObject":
        obj = cls(
            owner_id=data["owner_id"],
            ingestion_method=IngestionMethod(data["ingestion_method"]),
            primary_category=PrimaryCategory(data["category_constraints"]["primary_category"]),
            bootstrap_confidence=data.get("bootstrap_confidence"),
        )
        obj.id = data["id"]
        obj.created_at = dt.datetime.fromisoformat(data["created_at"])
        obj.last_updated = dt.datetime.fromisoformat(data["last_updated"])
        obj.lifecycle_state = LifecycleState(data["lifecycle_state"])

        if data.get("geometry_profile"):
            obj.geometry_profile = GeometryProfile.from_dict(data["geometry_profile"])
        if data.get("surface_properties"):
            obj.surface_properties = SurfaceProperties.from_dict(data["surface_properties"])

        obj.category_constraints = data["category_constraints"]
        obj.wearability_context = data["wearability_context"]

        obj.confidence_envelope = ConfidenceEnvelope.from_dict(data["confidence_envelope"])
        obj.regret_signals = RegretSignals.from_dict(data["regret_signals"])
        obj.usage_history = [WearEvent.from_dict(e) for e in data.get("usage_history", [])]

        obj.total_wears = int(data.get("total_wears", 0))
        obj.successful_wears = int(data.get("successful_wears", 0))
        obj.adaptive_slice_weight = float(data.get("adaptive_slice_weight", 0.0))
        obj.pending_decay_days = int(data.get("pending_decay_days", 0))
        obj._catalog_metadata = data.get("catalog_metadata", {})
        if data.get("last_worn"):
            obj.last_worn = dt.datetime.fromisoformat(data["last_worn"])
        return obj

    def __repr__(self) -> str:
        return (
            f"<WardrobeObject id={self.id[:8]} owner={self.owner_id} "
            f"cat={self.category_constraints['primary_category']} "
            f"state={self.lifecycle_state.value} conf={self.confidence_envelope.overall_confidence:.2f}>"
        )


# ────────────────────────────────────────────────────────────────
# Pure helper functions (used by graph/recommendation services)
# ────────────────────────────────────────────────────────────────


def categories_are_compatible(item1: WardrobeObject, item2: WardrobeObject) -> bool:
    """True if the two items' primary categories can be worn together."""
    c1 = item1.category_constraints["primary_category"]
    c2 = item2.category_constraints["primary_category"]
    return c2 in CATEGORY_COMPATIBILITY.get(c1, set())


def rule_based_compatibility(item1: WardrobeObject, item2: WardrobeObject) -> float:
    """Baseline compatibility score in [0, 0.6] used to seed graph edges."""
    weight = 0.1
    c1 = item1.confidence_envelope.overall_confidence
    c2 = item2.confidence_envelope.overall_confidence
    weight += (1.0 - abs(c1 - c2)) * 0.2

    cat1 = item1.category_constraints["primary_category"]
    cat2 = item2.category_constraints["primary_category"]
    if {cat1, cat2} == {"top", "bottom"}:
        weight += 0.15
    elif "outerwear" in (cat1, cat2):
        weight += 0.10

    if item1.surface_properties and item2.surface_properties:
        dist = item1.surface_properties.dominant_color.distance_to(
            item2.surface_properties.dominant_color
        )
        weight += (1.0 - min(dist / 100.0, 1.0)) * 0.10

    return min(weight, 0.6)


def top_k_by_confidence(
    items: Iterable[WardrobeObject], k: int
) -> list[WardrobeObject]:
    """Return the top-k items by overall confidence (stable)."""
    return sorted(
        items,
        key=lambda it: it.confidence_envelope.overall_confidence,
        reverse=True,
    )[:k]
