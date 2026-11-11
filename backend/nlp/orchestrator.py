"""RuleWise AI central service orchestrator coordinating NLP and symbolic reasoning (Phase 6).

Implements the neuro-symbolic pipeline:
1. Input sanitization and security boundary check.
2. Intent classification (GENERAL_CHAT vs RULE_QUERY).
3. If GENERAL_CHAT: Generates conversational response.
4. If RULE_QUERY:
   - Extracts validated structured query.
   - Retrieves student and course from existing Knowledge Base.
   - Constructs isolated WorkingMemory.
   - Synthesizes declarative rule for course if applicable.
   - Invokes EXISTING deterministic InferenceEngine (sole decision authority).
   - Generates Phase 5 Explanation / Why / WhyNot traces.
   - Generates response via ResponseGenerator strictly grounded in the symbolic result.
"""

import logging
from typing import Any, Dict, List, Optional

from backend.core.security import sanitize_user_input
from backend.engine.inference_engine import InferenceEngine
from backend.engine.working_memory import WorkingMemory
from backend.explainability.contrastive import build_why_not
from backend.explainability.trace_builder import build_trace, build_why
from backend.knowledge.loader import KnowledgeBase
from backend.nlp.live_search import LiveInformationService, is_live_information_query
from backend.nlp.provider import LanguageModelProvider, get_language_model_provider
from backend.nlp.query_parser import QueryParser
from backend.nlp.response_generator import ResponseGenerator
from backend.nlp.rule_synthesizer import synthesize_course_eligibility_rule
from backend.schemas.knowledge import Course, Student
from backend.schemas.query import (
    ChatResponse,
    QueryAction,
    StructuredRuleQuery,
    UserIntent,
)

logger = logging.getLogger(__name__)


