"""Canonical registry of appearance specialists and honest capability limits."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import SpecialistId, normalize_category

@dataclass(frozen=True)
class SpecialistDescriptor:
    specialist: SpecialistId
    display_name: str
    catalog_categories: frozenset[str]
    catalog_matching_available: bool
    image_analysis_status: str
    requires_fit_confidence: bool
    description: str
    limits: tuple[str, ...]

def _categories(*values: str) -> frozenset[str]:
    return frozenset(normalize_category(v) for v in values)

SPECIALISTS: dict[SpecialistId, SpecialistDescriptor] = {
    SpecialistId.HAIR: SpecialistDescriptor(
        SpecialistId.HAIR, "Hair", _categories("hair", "haircare", "hair care", "hair styling", "hairstyle", "hairstyles", "wig", "wigs", "hair accessories"),
        True, "provider_required_for_image_analysis", False,
        "Catalog-category matching for hair products and declared style categories.",
        ("Hair-image classification, hairstyle generation, and virtual hair rendering are unavailable.",)),
    SpecialistId.FACE: SpecialistDescriptor(
        SpecialistId.FACE, "Face", _categories("eyewear", "glasses", "eyeglasses", "sunglasses", "face accessories", "facial hair", "beard grooming"),
        True, "provider_required_for_image_analysis", True,
        "Catalog-category matching for declared face-styling products; not facial analysis.",
        ("Face-shape inference and face-image recommendations are unavailable.",)),
    SpecialistId.SKIN: SpecialistDescriptor(
        SpecialistId.SKIN, "Skin", frozenset(), False,
        "unavailable_until_validated_dermalsight_model_is_configured", False,
        "Cosmetic skin-attribute analysis through the existing DermalSight boundary.",
        ("DermalSight has an API/adapter but no approved model artifact and signed validation report are present.",)),
    SpecialistId.LOOK: SpecialistDescriptor(
        SpecialistId.LOOK, "Look", _categories("apparel", "clothing", "outfit", "outfits", "top", "tops", "shirt", "shirts", "trousers", "pants", "jeans", "dress", "dresses", "skirt", "skirts", "outerwear", "jacket", "jackets", "suits"),
        True, "provider_required_for_visual_try_on", True,
        "Catalog-backed clothing candidate evaluation and deterministic look composition.",
        ("Visual ranking, body measurement, and virtual try-on are not enabled.",)),
    SpecialistId.FOOTWEAR: SpecialistDescriptor(
        SpecialistId.FOOTWEAR, "Footwear", _categories("shoe", "shoes", "footwear", "sneakers", "boots", "sandals", "heels", "flats", "loafers", "slippers"),
        True, "provider_required_for_visual_try_on", True,
        "Catalog-category matching with physical-fit evidence required before display.",
        ("Size availability, comfort, and physical fit are not inferred from catalog category.",)),
    SpecialistId.MAKEUP: SpecialistDescriptor(
        SpecialistId.MAKEUP, "Makeup", _categories("makeup", "cosmetics", "lipstick", "lip gloss", "foundation", "concealer", "mascara", "eyeshadow", "eye shadow", "eyeliner", "blush", "highlighter", "makeup tools"),
        True, "provider_required_for_virtual_makeup", False,
        "Catalog-backed makeup matching using supplied metadata and declared constraints.",
        ("Shade inference, skin-tone prediction, and virtual makeup rendering are unavailable.",)),
    SpecialistId.SKINCARE: SpecialistDescriptor(
        SpecialistId.SKINCARE, "Skincare", _categories("skincare", "skin care", "cleanser", "moisturizer", "moisturiser", "serum", "sunscreen", "sun care", "toner", "skin care products"),
        True, "not_required_for_catalog_matching", False,
        "Catalog-category matching for skincare products using explicit preferences and verified product data.",
        ("No diagnosis, treatment plan, medical recommendation, or ingredient-safety guarantee is provided.",)),
}

def describe_specialist(specialist: SpecialistId | str) -> SpecialistDescriptor:
    try:
        key = specialist if isinstance(specialist, SpecialistId) else SpecialistId(specialist)
    except ValueError as exc:
        raise ValueError(f"unsupported appearance specialist: {specialist}") from exc
    return SPECIALISTS[key]
