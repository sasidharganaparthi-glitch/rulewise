"""Language model provider abstraction and implementations for RuleWise AI.

Phase 6: Defines an interchangeable provider interface supporting Google Gemini
and mock test providers. The symbolic rule engine remains completely independent
of the LLM provider.
"""

from abc import ABC, abstractmethod
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel, ValidationError

from backend.core.config import Settings, get_settings
from backend.core.exceptions import (
    InvalidModelResponseError,
    ProviderError,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LanguageModelProvider(ABC):
    """Abstract interface for language model providers."""

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
    ) -> str:
        """Generate unstructured text from a prompt.

        Args:
            prompt: User or task prompt.
            system_instruction: Optional system instruction directing model persona/task.

        Returns:
            Generated text string.

        Raises:
            ProviderUnavailableError: If provider cannot be contacted or lacks credentials.
            ProviderError: If the remote API call fails.
        """
        pass

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
    ) -> T:
        """Generate validated structured output adhering to a Pydantic schema.

        Args:
            prompt: User or task prompt.
            response_schema: Target Pydantic model class.
            system_instruction: Optional system instruction directing model task.

        Returns:
            Instance of response_schema populated with model outputs.

        Raises:
            ProviderUnavailableError: If provider is unconfigured or unreachable.
            InvalidModelResponseError: If model output is malformed or violates schema.
            ProviderError: If the remote API call fails.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the provider is configured and available for inference."""
        pass


_DEFAULT_KEY = object()

# Models that are retired/unavailable and return 404 on current Gemini API endpoints
RETIRED_MODELS_MAP: Dict[str, str] = {
    "gemini-2.5-flash": "gemini-3.5-flash-lite",
    "gemini-2.5-pro": "gemini-3.8-flash",
    "gemini-2.0-flash": "gemini-3.5-flash-lite",
    "gemini-1.5-flash": "gemini-3.5-flash-lite",
    "gemini-1.5-pro": "gemini-3.8-flash",
    "gemini-2.0-flash-lite": "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite": "gemini-3.5-flash-lite",
}


