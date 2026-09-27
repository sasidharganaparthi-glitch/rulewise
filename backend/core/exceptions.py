"""Custom application exceptions and error handling structures for RuleWise AI."""


class RuleWiseError(Exception):
    """Base exception for all RuleWise AI domain and engine errors."""

    pass


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
