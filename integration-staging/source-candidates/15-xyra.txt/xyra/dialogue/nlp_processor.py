"""
Natural language processing for intent parsing.
"""
import spacy

class NLPProcessor:
    def __init__(self):
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except:
            self.nlp = None

    async def parse_intent(self, query):
        if self.nlp:
            return self._parse_with_spacy(query)
        else:
            return self._parse_with_keywords(query)

    def _parse_with_spacy(self, query):
        doc = self.nlp(query.lower())
        intents = {
            "recommendation": ["recommend", "suggest", "should i use", "what product"],
            "explanation": ["why", "how does", "explain", "what is"],
            "comparison": ["compare", "difference", "versus", "vs", "better"],
            "scientific_inquiry": ["study", "research", "evidence", "clinical", "scientific"]
        }
        for intent, keywords in intents.items():
            if any(keyword in query.lower() for keyword in keywords):
                return {"intent": intent, "confidence": 0.9}
        if any(token.text in ["what", "how", "why", "when"] for token in doc):
            return {"intent": "general_inquiry", "confidence": 0.7}
        return {"intent": "general", "confidence": 0.5}

    def _parse_with_keywords(self, query):
        query_lower = query.lower()
        if any(word in query_lower for word in ["recommend", "suggest", "what should i"]):
            return {"intent": "recommendation", "confidence": 0.8}
        elif any(word in query_lower for word in ["why", "how does", "explain"]):
            return {"intent": "explanation", "confidence": 0.85}
        elif any(word in query_lower for word in ["compare", "difference", "vs"]):
            return {"intent": "comparison", "confidence": 0.9}
        return {"intent": "general", "confidence": 0.5}
