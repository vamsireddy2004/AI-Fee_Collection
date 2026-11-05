-- Example read-only queries for local development and validation.
-- These are for review and future implementation, not for production execution.

-- 1. Find a student by roll number.
SELECT *
FROM students
WHERE roll_number = :roll_number;

-- 2. List overdue installments and their outstanding balances.
SELECT i.installment_id,
       s.roll_number,
       s.full_name,
       i.amount_due,
       i.due_date,
       COALESCE(SUM(CASE WHEN pt.status = 'confirmed' THEN pt.amount ELSE 0 END), 0) AS paid_amount,
       (i.amount_due - COALESCE(SUM(CASE WHEN pt.status = 'confirmed' THEN pt.amount ELSE 0 END), 0)) AS outstanding
FROM installments i
JOIN fee_accounts fa ON fa.fee_account_id = i.fee_account_id
JOIN students s ON s.student_id = fa.student_id
LEFT JOIN payment_transactions pt ON pt.installment_id = i.installment_id
GROUP BY i.installment_id, s.roll_number, s.full_name, i.amount_due, i.due_date
HAVING outstanding > 0;

-- 3. Find scheduled call attempts before a due date.
SELECT *
FROM call_records
WHERE scheduled_at <= NOW()
  AND status IN ('scheduled', 'queued');

-- 4. Find commitments that are due and still pending.
SELECT *
FROM payment_commitments
WHERE promised_payment_date <= CURDATE()
  AND status = 'pending';

-- 5. Check for duplicate parent numbers on the same student.
SELECT student_id, phone_e164, COUNT(*) AS duplicate_count
FROM parent_contacts
GROUP BY student_id, phone_e164
HAVING COUNT(*) > 1;
