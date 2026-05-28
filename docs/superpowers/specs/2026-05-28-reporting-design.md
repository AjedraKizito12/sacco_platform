# Reporting Module — Design Spec

**Date:** 2026-05-28
**Status:** Approved

---

## Goal

Build the `reporting` bounded context: five pre-aggregated financial reports (trial balance, loan portfolio, income statement, savings statement, fee collection) served as JSON, PDF, and CSV. Reports are materialized nightly via Celery beat into per-report summary tables; API endpoints query the summary tables directly.

---

## Consumers

- **Internal SACCO staff** — loan officers, accountants, managers via management API / UI / PDF downloads
- **External regulators / auditors** — same data, different output layout. Statutory format variants are out of scope for v1 but the rendering layer is designed to accept alternative templates without changing service logic.

---

## Architecture

**Option chosen: Report-per-service (Option B)**

Each of the five report types has its own service class, its own Celery beat task, and its own summary table. Shared infrastructure (PDF/CSV rendering, `ReportRun` audit table) lives in the module root. This mirrors the existing bounded-context pattern throughout the codebase.

---

## Module Structure

```
app/modules/reporting/
├── models.py          — ReportRun + 5 summary table models
├── schemas.py         — Pydantic response types for all 5 reports
├── api.py             — FastAPI router, all report endpoints
├── beat.py            — Celery beat task registrations (5 nightly jobs)
├── _base.py           — Shared PDF (WeasyPrint) + CSV rendering utilities
├── services/
│   ├── trial_balance.py
│   ├── loan_portfolio.py
│   ├── income_statement.py
│   ├── savings_statement.py
│   └── fee_collection.py
└── templates/
    ├── trial_balance.html
    ├── loan_portfolio.html
    ├── income_statement.html
    ├── savings_statement.html
    └── fee_collection.html
```

---

## Data Model

### `ReportRun`

Tracks every materialization job run. One row per (report_type, run).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `report_type` | Text | `trial_balance`, `loan_portfolio`, `income_statement`, `savings_statement`, `fee_collection` |
| `as_of_date` | Date | The date the report reflects data up to |
| `status` | Text | `running`, `done`, `failed` |
| `started_at` | Timestamptz | |
| `completed_at` | Timestamptz | Nullable |
| `error_detail` | Text | Nullable — traceback on failure |

Check constraint: `status IN ('running', 'done', 'failed')`.
Index on `(report_type, as_of_date DESC)` for fast "latest run" lookups.

### Summary Tables

**`report_trial_balance_lines`**

| Column | Type |
|---|---|
| `id` | UUID PK |
| `report_run_id` | UUID FK → report_runs |
| `as_of_date` | Date |
| `account_id` | UUID |
| `account_code` | Text |
| `account_name` | Text |
| `account_type` | Text (`asset`, `liability`, `equity`, `income`, `expense`) |
| `debit_total` | Numeric(19,4) |
| `credit_total` | Numeric(19,4) |
| `balance` | Numeric(19,4) |

**`report_loan_portfolio_rows`**

| Column | Type |
|---|---|
| `id` | UUID PK |
| `report_run_id` | UUID FK → report_runs |
| `as_of_date` | Date |
| `loan_id` | UUID |
| `loan_reference` | Text |
| `member_id` | UUID |
| `product_name` | Text |
| `disbursed_at` | Date |
| `maturity_date` | Date |
| `status` | Text |
| `outstanding_principal` | Numeric(19,4) |
| `accrued_interest` | Numeric(19,4) |
| `total_written_off` | Numeric(19,4) |
| `days_in_arrears` | Integer |
| `aging_bucket` | Text (`current`, `1_30`, `31_60`, `61_90`, `90_plus`) |

**`report_income_statement_lines`**

