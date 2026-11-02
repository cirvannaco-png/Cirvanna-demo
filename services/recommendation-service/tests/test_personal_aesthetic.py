from app.personal_aesthetic import compose_personal_aesthetic


def payload():
    return {
        "request_id": "req-v2",
        "user_id": "user-1",
        "preferences": {
            "aesthetics": ["elegant"],
            "favorite_colors": ["emerald", "cream"],
            "avoid_colors": ["neon pink"],
            "favorite_fragrance_families": ["woody", "citrus"],
            "preferred_scent_notes": ["cedar", "bergamot"],
            "fragrance_sensitive": False,
            "fragrance_free": False,
            "fragrance_intensity": "light",
            "fragrance_projection": "intimate",
            "fragrance_longevity": "moderate",
            "fragrance_budget_minor": 750000,
            "fragrance_budget_currency": "KES",
            "earrings_preference": "yes",
            "preferred_earring_shapes": ["huggie"],
            "preferred_metals": ["gold"],
            "necklace_preference": "yes",
            "preferred_necklace_shapes": [],
            "glasses_preference": "no_preference",
            "preferred_frame_shapes": ["soft-square"],
            "preferred_finishing_accessories": ["watch"],
            "preferred_makeup_colors": ["rosewood", "bronze"],
            "self_described_undertone": None,
            "self_described_face_shape": None,
            "user_declared_cultural_style_tags": [],
        },
        "look": {
            "outfit_colors": ["emerald"],
            "neckline": "v_neck",
            "hairstyle": "up",
            "climate": "hot_humid",
            "occasion": "evening",
            "signature_items": ["silver heirloom ring"],
        },
    }


def test_v2_combines_fragrance_budget_colour_jewellery_and_style():
    result = compose_personal_aesthetic(payload())
    assert result["fragrance"]["preferred_notes"] == ["cedar", "bergamot"]
    assert result["fragrance"]["budget"] == {"amount_minor": 750000, "currency": "KES"}
    assert result["colour_intelligence"]["makeup"]["colours"] == ["rosewood", "bronze"]
    assert result["jewellery"]["earrings"]["shape"] == "huggie"
    assert result["jewellery"]["necklace"]["shape"] == "pendant or lariat"
    assert result["aesthetic"]["status"] == "ready"
    assert result["aesthetic"]["direction"].startswith("Elegant")
    assert result["look_completion"]["strategy"] == "minimal_change"
    assert result["look_completion"]["preserve"]["existing_signature_items"] == ["silver heirloom ring"]
    assert result["status"] == "ready"


def test_explicit_no_jewellery_and_no_glasses_are_respected():
    request = payload()
    request["preferences"]["earrings_preference"] = "avoid"
    request["preferences"]["necklace_preference"] = "avoid"
    request["preferences"]["glasses_preference"] = "avoid"
    result = compose_personal_aesthetic(request)
    assert result["jewellery"]["earrings"]["status"] == "omitted_by_preference"
    assert result["jewellery"]["necklace"]["status"] == "omitted_by_preference"
    assert result["jewellery"]["glasses"]["status"] == "omitted_by_preference"


def test_cultural_style_requires_user_selected_reference():
    request = payload()
    request["preferences"]["aesthetics"] = ["cultural"]
    request["preferences"]["user_declared_cultural_style_tags"] = []
    result = compose_personal_aesthetic(request)
    assert result["aesthetic"]["status"] == "needs_input"
    assert result["aesthetic"]["cultural_context_used"] is False
    request["preferences"]["user_declared_cultural_style_tags"] = ["beadwork", "kikuyu-inspired textile motifs"]
    result = compose_personal_aesthetic(request)
    assert result["aesthetic"]["status"] == "ready"
    assert result["aesthetic"]["cultural_context_used"] is True
    assert "references you selected" in result["aesthetic"]["reason"]


def test_identity_preserving_completion_does_not_replace_silhouette_or_signature():
    result = compose_personal_aesthetic(payload())
    assert result["look_completion"]["strategy"] == "minimal_change"
    assert result["look_completion"]["preserve"]["silhouette"] == "preserve_unless_user_requests_change"
    assert result["look_completion"]["preserve"]["existing_signature_items"] == ["silver heirloom ring"]


def test_fragrance_sensitive_profile_abstains_even_with_family_preferences():
    request = payload()
    request["preferences"]["fragrance_sensitive"] = True
    result = compose_personal_aesthetic(request)
    assert result["fragrance"]["status"] == "fragrance_free"
    assert result["fragrance"]["families"] == []
    assert result["fragrance"]["preferred_notes"] == ["cedar", "bergamot"]
    assert result["fragrance"]["direction"] == "Skip perfume and keep the look fragrance-free."
