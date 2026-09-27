"""In-memory Working Memory and fact resolution for RuleWise AI.

This module provides isolated, deterministic storage, sequence recency tracking,
and provenance tracking for facts and derived assertions during rule engine execution.
No database, no persistence, and no arbitrary code execution.
"""

import copy
from typing import Any, Dict, List, Optional, Set
from backend.core.exceptions import FactResolutionError
from backend.schemas.rule import FactProvenance


class WorkingMemory:
    """Isolated in-memory repository of facts available for rule evaluation."""

    def __init__(self, initial_facts: Optional[Dict[str, Any]] = None) -> None:
        """Initialize working memory with an optional dictionary of initial facts.

        Args:
            initial_facts: Initial fact dictionary (e.g. {"student": {...}, "course": {...}}).
        """
        self._facts: Dict[str, Any] = {}
        self._derived_facts: Dict[str, Any] = {}
        self._fact_step: Dict[str, int] = {}
        self._provenance: Dict[str, FactProvenance] = {}
        self._precluded_facts: Set[str] = set()

        if initial_facts:
            for key, val in initial_facts.items():
                self.add_fact(key, val)

    def _validate_path(self, path: str) -> List[str]:
        """Validate fact path string and return sanitized path segments.

        Raises:
            FactResolutionError: If path is empty or contains illegal traversal segments.
        """
        if not path or not isinstance(path, str):
            raise FactResolutionError(f"Fact path must be a non-empty string; got {type(path).__name__}")

        segments = path.strip().split(".")
        for segment in segments:
            if not segment:
                raise FactResolutionError(f"Fact path '{path}' contains an empty segment.")
            if segment.startswith("__"):
                raise FactResolutionError(f"Fact path '{path}' contains forbidden dunder segment: '{segment}'.")
        return segments

    def add_fact(self, path: str, value: Any) -> None:
        """Add or overwrite an initial fact at the given path in working memory.

        Supports both root facts (e.g. 'student') and nested dotted paths (e.g. 'student.gpa').

        Args:
            path: Key or dotted path for the fact.
            value: Value of the fact (primitives, dicts, lists, etc.).
        """
        segments = self._validate_path(path)

        # Set in root dictionary if single segment
        if len(segments) == 1:
            self._facts[segments[0]] = value
            self._fact_step[path] = 0
            self._provenance[path] = FactProvenance(path=path, value=value, is_derived=False, step=0)
            return

        # Ensure nested hierarchy exists
        current = self._facts
        for segment in segments[:-1]:
            if segment not in current or not isinstance(current[segment], dict):
                current[segment] = {}
            current = current[segment]
        current[segments[-1]] = value

        # Also store direct path for fast O(1) direct lookup
        self._facts[path] = value
        self._fact_step[path] = 0
        self._provenance[path] = FactProvenance(path=path, value=value, is_derived=False, step=0)

    def get_fact(self, path: str) -> Any:
        """Retrieve the value of a fact at the specified path.

        Args:
            path: Dot-separated fact path (e.g. 'student.gpa', 'student.skills').

        Returns:
            Resolved fact value.

        Raises:
            FactResolutionError: If the fact path cannot be resolved from working memory.
        """
        segments = self._validate_path(path)

        # Direct exact match check
        if path in self._facts:
            return self._facts[path]

        # First root segment check
        root_key = segments[0]
        if root_key not in self._facts:
            raise FactResolutionError(
                f"Fact path '{path}' could not be resolved: root key '{root_key}' does not exist in working memory."
            )

        current = self._facts[root_key]
        for idx, segment in enumerate(segments[1:], start=1):
            if isinstance(current, dict):
                if segment in current:
                    current = current[segment]
                else:
                    subpath = ".".join(segments[: idx + 1])
                    raise FactResolutionError(
                        f"Fact path '{path}' could not be resolved: segment '{segment}' not found at '{subpath}'."
                    )
            elif isinstance(current, (list, tuple)):
                if segment.isdigit():
                    i = int(segment)
                    if 0 <= i < len(current):
                        current = current[i]
                    else:
                        raise FactResolutionError(
                            f"Fact path '{path}' index {i} out of bounds for list of length {len(current)}."
                        )
                else:
                    raise FactResolutionError(
                        f"Fact path '{path}' cannot traverse list with non-integer segment '{segment}'."
                    )
            else:
                raise FactResolutionError(
                    f"Fact path '{path}' cannot traverse into non-traversable type: {type(current).__name__}."
                )

        return current

    def has_fact(self, path: str) -> bool:
        """Check whether a fact exists and is resolvable at the specified path.

        Args:
            path: Dotted fact path.

        Returns:
            True if fact exists, False otherwise.
        """
        try:
            self.get_fact(path)
            return True
        except FactResolutionError:
            return False

    def update_fact(self, path: str, value: Any) -> None:
        """Update the value of an existing fact or create it if not present.

        Args:
            path: Key or dotted path.
            value: New value.
        """
        self.add_fact(path, value)

    def add_derived_fact(
        self,
        path: str,
        value: Any,
        step: int = 0,
        source_rule_id: Optional[str] = None,
    ) -> None:
        """Add a newly derived fact produced by a rule consequence.

        Handles negative preclusion:
        If value is False, path is marked as precluded, overriding any positive derivation.
        If value is True but path is already precluded by False, the preclusion remains effective.

        Args:
            path: Target fact path.
            value: Inferred value.
            step: Deterministic inference step sequence number.
            source_rule_id: Identifier of the firing rule that derived this fact.
        """
        segments = self._validate_path(path)

        # Preclusion conflict resolution
        effective_value = value
        if value is False:
            self._precluded_facts.add(path)
        elif value is True and path in self._precluded_facts:
            effective_value = False

        # Set in root or nested hierarchy
        if len(segments) == 1:
            self._facts[segments[0]] = effective_value
        else:
            current = self._facts
            for segment in segments[:-1]:
                if segment not in current or not isinstance(current[segment], dict):
                    current[segment] = {}
                current = current[segment]
            current[segments[-1]] = effective_value

        self._facts[path] = effective_value
        self._derived_facts[path] = effective_value
        self._fact_step[path] = step
        self._provenance[path] = FactProvenance(
            path=path,
            value=effective_value,
            is_derived=True,
            step=step,
            rule_id=source_rule_id,
        )

    def get_fact_step(self, path: str) -> int:
        """Return the sequence step number at which the fact was derived.

        Initial facts return 0.
        """
        if path in self._fact_step:
            return self._fact_step[path]
        return 0

    def get_provenance(self, path: str) -> Optional[FactProvenance]:
        """Retrieve the origin provenance record for a given fact path."""
        return self._provenance.get(path)

    def get_all_provenance(self) -> Dict[str, FactProvenance]:
        """Return a copy of the complete fact provenance map."""
        return copy.deepcopy(self._provenance)

    def get_derived_facts(self) -> Dict[str, Any]:
        """Return a copy of all facts derived by rule execution.

        Returns:
            Dictionary of derived fact paths to their asserted values.
        """
        return copy.deepcopy(self._derived_facts)

    def get_all_facts(self) -> Dict[str, Any]:
        """Return a deep copy of all known facts in working memory.

        Returns:
            Dictionary containing all stored facts.
        """
        return copy.deepcopy(self._facts)

    def clone(self) -> "WorkingMemory":
        """Return an isolated deep copy of this working memory instance."""
        cloned = WorkingMemory()
        cloned._facts = copy.deepcopy(self._facts)
        cloned._derived_facts = copy.deepcopy(self._derived_facts)
        cloned._fact_step = copy.deepcopy(self._fact_step)
        cloned._provenance = copy.deepcopy(self._provenance)
        cloned._precluded_facts = copy.deepcopy(self._precluded_facts)
        return cloned

    def clear(self) -> None:
        """Reset working memory, removing all stored and derived facts."""
        self._facts.clear()
        self._derived_facts.clear()
        self._fact_step.clear()
        self._provenance.clear()
        self._precluded_facts.clear()
