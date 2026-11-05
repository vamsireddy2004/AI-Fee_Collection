USE fee_collection_db;

-- Sample students (fictional data only)
INSERT INTO students (
    roll_number,
    full_name,
    class_name,
    section,
    division,
    course,
    academic_year,
    parent_name,
    parent_mobile,
    preferred_language,
    call_consent
)
VALUES
(
    'DEMO001',
    'Arjun Kumar',
    'Intermediate 1st Year',
    'A',
    'Science',
    'MPC',
    '2026-2027',
    'Ravi Kumar',
    '9000000001',
    'English',
    FALSE
),
(
    'DEMO002',
    'Priya Sharma',
    'Intermediate 2nd Year',
    'B',
    'Science',
    'BiPC',
    '2026-2027',
    'Suresh Sharma',
    '9000000002',
    'English',
    FALSE
);

-- Sample fee accounts
INSERT INTO fee_accounts (
    student_id,
    academic_year,
    total_fee,
    currency
)
SELECT student_id, academic_year, 60000.00, 'INR'
FROM students
WHERE roll_number = 'DEMO001';

INSERT INTO fee_accounts (
    student_id,
    academic_year,
    total_fee,
    currency
)
SELECT student_id, academic_year, 50000.00, 'INR'
FROM students
WHERE roll_number = 'DEMO002';

-- Sample installments for student DEMO001
INSERT INTO installments (
    fee_account_id,
    installment_number,
    installment_amount,
    due_date
)
SELECT fee_account_id, 1, 20000.00, '2026-11-15'
FROM fee_accounts
WHERE student_id = (
    SELECT student_id
    FROM students
    WHERE roll_number = 'DEMO001'
)
AND academic_year = '2026-2027';

-- Sample installments for student DEMO002
INSERT INTO installments (
    fee_account_id,
    installment_number,
    installment_amount,
    due_date
)
SELECT fee_account_id, 1, 15000.00, '2026-11-20'
FROM fee_accounts
WHERE student_id = (
    SELECT student_id
    FROM students
    WHERE roll_number = 'DEMO002'
)
AND academic_year = '2026-2027';