class GeminiProvider(LanguageModelProvider):
    """Google Gemini implementation of LanguageModelProvider using the google-genai SDK."""

    def __init__(
        self,
        api_key: Any = _DEFAULT_KEY,
        model_name: Optional[str] = None,
    ) -> None:
        """Initialize GeminiProvider with API key and model name.

        Args:
            api_key: Optional Gemini API key. Defaults to Settings.GEMINI_API_KEY when omitted.
                     If explicitly passed as None or empty string, provider is treated as unconfigured.
            model_name: Optional Gemini model identifier. Defaults to Settings.GEMINI_MODEL.
        """
        settings = get_settings()
        if api_key is _DEFAULT_KEY:
            self.api_key = settings.GEMINI_API_KEY
        else:
            self.api_key = api_key

        raw_model = model_name if model_name is not None else settings.GEMINI_MODEL
        if raw_model in RETIRED_MODELS_MAP:
            target_model = RETIRED_MODELS_MAP[raw_model]
            logger.warning(
                "Configured Gemini model '%s' is retired/unavailable on current API endpoints (causes 404 NOT_FOUND). "
                "Automatically upgraded to '%s'.",
                raw_model,
                target_model,
            )
            self.model_name = target_model
        else:
            self.model_name = raw_model

        self._client: Optional[Any] = None

    def is_available(self) -> bool:
        """Return True if a non-empty API key is present."""
        if not self.api_key or not self.api_key.strip():
            return False
        # Disallow default placeholder
        if self.api_key.strip() in ("your_gemini_api_key_here", "PLACEHOLDER"):
            return False
        return True

    def _get_client(self) -> Any:
        """Lazy-initialize and return the official google-genai Client."""
        if not self.is_available():
            raise ProviderUnavailableError(
                "Gemini API key is not configured or is invalid. Set GEMINI_API_KEY."
            )
        if self._client is None:
            try:
                from google import genai
                from google.genai import types

                timeout_ms = max(10000, int(get_settings().LLM_TIMEOUT_SECONDS * 1000))
                http_opts = types.HttpOptions(
                    timeout=timeout_ms,
                    retry_options=types.HttpRetryOptions(attempts=1),
                )
                self._client = genai.Client(api_key=self.api_key, http_options=http_opts)
            except Exception as exc:
                raise ProviderUnavailableError(
                    f"Failed to initialize Google GenAI client: {exc}"
                ) from exc
        return self._client

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
    ) -> str:
        """Generate text using Google Gemini with dynamic model fallback."""
        client = self._get_client()
        candidate_models = [self.model_name]
        for m_name in (
            "gemini-3.5-flash-lite",
            "gemini-3.8-flash",
            "gemini-3.5-flash",
            "gemini-flash-lite-latest",
            "gemini-flash-latest",
        ):
            if m_name not in candidate_models:
                candidate_models.append(m_name)

        last_error = None
        for m in candidate_models:
            try:
                from google.genai import types

                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                )
                response = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=config,
                )
                if response and response.text:
                    return response.text.strip()
            except (ProviderUnavailableError, InvalidModelResponseError):
                raise
            except Exception as exc:
                last_error = exc
                logger.warning("Gemini model '%s' failed in generate_text (%s); trying fallback.", m, exc)
                continue

        logger.error("All Gemini candidate models failed in generate_text: %s", last_error)
        raise ProviderError(f"Gemini API call failed: {last_error}") from last_error

    @staticmethod
    def _clean_schema_additional_properties(schema: Any) -> None:
        """Recursively clear additional_properties which causes Gemini REST API 400 INVALID_ARGUMENT."""
        if schema is None:
            return
        if hasattr(schema, "additional_properties"):
            schema.additional_properties = None
        if hasattr(schema, "properties") and schema.properties:
            for prop in schema.properties.values():
                GeminiProvider._clean_schema_additional_properties(prop)
        if hasattr(schema, "items") and schema.items:
            GeminiProvider._clean_schema_additional_properties(schema.items)

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
    ) -> T:
        """Generate structured output adhering to response_schema using Google Gemini."""
        client = self._get_client()
        candidate_models = [self.model_name]
        for m_name in (
            "gemini-3.5-flash-lite",
            "gemini-3.8-flash",
            "gemini-3.5-flash",
            "gemini-flash-lite-latest",
            "gemini-flash-latest",
        ):
            if m_name not in candidate_models:
                candidate_models.append(m_name)

        last_error = None
        for m in candidate_models:
            try:
                from google.genai import types
                from google.genai._transformers import t_schema

                schema_obj = t_schema(None, response_schema)
                self._clean_schema_additional_properties(schema_obj)

                config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema_obj,
                    system_instruction=system_instruction,
                )
                response = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=config,
                )
                raw_text = response.text if response else None
                if not raw_text:
                    continue

                try:
                    return response_schema.model_validate_json(raw_text)
                except ValidationError as val_err:
                    raise InvalidModelResponseError(
                        f"Gemini response failed Pydantic validation: {val_err}"
                    ) from val_err
                except (ValueError, json.JSONDecodeError) as json_err:
                    raise InvalidModelResponseError(
                        f"Gemini response could not be parsed as JSON: {json_err}"
                    ) from json_err

            except (ProviderUnavailableError, InvalidModelResponseError):
                raise
            except Exception as exc:
                last_error = exc
                logger.warning("Gemini model '%s' failed in generate_structured (%s); trying fallback.", m, exc)
                continue

        logger.error("All Gemini candidate models failed in generate_structured: %s", last_error)
        raise ProviderError(f"Gemini structured API call failed: {last_error}") from last_error


