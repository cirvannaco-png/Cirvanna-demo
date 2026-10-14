"""
Doctrine compliance checking
"""

from typing import Dict, Any, Tuple, List


class ImmutableDoctrine:
    """Immutable decision doctrine"""
    
    def __init__(self):
        self.rules = {
            "min_confidence": 0.3,
            "max_risk": 0.8,
            "required_fields": ["action", "rationale"],
            "banned_actions": ["harm", "exploit", "deceive"],
            "ethical_constraints": [
                "respect_autonomy",
                "do_no_harm",
                "fairness",
                "transparency"
            ]
        }
    
    def check_compliance(self, option: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Check option compliance with doctrine"""
        violations = []
        
        # Check confidence
        if option.get("confidence", 0) < self.rules["min_confidence"]:
            violations.append("confidence_too_low")
        
        # Check risk
        if option.get("risk_score", 1.0) > self.rules["max_risk"]:
            violations.append("risk_too_high")
        
        # Check required fields
        for field in self.rules["required_fields"]:
            if field not in option:
                violations.append(f"missing_field_{field}")
        
        # Check banned actions
        action = str(option.get("action", "")).lower()
        for banned in self.rules["banned_actions"]:
            if banned in action:
                violations.append(f"banned_action_{banned}")
        
        return len(violations) == 0, violations
