"""Custom application exceptions and error handling structures for RuleWise AI."""


class RuleWiseError(Exception):
    """Base exception for all RuleWise AI domain and engine errors."""

    pass


# -----------------------------------------------------------------------------
# Knowledge Base Exceptions (Phase 2)
# -----------------------------------------------------------------------------

class KnowledgeBaseError(RuleWiseError):
    """Base exception for knowledge base operations and data handling."""

    pass


class KnowledgeFileNotFoundError(KnowledgeBaseError, FileNotFoundError):
    """Raised when a required knowledge base JSON data file is missing."""

    pass


class MalformedDataError(KnowledgeBaseError):
    """Raised when a knowledge base data file cannot be parsed as valid JSON."""

    pass


class DataValidationError(KnowledgeBaseError):
    """Raised when knowledge base content fails Pydantic schema validation."""

    pass


class EntityNotFoundError(KnowledgeBaseError, KeyError):
    """Base exception raised when a requested domain entity does not exist."""

    pass


class StudentNotFoundError(EntityNotFoundError):
    """Raised when a student cannot be found by their identifier."""

    pass


class CourseNotFoundError(EntityNotFoundError):
    """Raised when a course cannot be found by their identifier."""

    pass


class RuleNotFoundError(EntityNotFoundError):
    """Raised when a rule cannot be found by its identifier."""

    pass


# -----------------------------------------------------------------------------
# Declarative Rule Engine Exceptions (Phase 3)
# -----------------------------------------------------------------------------

class EngineError(RuleWiseError):
    """Base exception for declarative rule engine execution and evaluation errors."""

    pass


class OperatorError(EngineError):
    """Base exception for comparison and operator evaluation errors."""

    pass


class UnsupportedOperatorError(OperatorError):
    """Raised when an unrecognized or unsupported comparison operator is encountered."""

    pass


class InvalidComparisonError(OperatorError, TypeError):
    """Raised when an operator cannot be evaluated due to incompatible operand types."""

    pass


class ConditionEvaluationError(EngineError):
    """Base exception raised when rule condition evaluation fails."""

    pass


class UnknownConditionTypeError(ConditionEvaluationError):
    """Raised when an unknown condition structure or logical operator is encountered."""

    pass


class FactResolutionError(EngineError, KeyError):
    """Raised when a required fact path cannot be resolved from working memory."""

    pass


class MalformedRuleError(EngineError, ValueError):
    """Raised when a rule definition has an invalid, incomplete, or corrupted structure."""

    pass


# -----------------------------------------------------------------------------
# Natural Language Processing & AI Layer Exceptions (Phase 6)
# -----------------------------------------------------------------------------

class NLPError(RuleWiseError):
    """Base exception for Natural Language Processing and AI layer operations."""

    pass


class ProviderError(NLPError):
    """Base exception for language model provider failures."""

    pass


class ProviderUnavailableError(ProviderError):
    """Raised when an LLM provider is unavailable, unconfigured, or unreachable."""

    pass


class InvalidModelResponseError(NLPError):
    """Raised when the LLM produces a malformed, invalid, or unparseable response."""

    pass


class StructuredQueryValidationError(NLPError):
    """Raised when a generated or extracted structured query fails validation."""

    pass


class QueryExecutionError(NLPError):
    """Raised when structured query orchestration or fact resolution fails."""

    pass
