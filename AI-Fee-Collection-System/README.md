# AI Fee Collection & Parent Calling System

A staged project for managing student fee installments, reminding parents about
upcoming dues, recording payment commitments, and suppressing follow-ups when
payments are confirmed. The first development stages use synthetic data and
mock AI, calling, and payment services. This repository does not make real calls
or initiate payments.

## Project status

This is the initial scaffold and a **draft** MySQL schema for review. It does not
yet contain a backend, database connection, scheduler, AI agent, or integrations.
The schema must not be applied to a production database.

## Structure

- `app/`: future FastAPI application, organized by API, domain models, schemas,
  services, database access, scheduling, AI, calling, and payment integration.
- `database/schema.sql`: initial MySQL 8.0 DDL draft.
- `tests/`: future unit and integration tests.
- `.env.example`: names and safe local-development defaults for configuration;
  copy it to `.env` and replace placeholders locally.

Empty package directories are retained with `.gitkeep` files until their first
implementation. No application code is included in this phase.

## Development phases

1. Review and agree on the schema assumptions listed below.
2. Implement configuration, SQLAlchemy models, MySQL connectivity, and
   non-sensitive synthetic seed data.
3. Build student, fee-account, installment, payment, and call-history APIs.
4. Add date/intent extraction with tests and a mock AI service.
5. Add a scheduler with payment-status checks, idempotent call scheduling, and
   mock calling; test duplicate-call prevention and follow-up scheduling.
6. Add payment verification and institution-approved payment links in mock mode.
7. Evaluate and explicitly configure approved production providers, privacy,
   security, consent, and operational policies before any real calls/payments.

## Database design draft

`students` stores a student's institutional and academic identifiers.
`parent_contacts` allows multiple contacts per student. `fee_accounts` groups
fees by student and academic year; `installments` records each amount and local
due date. `payment_transactions` records payment and refund entries, while
`call_records`, `conversation_messages`, and `payment_commitments` retain the
reminder and commitment history.

Amounts use `DECIMAL`, identifiers use unsigned integer keys, and the schema
defines foreign keys, indexes, creation/update timestamps, and basic amount
checks. Historical rows use restrictive foreign keys rather than cascading
deletes. DDL uses `CREATE TABLE IF NOT EXISTS` only; it contains no `DROP`,
`TRUNCATE`, or database connection commands.

The paid amount and outstanding balance are intentionally derived from
**confirmed** payment and refund transactions rather than duplicated as
mutable totals. Payment status should be calculated against the installment
amount and institution-local date; application queries can expose statuses such
as unpaid, partially paid, paid, and overdue. A transaction reference may be
null for cash or other offline payments.

## Decisions to confirm before finalizing `schema.sql`

1. **Institution scope:** The draft models students for one institution and
   assumes a non-blank, whitespace-trimmed `roll_number` is unique
   institution-wide. The schema's default collation makes this uniqueness
   case-insensitive. No institution-specific roll-number pattern is enforced
   until that format is known. For multiple institutions, add an institution
   key and scope uniqueness to it.
2. **Academic identifiers:** Class, section, division, course, and branch are
   stored as text for the initial draft. Confirm whether these need normalized
   institution-managed lookup tables and whether any fields can be absent.
3. **Parent/contact ownership:** Contacts belong to one student in this draft.
   Phone numbers are checked for E.164 format and cannot be duplicated on
   multiple contact rows for the same student, but the same phone may be used
   for siblings. Confirm whether contacts should be shared across siblings and
   whether multiple numbers per parent are needed.
4. **Currency and accounting:** Each fee account has one ISO currency, and
   confirmed refunds reduce its net paid amount. Confirm currency, rounding,
   installment adjustments/waivers, and whether overpayments or payment
   allocations across installments are allowed.
5. **Timezones:** SQL `DATETIME` timestamps are intended to be stored in UTC;
   installment due dates and promised payment dates are institution-local
   `DATE` values. Set the actual institution timezone before implementing
   scheduling.
6. **Calling consent and retention:** The draft does not yet store consent,
   opt-out, recording, or transcript-retention evidence. Confirm the applicable
   institution policy and legal requirements before enabling calling or
   retaining conversation data.
7. **Scheduling and payment edge cases:** The draft includes a deduplication
   key for call jobs and records verification-needed commitments. Confirm the
   retry, call-window, grace-period, and follow-up rules.

## Local setup (scaffold only)

1. Install MySQL 8.0 locally and create a development database/user through
   MySQL Workbench using institution-approved local credentials.
2. Copy `.env.example` to `.env` and change the placeholders. Do not commit
   `.env` or use real student/parent information.
3. Review `database/schema.sql` and resolve the assumptions above before
   choosing to execute it. It has not been run as part of this scaffold.

Backend dependencies and run commands will be added in a later phase.
