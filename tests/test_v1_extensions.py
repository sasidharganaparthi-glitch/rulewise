"""Comprehensive tests for RuleWise AI V1 Extensions:
- Multi-domain management
- Rule authoring, validation, testing, and protection
- What-if simulation and delta analysis
- Evaluation decision history and explainability retrieval
- Authentication, tokens, and role-based permissions
- Knowledge statistics and export/import
"""

import pytest
from fastapi.testclient import TestClient

from backend.core.security import create_access_token, hash_password, verify_password
from backend.db.database import get_db_manager, reset_db_manager
from backend.db.seeder import seed_database
from backend.main import app


@pytest.fixture(scope="module")
def client():
    """TestClient instance with seeded database."""
    db = get_db_manager()
    seed_database(db)
    return TestClient(app)


# -----------------------------------------------------------------------------
# 1. Domain Tests
# -----------------------------------------------------------------------------

def test_list_domains(client):
    """GET /api/v1/domains returns official and custom domains."""
    response = client.get("/api/v1/domains")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 5
    slugs = [d["slug"] for d in data]
    assert "academic-eligibility" in slugs
    assert "loan-eligibility" in slugs
    assert "recruitment-screening" in slugs


def test_get_domain_by_slug(client):
    """GET /api/v1/domains/{slug} returns domain details and schema fields."""
    response = client.get("/api/v1/domains/loan-eligibility")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Retail Loan & Credit Underwriting"
    assert data["is_official"] is True
    assert len(data["schema_fields"]) > 0


