"""User-declared colour preferences for the Cirvanna Style Desk.

This contract deliberately stores preference separately from objective colour
analysis. A user's liked, disliked and "I feel my best in" colours are personal
declarations, not inferred facts about skin tone or colour harmony.
"""
from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from .core import StylePreference, USIProfile

COLOUR_PROFILE_PREFIX = "color_profile:"
COLOUR_PROFILE_GROUPS = ("liked", "disliked", "feel_best")
MAX_COLOURS_PER_GROUP = 24
MAX_COLOUR_LABEL_LENGTH = 60


def _clean_colour(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("colour labels must be strings")
    cleaned = unicodedata.normalize("NFC", value).strip()
    if not cleaned or len(cleaned) > MAX_COLOUR_LABEL_LENGTH:
        raise ValueError("colour labels must contain 1 to 60 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in cleaned):
        raise ValueError("colour labels must not contain control characters")
    return cleaned


def _normal_key(value: str) -> str:
    return _clean_colour(value).casefold()


def _validate_group(values: tuple[str, ...], group: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ValueError(f"{group} must be a tuple")
    if len(values) > MAX_COLOURS_PER_GROUP:
        raise ValueError(f"{group} may contain at most {MAX_COLOURS_PER_GROUP} colours")
    cleaned = tuple(_clean_colour(value) for value in values)
    keys = [_normal_key(value) for value in cleaned]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{group} must not contain duplicate colours")
    return cleaned


@dataclass(frozen=True)
class ColorPreferenceProfile:
    """A versioned, user-owned record of explicitly declared colour preferences."""

    user_id: str
    profile_version: int
    liked_colors: tuple[str, ...] = ()
    disliked_colors: tuple[str, ...] = ()
    feel_best_colors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, str) or not self.user_id.strip():
            raise ValueError("user_id must not be empty")
        if isinstance(self.profile_version, bool) or not isinstance(self.profile_version, int) or self.profile_version < 0:
            raise ValueError("profile_version must be a non-negative integer")
        object.__setattr__(self, "user_id", self.user_id.strip())
        object.__setattr__(self, "liked_colors", _validate_group(self.liked_colors, "liked_colors"))
        object.__setattr__(self, "disliked_colors", _validate_group(self.disliked_colors, "disliked_colors"))
        object.__setattr__(self, "feel_best_colors", _validate_group(self.feel_best_colors, "feel_best_colors"))
        liked = {_normal_key(value) for value in self.liked_colors}
        disliked = {_normal_key(value) for value in self.disliked_colors}
        if liked & disliked:
            raise ValueError("a colour cannot be both liked and disliked")

    @staticmethod
    def _preference_id(group: str, colour: str) -> str:
        digest = hashlib.sha256(_normal_key(colour).encode("utf-8")).hexdigest()[:16]
        return f"color-profile:{group}:{digest}"

    def to_style_preferences(self) -> tuple[StylePreference, ...]:
        """Encode this colour profile as namespaced, explicit USI preferences."""
        records: list[StylePreference] = []
        for group, colours in (
            ("liked", self.liked_colors),
            ("disliked", self.disliked_colors),
            ("feel_best", self.feel_best_colors),
        ):
            for colour in colours:
                records.append(StylePreference(
                    preference_id=self._preference_id(group, colour),
                    user_id=self.user_id,
                    attribute=f"{COLOUR_PROFILE_PREFIX}{group}:{colour}",
                    weight=1.0,
                    # USI scoring is positive-only; dislikes are stored but never score as matches.
                    active=(group != "disliked"),
                ))
        return tuple(records)

    def to_preference_records(self) -> tuple[dict[str, Any], ...]:
        """Return persistence-ready USI preference records."""
        return tuple({
            "preference_id": item.preference_id,
            "attribute": item.attribute,
            "weight": item.weight,
            "active": item.active,
        } for item in self.to_style_preferences())

    @classmethod
    def from_style_preferences(
        cls,
        user_id: str,
        profile_version: int,
        preferences: Iterable[StylePreference | dict[str, Any]],
    ) -> "ColorPreferenceProfile":
        """Read only the colour namespace; leave every other USI preference untouched."""
        groups: dict[str, list[str]] = {name: [] for name in COLOUR_PROFILE_GROUPS}
        for item in preferences:
            if isinstance(item, StylePreference):
                attribute, active, owner = item.attribute, item.active, item.user_id
            elif isinstance(item, dict):
                attribute = item.get("attribute")
                active = item.get("active", True)
                owner = item.get("user_id", user_id)
            else:
                raise ValueError("preferences must be StylePreference values or records")
            if owner != user_id:
                raise ValueError("colour preference belongs to another user")
            if not isinstance(attribute, str) or not attribute.startswith(COLOUR_PROFILE_PREFIX):
                continue
            encoded = attribute[len(COLOUR_PROFILE_PREFIX):]
            group, separator, colour = encoded.partition(":")
            if not separator or group not in groups:
                raise ValueError("invalid colour-profile preference namespace")
            # Dislikes are intentionally inactive in the positive-only USI scorer.
            if active is not True and group != "disliked":
                continue
            if group == "disliked" and active is True:
                raise ValueError("disliked colours must not be active positive USI preferences")
            groups[group].append(_clean_colour(colour))
        return cls(
            user_id=user_id,
            profile_version=profile_version,
            liked_colors=tuple(groups["liked"]),
            disliked_colors=tuple(groups["disliked"]),
            feel_best_colors=tuple(groups["feel_best"]),
        )

    def merge_into_usi_profile(self, profile: USIProfile) -> USIProfile:
        """Replace only this user's colour namespace and preserve every other preference."""
        if profile.user_id != self.user_id:
            raise ValueError("colour profile user does not match USI profile owner")
        retained = tuple(
            item for item in profile.preferences
            if not item.attribute.startswith(COLOUR_PROFILE_PREFIX)
        )
        merged = retained + self.to_style_preferences()
        return USIProfile(
            profile_id=profile.profile_id,
            user_id=profile.user_id,
            version=profile.version,
            preferences=merged,
        )
