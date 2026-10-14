"""
Emotional modulation of dialogue.
"""
import random
import numpy as np

class EmotionalModulator:
    def __init__(self):
        # Placeholder for a learned model; in production, load a BERT-tiny model.
        pass

    def modulate(self, explanation, user_mood, context, user_embedding=None):
        base_tone = "professional"
        if user_mood == "positive":
            tone = "encouraging"
            modifiers = ["Great news!", "You're making excellent progress.", "Keep up the good work!"]
        elif user_mood == "concerned":
            tone = "reassuring"
            modifiers = ["Don't worry,", "This is normal and manageable,", "Let me help you address this,"]
        else:
            tone = "neutral"
            modifiers = [""]
        # Personalise based on user embedding (simplified)
        if user_embedding is not None:
            # Example: if user embedding has high 'science' component, use scientific tone even if mood is neutral
            if np.mean(user_embedding) > 0.5:
                tone = "scientific"
        modifier = random.choice(modifiers) if modifiers else ""
        return {
            **explanation,
            "tone": tone,
            "modifier": modifier,
            "empathetic": user_mood in ["concerned", "frustrated"]
        }
