"""Knowledge base loader and repository interface for RuleWise AI.

This module provides deterministic loading, schema validation, and retrieval
of academic domain entities (students, courses) and declarative rules (active, staged).
NO rule evaluation, forward chaining, or reasoning logic is performed here.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import ValidationError

from backend.core.exceptions import (
    CourseNotFoundError,
    DataValidationError,
    KnowledgeFileNotFoundError,
    MalformedDataError,
    RuleNotFoundError,
    StudentNotFoundError,
)
from backend.schemas.knowledge import Course, Student
from backend.schemas.rule import Rule, RuleStatus


class KnowledgeLoader:
    """Utility class providing static validation and file loading methods."""

    @staticmethod
    def load_json_data(file_path: Union[str, Path]) -> Any:
        """Read and parse raw JSON data from a filesystem path.

        Args:
            file_path: Path to the target JSON file.

        Returns:
            Parsed Python data structure (typically list or dict).

        Raises:
            KnowledgeFileNotFoundError: If the file does not exist.
            MalformedDataError: If the file contains invalid or unparseable JSON.
        """
        path = Path(file_path)
        if not path.is_file():
            raise KnowledgeFileNotFoundError(
                f"Knowledge base file does not exist: {path}"
            )

        try:
            content = path.read_text(encoding="utf-8")
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise MalformedDataError(
                f"Malformed JSON in file '{path.name}' at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc

    @classmethod
    def load_students(cls, file_path: Union[str, Path]) -> List[Student]:
        """Load and validate student records from JSON.

        Args:
            file_path: Path to the students JSON file.

        Returns:
            List of validated Student model instances.

        Raises:
            KnowledgeFileNotFoundError: If the file is missing.
            MalformedDataError: If the JSON is invalid.
            DataValidationError: If structure or schema validation fails.
        """
        raw_data = cls.load_json_data(file_path)
        if not isinstance(raw_data, list):
            raise DataValidationError(
                f"Expected top-level JSON array in '{Path(file_path).name}', got {type(raw_data).__name__}"
            )

        students: List[Student] = []
        for index, item in enumerate(raw_data):
            try:
                students.append(Student.model_validate(item))
            except ValidationError as exc:
                raise DataValidationError(
                    f"Student record at index {index} failed schema validation: {exc}"
                ) from exc
        return students

    @classmethod
    def load_courses(cls, file_path: Union[str, Path]) -> List[Course]:
        """Load and validate course offerings from JSON.

        Args:
            file_path: Path to the courses JSON file.

        Returns:
            List of validated Course model instances.

        Raises:
            KnowledgeFileNotFoundError: If the file is missing.
            MalformedDataError: If the JSON is invalid.
            DataValidationError: If structure or schema validation fails.
        """
        raw_data = cls.load_json_data(file_path)
        if not isinstance(raw_data, list):
            raise DataValidationError(
                f"Expected top-level JSON array in '{Path(file_path).name}', got {type(raw_data).__name__}"
            )

        courses: List[Course] = []
        for index, item in enumerate(raw_data):
            try:
                courses.append(Course.model_validate(item))
            except ValidationError as exc:
                raise DataValidationError(
                    f"Course record at index {index} failed schema validation: {exc}"
                ) from exc
        return courses

    @classmethod
    def load_rules(
        cls,
        file_path: Union[str, Path],
        expected_status: Optional[RuleStatus] = None,
    ) -> List[Rule]:
        """Load and validate declarative rules from JSON.

        Args:
            file_path: Path to the rules JSON file.
            expected_status: Optional expected lifecycle status to enforce.

        Returns:
            List of validated Rule model instances.

        Raises:
            KnowledgeFileNotFoundError: If the file is missing.
            MalformedDataError: If the JSON is invalid.
            DataValidationError: If structure or schema validation fails.
        """
        raw_data = cls.load_json_data(file_path)
        if not isinstance(raw_data, list):
            raise DataValidationError(
                f"Expected top-level JSON array in '{Path(file_path).name}', got {type(raw_data).__name__}"
            )

        rules: List[Rule] = []
        for index, item in enumerate(raw_data):
            try:
                rule = Rule.model_validate(item)
            except ValidationError as exc:
                raise DataValidationError(
                    f"Rule record at index {index} failed schema validation: {exc}"
                ) from exc

            if expected_status is not None and rule.status != expected_status:
                raise DataValidationError(
                    f"Rule '{rule.id}' in '{Path(file_path).name}' has status '{rule.status.value}', "
                    f"expected status '{expected_status.value}'"
                )
            rules.append(rule)
        return rules


class KnowledgeBase:
    """In-memory repository managing validated domain entities and declarative rules."""

    def __init__(
        self,
        data_dir: Optional[Union[str, Path]] = None,
        auto_load: bool = True,
    ) -> None:
        """Initialize KnowledgeBase repository with data directory path.

        Args:
            data_dir: Path to directory containing JSON data files.
                      Defaults to 'backend/knowledge/data'.
            auto_load: If True, automatically loads and validates all assets upon initialization.
        """
        if data_dir is None:
            self.data_dir = Path(__file__).resolve().parent / "data"
        else:
            self.data_dir = Path(data_dir).resolve()

        self._students: Dict[str, Student] = {}
        self._courses: Dict[str, Course] = {}
        self._active_rules: Dict[str, Rule] = {}
        self._staged_rules: Dict[str, Rule] = {}

        if auto_load:
            self.load_all()

    def load_all(self) -> None:
        """Load and validate students, courses, active rules, and staged rules."""
        self.load_students()
        self.load_courses()
        self.load_active_rules()
        self.load_staged_rules()

    def load_students(self, filename: str = "students.json") -> List[Student]:
        """Load student records from the data directory.

        Args:
            filename: Name of the students JSON file.

        Returns:
            List of loaded Student instances.
        """
        file_path = self.data_dir / filename
        students = KnowledgeLoader.load_students(file_path)
        self._students = {student.id: student for student in students}
        return list(self._students.values())

    def load_courses(self, filename: str = "courses.json") -> List[Course]:
        """Load course offerings from the data directory.

        Args:
            filename: Name of the courses JSON file.

        Returns:
            List of loaded Course instances.
        """
        file_path = self.data_dir / filename
        courses = KnowledgeLoader.load_courses(file_path)
        self._courses = {course.id: course for course in courses}
        return list(self._courses.values())

    def load_active_rules(self, filename: str = "active_rules.json") -> List[Rule]:
        """Load active declarative rules from the data directory.

        Args:
            filename: Name of the active rules JSON file.

        Returns:
            List of loaded active Rule instances.
        """
        file_path = self.data_dir / filename
        rules = KnowledgeLoader.load_rules(file_path, expected_status=RuleStatus.ACTIVE)
        self._active_rules = {rule.id: rule for rule in rules}
        return list(self._active_rules.values())

    def load_staged_rules(self, filename: str = "staged_rules.json") -> List[Rule]:
        """Load staged/pending declarative rules from the data directory.

        Args:
            filename: Name of the staged rules JSON file.

        Returns:
            List of loaded staged Rule instances.
        """
        file_path = self.data_dir / filename
        rules = KnowledgeLoader.load_rules(file_path, expected_status=RuleStatus.STAGED)
        self._staged_rules = {rule.id: rule for rule in rules}
        return list(self._staged_rules.values())

    def get_student(self, student_id: str) -> Student:
        """Retrieve a student by their unique identifier.

        Args:
            student_id: Target student ID (e.g. 'student_001').

        Returns:
            The matched Student instance.

        Raises:
            StudentNotFoundError: If no student matches the provided ID.
        """
        if student_id not in self._students:
            raise StudentNotFoundError(
                f"Student with identifier '{student_id}' does not exist in the knowledge base."
            )
        return self._students[student_id]

    def get_course(self, course_id: str) -> Course:
        """Retrieve a course by its unique identifier.

        Args:
            course_id: Target course code (e.g. 'CS101').

        Returns:
            The matched Course instance.

        Raises:
            CourseNotFoundError: If no course matches the provided ID.
        """
        if course_id not in self._courses:
            raise CourseNotFoundError(
                f"Course with identifier '{course_id}' does not exist in the knowledge base."
            )
        return self._courses[course_id]

    def get_rule(self, rule_id: str) -> Rule:
        """Retrieve a rule (active or staged) by its unique identifier.

        Args:
            rule_id: Target rule ID (e.g. 'RULE_MIN_GPA').

        Returns:
            The matched Rule instance.

        Raises:
            RuleNotFoundError: If no rule matches the provided ID.
        """
        if rule_id in self._active_rules:
            return self._active_rules[rule_id]
        if rule_id in self._staged_rules:
            return self._staged_rules[rule_id]
        raise RuleNotFoundError(
            f"Rule with identifier '{rule_id}' does not exist in the knowledge base."
        )

    def get_students(self) -> List[Student]:
        """Retrieve all registered students as a list."""
        return list(self._students.values())

    def get_courses(self) -> List[Course]:
        """Retrieve all registered courses as a list."""
        return list(self._courses.values())

    def get_active_rules(self) -> List[Rule]:
        """Retrieve all active declarative rules as a list."""
        return list(self._active_rules.values())

    def get_staged_rules(self) -> List[Rule]:
        """Retrieve all staged declarative rules as a list."""
        return list(self._staged_rules.values())
