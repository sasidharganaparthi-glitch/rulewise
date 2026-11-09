# RuleWise AI — Complete Production System (v1.0.0)

**RuleWise AI** is an enterprise-grade, explainable Neuro-Symbolic Artificial Intelligence Platform. It couples natural-language conversational AI (powered by Google Gemini) with a deterministic, authoritative rule engine, an interactive visual rule studio, multi-domain governance, and deep reasoning explainability traces.

---

## 1. Core Architecture & Neuro-Symbolic Principle

RuleWise AI enforces a strict neuro-symbolic separation of concerns:

```
[User Natural Language Query]
           │
           ▼
[AI Layer (Gemini NLP / Parser)] ─── Extracts ───► [Structured Facts & Entity Query]
                                                              │
                                                              ▼
                                             [Deterministic Symbolic Engine]
                                                ├── Knowledge Base & Facts
                                                ├── Declarative Rule Base
                                                ├── Forward-Chaining Engine
                                                └── Conflict Resolution
                                                              │
                                                              ▼
                                                    [Authoritative Decision]
                                                              │
                                                              ▼
[Natural Language Response] ◄── Grounded in ─── [Explainability Trace Layer]
 (Strictly Preserves Result)                       (Why / Why-Not Chains)
```

### Key Principles:
1. **Symbolic Authority**: The rule engine is the sole decision authority. The language model **never** invents rules, modifies thresholds, or overrides deterministic decisions.
2. **Deterministic & Offline**: The core inference engine executes without network or LLM dependencies using forward chaining, salience prioritization, specificity ranking, and recency tracking.
3. **No `eval()` / `exec()`**: Rules are declarative data structures validated by Pydantic. Dynamic code execution is strictly prohibited.
4. **Injection Resistant**: Prompt injections cannot alter decisions because facts and rules reside strictly in isolated symbolic memory.

---

## 2. Platform Capabilities

- **Hybrid Conversational Assistant**: ChatGPT-style natural dialogue for general knowledge assistance, seamlessly dispatching policy queries to the symbolic engine with clear visual labelling.
- **Multi-Domain Management**: Expandable, domain-independent architecture supporting:
  - Academic Policy & Course Eligibility (Official)
  - Retail Loan & Credit Underwriting (Official)
  - Recruitment & HR Screening (Official)
  - Merit & Need-Based Scholarships (Official)
  - Enterprise Compliance & Data Governance (Official)
  - Custom User-Defined Domains (Created via UI or API)
- **Visual Rule Studio**: Intuitive IF-THEN rule builder with comparison operators (`==`, `!=`, `>`, `>=`, `<`, `<=`, `IN`), logical grouping (`AND`, `OR`), priority configuration, live JSON preview, and instant rule testing.
- **Official vs. Personal Rule Libraries**: Role-based governance where official rules are verified, versioned, and immutable by non-admin users, while personal rules can be authored, tested, edited, and deleted freely.
- **What-If Scenario Simulator**: Isolates working memory via `ForkManager` and runs `DeltaAnalyzer` to compare baseline vs. hypothetical outcomes, reporting newly fired rules, ceased rules, and derived fact changes.
- **Open Access & Authentication**: Zero-friction guest mode for instant exploration without registration, plus optional user registration and secure login (PBKDF2-HMAC-SHA256 password hashing, signed Bearer tokens).
- **Audit Trails & Decision History**: Complete provenance tracking of past evaluations with input facts, fired rule sequences, and step-by-step reasoning chains.

---

## 3. Technology Stack

- **Backend**: Python 3.13+, FastAPI, Uvicorn, Pydantic v2, Pydantic-Settings
- **Symbolic Inference**: Pure Python forward chaining, cycle detection, state hashing, WorkingMemory isolation
- **Language Model**: Google Gemini API via official `google-genai` SDK with smart deterministic fallback
- **Database**: SQLite with WAL mode, foreign keys, parameter binding, thread-safe connection pooling (PostgreSQL compatible)
- **Frontend**: Modern Minimal SaaS UI (HTML5, responsive CSS3 with Inter typography, modular Vanilla JS)
- **Testing**: Pytest, Httpx (275 automated tests)

---

## 4. Local Installation & Startup Guide

### Prerequisites
- Python 3.10+ (Python 3.13 recommended)
- Git

### Step 1: Clone the Repository
```bash
git clone https://github.com/your-org/rulewise-ai.git
cd RuleWise-AI
```

