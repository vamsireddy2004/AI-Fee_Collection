from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(prefix="/imports", tags=["Excel/CSV Import Preview"])
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
REQUIRED_COLUMNS = {
    "student id": "student_id",
    "student name": "student_name",
    "branch": "branch",
    "fee_pending": "fee_pending",
    "due_date": "due_date",
    "parent_name": "parent_name",
    "mobile_number": "mobile_number",
    "status": "status",
    "parent_response": "parent_response",
}


def _normalise_header(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def _parse_amount(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        amount = Decimal(str(value).replace(",", "").replace("₹", "").strip())
        if not amount.is_finite() or amount < 0:
            return None
        return amount.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _parse_file(filename: str, raw: bytes) -> list[dict[str, Any]]:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "csv":
        try:
            decoded = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(400, "CSV must be UTF-8 encoded (Excel CSV UTF-8 is recommended).")
        reader = csv.DictReader(io.StringIO(decoded))
        if not reader.fieldnames:
            raise HTTPException(400, "The CSV file has no header row.")
        headers = {_normalise_header(h): h for h in reader.fieldnames}
        missing = [h for h in REQUIRED_COLUMNS if h not in headers]
        if missing:
            raise HTTPException(400, {"message": "Required columns are missing.", "missing_columns": missing})
        result = []
        for row in reader:
            result.append({_normalise_header(k): v for k, v in row.items() if k is not None})
        return result
    if ext in ("xlsx", "xlsm"):
        try:
            from openpyxl import load_workbook
            workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        except Exception:
            raise HTTPException(400, "Could not read this Excel file. Please upload a valid .xlsx file.")
        try:
            sheet = workbook.active
            values = sheet.iter_rows(values_only=True)
            headers_row = next(values, None)
            if not headers_row:
                raise HTTPException(400, "The Excel sheet is empty.")
            headers = {_normalise_header(v): i for i, v in enumerate(headers_row) if v is not None}
            missing = [h for h in REQUIRED_COLUMNS if h not in headers]
            if missing:
                raise HTTPException(400, {"message": "Required columns are missing.", "missing_columns": missing})
            result = []
            for values_row in values:
                row = {}
                for key, idx in headers.items():
                    row[key] = values_row[idx] if idx < len(values_row) else None
                result.append(row)
            return result
        finally:
            workbook.close()
    raise HTTPException(400, "Unsupported file type. Upload .csv or .xlsx. Penalty is ignored.")


@router.post("/fee-list/preview", summary="Dry-run preview of college Excel/CSV fee list")
async def preview_fee_list(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Read-only import validation. Never inserts/updates data or places calls."""
    filename = file.filename or ""
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds 5 MB. Please split the spreadsheet into smaller files.")
    rows = _parse_file(filename, raw)
    if len(rows) > 2000:
        raise HTTPException(413, "Maximum 2,000 rows per preview. Please split the file.")

    # Build a read-only snapshot of the relevant MySQL records.
    students = db.execute(text("""
        SELECT student_id, roll_number, full_name, parent_name,
               parent_mobile, call_consent, is_active
        FROM students
    """)).mappings().all()
    # branch/class fields vary by installation; the supplied schema has course and division.
    student_by_id = {str(s["student_id"]): dict(s) for s in students}
    student_by_roll = {str(s["roll_number"]).strip().lower(): dict(s) for s in students}

    fee_rows = db.execute(text("""
        SELECT s.student_id, f.fee_account_id, f.account_status,
               i.installment_id, i.installment_amount, i.due_date,
               i.status AS installment_status, i.reminder_enabled,
               COALESCE(p.paid_amount, 0) AS verified_paid_amount,
               GREATEST(i.installment_amount - COALESCE(p.paid_amount, 0), 0) AS balance
        FROM students s
        JOIN fee_accounts f ON f.student_id = s.student_id
        JOIN installments i ON i.fee_account_id = f.fee_account_id
        LEFT JOIN (
            SELECT installment_id, SUM(amount) AS paid_amount
            FROM payments WHERE payment_status = 'verified'
            GROUP BY installment_id
        ) p ON p.installment_id = i.installment_id
    """)).mappings().all()
    fee_by_student = {}
    for fr in fee_rows:
        fee_by_student.setdefault(str(fr["student_id"]), []).append(dict(fr))

    seen = set()
    preview = []
    counts = {"ready_for_manual_review": 0, "blocked": 0, "invalid": 0, "duplicate_rows": 0}
    for idx, source in enumerate(rows, start=2):
        row = {k: source.get(k) for k in REQUIRED_COLUMNS}
        reasons: list[str] = []
        raw_id = str(row.get("student id") or "").strip()
        student = student_by_id.get(raw_id) or student_by_roll.get(raw_id.lower())
        pending = _parse_amount(row.get("fee_pending"))
        due_date = _parse_date(row.get("due_date"))
        mobile_raw = str(row.get("mobile_number") or "").strip()
        digits = re.sub(r"\D", "", mobile_raw)
        mobile_valid = len(digits) == 10 or (len(digits) == 12 and digits.startswith("91"))
        if not raw_id:
            reasons.append("missing_student_id")
        if not student:
            reasons.append("student_not_found_in_mysql")
        if pending is None:
            reasons.append("invalid_fee_pending_amount")
        if due_date is None:
            reasons.append("invalid_due_date")
        if not mobile_valid:
            reasons.append("invalid_mobile_number")
        if student:
            if not bool(student["is_active"]):
                reasons.append("student_inactive")
            if not bool(student["call_consent"]):
                reasons.append("no_call_consent")
            if mobile_valid and re.sub(r"\D", "", str(student["parent_mobile"] or ""))[-10:] != digits[-10:]:
                reasons.append("spreadsheet_mobile_mismatch")
        matched_fee = None
        if student and due_date:
            possible = fee_by_student.get(str(student["student_id"]), [])
            matching = [f for f in possible if f["due_date"] == due_date]
            if len(matching) == 1:
                matched_fee = matching[0]
            elif len(matching) == 0:
                reasons.append("no_installment_matches_student_and_due_date")
            else:
                reasons.append("multiple_installments_match_student_and_due_date")
        if matched_fee:
            if matched_fee["account_status"] != "active":
                reasons.append("fee_account_inactive")
            if not bool(matched_fee["reminder_enabled"]):
                reasons.append("reminders_disabled")
            if matched_fee["installment_status"] in ("paid", "cancelled"):
                reasons.append("installment_not_payable")
            balance = Decimal(str(matched_fee["balance"])).quantize(Decimal("0.01"))
            if balance <= 0:
                reasons.append("no_outstanding_balance")
            if pending is not None and pending != balance:
                reasons.append("spreadsheet_amount_does_not_match_verified_mysql_balance")
        duplicate_key = (str(student["student_id"]) if student else raw_id, str(due_date))
        if duplicate_key in seen:
            reasons.append("duplicate_student_and_due_date_in_file")
            counts["duplicate_rows"] += 1
        seen.add(duplicate_key)

        # A row can be technically valid but is never permission to place a call.
        invalid_codes = {"missing_student_id", "student_not_found_in_mysql", "invalid_fee_pending_amount", "invalid_due_date", "invalid_mobile_number", "no_installment_matches_student_and_due_date", "multiple_installments_match_student_and_due_date", "spreadsheet_mobile_mismatch", "spreadsheet_amount_does_not_match_verified_mysql_balance", "duplicate_student_and_due_date_in_file"}
        invalid = any(r in invalid_codes for r in reasons)
        blocked = any(r in {"student_inactive", "no_call_consent", "fee_account_inactive", "reminders_disabled", "installment_not_payable", "no_outstanding_balance"} for r in reasons)
        if invalid:
            status = "invalid"
            counts["invalid"] += 1
        elif blocked:
            status = "blocked"
            counts["blocked"] += 1
        else:
            status = "ready_for_manual_review"
            counts["ready_for_manual_review"] += 1
        preview.append({
            "source_row": idx,
            "student_id_from_file": raw_id,
            "student_name_from_file": str(row.get("student name") or "").strip(),
            "matched_student_id": student["student_id"] if student else None,
            "matched_student_name": student["full_name"] if student else None,
            "parent_name_from_file": str(row.get("parent_name") or "").strip(),
            "mobile_number_masked": ("******" + digits[-4:]) if mobile_valid else None,
            "due_date": due_date.isoformat() if due_date else None,
            "spreadsheet_fee_pending": str(pending) if pending is not None else None,
            "mysql_installment_id": matched_fee["installment_id"] if matched_fee else None,
            "mysql_verified_balance": str(Decimal(str(matched_fee["balance"])).quantize(Decimal("0.01"))) if matched_fee else None,
            "penalty_ignored": True,
            "status": status,
            "reasons": reasons or ["checks_passed_manual_approval_still_required"],
        })

    return {
        "mode": "dry_run_read_only",
        "filename": filename,
        "rows_checked": len(rows),
        "summary": counts,
        "rows": preview,
        "safety": {
            "database_changes_made": False,
            "phone_calls_placed": False,
            "penalty_column_used": False,
            "call_consent_required": True,
            "manual_approval_required_before_any_future_call": True,
        },
        "note": "This endpoint only validates rows against MySQL. It does not import data, update records, schedule calls, or place calls.",
    }
