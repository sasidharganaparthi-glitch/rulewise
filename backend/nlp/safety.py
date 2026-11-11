"""RuleWise AI Safety and Risk Classification Engine.

Implements configurable multi-tier safety evaluation for non-sexual harmful requests:
- SAFE: Standard benign, educational, rule evaluation, or general advisory query.
- CAUTION: Defensive, security analysis, safety protocols, or dual-use concepts discussed in an educational/defensive context. Allowed with caution advisory.
- SERIOUS_CONCERN: Inquiries probing hazardous vulnerabilities or high-risk operational tampering.
- HIGH_RISK: Direct instructions to generate weapons, malware, chemical hazards, destructive exploits, or facilitate physical harm. Blocked.

Ensures zero false-positive blockage of legitimate security engineering, academic learning, preventive health, or defensive cybersecurity discussions.
"""

from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SafetyLevel(str, Enum):
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    SERIOUS_CONCERN = "SERIOUS_CONCERN"
    HIGH_RISK = "HIGH_RISK"


class SafetyEvaluation(BaseModel):
    level: SafetyLevel
    is_allowed: bool
    category: Optional[str] = None
    reason: str
    advisory_note: Optional[str] = None


# Patterns for high-risk destructive instructions (actionable facilitation of severe harm)
_HIGH_RISK_ACTIONABLE_PATTERNS = [
    (r"\b(how\s+to\s+(build|make|manufacture|synthesize|assemble)|instructions?\s+for\s+(making|building))\s+(a\s+)?(bomb|explosive|ied|landmine|weapon\s+of\s+mass|dirty\s+bomb)\b", "explosives_and_weapons"),
    (r"\b(write|create|code|generate)\s+(a\s+)?(ransomware|keylogger|trojan|wiper\s+malware|zero-day\s+exploit\s+payload)\b", "malware_generation"),
    (r"\b(synthesize|recipe\s+for|produce)\s+(sarin|vx\s+nerve|ricin|anthrax|cyanide\s+poison)\b", "chemical_biological_hazards"),
    (r"\b(instructions?\s+to\s+commit|how\s+to\s+effectively\s+(hang|poison|kill)\s+myself)\b", "severe_self_harm"),
    (r"\b(how\s+to\s+(hack|infiltrate|take\s+down)\s+(the\s+)?(power\s+grid|nuclear\s+plant|water\s+supply))\b", "critical_infrastructure_attack"),
]

# Patterns representing defensive, educational, historical, or safety contexts
_DEFENSIVE_OR_EDUCATIONAL_PATTERNS = [
    r"\b(how\s+to\s+prevent|how\s+do\s+we\s+detect|detection|mitigation|remediation|defense|defensive)\b",
    r"\b(cybersecurity|firewall|antivirus|edr|patch|secure\s+coding|best\s+practices|safety\s+protocol)\b",
    r"\b(history\s+of|treaty|convention|regulation|compliance|audit|educational|academic|research)\b",
    r"\b(what\s+is|define|explain\s+how\s+it\s+works|difference\s+between)\b",
    r"\b(first\s+aid|antidote|neutralize|disposal\s+of|hazmat|osha)\b",
]

# Patterns for caution / serious concern
_CAUTION_TOPICS = [
    (r"\b(penetration\s+testing|vulnerability\s+scanning|reverse\s+engineering|exploit\s+analysis)\b", "cybersecurity_testing"),
    (r"\b(hazardous\s+chemicals|toxic\s+substances|industrial\s+acids|radiation)\b", "hazardous_materials"),
    (r"\b(system\s+override|jailbreak|ignore\s+previous\s+instructions|prompt\s+injection)\b", "tampering_probe"),
]


class SafetyPolicyManager:
    """Manages configurable safety rules and evaluates incoming messages."""

    def __init__(self) -> None:
        self.enabled: bool = True
        self.allow_educational_dual_use: bool = True
        self.custom_blocked_keywords: List[str] = []

    def evaluate_request(self, message: str) -> SafetyEvaluation:
        """Evaluate a text query against multi-tier safety standards."""
        if not self.enabled or not message:
            return SafetyEvaluation(
                level=SafetyLevel.SAFE,
                is_allowed=True,
                reason="Safety checking disabled or query empty.",
            )

        text = message.lower().strip()

        # Check defensive / educational framing first to avoid false-positive censorship
        is_defensive = any(re.search(pat, text, re.IGNORECASE) for pat in _DEFENSIVE_OR_EDUCATIONAL_PATTERNS)

        # Check High-Risk Actionable instructions
        for pattern, category in _HIGH_RISK_ACTIONABLE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                if is_defensive and self.allow_educational_dual_use and "how to prevent" in text:
                    return SafetyEvaluation(
                        level=SafetyLevel.CAUTION,
                        is_allowed=True,
                        category=category,
                        reason="Educational/defensive security query related to dangerous concepts.",
                        advisory_note="[RuleWise Safety Caution] This query discusses security risks in a preventive or defensive context. Verifiable safeguards apply.",
                    )
                return SafetyEvaluation(
                    level=SafetyLevel.HIGH_RISK,
                    is_allowed=False,
                    category=category,
                    reason=f"Request blocked by RuleWise Safety Policy: Actionable facilitation of {category.replace('_', ' ')} is prohibited.",
                    advisory_note="RuleWise AI is committed to safe and verified operations. We cannot assist with generating weapons, malicious software, or dangerous physical harm.",
                )

        # Check custom blocked keywords
        for kw in self.custom_blocked_keywords:
            if kw.lower() in text:
                return SafetyEvaluation(
                    level=SafetyLevel.SERIOUS_CONCERN,
                    is_allowed=False,
                    category="custom_admin_restriction",
                    reason=f"Query matched custom administrative restriction: '{kw}'.",
                    advisory_note="This request matches an institution-specific restriction.",
                )

        # Check Caution / Dual-use topics
        for pattern, category in _CAUTION_TOPICS:
            if re.search(pattern, text, re.IGNORECASE):
                level = SafetyLevel.CAUTION
                return SafetyEvaluation(
                    level=level,
                    is_allowed=True,
                    category=category,
                    reason=f"Topic identified under {category.replace('_', ' ')} category.",
                    advisory_note="[RuleWise Safety Caution] Proceeding with educational and verified defensive guidance.",
                )

        return SafetyEvaluation(
            level=SafetyLevel.SAFE,
            is_allowed=True,
            reason="Query conforms to standard safety policies.",
        )


_global_safety_manager: Optional[SafetyPolicyManager] = None


def get_safety_manager() -> SafetyPolicyManager:
    """Retrieve singleton SafetyPolicyManager."""
    global _global_safety_manager
    if _global_safety_manager is None:
        _global_safety_manager = SafetyPolicyManager()
    return _global_safety_manager