| Column | Type |
|---|---|
| `id` | UUID PK |
| `report_run_id` | UUID FK → report_runs |
| `period_start` | Date |
| `period_end` | Date |
| `account_id` | UUID |
| `account_code` | Text |
| `account_name` | Text |
| `account_type` | Text (`income`, `expense`) |
| `debit_total` | Numeric(19,4) |
| `credit_total` | Numeric(19,4) |
| `net_movement` | Numeric(19,4) — credit_total - debit_total (positive = income) |

**`report_savings_statement_lines`**

| Column | Type |
|---|---|
| `id` | UUID PK |
| `report_run_id` | UUID FK → report_runs |
| `period_start` | Date |
| `period_end` | Date |
| `savings_account_id` | UUID |
| `member_id` | UUID |
| `posted_at` | Timestamptz |
| `transaction_type` | Text |
| `narration` | Text |
| `amount` | Numeric(19,4) |
| `running_balance` | Numeric(19,4) |

**`report_fee_collection_rows`**

| Column | Type |
|---|---|
| `id` | UUID PK |
| `report_run_id` | UUID FK → report_runs |
| `period_start` | Date |
| `period_end` | Date |
| `fee_type_id` | UUID |
| `fee_type_name` | Text |
| `target_type` | Text |
| `assessed_total` | Numeric(19,4) |
| `collected_total` | Numeric(19,4) |
| `outstanding_total` | Numeric(19,4) |
| `waived_total` | Numeric(19,4) |

All summary tables live in the tenant schema (no `schema=` on models). They are **truncated and repopulated on each nightly run** — they are not append-only.

---

## Materialization

### Flow (identical for all 5 reports)

1. Insert `ReportRun(status="running", started_at=now())`.
2. Delete existing rows in the summary table for the same `report_run_id` (or truncate if first run of the day).
3. Run aggregation query.
4. Bulk-insert results into the summary table.
5. Update `ReportRun` to `status="done"`, set `completed_at`.
6. On exception: update `ReportRun` to `status="failed"`, store traceback in `error_detail`, re-raise.

### Data Sources (per CLAUDE.md authority rules)

| Report | Source |
|---|---|
| Trial balance | `journal_lines` + `journal_entries` + `chart_of_accounts` (GL authoritative for accounting) |
| Loan portfolio | `loans` snapshot columns (`outstanding_principal`, `accrued_interest`, `total_written_off`, `status`, `maturity_date`) — never recompute from GL |
| Income statement | `journal_lines` + `journal_entries` + `chart_of_accounts` filtered to `account_type IN ('income', 'expense')` |
| Savings statement | `savings_transactions` with window function for running balance — all members materialized; filtered by `member_id` at query time |
| Fee collection | `fee_assessments` + `fee_collections` |

### Aging Buckets (loan portfolio)

Computed at materialization time from `date.today() - first_overdue_installment.due_date` for loans in `in_arrears` status. Loans in `disbursed` status with no overdue installments = `current`. Stored as enum string in summary table.

```
current   — no overdue installments
1_30      — 1–30 days overdue
31_60     — 31–60 days overdue
61_90     — 61–90 days overdue
90_plus   — > 90 days overdue
```

### Schedule

Five independent Celery beat tasks, all scheduled at `01:00 UTC` nightly (same slot as `reconcile_loan_snapshots`). A failure in one does not affect the others.

---

## API

All endpoints under `/reporting/`. Auth: same tenant JWT dependency as all other modules.

### Endpoints

```
GET /reporting/trial-balance
    ?as_of=YYYY-MM-DD        (default: latest successful run)
    ?format=json|pdf|csv     (default: json)

GET /reporting/loan-portfolio
    ?as_of=YYYY-MM-DD        (default: latest)
    ?status=all|disbursed|in_arrears|written_off  (default: all)
    ?format=json|pdf|csv

GET /reporting/income-statement
    ?from_date=YYYY-MM-DD    (required)
    ?to_date=YYYY-MM-DD      (required)
    ?format=json|pdf|csv

GET /reporting/savings-statement
    ?member_id=UUID          (required)
    ?from_date=YYYY-MM-DD
    ?to_date=YYYY-MM-DD
    ?format=json|pdf|csv

GET /reporting/fee-collection
    ?from_date=YYYY-MM-DD    (required)
    ?to_date=YYYY-MM-DD      (required)
    ?fee_type_id=UUID        (optional filter)
    ?format=json|pdf|csv

GET /reporting/runs
    ?report_type=<type>      (optional filter)
    ?limit=20
```