class MockLanguageModelProvider(LanguageModelProvider):
    """In-memory mock provider for deterministic, offline testing."""

    def __init__(
        self,
        available: bool = True,
        default_text: str = "Mocked AI response.",
        text_responses: Optional[List[str]] = None,
        default_structured: Optional[Any] = None,
        structured_responses: Optional[List[Any]] = None,
        error_to_raise: Optional[Exception] = None,
        dynamic_handler: Optional[Callable[..., Any]] = None,
    ) -> None:
        """Initialize mock provider with controlled test behaviors."""
        self._available = available
        self.default_text = default_text
        self.text_responses = list(text_responses) if text_responses else []
        self.default_structured = default_structured
        self.structured_responses = list(structured_responses) if structured_responses else []
        self.error_to_raise = error_to_raise
        self.dynamic_handler = dynamic_handler
        self.call_history: List[Dict[str, Any]] = []

    def set_available(self, available: bool) -> None:
        """Toggle provider availability."""
        self._available = available

    def set_error(self, error: Optional[Exception]) -> None:
        """Set an exception to raise on subsequent calls."""
        self.error_to_raise = error

    def is_available(self) -> bool:
        """Return configured availability flag."""
        return self._available

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
    ) -> str:
        """Generate mocked text output."""
        self.call_history.append({
            "type": "text",
            "prompt": prompt,
            "system_instruction": system_instruction,
        })
        if not self._available:
            raise ProviderUnavailableError("Mock provider is marked unavailable.")
        if self.error_to_raise:
            raise self.error_to_raise

        if self.dynamic_handler:
            result = self.dynamic_handler(prompt, system_instruction, None)
            if isinstance(result, str):
                return result

        if self.text_responses:
            return self.text_responses.pop(0)
        return self.default_text

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
    ) -> T:
        """Generate mocked structured output conforming to response_schema."""
        self.call_history.append({
            "type": "structured",
            "prompt": prompt,
            "schema": response_schema,
            "system_instruction": system_instruction,
        })
        if not self._available:
            raise ProviderUnavailableError("Mock provider is marked unavailable.")
        if self.error_to_raise:
            raise self.error_to_raise

        if self.dynamic_handler:
            res = self.dynamic_handler(prompt, system_instruction, response_schema)
            if isinstance(res, response_schema):
                return res
            if isinstance(res, dict):
                return response_schema.model_validate(res)

        if self.structured_responses:
            item = self.structured_responses.pop(0)
            if isinstance(item, response_schema):
                return item
            if isinstance(item, dict):
                return response_schema.model_validate(item)
            if isinstance(item, str):
                return response_schema.model_validate_json(item)
            return item

        if self.default_structured is not None:
            if isinstance(self.default_structured, response_schema):
                return self.default_structured
            if isinstance(self.default_structured, dict):
                return response_schema.model_validate(self.default_structured)
            if isinstance(self.default_structured, str):
                return response_schema.model_validate_json(self.default_structured)

        # Fallback to an empty instance if schema allows or raise error
        try:
            return response_schema()  # type: ignore[call-arg]
        except Exception as exc:
            raise InvalidModelResponseError(
                f"Mock provider could not construct default instance of {response_schema.__name__}: {exc}"
            ) from exc


# Global provider instance override (for testing and runtime injection)
_provider_override: Optional[LanguageModelProvider] = None


def set_provider_override(provider: Optional[LanguageModelProvider]) -> None:
    """Set or clear a global provider override (e.g. mock provider for tests)."""
    global _provider_override
    _provider_override = provider


def get_language_model_provider(
    settings: Optional[Settings] = None,
) -> LanguageModelProvider:
    """Obtain the active LanguageModelProvider instance.

    Returns the global override if set, otherwise initializes a GeminiProvider.
    """
    global _provider_override
    if _provider_override is not None:
        return _provider_override

    cfg = settings or get_settings()
    return GeminiProvider(api_key=cfg.GEMINI_API_KEY, model_name=cfg.GEMINI_MODEL)