def test_create_and_delete_custom_domain(client):
    """POST /api/v1/domains creates custom domain; DELETE removes it."""
    payload = {
        "name": "Custom Test Domain",
        "slug": "custom-test-domain",
        "description": "A test domain for unit testing",
        "category": "custom",
        "schema_fields": [
            {"name": "test.score", "type": "number", "label": "Test Score"}
        ],
    }
    response = client.post("/api/v1/domains", json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created["slug"] == "custom-test-domain"
    domain_id = created["id"]

    # Official domains cannot be deleted
    del_official = client.delete("/api/v1/domains/dom_academic")
    assert del_official.status_code == 403

    # Custom domain can be deleted
    del_custom = client.delete(f"/api/v1/domains/{domain_id}")
    assert del_custom.status_code == 204


# -----------------------------------------------------------------------------
# 2. Rule Authoring, Validation, and Testing Tests
# -----------------------------------------------------------------------------

def test_validate_valid_and_invalid_rules(client):
    """POST /api/v1/rules/validate validates syntax safely without dynamic execution."""
    # Valid rule
    valid_payload = {
        "condition": {
            "field": "applicant.credit_score",
            "operator": ">=",
            "value": 700,
        },
        "consequence": {
            "action": "grant_clearance",
            "params": {"cleared": True},
        },
    }
    resp = client.post("/api/v1/rules/validate", json=valid_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert "applicant.credit_score" in data["referenced_facts"]

    # Security violation test (contains dangerous keywords)
    dangerous_payload = {
        "condition": {
            "field": "test.__class__",
            "operator": "==",
            "value": "eval",
        },
        "consequence": {
            "action": "dangerous_action",
        },
    }
    d_resp = client.post("/api/v1/rules/validate", json=dangerous_payload)
    assert d_resp.status_code == 200
    d_data = d_resp.json()
    assert d_data["valid"] is False
    assert any("dangerous token" in err for err in d_data["errors"])


def test_test_rule_execution(client):
    """POST /api/v1/rules/test tests single rule against fact inputs."""
    payload = {
        "rule": {
            "id": "TEMP_RULE",
            "name": "High Income Test",
            "condition": {
                "field": "user.income",
                "operator": ">=",
                "value": 100000,
            },
            "consequence": {
                "action": "grant_vip",
                "params": {"vip_status": True},
            },
        },
        "facts": {
            "user.income": 120000,
        },
    }
    resp = client.post("/api/v1/rules/test", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["matched"] is True
    assert data["derived_facts"].get("vip_status") is True


def test_create_and_manage_custom_rule(client):
    """POST /api/v1/rules creates rule in a custom domain."""
    import uuid
    slug = f"rule-domain-{uuid.uuid4().hex[:6]}"
    dom_resp = client.post(
        "/api/v1/domains",
        json={"name": "Rule Domain", "slug": slug},
    )
    assert dom_resp.status_code == 201
    domain_id = dom_resp.json()["id"]

    rule_payload = {
        "domain_id": domain_id,
        "name": "Test Minimum Score",
        "description": "Rule for testing",
        "priority": 60,
        "status": "active",
        "condition": {
            "field": "score",
            "operator": ">=",
            "value": 50,
        },
        "consequence": {
            "action": "pass_exam",
            "params": {"passed": True},
        },
    }
    resp = client.post("/api/v1/rules", json=rule_payload)
    assert resp.status_code == 201
    created = resp.json()
    rule_id = created["id"]
    assert created["priority"] == 60

    # Update rule
    update_resp = client.put(
        f"/api/v1/rules/{rule_id}",
        json={"priority": 85, "name": "Updated Test Rule"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["priority"] == 85

    # Delete rule
    del_resp = client.delete(f"/api/v1/rules/{rule_id}")
    assert del_resp.status_code == 204


# -----------------------------------------------------------------------------
# 3. What-If Simulation Tests
# -----------------------------------------------------------------------------

def test_run_simulation_delta(client):
    """POST /api/v1/simulation/run compares baseline vs forked fact changes."""
    payload = {
        "domain_id": "dom_loan",
        "baseline_facts": {
            "applicant.credit_score": 600,  # Below 680 threshold
            "applicant.debt_to_income_ratio": 50,  # Above 40 limit -> No rules fire
            "applicant.annual_income": 30000,
            "applicant.bankruptcies": 1,
        },
        "fact_overrides": {
            "applicant.credit_score": 750,  # Boosted -> Credit score rule fires
            "applicant.debt_to_income_ratio": 25,  # DTI rule fires
            "applicant.annual_income": 80000,
            "applicant.bankruptcies": 0,
        },
    }
    resp = client.post("/api/v1/simulation/run", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "delta" in data
    delta = data["delta"]
    assert len(delta["newly_fired_rules"]) > 0
    assert "RULE_LOAN_CREDIT_SCORE" in delta["newly_fired_rules"]
    assert delta["conclusion_changed"] is True


# -----------------------------------------------------------------------------
# 4. Authentication & Security Tests
# -----------------------------------------------------------------------------

def test_password_hashing():
    """PBKDF2-HMAC-SHA256 hashing and verification works securely."""
    pwd = "SecurePassword123!"
    h = hash_password(pwd)
    assert verify_password(pwd, h) is True
    assert verify_password("WrongPassword", h) is False


def test_auth_registration_and_login(client):
    """User registration, login, and token verification."""
    import uuid
    username = f"testuser_{uuid.uuid4().hex[:8]}"
    reg_payload = {
        "username": username,
        "password": "Password123",
        "email": f"{username}@example.com",
    }
    reg_resp = client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_resp.status_code == 201
    auth_data = reg_resp.json()
    token = auth_data["access_token"]
    assert len(token) > 20

    # Profile check with Bearer token
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == username

    # Login
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Password123"},
    )
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()


def test_guest_session_creation(client):
    """POST /api/v1/auth/guest issues zero-barrier guest access token."""
    resp = client.post("/api/v1/auth/guest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["role"] == "guest"
    assert "access_token" in data


# -----------------------------------------------------------------------------
# 5. History & Knowledge Stats Tests
# -----------------------------------------------------------------------------

def test_knowledge_stats(client):
    """GET /api/v1/knowledge/stats returns system statistics."""
    resp = client.get("/api/v1/knowledge/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["domains_count"] >= 5
    assert data["official_rules_count"] >= 10
    assert data["total_rules_count"] >= 10


def test_domain_export(client):
    """GET /api/v1/knowledge/export exports portable JSON."""
    resp = client.get("/api/v1/knowledge/export?domain_id=dom_loan")
    assert resp.status_code == 200
    data = resp.json()
    assert "domain" in data
    assert "rules" in data
    assert len(data["rules"]) > 0


def test_decision_history_retrieval(client):
    """GET /api/v1/history lists evaluations."""
    resp = client.get("/api/v1/history")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
