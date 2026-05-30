# Credit v1b Sub-Plan 07 — Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire guarantor hooks into disbursement/repayment/write-off, update CLAUDE.md
with v1b contracts, verify CI snapshot check, and confirm the full test suite passes.

**Architecture:** All lien mutations (`place_liens`, `adjust_liens`, `release_liens`,
`reactivate_liens`) are called within the same DB transaction as the triggering financial
operation. No new transactions are opened.

**Prerequisite:** Sub-plans 01–06 all complete and passing.

---

## Required Reading

Before starting:
- `app/modules/credit/services/disbursement.py` — Step 11 (finalize) is the insertion point for `place_liens`
- `app/modules/credit/services/repayment.py` — Step 6 (snapshot update) for `adjust_liens`; Step 9 (closure) for `release_liens`
- `app/modules/credit/services/write_off.py` — `_execute_write_off` is the insertion point for `release_liens`
- `app/modules/credit/services/guarantor.py` (from sub-plan 02) — method signatures
- `CLAUDE.md` — current credit contracts (lines 103–127)
- `scripts/check_snapshot_writes.sh` — CI snapshot check

---

## Task 1: Wire `place_liens` into disbursement

**Files:**
- Modify: `app/modules/credit/services/disbursement.py`

The insertion point is after `loan.status = "disbursed"` (Step 11, near line 242).
`GuarantorService.place_liens()` is a no-op when `product.required_guarantors == 0`,
so it's safe to call unconditionally.

- [ ] **Step 1: Write the failing integration test**

Create `tests/modules/credit/test_guarantor_integration.py`:

```python
"""Integration tests — guarantor hooks wired into disbursement/repayment/write-off."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select


# These tests assume sub-plans 01 and 02 are implemented. They verify that
# the integration hooks call the right GuarantorService methods at the right time.


async def test_disburse_no_guarantors_is_noop(
    tenant_session,
    seeded_loan_product,  # required_guarantors=0
    db_member,
    db_savings_account,
    gl_accounts,
):
    """Disbursement with required_guarantors=0 creates no lien rows."""
    from app.modules.credit.models import LoanApplication
    from app.modules.credit.services.disbursement import LoanDisbursementService
    from app.modules.credit.models import LoanGuarantorLien  # from sub-plan 01

    app_obj = LoanApplication(
        loan_product_id=seeded_loan_product.id,
        member_id=db_member.id,
        requested_amount=Decimal("100000"),
        requested_term_periods=6,
        purpose="integration test",
        disbursement_destination="internal_gl",
        disbursement_account_id=gl_accounts["disbursement"].id,
        status="approved",
        approved_amount=Decimal("100000"),
        approved_term_periods=6,
        idempotency_key=str(uuid.uuid4()),
    )
    tenant_session.add(app_obj)
    await tenant_session.commit()

    svc = LoanDisbursementService(tenant_session)
    loan = await svc.disburse(
        loan_application_id=app_obj.id,
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        idempotency_key=str(uuid.uuid4()),
    )
    await tenant_session.commit()

    liens = (
        await tenant_session.scalars(
            select(LoanGuarantorLien).where(
                LoanGuarantorLien.loan_guarantor_id.in_(
                    select(LoanGuarantor.id).where(LoanGuarantor.loan_id == loan.id)
                )
            )
        )
    ).all()
    # No guarantors required → no liens
    assert liens == []
```

> Note: This test will fail until the hook is wired. If `LoanGuarantorLien` import fails,
> confirm sub-plan 01 models are in place.

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/modules/credit/test_guarantor_integration.py::test_disburse_no_guarantors_is_noop -v
```

Expected: Either `PASSED` (no-op path already safe) or `FAILED` with import error.

- [ ] **Step 3: Add `place_liens` call to `disbursement.py`**

Open `app/modules/credit/services/disbursement.py`. Locate the section after
`loan.status = "disbursed"` (Step 11 finalize) and before `application.status = "disbursed"`.
Add the `place_liens` call:

```python
        # Step 11: Finalize.
        loan.status = "disbursed"

        # ── Step 11a: Place guarantor liens (no-op when required_guarantors=0) ──
        from app.modules.credit.services.guarantor import GuarantorService  # noqa: PLC0415
        guarantor_svc = GuarantorService(self._session)
        await guarantor_svc.place_liens(
            loan_id=loan.id,
            loan_application_id=loan_application_id,
            principal_amount=principal,
        )

        application.status = "disbursed"
        await self._session.flush()
