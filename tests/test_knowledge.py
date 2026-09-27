"""Comprehensive test suite for RuleWise AI Knowledge Base layer (Phase 2)."""

import json
from pathlib import Path
import pytest

from backend.core.exceptions import (
    CourseNotFoundError,
    DataValidationError,
    EntityNotFoundError,
    KnowledgeBaseError,
    KnowledgeFileNotFoundError,
    MalformedDataError,
    StudentNotFoundError,
)
from backend.knowledge.loader import KnowledgeBase, KnowledgeLoader
from backend.schemas.knowledge import AcademicStatus, Course, Student
from backend.schemas.rule import (
    ComparisonOperator,
    CompoundCondition,
    LogicalOperator,
    Rule,
    RuleStatus,
    SimpleCondition,
)


@pytest.fixture
def knowledge_base() -> KnowledgeBase:
    """Fixture returning an initialized KnowledgeBase instance."""
    return KnowledgeBase()


# -----------------------------------------------------------------------------
# 1. Valid Student Data Loading
# -----------------------------------------------------------------------------

def test_valid_student_data_loads(knowledge_base: KnowledgeBase):
    """Test that student data loads successfully with all expected attributes."""
    students = knowledge_base.get_students()
    assert len(students) >= 3

    for student in students:
        assert isinstance(student, Student)
        assert isinstance(student.id, str) and len(student.id) > 0
        assert isinstance(student.name, str) and len(student.name) > 0
        assert 0.0 <= student.gpa <= 10.0
        assert isinstance(student.completed_courses, list)
        assert isinstance(student.skills, list)
        assert isinstance(student.academic_status, AcademicStatus)


# -----------------------------------------------------------------------------
# 2. Valid Course Data Loading
# -----------------------------------------------------------------------------

def test_valid_course_data_loads(knowledge_base: KnowledgeBase):
    """Test that course data loads successfully with all expected attributes."""
    courses = knowledge_base.get_courses()
    assert len(courses) >= 3

    for course in courses:
        assert isinstance(course, Course)
        assert isinstance(course.id, str) and len(course.id) > 0
        assert isinstance(course.name, str) and len(course.name) > 0
        assert 0.0 <= course.minimum_gpa <= 10.0
        assert isinstance(course.prerequisite_courses, list)
        assert isinstance(course.required_skills, list)


# -----------------------------------------------------------------------------
# 3. Active Rules Loading
# -----------------------------------------------------------------------------

def test_active_rules_load(knowledge_base: KnowledgeBase):
    """Test that active declarative rules load successfully with active status."""
    active_rules = knowledge_base.get_active_rules()
    assert len(active_rules) >= 3

    for rule in active_rules:
        assert isinstance(rule, Rule)
        assert rule.status == RuleStatus.ACTIVE
        assert isinstance(rule.priority, int)
        assert isinstance(rule.condition, (SimpleCondition, CompoundCondition))
        assert rule.consequence.action is not None
        assert isinstance(rule.metadata, dict)


# -----------------------------------------------------------------------------
# 4. Staged Rules Loading
# -----------------------------------------------------------------------------

def test_staged_rules_load(knowledge_base: KnowledgeBase):
    """Test that staged declarative rules load successfully with staged status."""
    staged_rules = knowledge_base.get_staged_rules()
    assert len(staged_rules) >= 1

    for rule in staged_rules:
        assert isinstance(rule, Rule)
        assert rule.status == RuleStatus.STAGED
        assert isinstance(rule.priority, int)
        assert isinstance(rule.condition, (SimpleCondition, CompoundCondition))
        assert rule.consequence.action is not None


# -----------------------------------------------------------------------------
# 5. Student Lookup
# -----------------------------------------------------------------------------

def test_student_lookup_works(knowledge_base: KnowledgeBase):
    """Test that student lookup by ID retrieves the matching student entity."""
    student = knowledge_base.get_student("student_001")
    assert student.id == "student_001"
    assert student.name == "Arun Sharma"
    assert student.gpa == 8.7
    assert "CS101" in student.completed_courses
    assert "python" in student.skills
    assert student.academic_status == AcademicStatus.ACTIVE


# -----------------------------------------------------------------------------
# 6. Course Lookup
# -----------------------------------------------------------------------------

def test_course_lookup_works(knowledge_base: KnowledgeBase):
    """Test that course lookup by ID retrieves the matching course entity."""
    course = knowledge_base.get_course("AI101")
    assert course.id == "AI101"
    assert course.name == "Introduction to Artificial Intelligence"
    assert course.minimum_gpa == 7.0
    assert "CS101" in course.prerequisite_courses
    assert "python" in course.required_skills


