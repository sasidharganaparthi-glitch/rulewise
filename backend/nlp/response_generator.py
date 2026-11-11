"""Response generator transforming symbolic reasoning traces into user-facing responses.

Phase 6: Combines LanguageModelProvider text generation with a strict deterministic
fallback generator. The symbolic result is the immutable ground truth; the LLM is
never permitted to override or contradict the engine conclusion.
"""

import logging
import re
from typing import Any, Dict, Optional, Tuple

from backend.core.exceptions import (
    InvalidModelResponseError,
    ProviderError,
    ProviderUnavailableError,
)
from backend.nlp.prompt_templates import (
    GENERAL_CHAT_SYSTEM_INSTRUCTION,
    RESPONSE_GENERATION_SYSTEM_INSTRUCTION,
    build_explanation_prompt,
)
from backend.nlp.provider import LanguageModelProvider, get_language_model_provider
from backend.schemas.explanation import Explanation, WhyExplanation, WhyNotExplanation
from backend.schemas.knowledge import Course, Student
from backend.schemas.query import QueryAction, StructuredRuleQuery

logger = logging.getLogger(__name__)


class ResponseGenerator:
    """Generates natural language responses for both rule queries and general chat."""

    def __init__(self, provider: Optional[LanguageModelProvider] = None) -> None:
        """Initialize ResponseGenerator.

        Args:
            provider: Optional LanguageModelProvider instance. Defaults to active provider.
        """
        self._provider = provider

    @property
    def provider(self) -> LanguageModelProvider:
        """Obtain active LanguageModelProvider."""
        if self._provider is not None:
            return self._provider
        return get_language_model_provider()

    # -------------------------------------------------------------------------
    # Rule Query Response Generation
    # -------------------------------------------------------------------------

    def generate_rule_response(
        self,
        user_query: str,
        structured_query: StructuredRuleQuery,
        conclusion_reached: bool,
        conclusion_value: Any,
        trace: Optional[Explanation] = None,
        why: Optional[WhyExplanation] = None,
        why_not: Optional[WhyNotExplanation] = None,
        student: Optional[Student] = None,
        course: Optional[Course] = None,
    ) -> Tuple[str, bool]:
        """Generate a natural-language response explaining the deterministic symbolic result.

        Tries the LLM provider first. If unavailable, failing, or producing
        a hallucinated/contradictory response, falls back to deterministic generation.

        Returns:
            Tuple of (response_text: str, used_fallback: bool).
        """
        student_info = student.model_dump() if student else None
        course_info = course.model_dump() if course else None

        # Build prompt embedding solely verified symbolic data
        prompt = build_explanation_prompt(
            user_query=user_query,
            structured_query=structured_query,
            conclusion_reached=conclusion_reached,
            conclusion_value=conclusion_value,
            trace=trace,
            why=why,
            why_not=why_not,
            student_info=student_info,
            course_info=course_info,
        )

        if self.provider.is_available():
            try:
                llm_response = self.provider.generate_text(
                    prompt=prompt,
                    system_instruction=RESPONSE_GENERATION_SYSTEM_INSTRUCTION,
                )

                # Security check: Ensure LLM did not hallucinate a contradiction of the symbolic ground truth
                if self._verify_response_integrity(llm_response, conclusion_reached):
                    return llm_response, False
                else:
                    logger.warning(
                        "LLM response contradicted symbolic ground truth (reached=%s); reverting to deterministic fallback.",
                        conclusion_reached,
                    )
            except (ProviderUnavailableError, ProviderError, InvalidModelResponseError, Exception) as exc:
                logger.warning("LLM response generation failed (%s); using deterministic fallback.", exc)

        # Deterministic evidence-backed fallback response
        fallback_text = self._build_deterministic_rule_response(
            structured_query=structured_query,
            conclusion_reached=conclusion_reached,
            conclusion_value=conclusion_value,
            trace=trace,
            why=why,
            why_not=why_not,
            student=student,
            course=course,
        )
        return fallback_text, True

    def _verify_response_integrity(self, text: str, conclusion_reached: bool) -> bool:
        """Verify that the generated text does not contradict the symbolic engine conclusion.

        If the engine concluded False / not eligible, the text must NOT state
        that the student is eligible or approved without qualification.
        """
        lower = text.lower()
        if not conclusion_reached:
            # Engine said FALSE. Check for false positives:
            has_affirmative = bool(
                re.search(r"\b(is eligible|has been approved|is qualified|meets all requirements)\b", lower)
            )
            has_negative = bool(
                re.search(r"\b(not eligible|is ineligible|does not meet|failed|unmet|missing|denied)\b", lower)
            )
            if has_affirmative and not has_negative:
                return False
        return True

    def _build_deterministic_rule_response(
        self,
        structured_query: StructuredRuleQuery,
        conclusion_reached: bool,
        conclusion_value: Any,
        trace: Optional[Explanation] = None,
        why: Optional[WhyExplanation] = None,
        why_not: Optional[WhyNotExplanation] = None,
        student: Optional[Student] = None,
        course: Optional[Course] = None,
    ) -> str:
        """Construct a high-quality, auditable deterministic explanation without any LLM."""
        subject_name = student.name if student else structured_query.subject
        course_name = f"{course.name} ({course.id})" if course else (structured_query.target or "the requested course")

        # 1. Action: WHY_NOT_ELIGIBLE or Conclusion is False
        if not conclusion_reached or structured_query.action == QueryAction.WHY_NOT_ELIGIBLE:
            lines = [f"No. {subject_name} is not eligible for {course_name}."]

            if why_not and why_not.blocking_conditions:
                lines.append("\nThe following requirements were not satisfied:")
                for cond in why_not.blocking_conditions:
                    lines.append(
                        f"- {cond.fact}: expected {cond.operator} {cond.expected_value}, but current record has '{cond.actual_value}'."
                    )
            elif why_not and why_not.missing_facts:
                lines.append("\nThe following required information is missing from the record:")
                for mf in why_not.missing_facts:
                    lines.append(f"- Missing fact path: {mf}")
            elif course and student:
                # Compare against course requirements directly
                unmet = []
                if student.academic_status.value != "active":
                    unmet.append(f"Academic status is '{student.academic_status.value}' (must be 'active').")
                if student.gpa < course.minimum_gpa:
                    unmet.append(f"GPA {student.gpa:.1f} is below minimum requirement of {course.minimum_gpa:.1f}.")
                for prereq in course.prerequisite_courses:
                    if prereq not in student.completed_courses:
                        unmet.append(f"Prerequisite course {prereq} has not been completed.")
                for skill in course.required_skills:
                    if skill not in student.skills:
                        unmet.append(f"Required skill '{skill}' is not verified.")
                if unmet:
                    lines.append("\nUnmet requirements:")
                    for item in unmet:
                        lines.append(f"- {item}")
            else:
                lines.append(f"\nThe symbolic rule engine did not find sufficient criteria to grant eligibility.")

            return "\n".join(lines)

        # 2. Action: WHY_ELIGIBLE or Conclusion is True
        lines = [f"Yes. {subject_name} is eligible for {course_name}."]

        if why and why.derivation_chain:
            lines.append("\nReasoning Trace:")
            for step in why.derivation_chain:
                lines.append(f"- Rule '{step.rule_name}' fired at inference step {step.step}.")
            if why.root_facts:
                lines.append("\nVerified Student Evidence:")
                for k, v in sorted(why.root_facts.items()):
                    lines.append(f"- {k}: {v}")
        elif trace and trace.trace_steps:
            lines.append(f"\nThe decision was verified through {len(trace.trace_steps)} deterministic inference rule steps.")
            for step in trace.trace_steps:
                lines.append(f"- Step {step.step}: {step.rule_name} satisfied.")
        elif student and course:
            lines.append(
                f"\n{subject_name} meets all requirements: active academic status, "
                f"GPA {student.gpa:.1f} >= {course.minimum_gpa:.1f}, "
                f"completed prerequisites ({', '.join(course.prerequisite_courses) if course.prerequisite_courses else 'None'}), "
                f"and verified skills ({', '.join(course.required_skills) if course.required_skills else 'None'})."
            )

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # General Chat Response Generation
    # -------------------------------------------------------------------------

    def generate_general_chat_response(self, user_message: str) -> Tuple[str, bool]:
        """Generate a response for general conversational inquiries.

        If the provider is available, generates a natural assistant response.
        If unavailable, returns a friendly, controlled fallback notice.

        Returns:
            Tuple of (response_text: str, used_fallback: bool).
        """
        lowered = user_message.lower().strip()

        # Fast path for instantaneous greetings if provider is available (<0.1ms latency)
        if self.provider.is_available() and re.match(r"^(hi+|hello+|hey+|howdy|greetings|hola|good\s+(morning|afternoon|evening))\b", lowered):
            return (
                "Hello! I am RuleWise AI, powered by Gemini and equipped with neuro-symbolic reasoning capabilities. "
                "How can I help you today? You can ask me any question, brainstorm ideas, write or debug code, "
                "or evaluate rule-based policies (such as 'Is Arun eligible for AI?').",
                False,
            )

        provider_had_error = False
        if self.provider.is_available():
            try:
                response = self.provider.generate_text(
                    prompt=user_message,
                    system_instruction=GENERAL_CHAT_SYSTEM_INSTRUCTION,
                )
                return response, False
            except (ProviderUnavailableError, ProviderError, Exception) as exc:
                logger.warning("General chat LLM generation failed (%s); using fallback notice.", exc)
                provider_had_error = True

        lowered = user_message.lower().strip()

        # Context-aware offline responses
        if any(w in lowered for w in ("what can you do", "help", "capability", "capabilities", "features")):
            note_clause = (
                "Free-form conversational AI is temporarily operating in fallback mode due to an upstream model or network issue."
                if provider_had_error
                else "Free-form conversational AI is currently operating in offline mode because GEMINI_API_KEY is not configured in the environment."
            )
            text = (
                "RuleWise AI is an explainable neuro-symbolic academic advisory assistant.\n\n"
                "Available Capabilities:\n"
                "• Course Eligibility Evaluation: Deterministically check if a student meets GPA, prerequisite, and skill requirements.\n"
                "• Explainable Reasoning: Transparently inspect why a student is eligible or which specific criteria are blocking enrollment.\n"
                "• Academic Knowledge Base: Direct access to student profiles (Arun Sharma, Priya Patel, Carlos Gomez, Mei Lin) and course catalogs (AI101, CS101, CS201, MA101).\n\n"
                f"Note: {note_clause} All symbolic policy evaluations remain 100% operational."
            )
            return text, True

        if any(w in lowered for w in ("student", "students", "who is registered", "list students")):
            text = (
                "The academic knowledge base contains the following registered students:\n"
                "• Arun Sharma (student_001): Active status, GPA 8.7, completed CS101, MA101.\n"
                "• Priya Patel (student_002): Active status, GPA 7.2, completed CS101.\n"
                "• Carlos Gomez (student_003): Probation status, GPA 6.2.\n"
                "• Mei Lin (student_004): Active status, GPA 9.4, completed CS101, MA101, AI101, CS201.\n\n"
                "You can evaluate any student's eligibility by asking, for example: 'Is Priya eligible for CS201?'"
            )
            return text, True

        if any(w in lowered for w in ("course", "courses", "curriculum", "catalog", "list courses")):
            text = (
                "The academic curriculum contains the following courses:\n"
                "• AI101: Introduction to Artificial Intelligence (Min GPA 7.0, Prereqs: CS101, MA101, Skills: python, data_structures)\n"
                "• CS101: Programming Fundamentals (Min GPA 6.0, Prereqs: None, Skills: None)\n"
                "• CS201: Data Structures and Algorithms (Min GPA 6.5, Prereqs: CS101, Skills: python)\n"
                "• MA101: Calculus (Min GPA 6.0, Prereqs: None, Skills: None)\n\n"
                "Ask 'What are the requirements for AI101?' or 'Can Arun take AI101?' to evaluate policies."
            )
            return text, True

        # General offline fallback notice
        status_clause = (
            "(temporarily operating in fallback mode due to an upstream model or network issue)"
            if provider_had_error
            else "(operating in offline fallback mode because the Gemini API key is not configured in the environment)"
        )
        fallback_notice = (
            "Hello! I am RuleWise AI, an explainable neuro-symbolic academic advisory assistant.\n\n"
            f"General AI conversation is currently unavailable {status_clause}, "
            "but the deterministic rule engine and academic knowledge base are fully operational.\n\n"
            "You can query course eligibility, prerequisite checks, and policy rules, for example:\n"
            "• 'Is Arun eligible for AI course?'\n"
            "• 'Can Priya enroll in CS201?'\n"
            "• 'Why is Arun eligible for AI101?'\n"
            "• 'Why is Priya not eligible for AI101?'\n"
            "• 'What are the requirements for AI101?'"
        )
        return fallback_notice, True
