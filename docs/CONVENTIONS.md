# Conventions

Read this before writing any code that touches shared data — the API, the database,
or any object listed in `docs/contracts/`. If you need a name or status that isn't
here, add it in the same PR that introduces it. Do not invent a variant of an
existing name (e.g. `income` instead of `family_income`).

## Frozen extracted fields (exactly these 9 — no more, no fewer)

| field_name | data_type | notes |
|---|---|---|
| `student_name` | string | |
| `date_of_birth` | date (`YYYY-MM-DD`) | |
| `board_percentile` | float | e.g. `86.4` |
| `course_mode` | enum | `"Regular"` or `"Distance"` |
| `institution_name` | string | |
| `institution_recognized` | boolean | |
| `family_income` | integer | in INR, no currency symbol, no commas (e.g. `420000` not `"₹4,20,000"`) |
| `other_scholarship` | boolean | |
| `application_date` | date (`YYYY-MM-DD`) | |

## Frozen policy rules (exactly these 6)

| rule_code | Logic |
|---|---|
| `CSSS_PERCENTILE_MIN` | `board_percentile > 80` |
| `CSSS_COURSE_MODE` | `course_mode == "Regular"` |
| `CSSS_INSTITUTION_RECOGNIZED` | `institution_recognized == true` |
| `CSSS_NO_OTHER_SCHOLARSHIP` | `other_scholarship == false` |
| `CSSS_INCOME_LIMIT` | `family_income <= 450000` |
| `CSSS_DOCUMENTS_PRESENT` | all required documents uploaded |

## Enum strings — use these exact strings, exact casing

**Field validation status** (`extracted_fields.validation_status`)
`VALID` | `INVALID` | `MISSING` | `AMBIGUOUS`

**Field trust status** (`extracted_fields.status`)
`UNTRUSTED` | `VALIDATED` | `OVERRIDDEN`

**Rule result** (`decision_rule_results.result`)
`PASS` | `FAIL` | `NOT_EVALUATED` | `NEEDS_REVIEW`

**Decision outcome** (`decisions.outcome`)
`ELIGIBLE` | `INELIGIBLE` | `NEEDS_REVIEW`

**Decision mode** (`decisions.decision_mode`)
`AUTOMATED` | `HUMAN_CONFIRMED` | `HUMAN_OVERRIDDEN`

**Application status** (`applications.status`)
`DRAFT` | `DOCUMENTS_UPLOADED` | `OCR_COMPLETED` | `FIELDS_EXTRACTED` |
`FIELDS_VALIDATED` | `RULES_EVALUATED` | `NEEDS_REVIEW` | `AUTO_DECISION` |
`HUMAN_CONFIRMED` | `FINALIZED`

**Review action type** (`review_actions.action_type`)
`CONFIRM_FIELD` | `EDIT_FIELD` | `REJECT_FIELD` | `ACCEPT_DECISION` |
`OVERRIDE_DECISION` | `REQUEST_DOCUMENT` | `ADD_NOTE`

**Audit event action_type** (`audit_log_entries.action_type`)
`APPLICATION_CREATED` | `DOCUMENT_UPLOADED` | `OCR_COMPLETED` |
`EXTRACTION_COMPLETED` | `FIELD_VALIDATED` | `RULE_EVALUATED` |
`DECISION_CREATED` | `REVIEW_STARTED` | `FIELD_OVERRIDDEN` |
`DECISION_VERSION_CREATED` | `FINALIZED`

**User roles** (`users.role`)
`ADMIN` | `PROCESSOR` | `REVIEWER` | `AUDITOR`

## Naming conventions

- Database columns and JSON keys: `snake_case`. Always.
- TypeScript interfaces (frontend): `PascalCase` for the type name, `snake_case` for
  keys to match the API response exactly — do not camelCase API fields on the way in.
- Currency values: always plain integers in INR (no symbols, no separators) in the
  database and API. Format for display (`₹4,20,000`) only in the frontend.
- Dates/timestamps: ISO 8601 always. Dates as `YYYY-MM-DD`, timestamps as
  `YYYY-MM-DDTHH:MM:SSZ` (UTC).
- IDs: UUIDs everywhere except the human-readable `public_reference` on
  `applications` (e.g. `APP-00016`).

## Fixed demo application IDs (Person 5 owns — do not invent your own)

| public_reference | Case | Expected outcome |
|---|---|---|
| `APP-00016` | Clean, eligible | `ELIGIBLE`, `AUTOMATED`, high confidence |
| `APP-00017` | Low OCR confidence + missing document | `NEEDS_REVIEW` |
| `APP-00018` | Human override case (₹4,80,000 → ₹4,08,000) | `NEEDS_REVIEW` → `HUMAN_CONFIRMED` `ELIGIBLE` |

Everyone uses these exact IDs in screenshots, test scripts, and the demo — no ad hoc
test data mid-build.

## Policy version strings

- `CSSS-Demo-v1.0` — income ≤ ₹4,50,000
- `CSSS-Demo-v1.1` — same, plus requires a dated income certificate

## Confidence display rule (frontend)

Never show a bare percentage like "AI confidence: 92%". Always show the components:

```
Evidence confidence: High
OCR quality: 96%
Evidence matched: Exact
Rule validation: Passed
```

## Golden rule, restated

The rules engine only ever consumes objects with `status == "VALIDATED"`. Gemini
never decides eligibility. If in doubt about a name, check this file first, then
`docs/contracts/`, then the live `/docs` Swagger page — never guess.