```

- [ ] **Step 4: Run integration test**

```
pytest tests/modules/credit/test_guarantor_integration.py -v
```

Expected: `PASSED`.

- [ ] **Step 5: Run full disbursement test suite to check no regressions**

```
pytest tests/modules/credit/test_service.py \
       tests/modules/credit/test_api.py \
       tests/modules/credit/test_guarantor_integration.py -v --tb=short
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add app/modules/credit/services/disbursement.py \
        tests/modules/credit/test_guarantor_integration.py
git commit -m "feat(credit): wire GuarantorService.place_liens into disbursement"
```

---

## Task 2: Wire `adjust_liens` and `release_liens` into repayment

**Files:**
- Modify: `app/modules/credit/services/repayment.py`

Two insertion points:
1. **After Step 6** (snapshot update, ~line 166): call `adjust_liens` with `principal_applied`
2. **After Step 9** (closure detection, ~line 203): call `release_liens` when `is_closed=True`

- [ ] **Step 1: Add the hooks to `repayment.py`**

Open `app/modules/credit/services/repayment.py`. After the snapshot update block
(`loan.last_repayment_amount = amount`, Step 6), add:

```python
        # ── Step 6a: Adjust guarantor liens proportionally ────────────────────
        from app.modules.credit.services.guarantor import GuarantorService  # noqa: PLC0415
        guarantor_svc = GuarantorService(self._session)
        if principal_applied > Decimal("0"):
            await guarantor_svc.adjust_liens(
                loan_id=loan_id,
                principal_applied=principal_applied,
                original_principal=loan.principal_amount,
            )
```

After the closure detection block (the `if is_closed:` block that sets `loan.closed_at`),
add:

```python
        if is_closed:
            # ── Step 9a: Release all guarantor liens on closure ───────────────
            await guarantor_svc.release_liens(loan_id=loan_id)
```

> Note: `guarantor_svc` is already defined above (step 6a). Do not re-import.

- [ ] **Step 2: Write the hook test**

Add to `tests/modules/credit/test_guarantor_integration.py`:

```python
async def test_repayment_adjusts_liens(
    tenant_session,
    # Fixtures from sub-plan 02 test file — a loan with active guarantor liens
    loan_with_guarantor_lien,  # pre-built fixture
    gl_accounts,
):
    """After repayment, active lien current_lien is reduced proportionally."""
    from app.modules.credit.models import LoanGuarantorLien
    from app.modules.credit.services.repayment import LoanRepaymentService

    loan, lien = loan_with_guarantor_lien

    original_current_lien = lien.current_lien
    original_principal = loan.outstanding_principal

    # Apply a partial repayment (principal component only for simplicity).
    svc = LoanRepaymentService(tenant_session)
    await svc.apply_repayment(
        loan_id=loan.id,
        amount=Decimal("50000"),
        payment_account_id=gl_accounts["disbursement"].id,
        posted_by=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        idempotency_key=str(uuid.uuid4()),
    )
    await tenant_session.commit()

    await tenant_session.refresh(lien)
    await tenant_session.refresh(loan)

    # Lien must have been reduced.
    assert lien.current_lien < original_current_lien
    assert lien.current_lien >= Decimal("0")
```

> If `loan_with_guarantor_lien` fixture is not available in conftest.py, skip this
> test for now — the service unit tests in sub-plan 02 already cover `adjust_liens`
> in isolation. The important check is that the hook is wired (no exceptions on repayment).

- [ ] **Step 3: Run tests**

```
pytest tests/modules/credit/ -v --tb=short -k "repayment or guarantor"
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add app/modules/credit/services/repayment.py \
        tests/modules/credit/test_guarantor_integration.py
