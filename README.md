# OCI Enterprise AI — AI-Assisted AML Operations (Raqib · رقيب)

Raqib is a portfolio-grade technical reference solution for human-governed financial-crime operations on OCI Generative AI. It combines deterministic AML screening, a governed AI investigation workflow, persistent case and evidence history, maker-checker SAR review, interactive rule analytics, and bilingual reporting in a focused React workbench. It demonstrates how a complete solution can be shaped and tested without claiming to be a production banking platform or filing a report autonomously.

## When to Use This Asset

**The Challenge.** AML teams must investigate large alert queues without losing traceability. Each case can require ledger analysis, policy interpretation, document review, watchlist checks, adverse-media research, numerical reconciliation, and a defensible narrative. AI can accelerate that work, but it must not replace deterministic detection, silently access sensitive data, or make the final regulatory decision.

**Who Is This For?** Financial-crime and AML leaders, investigators, MLROs, internal auditors, solution architects, and technical stakeholders evaluating governed agentic workflows for regulated MEA organizations.

**When to Use It.** Use Raqib for a technical portfolio walkthrough, architecture workshop, customer discovery session, or controlled PoC that needs more depth than a linear demo. It is especially useful for showing how UI, APIs, persistence, AI tooling, human approvals, output validation, and automated testing fit together. It is not production-ready AML software and is not a substitute for a bank's validated rules, licensed screening sources, identity controls, or regulatory filing process.

**Key Capabilities**

| Capability | Implemented reference pattern | Human or governance control |
|---|---|---|
| Minimal operations workbench | Five primary destinations: Overview, Alerts, Cases, Intelligence, and Architecture | Progressive disclosure keeps technical detail out of the core task flow |
| Persona simulation | Analyst, MLRO Reviewer, Auditor, and Rule Administrator switcher | API and WebSocket actions enforce the selected simulated role; this is not authentication |
| Deterministic alerting | Four configurable AML rules over a synthetic bank ledger | Rules create evidence-backed alerts; AI does not decide what constitutes a rule match |
| Persistent case workflow | Additive SQLite schema for cases, runs, events, approvals, notes, SAR versions, and rule history | State is scoped by case and retained across page refreshes and app restarts |
| Governed AI investigation | OCI Responses API, Conversations, function tools, and Code Interpreter | Every model-proposed ledger query requires explicit analyst approval bound to its run and tool call |
| Separated retrieval paths | Trusted AML policy uses OCI embeddings and local cosine retrieval; customer evidence is read separately | Untrusted evidence is prompt-injection scanned before use |
| Structured SAR workflow | Pydantic-validated SAR draft, required output PII scan, editing, submission, review, and version history | Analyst prepares and submits; MLRO Reviewer approves or requests changes |
| Targeted Arabic support | Required Arabic narrative fields plus English and Arabic PDF exports | The operational UI remains English-first in this release |
| Interactive intelligence | Operational analytics, versioned rule parameters, baseline comparison, and no-write simulations | Rule changes and simulations are restricted to the Rule Administrator persona |
| Architecture explorer | Implemented and target OCI views, controls, runtime disclosure, and deployment profiles | Optional services are clearly marked as next or optional rather than presented as built |
| Automated verification | Backend unit, integration, API/WebSocket contract, security, evaluation, report, and opt-in live OCI checks; focused React component tests | Normal backend tests fail closed against accidental OCI calls and use isolated temporary data |

The product principle is: **Rules detect. AI investigates. Humans decide.** A generated SAR is a draft; the application never represents generation as regulatory filing.

### Service and data-boundary disclosures

- The seeded ledger, application state, policy files, case documents, and demo tape are local and fictional.
- OCI managed Vector Stores and File Search are now available. Raqib intentionally retains its local policy retrieval path for portable demo mode, deterministic tests, and a clear adapter boundary; managed File Search is shown as a target option, not as an implemented feature.
- OCI documents that xAI Grok models are hosted in an OCI data center in a tenancy provisioned for xAI and are managed by xAI. That is not the same as execution inside the customer's own tenancy.
- The optional xAI `web_search` adverse-media step intentionally reaches the public web. Treat it as an explicit egress path, disable it for no-egress environments, or replace it with an approved licensed data provider.
- Agentic APIs, individual models, and tools vary by region. Current OCI documentation lists agentic endpoints in Riyadh and notes that OCI OpenAI-compatible endpoints and tools are not available in Dubai. Verify the current model-by-region catalog before every deployment decision.
- The `.env` API-key flow is for development and controlled demonstrations. OCI recommends IAM-based authentication for production workloads and OCI-managed environments; that production identity integration is part of the target architecture, not this implementation.