class RuleWiseOrchestrator:
    """Orchestrates natural language interpretation, live web grounding, and deterministic symbolic reasoning."""

    def __init__(
        self,
        knowledge_base: Optional[KnowledgeBase] = None,
        provider: Optional[LanguageModelProvider] = None,
        query_parser: Optional[QueryParser] = None,
        response_generator: Optional[ResponseGenerator] = None,
        live_service: Optional[LiveInformationService] = None,
    ) -> None:
        """Initialize RuleWiseOrchestrator with dependencies."""
        self.kb = knowledge_base or KnowledgeBase()
        self.provider = provider or get_language_model_provider()
        self.query_parser = query_parser or QueryParser(
            provider=self.provider, knowledge_base=self.kb
        )
        self.response_generator = response_generator or ResponseGenerator(
            provider=self.provider
        )
        self.live_service = live_service or LiveInformationService()

    def process_message(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatResponse:
        """Process an incoming user message through the neuro-symbolic pipeline.

        Args:
            message: Raw user input text.
            conversation_history: Optional list of recent turns for multi-turn conversation.

        Returns:
            Validated ChatResponse containing response text, intent, and symbolic evidence.
        """
        # 1. Sanitize user input
        try:
            cleaned_message = sanitize_user_input(message)
        except ValueError as val_err:
            return ChatResponse(
                message=f"Invalid request: {val_err}",
                intent=UserIntent.GENERAL_CHAT,
                error=str(val_err),
            )

        # Format prompt with context if history is provided
        context_prompt = cleaned_message
        if conversation_history:
            recent_turns = conversation_history[-6:]
            history_lines = []
            for m in recent_turns:
                sender = "User" if m.get("sender") == "user" else "Assistant"
                text = (m.get("content") or "").strip()
                if text:
                    history_lines.append(f"{sender}: {text}")
            if history_lines:
                context_prompt = (
                    "Previous conversation:\n"
                    + "\n".join(history_lines)
                    + f"\n\nUser: {cleaned_message}\n\nAssistant:"
                )

        # 2. Intent classification
        intent_res, intent_fallback = self.query_parser.classify_intent(cleaned_message)

        # 3. Handle GENERAL_CHAT path
        if intent_res.intent == UserIntent.GENERAL_CHAT:
            # Check if query requests live/current updates (Requirement 7)
            if is_live_information_query(cleaned_message) and self.provider.is_available():
                try:
                    live_res = self.live_service.answer_with_live_grounding(
                        cleaned_message, self.provider, conversation_context=context_prompt
                    )
                    return ChatResponse(
                        message=live_res["text"],
                        intent=UserIntent.GENERAL_CHAT,
                        used_fallback=not live_res.get("is_live_verified", False),
                    )
                except Exception as live_err:
                    logger.warning("Live information grounding encountered error: %s", live_err)

            response_text, gen_fallback = self.response_generator.generate_general_chat_response(
                context_prompt
            )
            return ChatResponse(
                message=response_text,
                intent=UserIntent.GENERAL_CHAT,
                used_fallback=intent_fallback or gen_fallback,
            )

        # 4. Handle RULE_QUERY path
        return self._execute_rule_query(cleaned_message, intent_fallback, context_prompt=context_prompt)

    def _execute_rule_query(
        self,
        message: str,
        intent_fallback: bool,
        context_prompt: Optional[str] = None,
    ) -> ChatResponse:
        """Execute the deterministic rule query pipeline."""
        ctx = context_prompt or message

        # 4a. Extract validated structured query
        structured_query, query_fallback = self.query_parser.extract_structured_query(message)
        if structured_query is None:
            if self.provider.is_available():
                response_text, gen_fallback = self.response_generator.generate_general_chat_response(ctx)
                return ChatResponse(
                    message=response_text,
                    intent=UserIntent.GENERAL_CHAT,
                    used_fallback=gen_fallback,
                )
            return ChatResponse(
                message="I recognized this as a rule inquiry, but could not identify the student or course in your message. Please specify a student (e.g. 'Arun') and a course (e.g. 'AI').",
                intent=UserIntent.RULE_QUERY,
                used_fallback=True,
                error="StructuredQueryExtractionFailed",
            )

        # 4b. Course-level requirement inquiry (when no specific student was specified)
        is_generic_subject = (
            not structured_query.subject
            or structured_query.subject.lower() in ("unknown", "none", "anyone", "student", "someone", "there")
        )
        if structured_query.target and is_generic_subject:
            is_req_inquiry = any(
                w in message.lower()
                for w in ("require", "requirement", "requirements", "prereq", "prerequisite", "prerequisites", "criteria", "eligibility", "standing", "rule", "policy", "syllabus")
            )
            if not is_req_inquiry and self.provider.is_available():
                response_text, gen_fallback = self.response_generator.generate_general_chat_response(ctx)
                return ChatResponse(
                    message=response_text,
                    intent=UserIntent.GENERAL_CHAT,
                    used_fallback=gen_fallback,
                )
            course = self.query_parser.resolve_course(structured_query.target)
            if course:
                prereqs = ", ".join(course.prerequisite_courses) if course.prerequisite_courses else "None"
                skills = ", ".join(course.required_skills) if course.required_skills else "None"
                return ChatResponse(
                    message=(
                        f"Requirements for {course.name} ({course.id}):\n"
                        f"• Minimum GPA: {course.minimum_gpa:.1f}\n"
                        f"• Prerequisite Courses: {prereqs}\n"
                        f"• Required Verified Skills: {skills}\n"
                        f"• Academic Standing: Active status required"
                    ),
                    intent=UserIntent.RULE_QUERY,
                    structured_query=structured_query,
                    symbolic_result={
                        "course_id": course.id,
                        "course_name": course.name,
                        "minimum_gpa": course.minimum_gpa,
                        "prerequisites": course.prerequisite_courses,
                        "required_skills": course.required_skills,
                        "conclusion": f"course_info_{course.id.lower()}",
                        "conclusion_reached": True,
                    },
                    used_fallback=query_fallback,
                )
            else:
                available = [f"{c.name} ({c.id})" for c in self.kb.get_courses()]
                return ChatResponse(
                    message=(
                        f"Course '{structured_query.target}' was not found in the academic curriculum. "
                        f"Available courses include: {', '.join(available)}."
                    ),
                    intent=UserIntent.RULE_QUERY,
                    structured_query=structured_query,
                    used_fallback=True,
                    error="CourseNotFoundError",
                )

        # 4c. Resolve student entity from Knowledge Base
        student: Optional[Student] = self.query_parser.resolve_student(structured_query.subject)
        if student is None:
            is_explicit_student_inquiry = any(
                w in message.lower()
                for w in ("eligible", "eligibility", "ineligible", "admit", "prerequisite", "prereq", "enroll", "cleared", "gpa", "student_")
            )
            if not is_explicit_student_inquiry and self.provider.is_available():
                response_text, gen_fallback = self.response_generator.generate_general_chat_response(ctx)
                return ChatResponse(
                    message=response_text,
                    intent=UserIntent.GENERAL_CHAT,
                    used_fallback=gen_fallback,
                )
            available = [s.name for s in self.kb.get_students()]
            return ChatResponse(
                message=(
                    f"Student '{structured_query.subject}' was not found in the academic knowledge base. "
                    f"Registered students include: {', '.join(available)}."
                ),
                intent=UserIntent.RULE_QUERY,
                structured_query=structured_query,
                used_fallback=True,
                error="StudentNotFoundError",
            )

        # 4d. Resolve course entity from Knowledge Base (if specified)
        course: Optional[Course] = None
        if structured_query.target:
            course = self.query_parser.resolve_course(structured_query.target)
            if course is None:
                available = [f"{c.name} ({c.id})" for c in self.kb.get_courses()]
                return ChatResponse(
                    message=(
                        f"Course '{structured_query.target}' was not found in the academic curriculum. "
                        f"Available courses include: {', '.join(available)}."
                    ),
                    intent=UserIntent.RULE_QUERY,
                    structured_query=structured_query,
                    used_fallback=True,
                    error="CourseNotFoundError",
                )

        # If student resolved but course was not specified
        if not course:
            status_desc = student.academic_status.value
            courses_str = ", ".join(student.completed_courses) if student.completed_courses else "None"
            skills_str = ", ".join(student.skills) if student.skills else "None"
            return ChatResponse(
                message=(
                    f"{student.name} is registered with academic status '{status_desc}' and a GPA of {student.gpa:.1f}.\n"
                    f"Completed Courses: {courses_str}\n"
                    f"Verified Skills: {skills_str}\n\n"
                    f"To evaluate course eligibility, please specify a course (e.g. 'Is {student.name.split()[0]} eligible for AI101?')."
                ),
                intent=UserIntent.RULE_QUERY,
                structured_query=structured_query,
                symbolic_result={
                    "student_id": student.id,
                    "student_name": student.name,
                    "academic_status": status_desc,
                    "gpa": student.gpa,
                    "completed_courses": student.completed_courses,
                    "skills": student.skills,
                    "conclusion": "student_profile_retrieved",
                    "conclusion_reached": True,
                },
                used_fallback=query_fallback,
            )

        # 4e. Construct isolated Working Memory
        wm = WorkingMemory()
        wm.add_fact("student", student.model_dump())
        wm.add_fact("course", course.model_dump())

        # 4f. Gather rules: active rules + course eligibility rule
        rules = list(self.kb.get_active_rules())
        course_rule = synthesize_course_eligibility_rule(course)
        rules.append(course_rule)

        # 4g. Execute deterministic forward-chaining inference (LLM NEVER participates here)
        inference_result = InferenceEngine.infer(rules, wm)

        # 4h. Evaluate conclusion
        conclusion_key = f"eligible_for_{course.id.lower()}"
        conclusion_val = inference_result.final_facts.get(conclusion_key)
        conclusion_reached = bool(conclusion_val) if conclusion_val is not None else False

        # 4h. Generate Phase 5 explainability models
        trace = build_trace(inference_result, rules, conclusion=conclusion_key)
        why = build_why(inference_result, rules, conclusion=conclusion_key) if conclusion_reached else None
        why_not = (
            build_why_not(inference_result, rules, conclusion=conclusion_key)
            if not conclusion_reached
            else None
        )

        # 4i. Generate natural language response
        response_text, resp_fallback = self.response_generator.generate_rule_response(
            user_query=message,
            structured_query=structured_query,
            conclusion_reached=conclusion_reached,
            conclusion_value=conclusion_val,
            trace=trace,
            why=why,
            why_not=why_not,
            student=student,
            course=course,
        )

        # 4j. Assemble structured response
        symbolic_summary: Dict[str, Any] = {
            "conclusion": conclusion_key,
            "value": conclusion_val,
            "conclusion_reached": conclusion_reached,
            "fired_rule_ids": inference_result.fired_rule_ids,
            "inference_step_count": inference_result.inference_step_count,
            "termination_reason": inference_result.termination_reason,
            "student_id": student.id,
            "course_id": course.id if course else None,
        }

        explanation_summary: Dict[str, Any] = {
            "total_steps": trace.total_steps,
            "supporting_rules": trace.supporting_rules,
            "termination_reason": trace.termination_reason,
            "why_derivation_chain": [s.rule_id for s in why.derivation_chain] if why else [],
            "blocking_conditions": [
                {"fact": c.fact, "operator": c.operator, "expected": c.expected_value, "actual": c.actual_value}
                for c in (why_not.blocking_conditions if why_not else [])
            ],
        }

        return ChatResponse(
            message=response_text,
            intent=UserIntent.RULE_QUERY,
            structured_query=structured_query,
            symbolic_result=symbolic_summary,
            explanation=explanation_summary,
            used_fallback=intent_fallback or query_fallback or resp_fallback,
        )