git commit -m "feat(credit): wire adjust_liens and release_liens into repayment service"
```

---

## Task 3: Wire `release_liens` into write-off

**Files:**
- Modify: `app/modules/credit/services/write_off.py`

Insertion point: in `_execute_write_off`, after `loan.status = "written_off"` is set
(after the snapshot update) and before `EventPublisher.publish`.

- [ ] **Step 1: Add the hook to `_execute_write_off`**

Open `app/modules/credit/services/write_off.py`. In `_execute_write_off`, after the
snapshot mutation block:

```python
        # Update snapshot.
        loan.outstanding_principal = loan.outstanding_principal - amount
        loan.total_written_off = loan.total_written_off + amount
        if loan.outstanding_principal == Decimal("0"):
            loan.status = "written_off"

        await self._session.flush()

        # ── Release guarantor liens on write-off ─────────────────────────────
        from app.modules.credit.services.guarantor import GuarantorService  # noqa: PLC0415
        guarantor_svc = GuarantorService(self._session)
        await guarantor_svc.release_liens(loan_id=loan.id)

        await EventPublisher.publish(
```

- [ ] **Step 2: Run write-off and recovery tests**

```
pytest tests/modules/credit/test_write_off_recovery.py \
       tests/modules/credit/ -v --tb=short -k "write_off or recovery"
```

Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add app/modules/credit/services/write_off.py
git commit -m "feat(credit): wire GuarantorService.release_liens into write-off executor"
```

---

## Task 4: Update CLAUDE.md with v1b contracts

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append v1b contracts to CLAUDE.md**

Open `CLAUDE.md` and append the following section after the existing
`## Credit module contracts` block:

```markdown
## Credit module v1b contracts (do not violate)
- Guarantor lien balance is always computed as SUM(current_lien WHERE is_active=true)
  from loan_guarantor_liens. Never cache this value outside a transaction.
- SavingsService.get_available_balance() must always subtract active liens before
  returning a withdrawable balance. Never bypass this for guarantors.
- Lien mutations (place_liens, adjust_liens, release_liens, reactivate_liens) must
  happen in the same DB transaction as the triggering financial operation (disbursement,
  repayment, write-off, recovery). Never update liens in a separate transaction.
- Payroll batch lines are applied one per commit. A failed line records status=error
  and does NOT roll back successfully applied lines.
- Restructuring never deletes installment rows. Mark is_superseded=true and write new rows.
- Write-off recovery does not require maker-checker. The cash receipt is the authorizing event.
- WeasyPrint is the only permitted PDF renderer in this module. Do not add alternative
  PDF libraries.
```

- [ ] **Step 2: Verify CLAUDE.md reads well**

```bash
grep -n "v1b contracts" CLAUDE.md
```

Expected: One line with `v1b contracts`.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: append credit module v1b contracts to CLAUDE.md"
```

---

## Task 5: Verify CI snapshot check still passes

**Files:**
- None (read-only verification)

- [ ] **Step 1: Run the CI snapshot check**

```bash
bash scripts/check_snapshot_writes.sh
```

Expected output:
```
Checking snapshot column writes are confined to app/modules/credit/services/ ...
OK: No snapshot column writes found outside app/modules/credit/services/
Checking credit module does not call system_debit/system_credit ...
OK: No system_debit/system_credit in credit module

All checks passed.
```

If there are violations, identify which file is writing snapshot columns outside of
`app/modules/credit/services/` and fix it before proceeding.

- [ ] **Step 2: Check new v1b service files don't introduce violations**

The new files `guarantor.py`, `restructuring.py`, `payroll.py`, `statement.py` and
the modified `write_off.py` all live inside `app/modules/credit/services/` — they are
explicitly excluded from the snapshot write check. Verify:

```bash
rg "outstanding_principal|accrued_interest|total_written_off" \
   app/modules/credit/services/ --type py -l
```

Expected: Only files in `app/modules/credit/services/` listed.

---

## Task 6: Final verification — full test suite

- [ ] **Step 1: Import smoke test**

```bash
python -c "from app.main import app; print('OK')"
```

Expected: `OK`.

- [ ] **Step 2: Run the full credit test suite**

```
pytest tests/modules/credit/ -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 3: Run the full test suite**

```
pytest -x -q
```

Expected: All tests pass, no failures or errors.

If any test fails:
1. Read the full traceback.
2. Identify the root cause (missing import, wrong method signature, etc.).
3. Fix the specific file — do not comment out tests.
4. Re-run until clean.

- [ ] **Step 4: Run CI check one final time**

```bash
bash scripts/check_snapshot_writes.sh
```

Expected: `All checks passed.`

- [ ] **Step 5: Final commit**

```bash
git add -u  # stage any remaining unstaged changes
git status  # verify nothing unexpected is staged
git commit -m "feat(credit): credit v1b integration complete — guarantor hooks wired into all financial operations"
```

---

## Verification Checklist

- [ ] `python -c "from app.main import app; print('OK')"` — no import errors
- [ ] `pytest -x -q` — full suite passes
- [ ] `bash scripts/check_snapshot_writes.sh` — all checks passed
- [ ] Disbursement calls `place_liens` (no-op for products with `required_guarantors=0`)
- [ ] Repayment calls `adjust_liens` after principal update; calls `release_liens` on closure
- [ ] Write-off calls `release_liens` after snapshot update
- [ ] CLAUDE.md has `## Credit module v1b contracts` section
