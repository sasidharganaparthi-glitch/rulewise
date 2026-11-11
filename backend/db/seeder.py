"""Seed initial official domains, declarative rules, and default accounts in RuleWise AI.

Preserves existing academic rules while introducing multi-domain official collections:
1. Academic Policy & Course Eligibility (Official)
2. University Admissions (Official)
3. Merit & Need-Based Scholarships (Official)
4. Recruitment & HR Screening (Official)
5. Financial Loan Eligibility (Official)
6. Enterprise Compliance & Data Privacy (Official)
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from backend.db.database import DatabaseManager, get_db_manager
from backend.db.repositories import DomainRepository, RuleRepository, UserRepository

logger = logging.getLogger(__name__)


def seed_database(db: DatabaseManager) -> None:
    """Populate database with default users, official domains, and starter rules."""
    user_repo = UserRepository(db)
    domain_repo = DomainRepository(db)
    rule_repo = RuleRepository(db)

    # 1. Seed Owner Account (Secure Root Provisioning)
    from backend.core.config import get_settings
    settings = get_settings()

    owner_email = getattr(settings, "OWNER_EMAIL", "sasiganaparthi@gmail.com")
    owner_pwd = getattr(settings, "ADMIN_INITIAL_PASSWORD", None) or "Admin#RuleWise2026"

    owner = user_repo.get_by_email(owner_email) or user_repo.get_by_username("sasiganaparthi")
    if not owner:
        owner = user_repo.create_user(
            username="sasiganaparthi",
            password=owner_pwd,
            email=owner_email,
            role="owner",
        )
        logger.info("Provisioned initial authorized owner account: %s", owner_email)
    elif owner.get("role") != "owner":
        user_repo.update_user_role(owner["id"], "owner")
        logger.info("Elevated account %s to owner role.", owner_email)

    admin = owner

    demo_user = user_repo.get_by_username("demo_user")
    if not demo_user:
        demo_user = user_repo.create_user(
            username="demo_user",
            password="demo123",
            email="demo@rulewise.ai",
            role="user",
        )
        logger.info("Created default user account: demo_user")

    # 2. Domain 1: RuleWise Eligibility (Preserving original files)
    academic_domain = domain_repo.get_by_slug("academic-eligibility")
    if not academic_domain:
        academic_domain = domain_repo.create_domain(
            name="RuleWise Policy & Eligibility",
            slug="academic-eligibility",
            description="Evaluates student course eligibility, prerequisite chains, and minimum GPA requirements.",
            category="education",
            is_official=True,
            schema_fields=[
                {"name": "student.id", "type": "string", "label": "Student ID", "description": "Unique student identifier"},
                {"name": "student.name", "type": "string", "label": "Student Name", "description": "Full name"},
                {"name": "student.gpa", "type": "number", "label": "GPA", "description": "Cumulative GPA on 10.0 scale"},
                {"name": "student.academic_status", "type": "string", "label": "Status", "description": "active, probation, or suspended"},
                {"name": "student.completed_courses", "type": "list", "label": "Completed Courses", "description": "List of course IDs passed"},
                {"name": "target_course.id", "type": "string", "label": "Target Course", "description": "Course requested for enrollment"},
            ],
            created_by=admin["id"],
            domain_id="dom_academic",
        )
        logger.info("Created official domain: Academic Policy")

        # Load existing active_rules.json if present
        data_path = Path(__file__).resolve().parent.parent / "knowledge" / "data" / "active_rules.json"
        if data_path.is_file():
            try:
                active_rules = json.loads(data_path.read_text(encoding="utf-8"))
                for r in active_rules:
                    rule_repo.create_rule(
                        domain_id=academic_domain["id"],
                        name=r["name"],
                        rule_id=r["id"],
                        description=r.get("description", ""),
                        priority=r.get("priority", 50),
                        status=r.get("status", "active"),
                        is_official=True,
                        condition=r["condition"],
                        consequence=r["consequence"],
                        metadata=r.get("metadata", {}),
                        created_by=admin["id"],
                    )
            except Exception as e:
                logger.error("Failed to seed active_rules.json: %s", e)

    # 3. Domain 2: Recruitment & HR Screening
    recruitment_domain = domain_repo.get_by_slug("recruitment-screening")
    if not recruitment_domain:
        recruitment_domain = domain_repo.create_domain(
            name="Recruitment & HR Screening",
            slug="recruitment-screening",
            description="Automated deterministic candidate pre-screening for software engineering roles.",
            category="recruitment",
            is_official=True,
            schema_fields=[
                {"name": "candidate.name", "type": "string", "label": "Candidate Name"},
                {"name": "candidate.years_experience", "type": "number", "label": "Years Experience"},
                {"name": "candidate.skills", "type": "list", "label": "Technical Skills"},
                {"name": "candidate.degree", "type": "string", "label": "Highest Degree"},
                {"name": "candidate.notice_period_days", "type": "number", "label": "Notice Period (Days)"},
            ],
            created_by=admin["id"],
            domain_id="dom_recruitment",
        )
        # Seed Recruitment Rules
        rule_repo.create_rule(
            domain_id=recruitment_domain["id"],
            name="Senior Engineer Experience Threshold",
            rule_id="RULE_RECRUIT_SENIOR_EXP",
            description="Candidate must have at least 5 years of relevant engineering experience.",
            priority=80,
            status="active",
            is_official=True,
            condition={"field": "candidate.years_experience", "operator": ">=", "value": 5},
            consequence={
                "action": "grant_experience_clearance",
                "params": {"experience_qualified": True, "level": "senior"},
                "description": "Candidate clears senior experience requirement.",
            },
            metadata={"category": "experience", "role": "Senior Software Engineer"},
            created_by=admin["id"],
        )
        rule_repo.create_rule(
            domain_id=recruitment_domain["id"],
            name="Core Python Skill Requirement",
            rule_id="RULE_RECRUIT_PYTHON_SKILL",
            description="Candidate must possess verified Python programming proficiency.",
            priority=70,
            status="active",
            is_official=True,
            condition={"field": "candidate.skills", "operator": "IN", "value": "Python"},
            consequence={
                "action": "grant_skill_clearance",
                "params": {"python_verified": True},
                "description": "Candidate skills meet primary language requirements.",
            },
            metadata={"category": "skills"},
            created_by=admin["id"],
        )
        rule_repo.create_rule(
            domain_id=recruitment_domain["id"],
            name="Interview Shortlist Qualification",
            rule_id="RULE_RECRUIT_FINAL_SHORTLIST",
            description="Shortlists candidate when both experience and skill clearances are satisfied.",
            priority=90,
            status="active",
            is_official=True,
            condition={
                "operator": "AND",
                "conditions": [
                    {"field": "candidate.years_experience", "operator": ">=", "value": 5},
                    {"field": "candidate.skills", "operator": "IN", "value": "Python"},
                    {"field": "candidate.notice_period_days", "operator": "<=", "value": 60},
                ],
            },
            consequence={
                "action": "shortlist_candidate",
                "params": {"shortlisted": True, "stage": "technical_interview"},
                "description": "Candidate shortlisted for technical round.",
            },
            metadata={"category": "shortlist"},
            created_by=admin["id"],
        )

    # 4. Domain 3: Financial Loan Eligibility
    loan_domain = domain_repo.get_by_slug("loan-eligibility")
    if not loan_domain:
        loan_domain = domain_repo.create_domain(
            name="Retail Loan & Credit Underwriting",
            slug="loan-eligibility",
            description="Deterministic evaluation of personal loan and mortgage applications against underwriting criteria.",
            category="finance",
            is_official=True,
            schema_fields=[
                {"name": "applicant.name", "type": "string", "label": "Applicant Name"},
                {"name": "applicant.credit_score", "type": "number", "label": "Credit Score (300-850)"},
                {"name": "applicant.annual_income", "type": "number", "label": "Annual Income ($)"},
                {"name": "applicant.debt_to_income_ratio", "type": "number", "label": "Debt-to-Income % (DTI)"},
                {"name": "applicant.bankruptcies", "type": "number", "label": "Prior Bankruptcies"},
            ],
            created_by=admin["id"],
            domain_id="dom_loan",
        )
        rule_repo.create_rule(
            domain_id=loan_domain["id"],
            name="Minimum Credit Score Clearance",
            rule_id="RULE_LOAN_CREDIT_SCORE",
            description="Applicant credit score must be 680 or higher.",
            priority=95,
            status="active",
            is_official=True,
            condition={"field": "applicant.credit_score", "operator": ">=", "value": 680},
            consequence={
                "action": "grant_credit_clearance",
                "params": {"credit_tier": "prime", "credit_cleared": True},
                "description": "Credit score satisfies standard loan threshold.",
            },
            metadata={"category": "credit"},
            created_by=admin["id"],
        )
        rule_repo.create_rule(
            domain_id=loan_domain["id"],
            name="Debt-to-Income Ratio Limit",
            rule_id="RULE_LOAN_DTI_LIMIT",
            description="Applicant debt-to-income ratio must not exceed 40 percent.",
            priority=85,
            status="active",
            is_official=True,
            condition={"field": "applicant.debt_to_income_ratio", "operator": "<=", "value": 40},
            consequence={
                "action": "grant_dti_clearance",
                "params": {"dti_cleared": True},
                "description": "DTI within acceptable underwriting limits.",
            },
            metadata={"category": "dti"},
            created_by=admin["id"],
        )
        rule_repo.create_rule(
            domain_id=loan_domain["id"],
            name="Full Prime Loan Approval",
            rule_id="RULE_LOAN_PRIME_APPROVAL",
            description="Approves loan when credit score >= 720, DTI <= 35, and income >= 50000.",
            priority=100,
            status="active",
            is_official=True,
            condition={
                "operator": "AND",
                "conditions": [
                    {"field": "applicant.credit_score", "operator": ">=", "value": 720},
                    {"field": "applicant.debt_to_income_ratio", "operator": "<=", "value": 35},
                    {"field": "applicant.annual_income", "operator": ">=", "value": 50000},
                    {"field": "applicant.bankruptcies", "operator": "==", "value": 0},
                ],
            },
            consequence={
                "action": "approve_prime_loan",
                "params": {"decision": "Approved", "interest_rate": 5.75, "approved": True},
                "description": "Application approved at prime interest rate.",
            },
            metadata={"category": "approval"},
            created_by=admin["id"],
        )

    # 5. Domain 4: Merit & Need-Based Scholarships
    scholarship_domain = domain_repo.get_by_slug("scholarships")
    if not scholarship_domain:
        scholarship_domain = domain_repo.create_domain(
            name="Scholarship & Financial Aid Evaluation",
            slug="scholarships",
            description="Verifies merit and financial criteria for academic grant and scholarship disbursements.",
            category="education",
            is_official=True,
            schema_fields=[
                {"name": "student.gpa", "type": "number", "label": "GPA"},
                {"name": "student.household_income", "type": "number", "label": "Household Income ($)"},
                {"name": "student.community_hours", "type": "number", "label": "Community Service Hours"},
                {"name": "student.major", "type": "string", "label": "Field of Study"},
            ],
            created_by=admin["id"],
            domain_id="dom_scholarships",
        )
        rule_repo.create_rule(
            domain_id=scholarship_domain["id"],
            name="Presidential Merit Scholarship",
            rule_id="RULE_SCHOLARSHIP_MERIT",
            description="Grants full merit scholarship for GPA >= 9.0 and community hours >= 50.",
            priority=90,
            status="active",
            is_official=True,
            condition={
                "operator": "AND",
                "conditions": [
                    {"field": "student.gpa", "operator": ">=", "value": 9.0},
                    {"field": "student.community_hours", "operator": ">=", "value": 50},
                ],
            },
            consequence={
                "action": "award_scholarship",
                "params": {"scholarship_type": "Presidential Merit", "award_amount": 10000, "awarded": True},
                "description": "Presidential Merit Scholarship awarded.",
            },
            metadata={"category": "merit"},
            created_by=admin["id"],
        )

    # 6. Domain 5: Enterprise Compliance
    compliance_domain = domain_repo.get_by_slug("business-compliance")
    if not compliance_domain:
        compliance_domain = domain_repo.create_domain(
            name="Data Governance & Compliance Audit",
            slug="business-compliance",
            description="Audits data processing systems for regulatory compliance (GDPR, HIPAA, SOC 2).",
            category="compliance",
            is_official=True,
            schema_fields=[
                {"name": "system.encryption_at_rest", "type": "boolean", "label": "Encryption At Rest"},
                {"name": "system.encryption_in_transit", "type": "boolean", "label": "Encryption In Transit"},
                {"name": "system.consent_record_maintained", "type": "boolean", "label": "Consent Logged"},
                {"name": "system.data_retention_days", "type": "number", "label": "Retention Days"},
            ],
            created_by=admin["id"],
            domain_id="dom_compliance",
        )
        rule_repo.create_rule(
            domain_id=compliance_domain["id"],
            name="GDPR Encryption Standard",
            rule_id="RULE_COMPLIANCE_ENCRYPTION",
            description="Data systems must employ encryption both at rest and in transit.",
            priority=100,
            status="active",
            is_official=True,
            condition={
                "operator": "AND",
                "conditions": [
                    {"field": "system.encryption_at_rest", "operator": "==", "value": True},
                    {"field": "system.encryption_in_transit", "operator": "==", "value": True},
                ],
            },
            consequence={
                "action": "grant_encryption_compliance",
                "params": {"encryption_compliant": True},
                "description": "Encryption standards satisfy regulatory requirements.",
            },
            metadata={"category": "security"},
            created_by=admin["id"],
        )

    logger.info("Database seeding completed successfully.")

