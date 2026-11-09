"""Gemini client interface and facade for RuleWise AI NLP operations.

Phase 6: Exposes high-level text generation and structured extraction operations
delegating to the configured LanguageModelProvider.
"""

from typing import Optional, Type, TypeVar
from pydantic import BaseModel

from backend.nlp.provider import LanguageModelProvider, get_language_model_provider

T = TypeVar("T", bound=BaseModel)


class GeminiClient:
    """Client facade for language model interactions."""

    def __init__(self, provider: Optional[LanguageModelProvider] = None) -> None:
        """Initialize client with an optional custom provider.

        Args:
            provider: LanguageModelProvider instance. Defaults to get_language_model_provider().
        """
        self._provider = provider

    @property
    def provider(self) -> LanguageModelProvider:
        """Obtain the active language model provider."""
        if self._provider is not None:
            return self._provider
        return get_language_model_provider()

    def is_available(self) -> bool:
        """Check whether the active language model provider is available."""
        return self.provider.is_available()

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
    ) -> str:
        """Generate text from a prompt using the active provider."""
        return self.provider.generate_text(prompt, system_instruction=system_instruction)

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
    ) -> T:
        """Generate structured output adhering to response_schema using the active provider."""
        return self.provider.generate_structured(
            prompt,
            response_schema=response_schema,
            system_instruction=system_instruction,
        )
