# Ed-Copilot Multi-District Architecture Plan

> **Status:** Draft for team review  
> **Target repo:** `satsraja12-eng/wc-math-rag` (Ed-Copilot) merges with `flower16/copilot-for-families` (Frisco/Plano ISD)  
> **Goal:** Evolve Ed-Copilot into a true multi-district family assistant where each school district has a dedicated agent, and users register once to auto-route all future conversations.

---

## Table of Contents
1. [Current State Assessment](#1-current-state-assessment)
2. [Target Architecture](#2-target-architecture)
3. [Building Blocks](#3-building-blocks)
4. [Repo Merge Strategy](#4-repo-merge-strategy)
5. [Phased Delivery](#5-phased-delivery)
6. [File Structure After Merge](#6-file-structure-after-merge)
7. [Key Decisions Needed](#7-key-decisions-needed)
8. [Open Questions for Team](#8-open-questions-for-team)

---

## 1. Current State Assessment

### This repo (`wc-math-rag` / Ed-Copilot)

| Component | Implementation |
|---|---|
| **Orchestrator** | LangGraph single graph — `classify_intent → route → specialist` |
| **Math agent** | Hybrid retriever (ChromaDB + BM25 + CrossEncoder) over NC Math 1/2/3 PDFs |
| **Admin agent** | ChromaDB `chroma_db_admin` collection filtered by `district` metadata |
| **Districts** | Wake County NC, Frisco ISD TX, Plano ISD TX — UI dropdown only |
| **District guardrail** | Math specialist checks district state; refuses NC content to TX users |
| **User identity** | None — stateless per Streamlit session |
| **Evaluation** | LangSmith dataset + LLM-as-judge (Faithfulness, Relevance, Retrieval Hit Rate) |
| **Tracing** | LangSmith tracing enabled (`Ed-Copilot` project) |

### Team repo (`flower16/copilot-for-families`)

| Component | Implementation |
|---|---|
| **Tenant config** | YAML per county (`configs/tenants/collin-county-tx.yaml`) |
| **Graph** | LangGraph: `analyzer → safety_pre → retrieve → agent → verifier → [retry] → responder` |
| **Retrieval** | District + doc_type filtered retriever with relevance floor + reranking |
| **Groundedness** | LLM-scored groundedness check with automatic retry (widens k on retry) |
| **Course catalog** | Frisco via Apptegy API; Plano via PISD eschool web scraper |
| **Auth** | `auth/security.py` (JWT-based user context) |
| **Citations** | Structured citation builder from retrieved chunks |

### Gap Analysis

| Capability | Ed-Copilot | Team Repo | Target |
|---|---|---|---|
| Per-district dedicated agent | ❌ (single graph) | ❌ (single graph) | ✅ |
| District auto-routing from user profile | ❌ | ❌ | ✅ |
| User district registration | ❌ | ❌ | ✅ |
| Groundedness verifier + retry | ❌ | ✅ | ✅ (adopt) |
| Frisco/Plano course catalog ingestion | ❌ | ✅ | ✅ (adopt) |
| NC Math 1/2/3 curriculum | ✅ | ❌ | ✅ (keep) |
| LangSmith evaluation suite | ✅ | ❌ | ✅ (extend) |
| Tenant YAML config | ❌ | ✅ | ✅ (adopt) |
| Citations in responses | ❌ | ✅ | ✅ (adopt) |

---

## 2. Target Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Streamlit Frontend                       │
│   ┌─────────────────────────────────────────────────┐   │
│   │  District Registration (first visit only)        │   │
│   │  → student/parent/teacher + school district      │   │
│   │  → stored in SQLite user profile                 │   │
│   └─────────────────────────────────────────────────┘   │
│                         │                                 │
│                 user_context (district + role)            │
└─────────────────────────┼───────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│           Top-Level Orchestrator (LangGraph)              │
│                                                           │
│   [registration_check] → [classify_intent]               │
│                               │                           │
│                    route_by_district()                    │
│                      /        |        \                  │
└─────────────────────/─────────┼─────────\────────────────┘
                      │         │          │
          ┌───────────▼──┐  ┌───▼──────┐  ┌▼─────────────┐
          │ Wake County  │  │ Frisco   │  │   Plano ISD  │
          │  NC Agent    │  │ ISD TX   │  │   TX Agent   │
          │              │  │  Agent   │  │              │
          │ Math 1/2/3   │  │ Course   │  │ Course       │
          │ WCPSS Admin  │  │ Catalog  │  │ Catalog      │
          │              │  │ Handbook │  │ Handbook     │
          └──────────────┘  └──────────┘  └──────────────┘
                │                │                │
          ┌─────▼────────────────▼────────────────▼──────┐
          │         Shared Agent Pipeline                   │
          │  retrieve → synthesize → verify → [retry]      │
          │  (groundedness check from team repo)            │
          └────────────────────────────────────────────────┘
                              │
                              ▼
                    LangSmith Tracing + Evaluation
```

### Routing Flow

```
User message arrives
      │
      ▼
 Does user have a registered district? ──No──► Registration screen
      │ Yes
      ▼
 classify_intent()
   → math_curriculum   ──► route_by_district → district agent (math node)
   → admin_policy      ──► route_by_district → district agent (admin node)
   → out_of_scope      ──► shared out_of_scope_handler (no LLM call)
      │
      ▼
 District Agent Sub-Graph
   retrieve(district, doc_type, query)
      │
   synthesize(persona, query, context)
      │
   verify(groundedness_score)
      │
   score < threshold? ──Yes──► bump_retry → retrieve (wider k)
      │ No
   respond()
```

---

## 3. Building Blocks

### 3.1 Tenant Config (YAML per district)

One YAML file per district defines all data sources, retrieval parameters, and district metadata. Adding a new district = one new YAML + one ingestion run. No code changes.

**`config/tenants/wake-county-nc.yaml`**
```yaml
tenant_id: wake-county-nc
county: Wake
state: NC
districts:
  - id: wake_county_nc
    name: Wake County Public School System
    sources:
      - type: pdf
        path: data/math/
        doc_type: math_curriculum
        subject: math
        courses: [M1, M2, M3]
      - type: web
        url: "https://wcpss.net/student-life/calendars-and-attendance"
        doc_type: admin_policy
retrieval:
  k: 8
  rerank_n: 4
  min_score: 0.35
  groundedness_threshold: 0.6
```

**`config/tenants/frisco-isd-tx.yaml`**
```yaml
tenant_id: frisco-isd-tx
county: Collin
state: TX
districts:
  - id: frisco_isd_tx
    name: Frisco ISD
    sources:
      - type: apptegy_api
        url: "https://script.google.com/macros/s/..."
        doc_type: course_catalog
        subject: math
      - type: pdf
        path: data/frisco/
        doc_type: admin_policy
retrieval:
  k: 8
  rerank_n: 4
  min_score: 0.35
  groundedness_threshold: 0.6
```

**`config/tenants/plano-isd-tx.yaml`**
```yaml
tenant_id: plano-isd-tx
county: Collin
state: TX
districts:
  - id: plano_isd_tx
    name: Plano ISD
    sources:
      - type: web
        url: "https://www.pisd.edu/students-families-a6/eschool/catalog/mathematics"
        doc_type: course_catalog
        subject: math
      - type: pdf
        path: data/plano/
        doc_type: admin_policy
retrieval:
  k: 8
  rerank_n: 4
  min_score: 0.35
  groundedness_threshold: 0.6
```

---

### 3.2 ChromaDB Collection Strategy

Refactor from two monolithic DBs to named collections per district + doc_type:

```
chroma_db/                        (single persist directory)
  wake_county_nc__math_curriculum   ← existing NC Math 1/2/3 chunks
  wake_county_nc__admin_policy      ← WCPSS calendars, attendance, AIG
  frisco_isd_tx__course_catalog     ← from team repo Apptegy API ingestion
  frisco_isd_tx__admin_policy       ← Frisco handbook PDFs
  plano_isd_tx__course_catalog      ← from team repo PISD web scraper
  plano_isd_tx__admin_policy        ← Plano handbook PDFs
```

Collection naming convention: `{district_id}__{doc_type}`

Benefits:
- Clean isolation — no metadata-filter risk of cross-district leakage
- Easy to add new districts or doc_types without schema migration
- Each collection can be re-ingested independently

---

### 3.3 District Agent Sub-Graphs

All three agents share the same **base pipeline** (retrieve → synthesize → verify → respond) but are initialized with district-specific retrievers and configs.

```python
# src/agents/base_agent.py
def build_district_agent(district_id: str, retrievers: dict, tenant_config: dict):
    """
    Returns a compiled LangGraph sub-graph for a specific district.
    retrievers: {"math_curriculum": Retriever, "admin_policy": Retriever, ...}
    """
    graph = StateGraph(DistrictAgentState)
    graph.add_node("retrieve", make_retrieve_node(retrievers, tenant_config))
    graph.add_node("synthesize", make_synthesize_node())
    graph.add_node("verify", make_verify_node(tenant_config["groundedness_threshold"]))
    graph.add_node("bump_retry", bump_retry_node)
    graph.add_node("respond", respond_node)
    # ... edges + conditional retry loop
    return graph.compile()
```

```python
# src/agents/wake_county_agent.py
def build():
    config = load_tenant_config("wake-county-nc")
    retrievers = {
        "math_curriculum": WakeCountyMathRetriever(),   # existing hybrid retriever
        "admin_policy": AdminRetriever("wake_county_nc"),
    }
    return build_district_agent("wake_county_nc", retrievers, config)

# src/agents/frisco_agent.py
def build():
    config = load_tenant_config("frisco-isd-tx")
    retrievers = {
        "course_catalog": FriscoRetriever(),   # from team repo
        "admin_policy": AdminRetriever("frisco_isd_tx"),
    }
    return build_district_agent("frisco_isd_tx", retrievers, config)

# src/agents/plano_agent.py
def build():
    config = load_tenant_config("plano-isd-tx")
    retrievers = {
        "course_catalog": PlanoRetriever(),    # from team repo
        "admin_policy": AdminRetriever("plano_isd_tx"),
    }
    return build_district_agent("plano_isd_tx", retrievers, config)
```

---

### 3.4 District Registration

**First-visit flow:**
```
Streamlit page loads
      │
      ▼
 session_state["user_profile"] exists? ──No──► show registration form
      │ Yes
 load from SQLite
      │
      ▼
 Normal chat interface (district shown in sidebar, editable)
```

**Storage:**
```python
# src/district_registry.py

def register_user(session_id: str, district: str, role: str) -> UserProfile:
    """Save user's district + role to SQLite. Returns profile."""

def get_user_profile(session_id: str) -> UserProfile | None:
    """Load existing profile. Returns None if not registered."""

def update_district(session_id: str, new_district: str):
    """Allow users to change district later."""
```

**SQLite schema (no external DB needed):**
```sql
CREATE TABLE user_profiles (
    session_id TEXT PRIMARY KEY,
    district   TEXT NOT NULL,   -- wake_county_nc | frisco_isd_tx | plano_isd_tx
    role       TEXT NOT NULL,   -- student | parent | teacher
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP
);
```

---

### 3.5 Top-Level Orchestrator (Updated)

```python
# src/orchestrator.py (refactored)

def build_master_graph(district_agents: dict) -> CompiledGraph:
    """
    district_agents: {
        "wake_county_nc": <compiled LangGraph>,
        "frisco_isd_tx":  <compiled LangGraph>,
        "plano_isd_tx":   <compiled LangGraph>,
    }
    """
    graph = StateGraph(MasterState)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("wake_county_nc",  wrap_district_agent(district_agents["wake_county_nc"]))
    graph.add_node("frisco_isd_tx",   wrap_district_agent(district_agents["frisco_isd_tx"]))
    graph.add_node("plano_isd_tx",    wrap_district_agent(district_agents["plano_isd_tx"]))
    graph.add_node("out_of_scope",    out_of_scope_handler)

    graph.add_edge(START, "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        route_by_district,      # returns district_id or "out_of_scope"
        {
            "wake_county_nc": "wake_county_nc",
            "frisco_isd_tx":  "frisco_isd_tx",
            "plano_isd_tx":   "plano_isd_tx",
            "out_of_scope":   "out_of_scope",
        }
    )
    return graph.compile()
```

---

## 4. Repo Merge Strategy

### What we adopt from `flower16/copilot-for-families`

| Component | Source path | Destination | Notes |
|---|---|---|---|
| Tenant YAML config | `configs/tenants/` | `config/tenants/` | Extend with NC district |
| Query analyzer node | `backend/app/graph/nodes.py::query_analyzer` | `src/agents/base_agent.py` | Keyword-based doc_type detection |
| Groundedness verifier | `backend/app/guardrails/groundedness.py` | `src/guardrails/groundedness.py` | LLM-scored, drives retry loop |
| Retry loop | `backend/app/graph/build_graph.py` | `src/agents/base_agent.py` | verifier → bump_retry → retrieve |
| Frisco ingestion | `backend/app/ingestion/` (Apptegy API) | `src/ingestion/frisco_ingestion.py` | Ingests Frisco course catalog |
| Plano ingestion | `backend/app/ingestion/` (web scraper) | `src/ingestion/plano_ingestion.py` | Ingests Plano course catalog |
| Citation builder | `backend/app/rag/citations.py` | `src/rag/citations.py` | Structured citations in responses |
| Personas | `backend/app/graph/personas.py` | Merge with existing `PERSONA_INSTRUCTIONS` | Combine both patterns |

### What we keep from `wc-math-rag`

| Component | Why keep |
|---|---|
| Hybrid retriever (BM25 + CrossEncoder reranking) | Better retrieval quality for NC Math standards |
| LangSmith evaluation suite (`tests/langsmith_eval.py`) | Already working; extend with more districts |
| NC Math standard domain-name mapping | New feature — keep and extend to team repo |
| `chroma_db/` NC Math chunks (1,760 chunks) | Already ingested and committed |

### What we skip (for now)

| Component | Reason |
|---|---|
| `auth/security.py` (JWT auth) | Adds infra complexity; SQLite district registration is sufficient for POC |
| Docker / `docker-compose.yml` | Replit deployment handles this |
| `backend/app/main.py` (FastAPI) | We stay with Streamlit for now |

---

## 5. Phased Delivery

### Phase 1 — Tenant Config + ChromaDB Refactor (2–3 days)
- [ ] Create `config/tenants/` with 3 district YAML files
- [ ] Refactor ChromaDB from 2 monolithic DBs → named collections per district+doc_type
- [ ] Create `src/agents/base_agent.py` with shared pipeline template
- [ ] Port groundedness verifier + retry loop from team repo
- [ ] Create `src/agents/wake_county_agent.py` (wraps existing retrievers)
- [ ] Smoke test: Wake County still answers correctly

### Phase 2 — Frisco & Plano Agents (2 days)
- [ ] Port Frisco Apptegy API ingestion → ingest into `frisco_isd_tx__course_catalog`
- [ ] Port Plano web scraper ingestion → ingest into `plano_isd_tx__course_catalog`
- [ ] Create `src/agents/frisco_agent.py`
- [ ] Create `src/agents/plano_agent.py`
- [ ] Smoke test: Frisco/Plano course catalog questions answer correctly

### Phase 3 — Registration + Master Orchestrator (1–2 days)
- [ ] Build `src/district_registry.py` with SQLite backend
- [ ] Update `src/orchestrator.py` → master graph routing to district sub-graphs
- [ ] Update `app.py` → registration screen on first visit, auto-route after
- [ ] Remove manual district dropdown (replaced by profile)
- [ ] End-to-end test across all 3 districts

### Phase 4 — Evaluation Extension (1 day)
- [ ] Add Frisco + Plano questions to LangSmith dataset (`tests/langsmith_eval.py`)
- [ ] Add `retrieval_hit` evaluator for course catalog questions
- [ ] Run baseline experiment for all 3 district agents

### Phase 5 — Polish (1 day)
- [ ] Add citation display in Streamlit (from team repo's citation builder)
- [ ] Update architecture diagram (`pages/architecture.py`)
- [ ] Update `DEPLOY.md` with new ingestion steps

---

## 6. File Structure After Merge

```
ed-copilot/
├── app.py                          ← Updated: registration screen + auto-routing
├── config/
│   └── tenants/
│       ├── wake-county-nc.yaml     ← NEW
│       ├── frisco-isd-tx.yaml      ← NEW
│       └── plano-isd-tx.yaml       ← NEW
├── src/
│   ├── orchestrator.py             ← REFACTORED: master routing graph
│   ├── district_registry.py        ← NEW: SQLite user registration
│   ├── agents/
│   │   ├── base_agent.py           ← NEW: shared pipeline template
│   │   ├── wake_county_agent.py    ← NEW: wraps existing NC Math retriever
│   │   ├── frisco_agent.py         ← NEW: Frisco district agent
│   │   └── plano_agent.py          ← NEW: Plano district agent
│   ├── retrieval.py                ← KEPT: NC Math hybrid retriever
│   ├── ingestion.py                ← KEPT: NC Math ingestion
│   ├── ingestion/
│   │   ├── frisco_ingestion.py     ← NEW: from team repo Apptegy API
│   │   └── plano_ingestion.py      ← NEW: from team repo web scraper
│   ├── guardrails/
│   │   └── groundedness.py         ← NEW: from team repo
│   └── rag/
│       └── citations.py            ← NEW: from team repo
├── chroma_db/                      ← REFACTORED: named collections
│   (all collections in single persist dir)
├── pages/
│   └── architecture.py             ← UPDATE: new multi-agent diagram
├── tests/
│   ├── langsmith_eval.py           ← EXTEND: add Frisco/Plano questions
│   └── evaluation.py               ← KEPT
├── data/
│   ├── math/                       ← KEPT: NC Math PDFs
│   ├── frisco/                     ← NEW: Frisco admin PDFs
│   └── plano/                      ← NEW: Plano admin PDFs
└── MULTI_DISTRICT_PLAN.md          ← THIS FILE
```

---

## 7. Key Decisions Needed

| # | Decision | Options | Recommendation |
|---|---|---|---|
| 1 | **Registration persistence** | Session-only vs. SQLite | SQLite — survives refresh |
| 2 | **Single deployment or one per district** | One app vs. three | Single app — much simpler ops |
| 3 | **ChromaDB: refactor or keep existing** | Named collections vs. keep two DBs | Named collections — cleaner isolation |
| 4 | **Auth adoption** | Skip JWT / adopt team repo auth | Skip for POC — too much infra |
| 5 | **Citation display** | Plain text vs. structured citation cards | Structured (team repo pattern) |
| 6 | **Groundedness threshold** | 0.5 / 0.6 / 0.7 | 0.6 (team repo default) |

---

## 8. Open Questions for Team

1. **Frisco/Plano ingestion credentials**: The Apptegy API URL is in the team repo — is it still live and does it require auth?
2. **Admin PDF location**: Where are the most current Frisco/Plano handbook PDFs? (We have archived versions from Wayback Machine)
3. **Which GitHub repo becomes the merged repo?** `wc-math-rag` (this one) or `copilot-for-families`? Or a new repo?
4. **LangSmith project**: Should Frisco/Plano use the same `Ed-Copilot` LangSmith project or separate projects per district?
5. **Evaluation ground truth**: For Frisco/Plano course catalog questions, who on the team can write/validate the gold-standard answers?
6. **Deployment target**: Replit (current), or Docker + cloud once merged with team repo?

---

## References

- **This repo**: https://github.com/satsraja12-eng/wc-math-rag
- **Team repo**: https://github.com/flower16/copilot-for-families
- **LangSmith project**: https://smith.langchain.com (project: `Ed-Copilot`)
- **LangGraph docs**: https://langchain-ai.github.io/langgraph/
- **Deployed app**: Published via Replit