## How to Use This Asset

**For a Quick Demo.** Run Raqib without a `.env`. The flagship investigation replays a recorded live run through the same WebSocket event contract used by live mode, while screening, role permissions, case state, notes, SAR review, analytics, and rule simulations remain interactive.

1. Open **Alerts** and run screening to populate the governed alert queue.
2. Open the priority case and start the recorded investigation as **AML Analyst**.
3. Inspect evidence and approve or deny the proposed read-only ledger query.
4. Review the prompt-injection control, policy citations, computed findings, and PII scan before the SAR draft appears.
5. Edit and submit the draft, switch to **MLRO Reviewer**, then approve it or request changes.
6. Switch to **Rule Administrator** and use **Intelligence** to simulate a parameter change before saving a version.
7. Open **Architecture** to compare what is implemented with the OCI deployment path and its regional profiles.

Demo mode replays only the bundled flagship case. Configure live mode to investigate other alerts with the OCI agent. All data remains synthetic in both modes.

**For a PoC / Technical Evaluation.** Keep the product workflow and replace adapters deliberately:

- Replace `src/bankdb.py` with a governed customer data adapter, such as Autonomous AI Database with Semantic Store / NL2SQL and DBTools MCP.
- Replace synthetic KYC and case evidence with approved document sources while preserving the trusted-policy versus untrusted-evidence separation.
- Replace the internal watchlist and public-web adverse-media path with licensed provider integrations.
- Map simulated personas to OCI Identity Domains groups and enforce identity-derived authorization rather than accepting `X-Raqib-Role`.
- Move evidence and report artifacts to Object Storage, case records to Autonomous AI Database, and the containerized runtime to an OCI Hosted Generative AI Application only when those services are needed.
- Validate rules, thresholds, retention, Arabic content, maker-checker policy, and filing formats with the customer's compliance and legal teams.

**Customizing.** Endpoints, model IDs, CORS origins, and feature flags live in `config.py`. The investigation procedure is centralized in `src/agent.py`; structured report fields are in `src/schemas.py`; rule definitions are in `src/rules.py`; persisted workflow behavior is in `src/store.py`; and the page-level React experience is under `web/src/pages/`. Keep model availability checks and the service-boundary disclosures aligned whenever you change regions or providers.

## Architecture

### Implemented reference solution

```text
┌──────────────────────────── React workbench ────────────────────────────┐
│ Overview │ Alerts │ Cases + case workspace │ Intelligence │ Architecture│
│           Persona simulation: Analyst · Reviewer · Auditor · Rule Admin │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ REST + case-scoped WebSocket events
┌───────────────────────────────▼──────────────────────────────────────────┐
│ FastAPI application                                                       │
│  ├─ role-aware actions and case lifecycle                                  │
│  ├─ deterministic screening + rule simulation                              │
│  ├─ investigation run / approval orchestration                             │
│  └─ SAR draft → submit → review / changes requested                        │
└──────────────┬─────────────────────┬─────────────────────┬────────────────┘
               │                     │                     │
      ┌────────▼────────┐   ┌────────▼─────────┐  ┌────────▼────────────┐
      │ OCI Responses   │   │ OCI Guardrails  │  │ Additive SQLite     │
      │ Conversations   │   │ PI + output PII │  │ ledger + app state  │
      │ tools + sandbox │   └──────────────────┘  └─────────────────────┘
      └────────┬────────┘
               │
      ┌────────▼──────────────────────────────────────────────────────────┐
      │ Trusted policy retrieval │ untrusted case evidence │ watchlist   │
      │ optional public-web adverse media │ analyst-approved read-only SQL│
      └────────────────────────────────────────────────────────────────────┘
```

The application stores operational records additively in the same local SQLite file as the seeded ledger. Schema migrations create product tables without dropping the fictional transaction data. Set `RAQIB_DB_PATH` to isolate a demo run in another database. Tests use a new temporary database and copied documents for every test, so they do not mutate the developer's state.

### Target OCI expansion path

The in-app Architecture page presents this as a target, not as deployed infrastructure:

```text
Customer systems / licensed screening providers
                         │
                         ▼
OCI Identity Domains → Hosted Generative AI Application ← Logging / Monitoring / APM
       SSO + roles       React + FastAPI runtime
                               │
             ┌─────────────────┼──────────────────┐
             ▼                 ▼                  ▼
      OCI Responses API   Autonomous AI DB   Object Storage
      Guardrails + tools  cases + governed   evidence + report
      optional File Search     query path          versions
```

