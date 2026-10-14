"""
Multi-tier explanation generator.
"""
class ExplanationGenerator:
    def generate(self, recommendations, tier, context, extra=None):
        if not recommendations:
            return {"text": "I don't have enough information to make recommendations.", "tier": tier}
        primary_rec = recommendations[0]
        explanation_data = {
            "product_name": primary_rec.get("product", {}).get("name", "this product"),
            "reason": "it matches your skin profile well",
            "metric_trend": "consistent improvement in hydration",
            "detailed_reason": "the ingredients work synergistically to improve barrier function",
            "ingredient_list": ", ".join(primary_rec.get("product", {}).get("ingredients", [])[:3]),
            "simple_reason": "it addresses your specific skin concerns effectively"
        }
        if extra:
            explanation_data.update(extra)
        if tier == "detailed":
            explanation_data.update({
                "mechanism_details": "hydration retention through humectant action",
                "key_ingredients": "hyaluronic acid and ceramides"
            })
        elif tier == "scientific":
            explanation_data.update({
                "scientific_evidence": "significant improvement in TEWL values",
                "clinical_findings": "85% of participants showed improvement",
                "research_summary": "peer-reviewed studies support the efficacy",
                "biochemical_pathway": "enhances natural moisturizing factor production"
            })
        return {
            "template_data": explanation_data,
            "tier": tier,
            "confidence": 0.8,
            "sources": self._get_sources(tier)
        }

    def _get_sources(self, tier):
        if tier == "scientific":
            return ["Clinical Dermatology, 2023", "Journal of Cosmetic Science, 2022"]
        return []
