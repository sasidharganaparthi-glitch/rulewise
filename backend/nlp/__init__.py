"""Natural language processing and AI layer package for RuleWise AI (Phase 6).

Public API:
- LanguageModelProvider: Provider interface abstraction.
- GeminiProvider: Official Google Gemini SDK implementation.
- MockLanguageModelProvider: Test provider with customizable responses and error simulation.
- get_language_model_provider / set_provider_override: Provider resolution and injection.
- GeminiClient: High-level client facade.
- QueryParser: Intent classification and entity extraction.
- ResponseGenerator: Deterministic and LLM response generation.
- RuleWiseOrchestrator: End-to-end neuro-symbolic pipeline orchestrator.
- synthesize_course_eligibility_rule: Declarative rule synthesis from domain courses.
"""

from backend.nlp.gemini_client import GeminiClient
from backend.nlp.orchestrator import RuleWiseOrchestrator
from backend.nlp.provider import (
    GeminiProvider,
    LanguageModelProvider,
    MockLanguageModelProvider,
    get_language_model_provider,
    set_provider_override,
)
from backend.nlp.query_parser import QueryParser
from backend.nlp.response_generator import ResponseGenerator
from backend.nlp.rule_synthesizer import synthesize_course_eligibility_rule

__all__ = [
    "LanguageModelProvider",
    "GeminiProvider",
    "MockLanguageModelProvider",
    "get_language_model_provider",
    "set_provider_override",
    "GeminiClient",
    "QueryParser",
    "ResponseGenerator",
    "RuleWiseOrchestrator",
    "synthesize_course_eligibility_rule",
]
