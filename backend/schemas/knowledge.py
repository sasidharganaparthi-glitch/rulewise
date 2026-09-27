"""Pydantic schemas and data validation models for academic domain entities.

Represents students, courses, and related academic records for the RuleWise AI
Knowledge Base layer.
"""

from enum import Enum
from typing import List
from pydantic import BaseModel, ConfigDict, Field


class AcademicStatus(str, Enum):
    """Academic standing status for enrolled students."""

    ACTIVE = "active"
    PROBATION = "probation"
    GRADUATED = "graduated"
    SUSPENDED = "suspended"


class Student(BaseModel):
    """Represents a student profile within the academic domain knowledge base."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(
        ...,
        min_length=1,
        description="Unique student identifier (e.g. 'student_001')",
    )
    name: str = Field(
        ...,
        min_length=1,
        description="Full name of the student",
    )
    gpa: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description="Cumulative Grade Point Average (0.0 - 10.0 scale)",
    )
    completed_courses: List[str] = Field(
        default_factory=list,
        description="List of course IDs successfully completed by the student",
    )
    skills: List[str] = Field(
        default_factory=list,
        description="List of verified technical and domain skills",
    )
    academic_status: AcademicStatus = Field(
        default=AcademicStatus.ACTIVE,
        description="Current academic standing status",
    )


class Course(BaseModel):
    """Represents a curriculum course offering within the academic domain knowledge base."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(
        ...,
        min_length=1,
        description="Unique course code identifier (e.g. 'CS101')",
    )
    name: str = Field(
        ...,
        min_length=1,
        description="Official title of the course",
    )
    minimum_gpa: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        description="Minimum GPA threshold required for student enrollment",
    )
    prerequisite_courses: List[str] = Field(
        default_factory=list,
        description="List of prerequisite course codes required prior to enrollment",
    )
    required_skills: List[str] = Field(
        default_factory=list,
        description="List of skills recommended or required for course success",
    )