The page includes three discussion profiles: a Chicago showcase, a Riyadh deployment path, and a capability-constrained UAE-resident blueprint. These are architecture aids, not deployment guarantees. Confirm current regional availability, customer policy, data classification, and provider terms before selecting a profile.

## File Structure

```text
raqib-aml-investigator/
├── app.py                       # serves FastAPI and the built React UI
├── config.py                    # endpoints, models, origins, and feature flags
├── requirements.txt             # runtime dependencies
├── requirements-test.txt        # test-only dependencies
├── pytest.ini                   # markers and 85% branch-coverage gate
├── .coveragerc
├── .env.example                 # placeholders only; copy to .env for live mode
├── NotoNaskhArabic-Regular.ttf  # Arabic PDF font
├── docs/
│   ├── aml_policy.md            # trusted policy corpus
│   ├── kyc_profile.md           # synthetic customer evidence
│   └── wire_memo.md             # synthetic evidence with planted injection
├── src/
│   ├── agent.py                 # governed OCI Responses API loop
│   ├── api.py                   # REST, WebSocket, roles, and safe SPA serving
│   ├── bankdb.py                # seeded ledger and read-only SQL policy
│   ├── demo_tape.py/.json       # credential-free recorded investigation
│   ├── guardrails.py            # prompt-injection and PII checks
│   ├── knowledge.py             # trusted-policy embeddings + cosine retrieval
│   ├── oci_clients.py           # OCI/OpenAI-compatible client factories
│   ├── report.py                # English/Arabic PDF generation
│   ├── rules.py                 # deterministic, parameterized AML rules
│   ├── schemas.py               # validated domain and SAR contracts
│   ├── store.py                 # additive persistence and maker-checker state
│   └── tools.py                 # agent tool definitions and dispatcher
├── evals/                       # evaluation harness (writes EVALS.md)
│   ├── cases.py                 # labelled golden-case corpus + expectations
│   ├── runner.py                # headless investigation runner + token meter
│   ├── scoring.py               # verdict / grounding / policy scorers
│   ├── redteam.py               # prompt-injection corpus + guardrail sweep
│   ├── report.py                # EVALS.md generator
│   └── __main__.py              # CLI: golden | redteam | report
├── EVALS.md                     # generated evaluation report (real numbers)
├── tests/
│   ├── unit/                    # rules, ledger policy, and schema validation
│   ├── integration/             # persistence, retrieval, tools, and PDF output
│   ├── contract/                # REST, WebSocket, event, and agent contracts
│   ├── security/                # traversal, role, SQL, and trust-boundary checks
│   ├── evals/                   # deterministic flagship-case quality checks
│   └── live/                    # explicit opt-in OCI smoke tests
└── web/
    ├── src/
    │   ├── __tests__/           # Vitest/RTL routes, roles, SAR, architecture, rules
    │   ├── components/          # shell, states, dossier, timeline, and SAR UI
    │   ├── pages/               # five primary product destinations
    │   ├── api.js               # role-aware REST/WebSocket client
    │   └── App.jsx              # routing and application composition
    ├── package.json
    └── vite.config.js
```

## Setup

**Prerequisites**

- Python 3.11+
- Node.js 20.19+ and npm to rebuild, test, or develop the Vite 8 UI
- Optional for live mode: an OCI tenancy, a Generative AI project in a supported region, model access, and an OCI SDK profile for Guardrails and embeddings

**OCI Console Steps for Live Mode**

1. Open **Analytics & AI → Generative AI → Projects**, create a project, and copy its OCID.
2. Create a service-specific Generative AI API key for development.
3. Configure `~/.oci/config` with the `RAQIB_OCI_PROFILE` profile authorized for Guardrails and embeddings.
4. Verify the orchestrator, SAR, web-search, and embedding models in the chosen region. Do not assume that one model's availability implies every tool is available there.

**Install and Run in Demo Mode**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd web
npm ci
npm run build
cd ..
python app.py
```

Open `http://localhost:8117`. With no `.env`, the application identifies itself as **Recorded mode**.

**Enable Live Mode**

```bash
cp .env.example .env
# Replace placeholders in .env, then restart:
python app.py
```

