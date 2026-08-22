# Project Synapse

**Evidence-Grounded Decision Audit for AI-Assisted Government Workflows**
SIH 2026 — Internal Round Prototype

## What this is

A single-workflow prototype that shows, for one government scholarship scheme (PM-USP
Central Sector Scheme of Scholarship), exactly which document evidence produced an
eligibility decision, which policy rule was applied, what confidence/uncertainty
existed, what a human reviewer changed, and lets that decision be replayed step by
step afterward.

We are **not** building the real scholarship portal. We are building the
accountability layer around an AI-assisted decision.

Full build plan, per-person task breakdown, timeline, and demo script:
see `docs/BUILD_MANUAL.docx` (shared separately with the team).

## Team & roles

| Person | Role | Owns |
|---|---|---|
| Person 1 (Lead) | Backend / Orchestration | Repo, FastAPI skeleton, DB, API endpoints, `/process` pipeline |
| Person 2 | AI / OCR Engineer | OCR pipeline, Gemini structured extraction, evidence matching |
| Person 3 | Frontend Engineer | Next.js app — dashboard, evidence, rules, review, replay screens |
| Person 4 | Security / Audit / Replay | Hash-chain + HMAC audit log, verify-chain, decision versioning, replay |
| Person 5 | Demo Data / Integration / Deployment | Synthetic documents, end-to-end testing, deployment, adversarial testing |

## Repo structure

```
sih-synapse/
├── frontend/            Next.js + TypeScript + Tailwind + shadcn/ui
├── backend/              FastAPI + Python
│   └── app/
│       ├── main.py
│       ├── api/          applications.py, documents.py, review.py, replay.py
│       ├── core/         config.py, security.py
│       ├── db/           models.py, session.py
│       ├── services/     ocr_service.py, extraction_service.py, evidence_service.py,
│       │                 rules_service.py, audit_service.py, replay_service.py,
│       │                 report_service.py
│       └── schemas/      application.py, extraction.py, decision.py, audit.py
├── demo-data/            Synthetic PDFs + expected outcomes (Person 5 owns)
├── docs/
│   ├── CONVENTIONS.md    Frozen field names, rule codes, enum strings — read this first
│   ├── contracts/        One example JSON per data handoff point (see below)
│   └── BUILD_MANUAL.docx Full task breakdown, timeline, demo script
├── .env.example
├── .gitignore
└── README.md
```

## Shared data contracts

Before writing any service logic, read `docs/contracts/`. These six JSON files are
the literal, frozen shape of data at every handoff point in the pipeline:

1. `ocr_token.json` — Person 2 → Person 1
2. `extraction_candidate.json` — Person 2 → Person 1
3. `validated_field.json` — Person 1/2 → Person 3, Person 4
4. `rule_result.json` — Person 1 → Person 3, Person 4
5. `decision.json` — Person 1/4 → Person 3
6. `audit_event.json` — Person 4 → everyone

If a contract needs to change, post it in the team chat and get explicit sign-off
from everyone who touches that object before changing it, then update the file in
the same PR.

## Getting started

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env     # fill in your own keys
uvicorn app.main:app --reload
```

API docs (live, always up to date): `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
cp ../.env.example .env.local  # fill in NEXT_PUBLIC_ vars only
npm run dev
```

App: `http://localhost:3000`

### Environment variables

See `.env.example` for the full list. Never commit a real `.env` or `.env.local` —
both are already in `.gitignore`.

## Git workflow

- `main` — always deployable. Protected, requires PR + 1 approval.
- `develop` — integration branch. Protected, requires PR + 1 approval.
- `feature/backend`, `feature/ocr`, `feature/frontend`, `feature/audit`, `feature/demo`
  — one per role, branch off `develop`, PR back into `develop`.
- Merge into `develop` at each integration checkpoint (hour 6 / 12 / 18 / 24) —
  not once at the end.

## Integration checkpoints

| Hour | Checkpoint | Pass condition |
|---|---|---|
| 6 | OCR + skeleton API | Real OCR JSON matches `ocr_token.json`, Person 1 can store it |
| 12 | Extraction + evidence | A real document produces a `validated_field.json`-shaped object end-to-end |
| 18 | Rules + decision | A real field list produces a real `decision.json`-shaped object |
| 24 | Full chain + audit | Upload → OCR → extraction → rules → decision → review → audit → replay works once, live |

Post a status update in the team chat at each checkpoint: what's live, what broke,
what changed in a contract.

## Non-negotiable rules

- The rules engine is pure Python. Gemini never decides eligibility.
- Any extracted field that can't be linked to real OCR text (≥ 0.90 match) is
  `UNTRUSTED` and is blocked from the rules engine.
- A `FINALIZED` decision is never edited in place — corrections create a new
  decision version + a new audit event.
- Replay reconstructs historical snapshots. It never re-runs today's live rules.
- No message queue, no blockchain, no complex rules framework, no scope creep past
  the frozen fields and rules in `docs/CONVENTIONS.md`.