# -----------------------------------------------------------------------------
# 7. Missing Student Lookup Exception
# -----------------------------------------------------------------------------

def test_missing_student_raises_exception(knowledge_base: KnowledgeBase):
    """Test that requesting an unknown student ID raises StudentNotFoundError."""
    with pytest.raises(StudentNotFoundError) as exc_info:
        knowledge_base.get_student("nonexistent_student_999")

    assert "nonexistent_student_999" in str(exc_info.value)
    assert isinstance(exc_info.value, EntityNotFoundError)
    assert isinstance(exc_info.value, KnowledgeBaseError)


# -----------------------------------------------------------------------------
# 8. Missing Course Lookup Exception
# -----------------------------------------------------------------------------

def test_missing_course_raises_exception(knowledge_base: KnowledgeBase):
    """Test that requesting an unknown course ID raises CourseNotFoundError."""
    with pytest.raises(CourseNotFoundError) as exc_info:
        knowledge_base.get_course("NONEXISTENT_COURSE_999")

    assert "NONEXISTENT_COURSE_999" in str(exc_info.value)
    assert isinstance(exc_info.value, EntityNotFoundError)
    assert isinstance(exc_info.value, KnowledgeBaseError)


# -----------------------------------------------------------------------------
# 9. Malformed JSON Rejection
# -----------------------------------------------------------------------------

def test_malformed_json_is_rejected(tmp_path: Path):
    """Test that invalid, unparseable JSON syntax raises MalformedDataError."""
    bad_json_file = tmp_path / "bad.json"
    bad_json_file.write_text("{\ninvalid_json: true\n", encoding="utf-8")

    with pytest.raises(MalformedDataError) as exc_info:
        KnowledgeLoader.load_students(bad_json_file)

    assert "Malformed JSON" in str(exc_info.value)
    assert isinstance(exc_info.value, KnowledgeBaseError)


# -----------------------------------------------------------------------------
# 10. Invalid Student Schema Rejection
# -----------------------------------------------------------------------------

def test_invalid_student_schema_is_rejected(tmp_path: Path):
    """Test that student data violating Pydantic schema is rejected with DataValidationError."""
    invalid_student_file = tmp_path / "invalid_students.json"
    # GPA exceeds 10.0 and academic_status is invalid
    invalid_data = [
        {
            "id": "student_invalid",
            "name": "Invalid Student",
            "gpa": 12.5,
            "completed_courses": [],
            "skills": [],
            "academic_status": "unrecognized_status",
        }
    ]
    invalid_student_file.write_text(json.dumps(invalid_data), encoding="utf-8")

    with pytest.raises(DataValidationError) as exc_info:
        KnowledgeLoader.load_students(invalid_student_file)

    assert "failed schema validation" in str(exc_info.value)


# -----------------------------------------------------------------------------
# 11. Invalid Course Schema Rejection
# -----------------------------------------------------------------------------

def test_invalid_course_schema_is_rejected(tmp_path: Path):
    """Test that course data violating Pydantic schema is rejected with DataValidationError."""
    invalid_course_file = tmp_path / "invalid_courses.json"
    # Negative minimum GPA
    invalid_data = [
        {
            "id": "CS_BAD",
            "name": "Bad Course",
            "minimum_gpa": -2.0,
            "prerequisite_courses": [],
            "required_skills": [],
        }
    ]
    invalid_course_file.write_text(json.dumps(invalid_data), encoding="utf-8")

    with pytest.raises(DataValidationError) as exc_info:
        KnowledgeLoader.load_courses(invalid_course_file)

    assert "failed schema validation" in str(exc_info.value)


# -----------------------------------------------------------------------------
# 12. Invalid Rule Schema Rejection
# -----------------------------------------------------------------------------

def test_invalid_rule_schema_is_rejected(tmp_path: Path):
    """Test that rule with invalid operators or malformed structure is rejected."""
    invalid_rule_file = tmp_path / "invalid_rules.json"
    # Unsupported operator and missing consequence
    invalid_data = [
        {
            "id": "RULE_INVALID",
            "name": "Unsupported Operator Rule",
            "description": "Rule using illegal comparison operator",
            "priority": 10,
            "status": "active",
            "condition": {
                "field": "student.gpa",
                "operator": "MAGIC_OPERATOR",
                "value": 7.0,
            },
            "consequence": {
                "action": "grant",
            },
        }
    ]
    invalid_rule_file.write_text(json.dumps(invalid_data), encoding="utf-8")

    with pytest.raises(DataValidationError) as exc_info:
        KnowledgeLoader.load_rules(invalid_rule_file)

    assert "failed schema validation" in str(exc_info.value)