`OPENAI_API_KEY_CHICAGO` and `CHICAGO_PROJECT_OCID` retain their original names even if `RAQIB_REGION` points to another supported region. Never commit `.env`. Live investigations can incur OCI usage and the adverse-media tool can create public-web egress.

**Run the Backend Test Suite**

```bash
source .venv/bin/activate
pip install -r requirements-test.txt
.venv/bin/pytest -q
```

`pytest.ini` enforces an 85% branch-coverage minimum across `src/`. The current baseline is **105 passing tests, 4 skipped opt-in live checks, and 86.26% branch coverage**. The normal suite replaces OCI client factories with fail-closed fakes, creates a fresh temporary SQLite database, and copies the bundled documents for isolation.

Run the real OCI smoke checks only after intentionally configuring credentials:

```bash
RAQIB_RUN_LIVE_TESTS=1 .venv/bin/pytest tests/live -q --no-cov
```

These checks make billable network calls. Possessing credentials alone never enables them.

**Run the UI Test Suite**

```bash
cd web
npm ci
npm test
```

The Vitest and React Testing Library suite exercises client-side routing, persona permissions, the maker-checker SAR lifecycle, the current/target architecture switch, and interactive rule simulation. The current baseline is **5 passing UI tests**. Use `npm run test:watch` during UI development.

**Develop the UI**

Run the API on port `8117`, then start Vite in a second terminal:

```bash
cd web
npm ci
npm run dev
```

The development origins in `config.py` are explicit. Set `RAQIB_ALLOWED_ORIGINS` if you use a different port or host.

**Model Alternatives**

Model IDs change over time and may be deprecated or unavailable in a selected region. Use the environment overrides in `.env.example` rather than editing application code, and verify the current **Models and Regions** documentation before a customer session. If a deployment cannot accept xAI's service boundary or public-web egress, choose an approved OCI model and replace or disable the adverse-media tool.

## Evaluation

Raqib is measured, not vibed. The `evals/` harness scores the agent against a
labelled corpus and red-teams the guardrail layer, writing a regenerable
[`EVALS.md`](EVALS.md):

```bash
python -m evals redteam            # guardrail injection sweep (no model credits needed)
python -m evals golden             # live golden-case suite (needs OPENAI_API_KEY_CHICAGO)
python -m evals golden --repeat 3  # + verdict-variance calibration
python -m evals report             # regenerate EVALS.md from both suites
```

- **Golden-case suite** — investigates labelled alerts end-to-end and scores each SAR
  on schema validity, verdict (file/no-file + risk band), watchlist call, policy
  citations, and **numeric grounding** (every counterparty amount must reconcile to the
  ledger — the anti-hallucination check). Includes calibration cases the agent should
  *stand down* on, not just launders.
- **Prompt-injection red-team** — 24 adversarial documents across 8 attack families
  fired at the same `ApplyGuardrails` layer the agent uses; reports catch rate per
  family and false-positive rate on benign documents. The guardrail sweep signs with
  `~/.oci/config` (IAM), so it runs without the Responses API key.
- **Defence in depth** — a missed guardrail catch is not a successful attack; the agent
  is separately instructed to distrust document content. Layer-2 (agent behaviour under
  attack) is measured by the golden suite.

The scorers have their own deterministic unit tests (`tests/evals/`), so the numbers
the report publishes are themselves tested.

## Useful Links

- [OCI Generative AI](https://docs.oracle.com/en-us/iaas/Content/generative-ai/home.htm)
- [OCI Responses API](https://docs.oracle.com/en-us/iaas/Content/generative-ai/responses-api.htm)
- [OCI Responses API authentication](https://docs.oracle.com/en-us/iaas/Content/generative-ai/oci-openai.htm)
- [File Search](https://docs.oracle.com/en-us/iaas/Content/generative-ai/file-search.htm)
- [Vector Stores and Semantic Stores](https://docs.oracle.com/en-us/iaas/Content/generative-ai/vector-stores.htm)
- [Agentic models and region availability](https://docs.oracle.com/en-us/iaas/Content/generative-ai/agentic-regions.htm)
- [OCI AI Guardrails](https://docs.oracle.com/en-us/iaas/Content/generative-ai/guardrails.htm)
- [SQL Search / NL2SQL](https://docs.oracle.com/en-us/iaas/Content/generative-ai/nl2sql.htm)

## License

Copyright (c) 2026 Oracle and/or its affiliates.
Licensed under the Universal Permissive License (UPL), Version 1.0.
All data in this asset is fictional and generated for demonstration purposes.
