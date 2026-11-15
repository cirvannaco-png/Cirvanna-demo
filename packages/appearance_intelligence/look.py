"""Provider-neutral, identity-preserving appearance transformation contracts.

This package defines the shared look vocabulary and validation rules. It does not
perform image analysis, store media, authorize products, or render transformations.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


CONTRACT_VERSION = "1.0.0"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{1,159}$")
_MODEL_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,159}@sha256:[0-9a-f]{64}$")

_DEFAULT_REGIONS: dict["AppearanceComponent", tuple[str, ...]] = {}


class LookBaseKind(str, Enum):
    SOURCE_PHOTO = "source_photo"
    VIRTUAL_TWIN = "virtual_twin"
    PREVIOUS_RENDER = "previous_render"


class AppearanceComponent(str, Enum):
    HAIRSTYLE = "hairstyle"
    HAIR_COLOUR = "hair_colour"
    HAIRLINE = "hairline"
    FACIAL_HAIR = "facial_hair"
    EYEBROWS = "eyebrows"
    EYELASHES = "eyelashes"
    LIPSTICK = "lipstick"
    MAKEUP = "makeup"
    SKINCARE_APPLICATION = "skincare_application"
    SKINCARE_PRODUCT = "skincare_product"
    HAIRCARE_PRODUCT = "haircare_product"
    GARMENT = "garment"
    FOOTWEAR = "footwear"
    JEWELLERY = "jewellery"
    EYEWEAR = "eyewear"
    HEADWEAR = "headwear"
    HAIR_ACCESSORY = "hair_accessory"
    BAG = "bag"
    ACCESSORY = "accessory"
    NAIL_ART = "nail_art"
    FRAGRANCE = "fragrance"


class EditAction(str, Enum):
    APPLY = "apply"
    REPLACE = "replace"
    ADJUST = "adjust"
    REMOVE = "remove"


class ReferenceKind(str, Enum):
    CATALOG_PRODUCT = "catalog_product"
    WARDROBE_ITEM = "wardrobe_item"
    STYLE_CATALOG = "style_catalog"


class OperationOrigin(str, Enum):
    USER_DIRECTED = "user_directed"
    ACCEPTED_RECOMMENDATION = "accepted_recommendation"


class RecommendationTrack(str, Enum):
    HARMONIOUS = "harmonious"
    EXPRESSIVE = "expressive"
    EXPERIMENTAL = "experimental"
    PRACTICAL = "practical"
    TRANSFORMATIONAL = "transformational"


class FidelityGate(str, Enum):
    IDENTITY_CONSISTENCY = "identity_consistency"
    FACIAL_GEOMETRY_PRESERVATION = "facial_geometry_preservation"
    SKIN_TONE_PRESERVATION = "skin_tone_preservation"
    UNAFFECTED_REGION_PRESERVATION = "unaffected_region_preservation"
    HAIRLINE_INTEGRATION = "hairline_integration"
    HAIR_AND_FACIAL_HAIR_REALISM = "hair_and_facial_hair_realism"
    GARMENT_AND_ACCESSORY_OCCLUSION = "garment_and_accessory_occlusion"
    LIGHTING_CONSISTENCY = "lighting_consistency"
    ANATOMICAL_CORRECTNESS = "anatomical_correctness"
    PHOTOGRAPHIC_CREDIBILITY = "photographic_credibility"


class GateStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW_REQUIRED = "review_required"
    NOT_APPLICABLE = "not_applicable"


_CORE_FIDELITY_GATES = frozenset({
    FidelityGate.IDENTITY_CONSISTENCY,
    FidelityGate.FACIAL_GEOMETRY_PRESERVATION,
    FidelityGate.SKIN_TONE_PRESERVATION,
    FidelityGate.UNAFFECTED_REGION_PRESERVATION,
    FidelityGate.LIGHTING_CONSISTENCY,
    FidelityGate.ANATOMICAL_CORRECTNESS,
    FidelityGate.PHOTOGRAPHIC_CREDIBILITY,
})

_DEFAULT_REGIONS = {
    AppearanceComponent.HAIRSTYLE: ("hair", "scalp"),
    AppearanceComponent.HAIR_COLOUR: ("hair", "scalp"),
    AppearanceComponent.HAIRLINE: ("hairline", "temples", "forehead_boundary"),
    AppearanceComponent.FACIAL_HAIR: ("facial_hair", "chin", "jaw"),
    AppearanceComponent.EYEBROWS: ("eyebrows",),
    AppearanceComponent.EYELASHES: ("eyelashes",),
    AppearanceComponent.LIPSTICK: ("lips",),
    AppearanceComponent.MAKEUP: ("user_selected_makeup_regions",),
    AppearanceComponent.SKINCARE_APPLICATION: ("skin_surface",),
    AppearanceComponent.SKINCARE_PRODUCT: ("product_item",),
    AppearanceComponent.HAIRCARE_PRODUCT: ("product_item",),
    AppearanceComponent.GARMENT: ("user_selected_body_regions",),
    AppearanceComponent.FOOTWEAR: ("feet",),
    AppearanceComponent.JEWELLERY: ("user_selected_jewellery_anchor",),
    AppearanceComponent.EYEWEAR: ("eyes", "nose_bridge", "ears"),
    AppearanceComponent.HEADWEAR: ("head", "hairline_boundary"),
    AppearanceComponent.HAIR_ACCESSORY: ("hair",),
    AppearanceComponent.BAG: ("user_selected_bag_anchor",),
    AppearanceComponent.ACCESSORY: ("user_selected_accessory_anchor",),
    AppearanceComponent.NAIL_ART: ("nails",),
    AppearanceComponent.FRAGRANCE: ("non_visual_product",),
}


def _opaque_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string identifier.")
    normalized = value.strip()
    if (
        not _IDENTIFIER_RE.fullmatch(normalized)
        or "://" in normalized
        or "/" in normalized
        or "\\" in normalized
    ):
        raise ValueError(f"{field_name} must be an opaque internal identifier, not a URL or path.")
    return normalized


@dataclass(frozen=True)
class LookBase:
    """Immutable root lineage for a look; prior renders never replace this lineage."""

    kind: LookBaseKind
    source_asset_ids: tuple[str, ...]
    twin_id: str | None = None
    parent_look_id: str | None = None
    parent_render_asset_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LookBaseKind):
            raise ValueError("kind must be a LookBaseKind.")
        if not isinstance(self.source_asset_ids, tuple) or not self.source_asset_ids:
            raise ValueError("source_asset_ids must retain at least one original source asset.")
        normalized = tuple(_opaque_identifier(value, "source_asset_id") for value in self.source_asset_ids)
        if len(normalized) != len(set(normalized)):
            raise ValueError("source_asset_ids must be unique.")
        object.__setattr__(self, "source_asset_ids", normalized)

        if self.kind is LookBaseKind.SOURCE_PHOTO:
            if self.twin_id or self.parent_look_id or self.parent_render_asset_id:
                raise ValueError("source_photo cannot carry Twin or previous-render references.")
        elif self.kind is LookBaseKind.VIRTUAL_TWIN:
            if not self.twin_id:
                raise ValueError("virtual_twin requires twin_id.")
            if self.parent_look_id or self.parent_render_asset_id:
                raise ValueError("virtual_twin cannot carry previous-render references.")
        elif self.kind is LookBaseKind.PREVIOUS_RENDER:
            if not self.parent_look_id or not self.parent_render_asset_id:
                raise ValueError("previous_render requires both parent_look_id and parent_render_asset_id.")
            object.__setattr__(self, "parent_look_id", _opaque_identifier(self.parent_look_id, "parent_look_id"))
            object.__setattr__(self, "parent_render_asset_id", _opaque_identifier(self.parent_render_asset_id, "parent_render_asset_id"))

        if self.twin_id is not None:
            object.__setattr__(self, "twin_id", _opaque_identifier(self.twin_id, "twin_id"))


@dataclass(frozen=True)
class ComponentOperation:
    """One user-directed or user-accepted edit to a specific appearance component."""

    operation_id: str
    component: AppearanceComponent
    action: EditAction
    origin: OperationOrigin = OperationOrigin.USER_DIRECTED
    reference_kind: ReferenceKind | None = None
    reference_id: str | None = None
    description: str | None = None
    target_regions: tuple[str, ...] = ()
    recommendation_track: RecommendationTrack | None = None
    recommendation_id: str | None = None
    parameters: tuple[tuple[str, str], ...] = ()
    preserve_unrequested_regions: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _opaque_identifier(self.operation_id, "operation_id"))
        if not isinstance(self.component, AppearanceComponent):
            raise ValueError("component must be an AppearanceComponent.")
        if not isinstance(self.action, EditAction):
            raise ValueError("action must be an EditAction.")
        if not isinstance(self.origin, OperationOrigin):
            raise ValueError("origin must be an OperationOrigin.")
        if self.preserve_unrequested_regions is not True:
            raise ValueError("operations must preserve every region the user did not request to change.")

        if self.reference_id is None:
            if self.reference_kind is not None:
                raise ValueError("reference_kind requires reference_id.")
        else:
            object.__setattr__(self, "reference_id", _opaque_identifier(self.reference_id, "reference_id"))
            if not isinstance(self.reference_kind, ReferenceKind):
                raise ValueError("reference_id requires a valid reference_kind.")

        if self.action is not EditAction.REMOVE and not (
            self.reference_id or (isinstance(self.description, str) and self.description.strip()) or self.parameters
        ):
            raise ValueError("apply, replace and adjust operations require a reference, description or parameters.")

        if self.description is not None:
            if not isinstance(self.description, str) or not self.description.strip() or len(self.description) > 500:
                raise ValueError("description must contain 1 to 500 non-whitespace characters.")
            object.__setattr__(self, "description", self.description.strip())

        regions = self.target_regions or _DEFAULT_REGIONS[self.component]
        if not isinstance(regions, tuple) or not regions:
            raise ValueError("target_regions must be a non-empty tuple.")
        normalized_regions: list[str] = []
        for region in regions:
            if not isinstance(region, str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", region.strip()):
                raise ValueError("target_regions must contain stable lowercase region keys.")
            normalized_regions.append(region.strip())
        if len(normalized_regions) != len(set(normalized_regions)):
            raise ValueError("target_regions must not contain duplicates.")
        object.__setattr__(self, "target_regions", tuple(normalized_regions))

        if self.origin is OperationOrigin.ACCEPTED_RECOMMENDATION:
            if not self.recommendation_id:
                raise ValueError("accepted recommendations require a recommendation_id.")
            object.__setattr__(self, "recommendation_id", _opaque_identifier(self.recommendation_id, "recommendation_id"))
            if self.recommendation_track is None:
                raise ValueError("accepted recommendations require a recommendation_track.")
        elif self.recommendation_id is not None or self.recommendation_track is not None:
            raise ValueError("user-directed operations must not carry recommendation metadata.")

        if not isinstance(self.parameters, tuple):
            raise ValueError("parameters must be an immutable tuple of key/value pairs.")
        keys: set[str] = set()
        for pair in self.parameters:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("each parameter must be a two-item tuple.")
            key, value = pair
            if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", key):
                raise ValueError("parameter keys must be stable lowercase identifiers.")
            if not isinstance(value, str) or len(value) > 200:
                raise ValueError("parameter values must be strings of at most 200 characters.")
            if key in keys:
                raise ValueError("parameter keys must be unique.")
            keys.add(key)


@dataclass(frozen=True)
class LookComposition:
    """A versioned, editable composition shared by Cirvanna experience surfaces."""

    look_id: str
    subject_id: str
    version: int
    base: LookBase
    operations: tuple[ComponentOperation, ...]
    preserve_identity: bool = True
    preserve_facial_geometry: bool = True
    preserve_underlying_skin_tone: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "look_id", _opaque_identifier(self.look_id, "look_id"))
        object.__setattr__(self, "subject_id", _opaque_identifier(self.subject_id, "subject_id"))
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer.")
        if not isinstance(self.base, LookBase):
            raise ValueError("base must be a LookBase.")
        if not isinstance(self.operations, tuple) or not self.operations:
            raise ValueError("operations must be a non-empty immutable tuple.")
        if any(not isinstance(op, ComponentOperation) for op in self.operations):
            raise ValueError("operations must contain ComponentOperation instances.")
        operation_ids = [op.operation_id for op in self.operations]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("operation_id values must be unique within a look version.")
        if self.preserve_identity is not True:
            raise ValueError("appearance transformations must preserve source identity.")
        if self.preserve_facial_geometry is not True:
            raise ValueError("appearance transformations must preserve facial geometry.")
        if self.preserve_underlying_skin_tone is not True:
            raise ValueError("appearance transformations must preserve underlying skin tone.")


@dataclass(frozen=True)
class FidelityAssessment:
    """Render-release assessment; failed or uncertain outputs must remain private."""

    assessment_id: str
    look_id: str
    look_version: int
    output_asset_id: str
    model_version: str
    checks: tuple[tuple[FidelityGate, GateStatus], ...]

    def __post_init__(self) -> None:
        for name in ("assessment_id", "look_id", "output_asset_id"):
            object.__setattr__(self, name, _opaque_identifier(getattr(self, name), name))
        if not isinstance(self.look_version, int) or isinstance(self.look_version, bool) or self.look_version < 1:
            raise ValueError("look_version must be a positive integer.")
        if not isinstance(self.model_version, str) or not _MODEL_VERSION_RE.fullmatch(self.model_version):
            raise ValueError("model_version must include a SHA-256-pinned revision.")
        if not isinstance(self.checks, tuple):
            raise ValueError("checks must be an immutable tuple.")
        statuses: dict[FidelityGate, GateStatus] = {}
        for check in self.checks:
            if not isinstance(check, tuple) or len(check) != 2:
                raise ValueError("each fidelity check must be a (gate, status) tuple.")
            gate, status = check
            if not isinstance(gate, FidelityGate) or not isinstance(status, GateStatus):
                raise ValueError("fidelity checks must use FidelityGate and GateStatus values.")
            if gate in statuses:
                raise ValueError("each fidelity gate must be reported exactly once.")
            statuses[gate] = status
        if set(statuses) != set(FidelityGate):
            raise ValueError("every fidelity gate must be reported exactly once.")
        for gate in _CORE_FIDELITY_GATES:
            if statuses[gate] is not GateStatus.PASS:
                raise ValueError(f"core fidelity gate {gate.value} must pass before an output can be released.")

    @property
    def releasable(self) -> bool:
        """True only when all applicable checks pass and none fail or need review."""
        return all(status in {GateStatus.PASS, GateStatus.NOT_APPLICABLE} for _, status in self.checks)

    @property
    def disposition(self) -> str:
        if any(status is GateStatus.FAIL for _, status in self.checks):
            return "withheld"
        if any(status is GateStatus.REVIEW_REQUIRED for _, status in self.checks):
            return "review_required"
        return "releasable" if self.releasable else "withheld"
