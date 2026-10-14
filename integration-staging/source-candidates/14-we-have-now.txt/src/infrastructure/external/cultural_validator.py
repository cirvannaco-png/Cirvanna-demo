# src/infrastructure/external/cultural_validator.py
import yaml
from typing import List, Dict, Any, Optional
from src.core.domain.entities import UserProfile, Item

class CulturalValidator:
    def __init__(self, rules_file: str = "config/cultural_rules.yaml"):
        with open(rules_file, 'r') as f:
            self.rules = yaml.safe_load(f)

    async def validate(self, items: List[Item], constraints: Dict[str, Any]) -> List[Item]:
        # Remove items that violate any cultural rule
        filtered = []
        for item in items:
            if self._is_allowed(item, constraints):
                filtered.append(item)
        return filtered

    async def get_severity(self, user: UserProfile, item: Item) -> float:
        # Compute severity of violation (0-1)
        if not user.cultural_constraints:
            return 0.0
        severity = 0.0
        for rule in self.rules.get('modesty', []):
            if rule['category'] == item.category:
                severity = max(severity, rule.get('severity', 0.5))
        return severity

    def _is_allowed(self, item: Item, constraints: Dict) -> bool:
        # Apply rules
        if constraints.get('modesty', False):
            for rule in self.rules.get('modesty', []):
                if item.category == rule['category']:
                    return False
        return True
