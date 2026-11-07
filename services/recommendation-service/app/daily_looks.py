"""Deterministic daily outfit composition from an owner-scoped wardrobe snapshot.

This module never invents wardrobe items or marketplace products. It creates
three role slots and reports missing wardrobe coverage instead of duplicating
an outfit to fill the response.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Iterable
from typing import Any

from app.wardrobe_rotation import build_rotation_state

POLICY_VERSION = "pnelly-daily-looks-v1"
ROLES = ("everyday", "elevated", "explore")

_CATEGORY_ALIASES = {
    "top": "top", "tops": "top", "upper_body": "top", "shirt": "top", "shirts": "top",
    "t-shirt": "top", "tshirts": "top", "t_shirts": "top", "tee": "top", "tees": "top",
    "blouse": "top", "blouses": "top", "sweater": "top", "sweaters": "top",
    "knitwear": "top", "hoodie": "top", "hoodies": "top",
    "bottom": "bottom", "bottoms": "bottom", "lower_body": "bottom", "trouser": "bottom",
    "trousers": "bottom", "pants": "bottom", "jeans": "bottom",
    "skirt": "bottom", "skirts": "bottom", "shorts": "bottom",
    "leggings": "bottom",
    "dress": "one_piece", "dresses": "one_piece", "jumpsuit": "one_piece",
    "jumpsuits": "one_piece", "romper": "one_piece", "overalls": "one_piece",
    "one_piece": "one_piece", "full_outfit": "one_piece", "outfit_set": "one_piece",
    "shoe": "footwear", "shoes": "footwear", "footwear": "footwear",
    "sneaker": "footwear", "sneakers": "footwear", "boot": "footwear",
    "boots": "footwear", "sandal": "footwear", "sandals": "footwear",
    "heels": "footwear", "flats": "footwear",
    "jacket": "outerwear", "coat": "outerwear", "blazer": "outerwear",
    "cardigan": "outerwear", "outerwear": "outerwear",
    "bag": "accessory", "belt": "accessory", "watch": "accessory",
    "scarf": "accessory", "hat": "accessory", "jewellery": "accessory",
    "jewelry": "accessory", "accessory": "accessory", "accessories": "accessory",
}
_ROLE_TERMS = {
    "everyday": ("casual", "daily", "everyday", "comfortable", "relaxed"),
    "elevated": ("formal", "work", "office", "smart", "evening", "tailored", "elegant"),
    "explore": ("bold", "statement", "editorial", "creative", "experimental", "pattern"),
}


def _normalise(value: str) -> str:
    return " ".join(re.sub(r"[_-]+", " ", value.casefold()).split())


def _kind(item: dict[str, Any]) -> str | None:
    raw = _normalise(str(item.get("category", "")))
    direct = _CATEGORY_ALIASES.get(raw.replace(" ", "_")) or _CATEGORY_ALIASES.get(raw)
    if direct:
        return direct
    for attribute in item.get("attributes", []):
        key = _normalise(str(attribute)).split(":", 1)[0]
        candidate = _CATEGORY_ALIASES.get(key.replace(" ", "_")) or _CATEGORY_ALIASES.get(key)
        if candidate:
            return candidate
    return None


def _item_text(item: dict[str, Any]) -> str:
    fields = [str(item.get("display_name", "")), str(item.get("category", ""))]
    fields.extend(str(value) for value in item.get("attributes", []))
    return _normalise(" ".join(fields))


def _stable_tie(user_id: str, local_date: str, role: str, ids: Iterable[str]) -> str:
    raw = "|".join((user_id, local_date, role, *sorted(ids)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_OCCASION_TERMS = {
    "everyday": ("casual", "daily", "comfortable", "relaxed"),
    "work": ("work", "office", "tailored", "smart", "formal", "structured"),
    "meeting": ("meeting", "work", "office", "tailored", "smart", "formal"),
    "office": ("office", "work", "tailored", "smart", "formal", "structured"),
    "evening": ("evening", "elegant", "formal", "dress", "statement"),
    "date": ("date", "elegant", "evening", "romantic"),
    "formal": ("formal", "tailored", "suit", "dress", "blazer"),
    "travel": ("travel", "comfortable", "relaxed", "cotton", "linen"),
    "sport": ("sport", "active", "performance", "breathable", "sneaker"),
    "special occasion": ("formal", "elegant", "statement", "dress", "tailored"),
}
_CLIMATE_TERMS = {
    "hot_humid": {
        "positive": ("breathable", "linen", "cotton", "lightweight", "airy", "light"),
        "negative": ("wool", "fleece", "heavy", "thick", "thermal"),
    },
    "hot_dry": {
        "positive": ("breathable", "linen", "cotton", "lightweight", "airy", "light"),
        "negative": ("wool", "fleece", "heavy", "thick", "thermal"),
    },
    "cool": {
        "positive": ("wool", "knit", "sweater", "fleece", "jacket", "coat", "layered"),
        "negative": ("sleeveless", "shorts", "linen", "lightweight"),
    },
    "temperate": {"positive": (), "negative": ()},
}


_EVALUATION_STYLE_WORDS = {
    "minimal", "minimalist", "classic", "elegant", "romantic", "bold",
    "bohemian", "streetwear", "editorial", "natural", "casual", "formal",
    "relaxed", "tailored", "sporty", "smart", "vintage", "preppy",
}
_EVALUATION_COLOR_WORDS = {
    "black", "white", "blue", "navy", "red", "green", "pink", "purple",
    "yellow", "orange", "brown", "beige", "cream", "gray", "grey",
    "silver", "gold", "teal", "maroon", "burgundy", "khaki", "ivory",
}
_EVALUATION_OCCASION_WORDS = set(_OCCASION_TERMS) | {
    "casual", "daily", "everyday", "work", "office", "meeting",
    "evening", "date", "formal", "travel", "sport",
}


def _normalise_active_items(wardrobe_items: list[dict[str, Any]], user_id: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    active: list[dict[str, Any]] = []
    for item in wardrobe_items:
        if not isinstance(item, dict):
            raise ValueError("wardrobe item must be an object")
        item_id = item.get("item_id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError("wardrobe item id is required")
        if item.get("owner_user_id") != user_id:
            raise PermissionError("wardrobe item belongs to another subject")
        if item_id in seen:
            raise ValueError("duplicate wardrobe item id")
        seen.add(item_id)
        if item.get("status") != "active":
            continue
        if not isinstance(item.get("display_name"), str) or not isinstance(item.get("category"), str):
            raise ValueError("active wardrobe item is missing display name or category")
        attributes = item.get("attributes", [])
        if not isinstance(attributes, list) or any(not isinstance(x, str) for x in attributes):
            raise ValueError("wardrobe item attributes must be a list of strings")
        # The evaluator receives only canonical tags and keyed garment tokens.
        active.append({
            "item_id": item_id,
            "display_name": item["display_name"],
            "category": item["category"],
            "attributes": attributes,
        })
    return active


def _classify_items(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    classified: dict[str, list[dict[str, Any]]] = {
        "top": [], "bottom": [], "one_piece": [], "footwear": [],
        "outerwear": [], "accessory": [],
    }
    for item in items:
        kind = _kind(item)
        if kind:
            classified[kind].append(item)
    return classified


def _base_candidates(classified: dict[str, list[dict[str, Any]]], limit: int = 500) -> tuple[list[list[dict[str, Any]]], bool]:
    candidates: list[list[dict[str, Any]]] = []
    truncated = False
    for item in classified["one_piece"]:
        if len(candidates) >= limit:
            truncated = True
            break
        candidates.append([item])
    if not truncated:
        for top in classified["top"]:
            for bottom in classified["bottom"]:
                if len(candidates) >= limit:
                    truncated = True
                    break
                candidates.append([top, bottom])
            if truncated:
                break
    return candidates, truncated


def _add_optional_item(
    candidate: list[dict[str, Any]],
    classified: dict[str, list[dict[str, Any]]],
    *,
    role: str,
    user_id: str,
    local_date: str,
    style_signals: tuple[str, ...],
    feedback_signals: tuple[str, ...],
    occasion: str | None,
    climate: str | None,
) -> list[dict[str, Any]]:
    """Mirror the live composer's single safe complementary-item step."""
    chosen = list(candidate)
    used = {item["item_id"] for item in chosen}
    optional_candidates: list[dict[str, Any]] = []
    for kind in ("footwear", "outerwear", "accessory"):
        pool = [item for item in classified[kind] if item["item_id"] not in used]
        if pool:
            optional_candidates.append(max(
                pool,
                key=lambda item: (
                    _score([item], role, style_signals, feedback_signals, occasion, climate),
                    _stable_tie(user_id, local_date, role, [item["item_id"]]),
                ),
            ))
    if optional_candidates:
        optional = max(
            optional_candidates,
            key=lambda item: (
                _score([item], role, style_signals, feedback_signals, occasion, climate),
                _stable_tie(user_id, local_date, role, [item["item_id"]]),
            ),
        )
        chosen.append(optional)
    return chosen


