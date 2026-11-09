"""Rule synthesis translating course requirements into declarative rules (Phase 6).

Produces validated, pure declarative Rule instances (Pydantic models) conforming
to Phase 3 & 4 schemas. No eval(), no exec(), no arbitrary code.
"""

from typing import List, Optional
from backend.schemas.knowledge import Course
from backend.schemas.rule import (
    ComparisonOperator,
    CompoundCondition,
    LogicalOperator,
    Rule,
    RuleCondition,
    RuleConsequence,
    RuleStatus,
    SimpleCondition,
)


def synthesize_course_eligibility_rule(course: Course, priority: int = 10) -> Rule:
    """Synthesize a declarative Rule that evaluates student eligibility for a specific course.

    The generated rule checks:
    1. Student academic status == 'active'.
    2. Student GPA >= course.minimum_gpa (if minimum_gpa > 0).
    3. Each prerequisite course IN student.completed_courses.
    4. Each required skill IN student.skills.

    Args:
        course: Validated Course domain entity from the Knowledge Base.
        priority: Rule precedence / salience score (default 10).

    Returns:
        A validated, frozen Rule instance.
    """
    conditions: List[RuleCondition] = [
        SimpleCondition(
            field="student.academic_status",
            operator=ComparisonOperator.EQUALS,
            value="active",
        )
    ]

    if course.minimum_gpa > 0.0:
        conditions.append(
            SimpleCondition(
                field="student.gpa",
                operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
                value=course.minimum_gpa,
            )
        )

    for prereq in course.prerequisite_courses:
        conditions.append(
            SimpleCondition(
                field="student.completed_courses",
                operator=ComparisonOperator.IN,
                value=prereq,
            )
        )

    for skill in course.required_skills:
        conditions.append(
            SimpleCondition(
                field="student.skills",
                operator=ComparisonOperator.IN,
                value=skill,
            )
        )

    compound_cond = CompoundCondition(
        operator=LogicalOperator.AND,
        conditions=conditions,
    )

    fact_key = f"eligible_for_{course.id.lower()}"

    consequence = RuleConsequence(
        action="grant_course_eligibility",
        params={
            fact_key: True,
            "eligible": True,
            "course_id": course.id,
            "course_name": course.name,
        },
        description=f"Student satisfies all academic prerequisites and skills for {course.name} ({course.id}).",
    )

    return Rule(
        id=f"RULE_ELIGIBILITY_{course.id.upper()}",
        name=f"{course.name} Eligibility",
        description=f"Evaluates full enrollment eligibility for course {course.id}: {course.name}.",
        priority=priority,
        status=RuleStatus.ACTIVE,
        condition=compound_cond,
        consequence=consequence,
        metadata={
            "category": "course_eligibility",
            "course_id": course.id,
            "synthesized": True,
        },
    )
