# RuleWise AI

RuleWise AI is an explainable hybrid Neuro-Symbolic AI Rule Engine and Advisory Assistant designed to evaluate complex academic and administrative policies, combine symbolic forward-chaining rule evaluation with natural language explanation, and support what-if policy simulations.

## Project Status

- **Current Phase**: Phase 4 (Deterministic Forward-Chaining Inference Engine)
- Phase 1 (Scaffolding), Phase 2 (Knowledge Base), Phase 3 (Rule Engine), and Phase 4 (Inference Engine) are implemented and verified.

## Phase 2: Knowledge Base Layer

The Knowledge Base is a deterministic, in-memory repository and validation layer for academic domain entities and declarative policy rules.

### Capabilities and Storage
- **Student Data (`students.json`)**: Profiles containing identifier, name, GPA, completed courses, verified skills, and academic status.
- **Course Data (`courses.json`)**: Course offerings including identifier, name, minimum GPA requirements, prerequisites, and required skills.
- **Active Rules (`active_rules.json`)**: Declarative rules structured with conditions and consequences governing academic eligibility.
- **Staged Rules (`staged_rules.json`)**: Proposed or unpromoted rules isolated from active policy.
- **Schema Validation**: Strongly typed and validated using Pydantic v2 models (`Student`, `Course`, `Rule`, `Condition`, `Consequence`).

### Boundaries & Design Principles
- **No Reasoning / Inference**: The Knowledge Base strictly stores, validates, loads, and retrieves structured data. It does **not** evaluate IF-THEN conditions, determine student eligibility, or resolve rule conflicts.
- **Security**: Data is never executed as code (`eval()`, `exec()`, or dynamic imports are strictly prohibited).
- **Determinism**: Loading the same files produces equivalent data with zero randomness or external API dependencies.

## Phase 3: Declarative Rule Engine

Phase 3 implements the deterministic, offline evaluation engine for declarative rules.

### Capabilities
- **Operators Layer (`backend/engine/operators.py`)**: Explicit, safe comparison dispatch without `eval()`:
  - Supported comparison operators: `==`, `!=`, `>`, `>=`, `<`, `<=`, `IN` (handles scalar-in-collection and collection-membership).
  - Strongly typed with `InvalidComparisonError` and `UnsupportedOperatorError`.
- **Working Memory (`backend/engine/working_memory.py`)**: Isolated in-memory fact storage with safe dot-separated path resolution (e.g. `student.gpa`, `student.skills`, `student.completed_courses`).
- **Condition Evaluator (`backend/engine/condition_evaluator.py`)**: Evaluates Boolean condition trees against working memory facts:
  - Supported Boolean operators: `AND`, `OR`, `NOT` (including arbitrary nested trees).
  - Purely data-driven with strict rejection of malformed or unknown condition nodes.
- **Rule Matcher (`backend/engine/rule_matcher.py`)**: Tests whether a validated rule's condition is satisfied by facts in working memory.
- **Consequence & Single-Rule Execution (`backend/engine/inference_engine.py`)**:
  - Evaluates rules and asserts structured derived facts (e.g. `{"student.eligible_for_ai": true}`).
  - Provides primitive interfaces: `evaluate_rule(rule, wm)` and `apply_rule(rule, wm)`.

### Strict Security & Boundaries
- **No Executable Code**: Rules are pure data. `eval()`, `exec()`, `compile()`, and dynamic imports are strictly barred.
- **No LLM / Offline**: The rule engine is the deterministic final authority for policy evaluation and never calls Gemini or external network services.

## Phase 4: Deterministic Forward-Chaining Inference Engine

Phase 4 extends the Phase 3 single-rule primitives into a full forward-chaining inference system capable of multi-step reasoning to a stable fixed point.

### Capabilities

- **Forward Chaining (`infer()`)**: Starts with initial facts in Working Memory, evaluates all active rules, fires matching rules, asserts derived facts, and repeats until no new rules match (fixed point) or a safety limit is reached.
- **Conflict Resolution** (deterministic, 4-level sort key applied on every cycle):
  1. **Salience / Priority** — higher integer `priority` fires first.
  2. **Specificity** — rule with more atomic conditions in its condition tree fires first.
  3. **Recency** — rule depending on the most recently derived fact fires first.
  4. **Rule ID** — lexicographic ascending sort as the final tie-breaker.
- **Cycle Detection**: State signature (deterministic JSON hash of all working memory facts) is recorded after every rule firing. A repeated signature triggers `termination_reason = "cycle_detected"`.
- **Max Depth Enforcement**: Configurable `max_depth` parameter (default 50) caps the number of rule firings per run. Exits with `termination_reason = "max_depth_reached"`.
- **Negative Preclusion**: Once a fact is asserted as `False`, subsequent `True` assertions for the same path have no effect — order-independent and deterministic.
- **State Isolation**: `infer()` clones the caller's `WorkingMemory` before execution. The original working memory is never mutated.
- **Structured Result (`InferenceResult`)**:
  - `final_facts` — complete working memory after inference.
  - `derived_facts` — all newly asserted facts produced during the run.
  - `fired_rule_ids` — ordered list of rule IDs that fired.
  - `derivation_history` — `DerivationStep` records, each capturing step number, rule ID/name, matched condition, derived facts, and source facts.
  - `fact_provenance` — `FactProvenance` map tracking origin (initial vs. derived, step number, source rule ID) for every fact.
  - `termination_reason` — `"fixed_point"`, `"cycle_detected"`, or `"max_depth_reached"`.
- **Working Memory Extensions**:
  - `get_fact_step(path)` — returns the sequence step at which a fact was asserted (0 = initial).
  - `get_provenance(path)` / `get_all_provenance()` — audit trail for individual or all facts.
  - `clone()` — deep copy for state isolation.

### Phase 4 Security & Boundaries
- No `eval()`, `exec()`, `compile()`, subprocess calls, dynamic imports, network calls, or LLM calls anywhere in the inference engine.
- Phase 5 (natural language explanations, Gemini integration, what-if simulation) is **not yet implemented**.


## Getting Started

### 1. Prerequisites

- Python 3.11+
- Git

### 2. Create the Virtual Environment

Create an isolated virtual environment:

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

Install the core dependencies required for Phase 1:

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the template configuration file:

```bash
# Windows (PowerShell)
Copy-Item .env.example .env

# Linux / macOS
cp .env.example .env
```

> **Note**: Never commit your `.env` file or real API keys to version control.

### 5. Run Tests

Execute the test suite using pytest:

```bash
python -m pytest
```

### 6. Start the FastAPI Server

Run the development server with Uvicorn:

```bash
uvicorn backend.main:app --reload
```

The server will start at `http://127.0.0.1:8000`.

### 7. Health Endpoint

Verify that the application is running by querying the health check endpoint:

- **URL**: `GET http://127.0.0.1:8000/health`
- **Sample Response**:
  ```json
  {
    "status": "ok",
    "project": "RuleWise AI",
    "phase": 1
  }
  ```

API interactive documentation is also available at:
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