def _trace_token(secret: str, namespace: str, value: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        (namespace + "|" + value).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return namespace + "_" + digest


def _safe_attribute_tags(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    style: set[str] = set()
    colors: set[str] = set()
    occasions: set[str] = set()
    prefixes = ("style", "aesthetic", "silhouette", "pattern", "color", "colour", "occasion")
    for item in items:
        for raw in item.get("attributes", []):
            raw_value = str(raw).strip().casefold()
            key, separator, tagged_value = raw_value.partition(":")
            if not separator:
                for prefix in prefixes:
                    if raw_value.startswith(prefix + " "):
                        key, tagged_value, separator = prefix, raw_value[len(prefix) + 1:], " "
                        break
            if separator:
                tag = re.sub(r"[^a-z0-9_-]", "", _normalise(tagged_value).replace(" ", "_"))[:40]
                if not tag:
                    continue
                if key in {"style", "aesthetic", "silhouette", "pattern"}:
                    style.add(tag)
                elif key in {"color", "colour"}:
                    colors.add(tag)
                elif key == "occasion":
                    occasions.add(tag)
            else:
                safe = re.sub(r"[^a-z0-9_-]", "", _normalise(raw_value).replace(" ", "_"))[:40]
                if safe in _EVALUATION_STYLE_WORDS:
                    style.add(safe)
                if safe in _EVALUATION_COLOR_WORDS:
                    colors.add(safe)
                if safe in _EVALUATION_OCCASION_WORDS:
                    occasions.add(safe)
    return {
        "style_tags": sorted(style),
        "color_tags": sorted(colors),
        "occasion_tags": sorted(occasions),
    }


def _preferred_trace_tags(style_signals: tuple[str, ...]) -> tuple[list[str], list[str]]:
    styles: set[str] = set()
    colors: set[str] = set()
    prefixes = ("style", "aesthetic", "silhouette", "pattern", "color", "colour")
    for raw in style_signals:
        raw_value = str(raw).strip().casefold()
        key, separator, tagged_value = raw_value.partition(":")
        if not separator:
            for prefix in prefixes:
                if raw_value.startswith(prefix + " "):
                    key, tagged_value, separator = prefix, raw_value[len(prefix) + 1:], " "
                    break
        if not separator:
            continue
        normalized = re.sub(r"[^a-z0-9_-]", "", _normalise(tagged_value).replace(" ", "_"))[:40]
        if not normalized:
            continue
        if key in {"style", "aesthetic", "silhouette", "pattern"}:
            styles.add(normalized)
        elif key in {"color", "colour"}:
            colors.add(normalized)
    return sorted(styles), sorted(colors)


def _evaluation_candidate(
    items: list[dict[str, Any]],
    *,
    secret: str,
) -> dict[str, Any]:
    raw_ids = sorted({item["item_id"] for item in items})
    garment_ids = sorted(_trace_token(secret, "garment", item_id) for item_id in raw_ids)
    look_id = _trace_token(secret, "look", "|".join(garment_ids))
    tags = _safe_attribute_tags(items)
    categories = sorted({kind for item in items if (kind := _kind(item))})
    return {
        "look_id": look_id,
        "garment_ids": garment_ids,
        "category_tags": categories,
        "style_tags": tags["style_tags"],
        "color_tags": tags["color_tags"],
        "occasion_tags": tags["occasion_tags"],
        "exclusion_tags": [],
    }


def _build_evaluation_trace(
    *,
    request_id: str,
    user_id: str,
    local_date: str,
    eligible_items: list[dict[str, Any]],
    evaluation_items: list[dict[str, Any]],
    excluded_item_ids: set[str],
    occasion: str | None,
    climate: str | None,
    style_signals: tuple[str, ...],
    feedback_signals: tuple[str, ...],
    secret: str,
) -> dict[str, Any]:
    """Create pseudonymous, role-specific candidate/ranking cases for offline review."""
    eligible_classified = _classify_items(eligible_items)
    full_classified = _classify_items(evaluation_items)
    eligible_candidates, eligible_truncated = _base_candidates(eligible_classified)
    full_candidates, full_truncated = _base_candidates(full_classified)
    rotation_seen = tuple(rotation_seen_item_ids)
    rotation_seen_set = {value for value in rotation_seen if isinstance(value, str)}
    wear_by_id = {entry.get("item_id"): entry for entry in (wear_history or []) if isinstance(entry, dict)}
    selected_base: set[frozenset[str]] = set()
    selected_item_ids: set[str] = set()
    cases: list[dict[str, Any]] = []
    no_result_roles: list[str] = []
    rankings_by_role: dict[str, list[dict[str, Any]]] = {}
    blocked_by_role: dict[str, list[str]] = {}

    for role in ROLES:
        eligible_available = [
            candidate for candidate in eligible_candidates
            if frozenset(item["item_id"] for item in candidate) not in selected_base
        ]
        full_available = [
            candidate for candidate in full_candidates
            if frozenset(item["item_id"] for item in candidate) not in selected_base
        ]

        def rank_key(candidate: list[dict[str, Any]]) -> tuple[int, int, str]:
            ids = {item["item_id"] for item in candidate}
            return (
                _score(candidate, role, style_signals, feedback_signals, occasion, climate),
                -len(ids & selected_item_ids),
                _stable_tie(user_id, local_date, role, ids),
            )

        candidate_docs: dict[str, dict[str, Any]] = {}
        candidate_raw_ids: dict[str, set[str]] = {}
        for base_candidate in full_available:
            complete = _add_optional_item(
                base_candidate, eligible_classified, role=role, user_id=user_id,
                local_date=local_date, style_signals=style_signals,
                feedback_signals=feedback_signals, occasion=occasion, climate=climate,
            )
            document = _evaluation_candidate(complete, secret=secret)
            candidate_docs[document["look_id"]] = document
            candidate_raw_ids[document["look_id"]] = {item["item_id"] for item in base_candidate}

        ranked = sorted(eligible_available, key=rank_key, reverse=True)
        ranking_rows: list[dict[str, Any]] = []
        ranked_ids: list[str] = []
        for index, base_candidate in enumerate(ranked, start=1):
            complete = _add_optional_item(
                base_candidate, eligible_classified, role=role, user_id=user_id,
                local_date=local_date, style_signals=style_signals,
                feedback_signals=feedback_signals, occasion=occasion, climate=climate,
            )
            document = _evaluation_candidate(complete, secret=secret)
            candidate_docs.setdefault(document["look_id"], document)
            ranked_ids.append(document["look_id"])
            ranking_rows.append({
                "look_id": document["look_id"],
                "rank": index,
                "score": rank_key(base_candidate)[0],
            })

        blocked_ids = sorted(
            look_id for look_id, raw_ids in candidate_raw_ids.items()
            if raw_ids & excluded_item_ids
        )
        style_tags, color_tags = _preferred_trace_tags(style_signals)
        case_id = _trace_token(secret, "case", request_id + "|" + role)
        if ranked_ids and candidate_docs:
            cases.append({
                "schema_version": "1.0",
            "case_id": case_id,
            "participant_key": _trace_token(secret, "participant", user_id),
            "session_id": _trace_token(secret, "session", request_id),
            "assigned_system": "cirvanna",
                "context": {
                    "role": role,
                "required_categories": [],
                "preferred_style_tags": style_tags,
                "preferred_color_tags": color_tags,
                "occasion": occasion,
                "climate": climate,
                "hard_excluded_item_ids": sorted(
                    _trace_token(secret, "garment", item_id) for item_id in excluded_item_ids
                ),
                "hard_excluded_tags": [],
            },
                "candidate_outfits": [candidate_docs[key] for key in sorted(candidate_docs)],
                "cirvanna_ranked_look_ids": ranked_ids,
                "human_reviews": [],
                "adjudications": [],
                "exposures": [],
            })
        else:
            no_result_roles.append(role)
        rankings_by_role[role] = ranking_rows
        blocked_by_role[role] = blocked_ids

        if ranked:
            selected = ranked[0]
            selected_base.add(frozenset(item["item_id"] for item in selected))
            complete_selected = _add_optional_item(
                selected, eligible_classified, role=role, user_id=user_id,
                local_date=local_date, style_signals=style_signals,
                feedback_signals=feedback_signals, occasion=occasion, climate=climate,
            )
            selected_item_ids.update(item["item_id"] for item in complete_selected)

    return {
        "trace_version": "1.0",
        "policy_version": POLICY_VERSION,
        "participant_key": _trace_token(secret, "participant", user_id),
        "session_id": _trace_token(secret, "session", request_id),
        "candidate_pool_limit": 500,
        "candidate_pool_truncated": bool(eligible_truncated or full_truncated),
        "candidate_pool_source": "owner_scoped_active_wardrobe_metadata",
        "ranking_trace_by_role": rankings_by_role,
        "hard_excluded_candidate_ids_by_role": blocked_by_role,
        "no_result_roles": no_result_roles,
        "cases": cases,
        "human_review_state": "awaiting_two_independent_reviewers_per_candidate",
        "user_exposure_state": "not_collected_by_composer",
        "assignment_policy": "cirvanna_only_live_arm",
        "baseline_comparison": "offline_replay_on_identical_candidate_pool",
        "consent": {
            "required": True,
            "validated_by_gateway": True,
            "scope": "style_learning_or_personalization",
        },
        "privacy": {
            "raw_user_id_included": False,
            "raw_wardrobe_item_ids_included": False,
            "display_names_included": False,
            "image_assets_included": False,
            "pseudonyms_are_stable_within_study_key": True,
        },
    }


def _context_terms(value: str | None, mapping: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    if not isinstance(value, str) or not value.strip():
        return ()
    normalized = _normalise(value)
    for key, terms in mapping.items():
        if normalized == key or key in normalized:
            return terms
    return ()


def _score(
    items: list[dict[str, Any]],
    role: str,
    style_signals: tuple[str, ...],
    feedback_signals: tuple[str, ...],
    occasion: str | None = None,
    climate: str | None = None,
) -> int:
    text = " ".join(_item_text(item) for item in items)
    score = sum(3 for term in _ROLE_TERMS[role] if term in text)

    # Only explicit occasion/climate values and item metadata are used. These
    # are transparent ranking hints, not weather forecasts or fit predictions.
    occasion_terms = _context_terms(occasion, _OCCASION_TERMS)
    score += sum(5 for term in occasion_terms if term in text)

    climate_key = _normalise(climate or "").replace(" ", "_")
    climate_rules = _CLIMATE_TERMS.get(climate_key, {"positive": (), "negative": ()})
    score += sum(3 for term in climate_rules["positive"] if term in text)
    score -= sum(3 for term in climate_rules["negative"] if term in text)

    # USI attributes are explicit positive fashion preference strings; they
    # are ranking hints only and never inferred traits or hard exclusions.
    style_matches = sum(2 for signal in style_signals if signal and signal.split(":", 1)[-1] in text)
    feedback_matches = sum(1 for signal in feedback_signals if signal and signal.split(":", 1)[-1] in text)
    # Keep learned feedback advisory and bounded so a noisy event history
    # cannot overwhelm the declared day context or hard policy boundaries.
    score += min(8, style_matches) + min(4, feedback_matches)
    return score



def _explain_selection(
    items: list[dict[str, Any]],
    role: str,
    occasion: str | None,
    climate: str | None,
    style_signals: tuple[str, ...],
    feedback_signals: tuple[str, ...],
) -> str:
    """Explain only the explicit context and item metadata that matched."""
    text = " ".join(_item_text(item) for item in items)
    parts = [{
        "everyday": "A practical combination assembled from active items in your wardrobe.",
        "elevated": "A more polished combination assembled from active items in your wardrobe.",
        "explore": "A distinct alternative assembled from active items in your wardrobe.",
    }[role]]

    occasion_terms = _context_terms(occasion, _OCCASION_TERMS)
    occasion_matches = [term for term in occasion_terms if term in text]
    if occasion and occasion_matches:
        parts.append(
            f"Matched your declared occasion ({occasion}) through wardrobe tags: "
            + ", ".join(occasion_matches[:4]) + "."
        )

    climate_key = _normalise(climate or "").replace(" ", "_")
    climate_rules = _CLIMATE_TERMS.get(climate_key, {"positive": (), "negative": ()})
    climate_matches = [term for term in climate_rules["positive"] if term in text]
    if climate and climate_matches:
        parts.append(
            f"Matched your declared climate ({climate.replace('_', ' ')}) through wardrobe tags: "
            + ", ".join(climate_matches[:4]) + "."
        )

    saved_matches = [
        signal.split(":", 1)[-1]
        for signal in style_signals
        if signal and signal.split(":", 1)[-1] in text
    ]
    if saved_matches:
        parts.append("Reflects your saved style preferences: " + ", ".join(saved_matches[:4]) + ".")

    feedback_matches = [
        signal.split(":", 1)[-1]
        for signal in feedback_signals
        if signal and signal.split(":", 1)[-1] in text
    ]
    if feedback_matches:
        parts.append(
            "Reflects attributes from your consented like/wear feedback: "
            + ", ".join(feedback_matches[:4]) + "."
        )

    return " ".join(parts)

def build_daily_looks(
    *,
    request_id: str,
    user_id: str,
    wardrobe_items: list[dict[str, Any]],
    local_date: str,
    occasion: str | None = None,
    climate: str | None = None,
    style_signals: Iterable[str] = (),
    feedback_signals: Iterable[str] = (),
    evaluation_wardrobe_items: list[dict[str, Any]] | None = None,
    hard_excluded_item_ids: Iterable[str] = (),
    evaluation_trace_enabled: bool = False,
    evaluation_secret: str | None = None,
    rotation_seen_item_ids: Iterable[str] = (),
    rotation_cycle_started_at: str | None = None,
    rotation_cycle_number: int = 1,
    wear_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build exactly three distinct look roles from verified wardrobe records."""
    if not request_id.strip() or not user_id.strip():
        raise ValueError("request_id and user_id are required")
    if len(wardrobe_items) > 150:
        raise ValueError("wardrobe snapshot exceeds 150 items")

    if evaluation_wardrobe_items is not None and len(evaluation_wardrobe_items) > 150:
        raise ValueError("evaluation wardrobe snapshot must not exceed 150 items")
    active = _normalise_active_items(wardrobe_items, user_id)
    evaluation_source = evaluation_wardrobe_items if evaluation_wardrobe_items is not None else wardrobe_items
    evaluation_active = _normalise_active_items(evaluation_source, user_id) if evaluation_trace_enabled else active
    if evaluation_trace_enabled and (not isinstance(evaluation_secret, str) or len(evaluation_secret.encode("utf-8")) < 32):
        raise ValueError("evaluation trace requires a 32-byte pseudonymization secret")
    excluded_ids = {value.strip() for value in hard_excluded_item_ids if isinstance(value, str) and value.strip()}
    active = [item for item in active if item["item_id"] not in excluded_ids]
    classified = _classify_items(active)
    candidates, _ = _base_candidates(classified)

    signals = tuple(_normalise(value) for value in style_signals if isinstance(value, str) and value.strip())[:40]
    feedback = tuple(_normalise(value) for value in feedback_signals if isinstance(value, str) and value.strip())[:40]
    selected_base: set[frozenset[str]] = set()
    selected_item_ids: set[str] = set()
    looks: list[dict[str, Any]] = []
    context = {
        "occasion": occasion.strip() if isinstance(occasion, str) and occasion.strip() else None,
        "climate": climate.strip() if isinstance(climate, str) and climate.strip() else None,
    }

    for role in ROLES:
        available = [candidate for candidate in candidates
                     if frozenset(x["item_id"] for x in candidate) not in selected_base]
        if not available:
            missing = (
                ["a top and a bottom, or a one-piece outfit"]
                if not candidates else ["additional wardrobe pieces for a distinct outfit"]
            )
            looks.append({
                "role": role,
                "status": "needs_input",
                "item_ids": [],
                "items": [],
                "missing": missing,
                "reason": "There are not enough distinct complete outfit combinations in the active wardrobe yet.",
                "virtual_twin_preview": {
                    "status": "unavailable",
                    "reason_code": "PERSISTENT_TWIN_AND_VALIDATED_RENDERER_NOT_READY",
                },
            })
            continue

        candidate = max(
            available,
            key=lambda group: (
                -sum(1 for item in group if item["item_id"] in rotation_seen_set),
                _score(group, role, signals, feedback, occasion, climate),
                -sum((wear_by_id.get(item["item_id"]) or {}).get("wear_count", 0) for item in group),
                -sum(1 for item in group if (wear_by_id.get(item["item_id"]) or {}).get("last_worn_at")),
                -sum(len(set(x["item_id"] for x in group) & selected_item_ids) for _ in (0,)),
                _stable_tie(user_id, local_date, role, (x["item_id"] for x in group)),
            ),
        )
        base_ids = frozenset(x["item_id"] for x in candidate)
        selected_base.add(base_ids)
        chosen = list(candidate)
        used = {x["item_id"] for x in chosen}

        # Footwear is helpful but not required; add at most one safe complement.
        chosen = _add_optional_item(
            candidate, classified, role=role, user_id=user_id, local_date=local_date,
            style_signals=signals, feedback_signals=feedback, occasion=occasion, climate=climate,
        )
        used = {item["item_id"] for item in chosen}

        selected_item_ids.update(used)
        looks.append({
            "role": role,
            "status": "ready",
            "item_ids": [x["item_id"] for x in chosen],
            "items": chosen,
            "missing": [],
            "reason": _explain_selection(
                chosen, role, occasion, climate, signals, feedback
            ),
            "context": context,
            "virtual_twin_preview": {
                "status": "unavailable",
                "reason_code": "PERSISTENT_TWIN_AND_VALIDATED_RENDERER_NOT_READY",
            },
        })

    ready_count = sum(look["status"] == "ready" for look in looks)
    surfaced_today = sorted({item_id for look in looks if look["status"] == "ready" for item_id in look["item_ids"]})
    rotation = build_rotation_state(items=active, local_date=local_date, seen_item_ids=rotation_seen, cycle_started_at=rotation_cycle_started_at, cycle_number=rotation_cycle_number, wear_history=wear_history, surfaced_item_ids=surfaced_today)
    output = {
        "schema_version": "1.0",
        "policy_version": POLICY_VERSION,
        "request_id": request_id,
        "capability": "pnelly_daily_looks",
        "status": "ready" if ready_count == 3 else ("partial" if ready_count else "needs_input"),
        "look_count": 3,
        "ready_count": ready_count,
        "looks": looks,
        "wardrobe_rotation": rotation,
        "personalization": {
            "style_signals_used": bool(signals),
            "style_signal_count": len(signals),
            "style_source": "consented_usi_profile" if signals else "no_profile_signals_used",
            "feedback_signals_used": bool(feedback),
            "feedback_signal_count": len(feedback),
            "feedback_source": "consented_wardrobe_feedback" if feedback else "no_active_consent_feedback_signals",
            "durable_learning_performed": False,
        },
        "limits": [
            "Looks use only active, owner-scoped wardrobe item records.",
            "The three roles are distinct outfit combinations, not a fit or purchase guarantee.",
            "No body, face, culture, gender, religion or modesty attribute is inferred.",
            "Virtual Twin preview is unavailable until persistent Twin ownership, consent and a validated renderer are integrated.",
            "Marketplace candidates, prices, stock and product-display authorization are not part of this response.",
        ],
    }
    if evaluation_trace_enabled:
        output["evaluation_trace"] = _build_evaluation_trace(
            request_id=request_id,
            user_id=user_id,
            local_date=local_date,
            eligible_items=active,
            evaluation_items=evaluation_active,
            excluded_item_ids=excluded_ids,
            occasion=occasion,
            climate=climate,
            style_signals=signals,
            feedback_signals=feedback,
            secret=evaluation_secret or "",
        )
    return output
