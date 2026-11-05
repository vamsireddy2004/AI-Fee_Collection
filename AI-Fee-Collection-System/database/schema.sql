-- ============================================================
-- AI Fee Collection & Parent Calling System
-- Database: fee_collection_db
-- MySQL: 8.0+
-- ============================================================

CREATE DATABASE IF NOT EXISTS fee_collection_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE fee_collection_db;

-- ============================================================
-- 1. STUDENTS
-- Stores student and parent contact information.
-- ============================================================

CREATE TABLE IF NOT EXISTS students (
    student_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    roll_number VARCHAR(30) NOT NULL UNIQUE,
    full_name VARCHAR(150) NOT NULL,
    class_name VARCHAR(50) NOT NULL,
    section VARCHAR(20),
    division VARCHAR(30),
    course VARCHAR(100),
    academic_year VARCHAR(20) NOT NULL,
    parent_name VARCHAR(150),
    parent_mobile VARCHAR(20) NOT NULL,
    preferred_language VARCHAR(20) DEFAULT 'English',
    call_consent BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_students_parent_mobile (parent_mobile),
    INDEX idx_students_class (class_name, section),
    INDEX idx_students_active (is_active)
) ENGINE=InnoDB;

-- ============================================================
-- 2. FEE ACCOUNTS
-- One account per student per academic year.
-- ============================================================

CREATE TABLE IF NOT EXISTS fee_accounts (
    fee_account_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    student_id BIGINT UNSIGNED NOT NULL,
    academic_year VARCHAR(20) NOT NULL,
    total_fee DECIMAL(12,2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'INR',
    account_status ENUM(
        'active', 'completed', 'cancelled'
    ) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_fee_accounts_student
        FOREIGN KEY (student_id)
        REFERENCES students(student_id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_student_academic_year
        UNIQUE (student_id, academic_year),

    CONSTRAINT chk_total_fee
        CHECK (total_fee >= 0)
) ENGINE=InnoDB;

-- ============================================================
-- 3. INSTALLMENTS
-- Each account can have multiple installments.
-- ============================================================

CREATE TABLE IF NOT EXISTS installments (
    installment_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    fee_account_id BIGINT UNSIGNED NOT NULL,
    installment_number INT UNSIGNED NOT NULL,
    installment_amount DECIMAL(12,2) NOT NULL,
    due_date DATE NOT NULL,
    status ENUM(
        'pending',
        'partially_paid',
        'paid',
        'overdue',
        'cancelled'
    ) NOT NULL DEFAULT 'pending',
    reminder_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_installments_fee_account
        FOREIGN KEY (fee_account_id)
        REFERENCES fee_accounts(fee_account_id)
        ON DELETE RESTRICT,

    CONSTRAINT uq_account_installment
        UNIQUE (fee_account_id, installment_number),

    CONSTRAINT chk_installment_amount
        CHECK (installment_amount > 0),

    INDEX idx_installments_due_status (due_date, status)
) ENGINE=InnoDB;

-- ============================================================
-- 4. PAYMENTS
-- Records payment attempts and verified transactions.
-- Only verified payments count toward paid fees.
-- ============================================================

CREATE TABLE IF NOT EXISTS payments (
    payment_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    installment_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    payment_method VARCHAR(50),
    transaction_reference VARCHAR(150),
    payment_status ENUM(
        'pending', 'verified', 'failed', 'refunded'
    ) NOT NULL DEFAULT 'pending',
    payment_link TEXT,
    payment_date DATETIME NULL,
    verified_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_payments_installment
        FOREIGN KEY (installment_id)
        REFERENCES installments(installment_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_payment_amount
        CHECK (amount > 0),

    INDEX idx_payments_installment_status
        (installment_id, payment_status),

    INDEX idx_payments_transaction_reference
        (transaction_reference)
) ENGINE=InnoDB;

-- ============================================================
-- 5. CALL RECORDS
-- Tracks scheduled calls and their outcomes.
-- ============================================================

CREATE TABLE IF NOT EXISTS call_records (
    call_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    installment_id BIGINT UNSIGNED NOT NULL,
    scheduled_at DATETIME NOT NULL,
    started_at DATETIME NULL,
    ended_at DATETIME NULL,
    call_status ENUM(
        'scheduled',
        'in_progress',
        'completed',
        'no_answer',
        'failed',
        'cancelled'
    ) NOT NULL DEFAULT 'scheduled',
    call_outcome ENUM(
        'payment_promised',
        'already_paid',
        'payment_link_requested',
        'callback_requested',
        'dispute',
        'no_response',
        'other'
    ) NULL,
    provider_call_id VARCHAR(150),
    summary TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_calls_installment
        FOREIGN KEY (installment_id)
        REFERENCES installments(installment_id)
        ON DELETE RESTRICT,

    UNIQUE KEY uq_provider_call_id (provider_call_id),

    INDEX idx_calls_schedule_status (scheduled_at, call_status),
    INDEX idx_calls_installment (installment_id)
) ENGINE=InnoDB;

-- ============================================================
-- 6. CONVERSATION MESSAGES
-- Stores individual messages from parents and the AI agent.
-- ============================================================

CREATE TABLE IF NOT EXISTS conversation_messages (
    message_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    call_id BIGINT UNSIGNED NOT NULL,
    speaker ENUM(
        'ai_agent', 'parent', 'system'
    ) NOT NULL,
    message_text TEXT NOT NULL,
    detected_intent VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_messages_call
        FOREIGN KEY (call_id)
        REFERENCES call_records(call_id)
        ON DELETE RESTRICT,

    INDEX idx_messages_call_time (call_id, created_at)
) ENGINE=InnoDB;

-- ============================================================
-- 7. PAYMENT COMMITMENTS
-- Stores dates promised by parents.
-- ============================================================

CREATE TABLE IF NOT EXISTS payment_commitments (
    commitment_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    installment_id BIGINT UNSIGNED NOT NULL,
    call_id BIGINT UNSIGNED NOT NULL,
    promised_payment_date DATE NOT NULL,
    status ENUM(
        'pending',
        'fulfilled',
        'missed',
        'cancelled'
    ) NOT NULL DEFAULT 'pending',
    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fulfilled_at DATETIME NULL,
    notes TEXT,

    CONSTRAINT fk_commitments_installment
        FOREIGN KEY (installment_id)
        REFERENCES installments(installment_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_commitments_call
        FOREIGN KEY (call_id)
        REFERENCES call_records(call_id)
        ON DELETE RESTRICT,

    INDEX idx_commitments_date_status
        (promised_payment_date, status),

    INDEX idx_commitments_installment
        (installment_id, status)
) ENGINE=InnoDB;

-- ============================================================
-- END OF SCHEMA
-- ============================================================