### Format Dispatch

Handled in `_base.py`, not in service classes:

- `json` — FastAPI serializes the Pydantic response model. Response includes `as_of_date` and `generated_at` metadata.
- `pdf` — `render_pdf(template_name, context) -> bytes` via WeasyPrint. Returns `application/pdf` with `Content-Disposition: attachment; filename="<report>-<date>.pdf"`.
- `csv` — `render_csv(headers, rows) -> bytes` via Python stdlib `csv`. Returns `text/csv`.

Excel is not a separate format — CSV opens cleanly in Excel without adding an `openpyxl` dependency.

### Error responses

- `404` — No materialized data exists for the requested date/period. Response body includes `last_successful_run` timestamp.
- `422` — Invalid query parameters (missing required param, bad date format, unknown status value).

---

## Output Rendering (`_base.py`)

```python
def render_pdf(template_name: str, context: dict) -> bytes
def render_csv(headers: list[str], rows: list[list]) -> bytes
```

`render_pdf` uses the Jinja2 + WeasyPrint pipeline already established in `LoanStatementService`. Templates live in `app/modules/reporting/templates/`.

Each HTML template receives: report data rows, metadata (`as_of_date`, `generated_at`, `tenant_name`), and filter parameters (date range, status filter, etc.).

---

## Testing

**Per-service tests** (`tests/modules/reporting/test_<name>.py`):
- Seed relevant source tables directly.
- Call `service.materialize(as_of_date)` and assert summary table rows are correct (amounts, aging buckets, running balances).
- Run `materialize()` twice — assert idempotency (no duplicate rows).

**Rendering tests** (in same file):
- Call `service.get_*()` → pass through `render_pdf()` → assert `result[:4] == b"%PDF"`.
- Call `render_csv()` → assert valid UTF-8 with correct headers.

**Beat task tests**:
- Call Celery task function directly (not via worker) → assert `ReportRun` created with `status="done"`.

**API tests** (`tests/modules/reporting/test_api.py`):
- One test per endpoint per format (json, pdf, csv) — assert status code and content-type.
- One test per endpoint for missing materialized data — assert 404.

---

## Sub-Plan Breakdown

| Sub-plan | Scope |
|---|---|
| 01 | Module skeleton: Alembic migration (6 tables), `ReportRun` model + 5 summary models, `_base.py` PDF/CSV rendering, `api.py` router stub |
| 02 | Trial Balance: `TrialBalanceService.materialize()` + `get_trial_balance()`, beat task, API endpoint, HTML template |
| 03 | Loan Portfolio: `LoanPortfolioService.materialize()` + `get_loan_portfolio()`, beat task, API endpoint, HTML template |
| 04 | Income Statement: `IncomeStatementService.materialize()` + `get_income_statement()`, beat task, API endpoint, HTML template |
| 05 | Savings Statement: `SavingsStatementService.materialize()` + `get_savings_statement()`, beat task, API endpoint, HTML template |
| 06 | Fee Collection: `FeeCollectionService.materialize()` + `get_fee_collection()`, beat task, API endpoint, HTML template |

Each sub-plan produces independently testable, working software.

---

## Constraints (from CLAUDE.md)

- Loan balance snapshot columns (`outstanding_principal` etc.) are authoritative for operational queries. Never recompute from GL journal lines for loan portfolio data.
- All cross-module reads go through service interfaces. Reporting reads directly from source tables (GL, loans, savings, fees) — it does not call other modules' service classes, to avoid coupling.
- No direct `system_debit`/`system_credit` calls from reporting (read-only module).
- WeasyPrint is the only permitted PDF renderer.