### Step 2: Set Up Virtual Environment & Dependencies
```bash
# Windows
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

Edit `.env` and set your Google Gemini API key:
```env
GEMINI_API_KEY=AIzaSy...your_actual_key_here
GEMINI_MODEL=gemini-2.5-flash
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=True
LLM_TIMEOUT_SECONDS=3.5
```
*(Note: If no API key is provided, the platform automatically activates its built-in deterministic fallback engine without interruption).*

### Step 4: Run the Application
```bash
# Windows
.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# Linux / macOS
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser and navigate to:
**`http://127.0.0.1:8000/`**

---

## 5. Running the Automated Test Suite

The comprehensive test suite includes 275 tests covering health checks, API endpoints, rule evaluation, inference engine, conflict resolution, explainability traces, simulation deltas, authentication, and security protections:

```bash
# Run all tests
.\.venv\Scripts\python -m pytest

# Run with verbose output
.\.venv\Scripts\python -m pytest -v
```

---

## 6. REST API Reference

### Health & Telemetry
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Root health check |
| `GET` | `/api/v1/health` | API v1 subsystem readiness |
| `GET` | `/api/v1/chat/status` | Provider status, fallback readiness, and symbolic engine state |
| `GET` | `/api/v1/knowledge/stats` | System-wide statistics and metrics |

### Chat & Advisory
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/chat` | Process natural language inquiry through neuro-symbolic pipeline |
| `GET` | `/api/v1/chat/conversations` | List conversation threads |
| `GET` | `/api/v1/chat/conversations/{id}/messages` | Get message history for a conversation |

### Domains & Governance
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/domains` | List official and personal domains |
| `GET` | `/api/v1/domains/{id_or_slug}` | Get domain details and schema fields |
| `POST` | `/api/v1/domains` | Create a new custom domain |
| `DELETE` | `/api/v1/domains/{id}` | Delete a user-created domain |

### Rules & Authoring
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/rules` | List rules (filter by domain, status, official) |
| `GET` | `/api/v1/rules/{id}` | Get rule details |
| `POST` | `/api/v1/rules` | Create a new validated rule |
| `PUT` | `/api/v1/rules/{id}` | Update existing rule |
| `DELETE` | `/api/v1/rules/{id}` | Delete rule |
| `POST` | `/api/v1/rules/validate` | Validate condition structure without persisting |
| `POST` | `/api/v1/rules/test` | Test single rule against sample facts |

### What-If Simulation
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/simulation/run` | Execute forked simulation and analyze delta |

### Decision History
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/history` | List historical evaluation records |
| `GET` | `/api/v1/history/{id}` | Retrieve complete reasoning trace and evidence JSON |

### Authentication & Sessions
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Register new user account |
| `POST` | `/api/v1/auth/login` | Authenticate and obtain JWT Bearer token |
| `POST` | `/api/v1/auth/guest` | Create immediate guest access session |
| `GET` | `/api/v1/auth/me` | Get current user profile |

---

## 7. Security & Compliance Highlights

- **Input Sanitization**: User messages stripped of null bytes and non-printable control characters; length-bounded to 2000 chars.
- **SQL Injection Prevention**: All database queries strictly parameterized via sqlite3 / DB API.
- **Dynamic Execution Prohibition**: No `eval()`, `exec()`, or dynamic module loading anywhere in the codebase.
- **Credential Protection**: Secrets and API keys masked in all logs and status endpoints; never returned to frontend.
- **Password Security**: PBKDF2-HMAC-SHA256 with 100,000 iterations and 16-byte cryptographically secure salts.
- **Tamper-Proof Tokens**: Signed Bearer access tokens with HMAC-SHA256 signatures and expiry verification.
- **Prompt Injection Defense**: Evaluator enforces rules directly in working memory; natural language cannot bypass thresholds or falsify facts.

---

## 8. Production Preparation & Deployment

1. **Environment Variables**: Use Docker secrets or a secrets manager (e.g. AWS Secrets Manager, Google Secret Manager) to inject `GEMINI_API_KEY`.
2. **Reverse Proxy**: Place behind Nginx, Caddy, or Cloudflare with TLS termination and rate limiting.
3. **Database Migration**: The database manager uses SQLite WAL mode with zero configuration for single-instance containers. For multi-instance clustered deployments, migrate the repository interface to PostgreSQL.
4. **Containerization**:
   ```dockerfile
   FROM python:3.13-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY . .
   EXPOSE 8000
   CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
   ```

---

## 9. License

RuleWise AI is distributed under the MIT License.