def test_rule_arbitrary_code_injection_rejected():
    """Test that rules rejecting arbitrary/executable fields satisfy security constraints."""
    with pytest.raises(Exception):  # ValidationError due to extra='forbid'
        Rule.model_validate(
            {
                "id": "RULE_INJECTION",
                "name": "Code Injection Attempt",
                "description": "Attempt to attach executable python expression",
                "status": "active",
                "condition": {
                    "field": "student.gpa",
                    "operator": "==",
                    "value": 10.0,
                },
                "consequence": {"action": "grant"},
                "executable_code": "import os; os.system('echo compromised')",
            }
        )


# -----------------------------------------------------------------------------
# 13. No Rule Execution Occurs During Loading
# -----------------------------------------------------------------------------

def test_no_rule_execution_during_loading(knowledge_base: KnowledgeBase):
    """Test that loading the knowledge base strictly parses data without executing rules."""
    # Ensure students' fields are completely unmutated by any rule consequence
    student = knowledge_base.get_student("student_001")
    assert not hasattr(student, "gpa_satisfied")
    assert not hasattr(student, "eligible")
    assert not hasattr(student, "inferred_facts")

    # Ensure rules are purely data models, without execution methods or side effects
    for rule in knowledge_base.get_active_rules():
        assert not hasattr(rule, "execute")
        assert not hasattr(rule, "fire")
        assert not hasattr(rule, "evaluate")


# -----------------------------------------------------------------------------
# 14. Loader Results Are Deterministic
# -----------------------------------------------------------------------------

def test_loader_is_deterministic():
    """Test that two separate KnowledgeBase instances produce identical data."""
    kb1 = KnowledgeBase()
    kb2 = KnowledgeBase()

    # Compare student data equality
    students1 = kb1.get_students()
    students2 = kb2.get_students()
    assert len(students1) == len(students2)
    for s1, s2 in zip(students1, students2):
        assert s1.model_dump() == s2.model_dump()

    # Compare course data equality
    courses1 = kb1.get_courses()
    courses2 = kb2.get_courses()
    assert len(courses1) == len(courses2)
    for c1, c2 in zip(courses1, courses2):
        assert c1.model_dump() == c2.model_dump()

    # Compare active and staged rules equality
    assert [r.model_dump() for r in kb1.get_active_rules()] == [
        r.model_dump() for r in kb2.get_active_rules()
    ]
    assert [r.model_dump() for r in kb1.get_staged_rules()] == [
        r.model_dump() for r in kb2.get_staged_rules()
    ]


# -----------------------------------------------------------------------------
# 15. Missing File Error Handling
# -----------------------------------------------------------------------------

def test_missing_file_raises_knowledge_file_not_found(tmp_path: Path):
    """Test that pointing to a nonexistent file raises KnowledgeFileNotFoundError."""
    missing_file = tmp_path / "does_not_exist.json"
    with pytest.raises(KnowledgeFileNotFoundError) as exc_info:
        KnowledgeLoader.load_students(missing_file)

    assert "does not exist" in str(exc_info.value)
    assert isinstance(exc_info.value, FileNotFoundError)


# -----------------------------------------------------------------------------
# 16. Invalid Root Structure Rejection
# -----------------------------------------------------------------------------

def test_invalid_root_structure_rejected(tmp_path: Path):
    """Test that JSON files with dict roots instead of lists are rejected."""
    dict_file = tmp_path / "dict_root.json"
    dict_file.write_text(json.dumps({"student": "object"}), encoding="utf-8")

    with pytest.raises(DataValidationError) as exc_info:
        KnowledgeLoader.load_students(dict_file)

    assert "Expected top-level JSON array" in str(exc_info.value)


# -----------------------------------------------------------------------------
# 17. Rule Status Enforcement
# -----------------------------------------------------------------------------

def test_rule_status_enforcement(tmp_path: Path):
    """Test that loading active rules with staged status (or vice versa) is rejected."""
    mismatched_file = tmp_path / "mismatched_rules.json"
    data = [
        {
            "id": "RULE_STAGED_IN_ACTIVE",
            "name": "Staged Rule Test",
            "description": "Rule marked staged loaded under active expectation",
            "priority": 1,
            "status": "staged",
            "condition": {
                "field": "student.gpa",
                "operator": ">=",
                "value": 6.0,
            },
            "consequence": {
                "action": "flag",
            },
        }
    ]
    mismatched_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(DataValidationError) as exc_info:
        KnowledgeLoader.load_rules(mismatched_file, expected_status=RuleStatus.ACTIVE)

    assert "expected status 'active'" in str(exc_info.value)
