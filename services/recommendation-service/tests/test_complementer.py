from app.complementer import compose_complementary_look


def payload():
    return {
        "request_id": "req-1",
        "user_id": "user-1",
        "preferences": {
            "aesthetics": ["minimalist"],
            "favorite_colors": ["teal", "coral"],
            "avoid_colors": ["coral"],
            "favorite_fragrance_families": ["citrus", "woody"],
            "fragrance_sensitive": False,
            "fragrance_free": False,
            "fragrance_intensity": None,
            "earrings_preference": "yes",
            "preferred_earring_shapes": ["huggie"],
            "preferred_metals": ["gold"],
        },
        "look": {
            "outfit_colors": ["navy"], "neckline": "off_shoulder",
            "hairstyle": "up", "climate": "hot_humid", "occasion": "evening",
        },
    }


def test_favourite_colors_win_and_exclusions_are_removed():
    result = compose_complementary_look(payload())
    assert result["palette"]["base_colors"] == ["navy"]
    assert result["palette"]["accent_colors"] == ["teal"]
    assert "coral" not in result["palette"]["accent_colors"]


def test_fragrance_sensitivity_overrides_scent_preferences():
    request = payload()
    request["preferences"]["fragrance_sensitive"] = True
    result = compose_complementary_look(request)
    assert result["fragrance"]["status"] == "fragrance_free"
    assert result["fragrance"]["families"] == []
    assert result["fragrance"]["intensity"] == "none"


def test_declared_scent_preferences_are_kept_and_hot_humid_defaults_light():
    result = compose_complementary_look(payload())
    assert result["fragrance"]["families"] == ["citrus", "woody"]
    assert result["fragrance"]["intensity"] == "light"


def test_no_earrings_preference_is_respected():
    request = payload()
    request["preferences"]["earrings_preference"] = "avoid"
    result = compose_complementary_look(request)
    assert result["earrings"]["status"] == "omitted_by_preference"
    assert result["earrings"]["shape"] is None


def test_user_earring_shape_and_metal_override_context():
    result = compose_complementary_look(payload())
    assert result["earrings"]["shape"] == "huggie"
    assert result["earrings"]["metal"] == "gold"


def test_missing_preferences_are_requested_not_invented():
    request = payload()
    request["preferences"] = {
        "aesthetics": [], "favorite_colors": [], "avoid_colors": [],
        "favorite_fragrance_families": [], "fragrance_sensitive": False,
        "fragrance_free": False, "fragrance_intensity": None,
        "earrings_preference": "no_preference", "preferred_earring_shapes": [],
        "preferred_metals": [],
    }
    request["look"]["outfit_colors"] = ["unlisted-colour"]
    result = compose_complementary_look(request)
    assert result["status"] == "needs_input"
    assert result["fragrance"]["status"] == "needs_input"
    assert result["aesthetic"]["status"] == "needs_input"


def test_result_is_deterministic_and_stateless():
    first = compose_complementary_look(payload())
    assert first == compose_complementary_look(payload())
    assert first["persistence"] == "stateless_request_only"
    assert first["limits"][-1].startswith("Specific catalog products")
