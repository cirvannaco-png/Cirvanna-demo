"""
Dialogue orchestration with multi-tier explanations and emotional modulation.
"""
import time
import random
from datetime import datetime
from .memory import DialogueMemoryManager
from .explanation import ExplanationGenerator
from .emotional_modulator import EmotionalModulator
from .nlp_processor import NLPProcessor

class DialogueOrchestrator:
    def __init__(self, config, cache):
        self.config = config
        self.cache = cache
        self.memory_manager = DialogueMemoryManager(config)
        self.explanation_generator = ExplanationGenerator()
        self.emotional_modulator = EmotionalModulator()
        self.nlp_processor = NLPProcessor()
        self.templates = self._load_templates()

    def _load_templates(self):
        return {
            "recommendation": {
                "summary": "Based on your {skin_type} skin, I recommend {product_name}. {reason}",
                "detailed": "Your recent metrics show {metric_trend}. {product_name} can help because {detailed_reason}",
                "scientific": "Analysis of {ingredient_list} shows {scientific_evidence}. Clinical studies indicate {clinical_findings}"
            },
            "explanation": {
                "summary": "This works because {simple_reason}",
                "detailed": "The mechanism involves {mechanism_details}. Key ingredients include {key_ingredients}",
                "scientific": "Research indicates {research_summary}. The biochemical pathway is {biochemical_pathway}"
            },
            "clarification": {
                "summary": "Could you clarify {aspect}?",
                "detailed": "To provide better advice, I need more details about {specific_aspect}"
            }
        }

    async def generate_response(self, user_id, query, context,
                                recommendations=None,
                                face_results=None,
                                body_results=None,
                                user_embedding=None):
        start_time = time.perf_counter()
        intent_result = await self.nlp_processor.parse_intent(query)
        intent = intent_result.get("intent", "general")
        confidence = intent_result.get("confidence", 0.5)
        history = await self.memory_manager.get_dialogue_history(user_id)
        tier = self._determine_tier(user_id, intent, confidence, history, user_embedding)

        # Build extra context for templates
        extra = {}
        if face_results:
            extra.update({
                "face_suitability": face_results.get("illumination_metrics", {}),
                "makeup_zones": face_results.get("face_analysis", {}).get("makeup_zones", {})
            })
        if body_results:
            recs = body_results.get("recommendations", {})
            extra.update({
                "body_measurements": recs.get("measurements", {}),
                "recommended_size": recs.get("recommended_size", "unknown")
            })

        explanation = self.explanation_generator.generate(
            recommendations=recommendations or [],
            tier=tier,
            context=context,
            extra=extra
        )
        modulated = self.emotional_modulator.modulate(
            explanation,
            user_mood=self._detect_mood(query, history),
            context=context,
            user_embedding=user_embedding
        )
        dialogue = self._assemble_dialogue(
            intent=intent,
            tier=tier,
            explanation=modulated,
            recommendations=recommendations[:3] if recommendations else [],
            context=context
        )
        await self.memory_manager.store_interaction(
            user_id=user_id,
            query=query,
            response=dialogue,
            tier=tier,
            intent=intent
        )
        elapsed = (time.perf_counter() - start_time) * 1000
        return {
            "dialogue": dialogue,
            "metadata": {
                "tier": tier,
                "intent": intent,
                "confidence": confidence,
                "generation_time_ms": elapsed,
                "history_length": len(history),
                "emotional_tone": modulated.get("tone", "neutral")
            },
            "recommendations": recommendations[:3] if recommendations else []
        }

    def _determine_tier(self, user_id, intent, confidence, history, user_embedding=None):
        tier = "summary"
        if history:
            recent_tiers = [h.get("tier", "summary") for h in history[-5:]]
            if "scientific" in recent_tiers:
                tier = "scientific"
            elif "detailed" in recent_tiers:
                tier = "detailed"
        if intent == "explanation" and confidence > 0.8:
            tier = "detailed"
        elif intent == "scientific_inquiry":
            tier = "scientific"
        # Personalisation via user embedding (simplified)
        if user_embedding is not None and hasattr(self, 'persona_classifier'):
            persona = self.persona_classifier(user_embedding)
            if persona == "scientific":
                tier = "scientific"
            elif persona == "detailed" and tier == "summary":
                tier = "detailed"
        return tier

    def _detect_mood(self, query, history):
        query_lower = query.lower()
        positive_words = ["great", "good", "happy", "excited", "thanks", "thank you"]
        negative_words = ["bad", "worried", "concerned", "frustrated", "disappointed"]
        if any(word in query_lower for word in positive_words):
            return "positive"
        elif any(word in query_lower for word in negative_words):
            return "concerned"
        return "neutral"

    def _assemble_dialogue(self, intent, tier, explanation, recommendations, context):
        template = self.templates.get(intent, {}).get(tier, "")
        if not template and intent in self.templates:
            template = self.templates[intent].get("summary", "")
        filled_template = template.format(**explanation.get("template_data", {}))
        return {
            "text": filled_template,
            "tone": explanation.get("tone", "neutral"),
            "tier": tier,
            "suggested_followups": self._generate_followups(intent, tier, context),
            "visualization_hint": self._get_visualization_hint(intent, tier),
            "timestamp": datetime.now().isoformat()
        }

    def _generate_followups(self, intent, tier, context):
        followups = []
        if tier != "scientific":
            followups.append("Can you explain that in more detail?")
        if intent == "recommendation":
            followups.append("How does this compare to other options?")
            followups.append("What are the expected results?")
        return followups[:3]

    def _get_visualization_hint(self, intent, tier):
        if tier == "scientific" and intent in ["explanation", "recommendation"]:
            return {
                "type": "biochemical_pathway",
                "suggested": True,
                "complexity": "high"
            }
        return None
