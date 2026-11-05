import os
import secrets

from dotenv import load_dotenv
from fastapi import Header

from datetime import datetime, timezone

from decimal import Decimal
from app.telugu_agent import router as telugu_agent_router
from app.conversation_schemas import ConversationMessageCreate

from fastapi import Depends, FastAPI, HTTPException

from sqlalchemy import text

from sqlalchemy.orm import Session



from app.database import get_db, check_database_connection

from app.payment_service import (

    get_installment_balance,

    refresh_installment_status,

)

from app.payment_schemas import PaymentCreate, PaymentVerification

from app.commitment_schemas import PaymentCommitmentCreate


load_dotenv()
def verify_voice_agent_key(
    x_api_key: str | None = Header(default=None),
):
    expected_key = os.getenv("VOICE_AGENT_API_KEY")

    if not expected_key or not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )

    if not secrets.compare_digest(x_api_key, expected_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )


app = FastAPI(

    title="AI Fee Collection System API",

    description="""

## Overview



Backend API for college fee management and AI-powered fee reminders.



### Main features

- Student and fee installment management

- Payment recording and verification

- Outstanding balance calculation

- Payment commitments and follow-ups

- AI voice-call scheduling and conversation history



### Testing guidelines

- Use the example values provided by each endpoint.

- GET endpoints are intended for reading data.

- POST endpoints may create or modify database records.

- The reminder scheduler creates database records only;

  it does not place real phone calls.



### Environment

Development API connected to MySQL.

""",

    version="1.0.0",

    contact={

        "name": "AI Fee Collection System",

    },

    openapi_tags=[

        {

            "name": "System & Health",

            "description": "Check API availability and database connectivity.",

        },

        {

            "name": "Students",

            "description": "Retrieve and manage student information.",

        },

        {

            "name": "Fee Accounts & Installments",

            "description": "View fee accounts, installments, and outstanding balances.",

        },

        {

            "name": "Payments",

            "description": "Record payments and handle verification workflows.",

        },

        {

            "name": "Payment Commitments",

            "description": "Track promised payment dates and overdue commitments.",

        },

        {

            "name": "Call Scheduling",

            "description": "Preview and schedule fee reminders without placing real calls.",

        },

        {

            "name": "Call History & Conversations",

            "description": "Inspect call records and stored conversation messages.",

        },

    ],

)
app.include_router(telugu_agent_router)



from app.fee_import_preview import router as fee_import_preview_router
app.include_router(fee_import_preview_router)



@app.get("/")

def home():

    return {

        "message": "AI Fee Collection System API is running",

        "status": "success",

    }





@app.get("/health")

def health_check():

    try:

        version = check_database_connection()

        return {

            "status": "healthy",

            "database": "connected",

            "mysql_version": version,

        }

    except Exception as exc:

        raise HTTPException(

            status_code=503,

            detail="Database connection failed",

        ) from exc





@app.get("/students")

def get_students(db: Session = Depends(get_db)):

    query = text("""

        SELECT

            student_id,

            roll_number,

            full_name,

            class_name,

            section,

            division,

            course,

            academic_year,

            parent_name,

            preferred_language,

            is_active

        FROM students

        WHERE is_active = TRUE

        ORDER BY roll_number

    """)



    rows = db.execute(query).mappings().all()

    return {"count": len(rows), "students": [dict(row) for row in rows]}





@app.get("/fees")

def get_fee_installments(db: Session = Depends(get_db)):

    query = text("""

        SELECT

            s.roll_number,

            s.full_name,

            f.total_fee,

            COALESCE(

                SUM(

                    CASE

                        WHEN p.payment_status = 'verified'

                        THEN p.amount

                        ELSE 0

                    END

                ),

                0

            ) AS verified_paid_amount,

            i.installment_id,

            i.installment_number,

            i.installment_amount,

            i.due_date,

            i.status AS installment_status

        FROM students AS s

        JOIN fee_accounts AS f

            ON f.student_id = s.student_id

        JOIN installments AS i

            ON i.fee_account_id = f.fee_account_id

        LEFT JOIN payments AS p

            ON p.installment_id = i.installment_id

        GROUP BY

            s.student_id,

            s.roll_number,

            s.full_name,

            f.fee_account_id,

            f.total_fee,

            i.installment_id,

            i.installment_number,

            i.installment_amount,

            i.due_date,

            i.status

        ORDER BY i.due_date, s.roll_number

    """)



    rows = db.execute(query).mappings().all()

    return {"count": len(rows), "installments": [dict(row) for row in rows]}





@app.post(

    "/payments",

    status_code=201,

    tags=["Payments"],

    summary="Record a payment attempt",

    description="""

Creates a payment record with an initial status of `pending`.



**Important:**

- Recording a payment does not prove that money was received.

- Only verified payments count toward the installment balance.

- The amount cannot exceed the current outstanding balance.



**Example:** Record a test payment of ₹5,000 against installment ID 1.

""",

    response_description="The newly created pending payment record.",

)

def create_payment(

    payload: PaymentCreate,

    db: Session = Depends(get_db),

):

    try:

        installment = db.execute(

            text("""

                SELECT installment_id, status

                FROM installments

                WHERE installment_id = :id

                FOR UPDATE

            """),

            {"id": payload.installment_id},

        ).mappings().first()



        if not installment:

            raise HTTPException(

                status_code=404,

                detail="Installment not found",

            )



        if installment["status"] == "cancelled":

            raise HTTPException(

                status_code=409,

                detail="Cannot record payment for a cancelled installment",

            )



        balance = get_installment_balance(db, payload.installment_id)



        if payload.amount > Decimal(str(balance["balance"])):

            raise HTTPException(

                status_code=409,

                detail="Payment amount exceeds the remaining installment balance",

            )



        result = db.execute(

            text("""

                INSERT INTO payments (

                    installment_id,

                    amount,

                    payment_method,

                    transaction_reference,

                    payment_status

                )

                VALUES (

                    :installment_id,

                    :amount,

                    :payment_method,

                    :transaction_reference,

                    'pending'

                )

            """),

            {

                "installment_id": payload.installment_id,

                "amount": payload.amount,

                "payment_method": payload.payment_method,

                "transaction_reference": payload.transaction_reference,

            },

        )



        payment_id = result.lastrowid

        db.commit()



        return {

            "payment_id": payment_id,

            "payment_status": "pending",

            "message": "Payment recorded and awaiting verification",

        }



    except HTTPException:

        db.rollback()

        raise

    except Exception as exc:

        db.rollback()

        raise HTTPException(

            status_code=500,

            detail="Unable to record payment",

        ) from exc







@app.post(

    "/payments/{payment_id}/verify",

    tags=["Payments"],

    summary="Verify a payment (development workflow)",

    description="""

Updates a payment's verification status in the current development workflow.



**Path parameter**

- `payment_id`: ID of the payment record. Example: `1`.



**Request body**

- `verified`: `true` or `false`.

- `transaction_reference`: Reference used to match the payment, when required.



**Important security limitation**

This endpoint is for development and demonstration only. It does not independently

confirm receipt of funds through a real payment gateway.



For production, verification must be performed using authenticated gateway

webhooks or trusted server-side gateway verification.

""",

    response_description="The result of the payment verification operation.",

)

def verify_payment(

    payment_id: int,

    payload: PaymentVerification,

    db: Session = Depends(get_db),

):

    try:

        payment = db.execute(

            text("""

                SELECT

                    payment_id,

                    installment_id,

                    amount,

                    payment_status,

                    transaction_reference

                FROM payments

                WHERE payment_id = :payment_id

                FOR UPDATE

            """),

            {"payment_id": payment_id},

        ).mappings().first()



        if not payment:

            raise HTTPException(

                status_code=404,

                detail="Payment not found",

            )



        if payment["payment_status"] != "pending":

            raise HTTPException(

                status_code=409,

                detail="Only pending payments can be verified",

            )



        if not payload.verified:

            db.execute(

                text("""

                    UPDATE payments

                    SET payment_status = 'failed'

                    WHERE payment_id = :payment_id

                """),

                {"payment_id": payment_id},

            )

            db.commit()



            return {

                "payment_id": payment_id,

                "payment_status": "failed",

            }



        if (

            payload.transaction_reference

            and payment["transaction_reference"]

            and payload.transaction_reference

            != payment["transaction_reference"]

        ):

            raise HTTPException(

                status_code=409,

                detail="Transaction reference does not match",

            )



        if (

            payload.transaction_reference

            and not payment["transaction_reference"]

        ):

            db.execute(

                text("""

                    UPDATE payments

                    SET transaction_reference = :reference

                    WHERE payment_id = :payment_id

                """),

                {

                    "reference": payload.transaction_reference,

                    "payment_id": payment_id,

                },

            )



        # DEMO ONLY: this endpoint is not a secure payment-verification

        # mechanism. Production verification must use an authenticated

        # operator or a trusted, validated payment-gateway notification.

        now = datetime.now(timezone.utc).replace(tzinfo=None)



        db.execute(

            text("""

                UPDATE payments

                SET payment_status = 'verified',

                    verified_at = :verified_at,

                    payment_date = :payment_date

                WHERE payment_id = :payment_id

            """),

            {

                "verified_at": now,

                "payment_date": now,

                "payment_id": payment_id,

            },

        )



        status = refresh_installment_status(

            db,

            payment["installment_id"],

        )

        db.commit()



        return {

            "payment_id": payment_id,

            "payment_status": "verified",

            "installment_status": status,

        }



    except HTTPException:

        db.rollback()

        raise

    except Exception as exc:

        db.rollback()

        raise HTTPException(

            status_code=500,

            detail="Unable to verify payment",

        ) from exc





@app.get(

    "/installments/{installment_id}/balance",

    tags=["Fee Accounts & Installments"],

    summary="Get installment balance",

    description="""

Returns the installment amount, total verified payments, remaining balance,

and current installment status.



**Path parameter**

- `installment_id`: The unique ID of the installment. Example: `1`.



**Example with current demo data**

- Installment amount: ₹20,000

- Verified payments: ₹5,000

- Remaining balance: ₹15,000



**Possible responses**

- `200`: Balance retrieved successfully.

- `404`: Installment ID does not exist.



This endpoint reads balance information; it does not create a payment.

""",

    response_description="Installment amount and outstanding balance.",

)

def installment_balance(
    installment_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(verify_voice_agent_key),
):

    try:

        return get_installment_balance(db, installment_id)

    except HTTPException:

        raise

    except Exception as exc:

        raise HTTPException(

            status_code=500,

            detail="Unable to retrieve installment balance",

        ) from exc





@app.post(

    "/commitments",

    status_code=201,

    tags=["Payment Commitments"],

    summary="Record a payment commitment",

    description="""

Records a parent's promise to pay an installment by a specified date.



**Request body example**

- `installment_id`: `1` — installment being discussed.

- `call_id`: `1` — existing call associated with the promise.

- `promised_payment_date`: `2026-10-19` — promised payment date.

- `notes`: Optional explanation of the promise.



**Important:** A promise is not a payment. The commitment remains pending until

the application updates its status.



**Responses**

- `201`: Commitment created.

- `404`: Referenced installment or call not found, if handled by the endpoint.

- `422`: Invalid request data.

""",

    response_description="The result of recording the commitment.",

)

def create_payment_commitment(

    payload: PaymentCommitmentCreate,

    db: Session = Depends(get_db),

):

    try:

        # 1. Confirm that the installment exists.

        installment = db.execute(

            text("""

                SELECT installment_id

                FROM installments

                WHERE installment_id = :installment_id

            """),

            {"installment_id": payload.installment_id},

        ).mappings().first()



        if not installment:

            raise HTTPException(

                status_code=404,

                detail="Installment not found",

            )



        # 2. Confirm that the call exists and belongs to this installment.

        call = db.execute(

            text("""

                SELECT call_id

                FROM call_records

                WHERE call_id = :call_id

                  AND installment_id = :installment_id

            """),

            {

                "call_id": payload.call_id,

                "installment_id": payload.installment_id,

            },

        ).mappings().first()



        if not call:

            raise HTTPException(

                status_code=404,

                detail="Call not found for this installment",

            )



        # 3. Insert the commitment. MySQL supplies the default

        # status ('pending') and recorded_at timestamp.

        result = db.execute(

            text("""

                INSERT INTO payment_commitments (

                    installment_id,

                    call_id,

                    promised_payment_date,

                    notes

                )

                VALUES (

                    :installment_id,

                    :call_id,

                    :promised_payment_date,

                    :notes

                )

            """),

            {

                "installment_id": payload.installment_id,

                "call_id": payload.call_id,

                "promised_payment_date": payload.promised_payment_date,

                "notes": payload.notes,

            },

        )



        commitment_id = result.lastrowid

        db.commit()



        return {

            "commitment_id": commitment_id,

            "installment_id": payload.installment_id,

            "call_id": payload.call_id,

            "promised_payment_date": (

                payload.promised_payment_date.isoformat()

            ),

            "status": "pending",

            "message": "Payment commitment recorded successfully",

        }



    except HTTPException:

        db.rollback()

        raise

    except Exception as exc:

        db.rollback()

        raise HTTPException(

            status_code=500,

            detail="Unable to record payment commitment",

        ) from exc





@app.get(

    "/commitments",

    tags=["Payment Commitments"],

    summary="List payment commitments",

    description="""

Returns recorded payment commitments.



**Optional query parameter**

- `status`: Filter by commitment status.



Supported statuses:

- `pending`

- `fulfilled`

- `missed`

- `cancelled`



**Example:** Use `status=pending` to list promises that are still pending.



This endpoint reads data and does not create or modify commitments.

""",

    response_description="A count and list of matching commitments.",

)

def get_payment_commitments(

    status: str | None = None,

    db: Session = Depends(get_db),

):

    allowed_statuses = {

        "pending",

        "fulfilled",

        "missed",

        "cancelled",

    }



    if status is not None and status not in allowed_statuses:

        raise HTTPException(

            status_code=400,

            detail="Invalid status. Use pending, fulfilled, missed, or cancelled.",

        )



    query = """

        SELECT

            commitment_id,

            installment_id,

            call_id,

            promised_payment_date,

            status,

            recorded_at,

            fulfilled_at,

            notes

        FROM payment_commitments

    """



    params = {}



    if status is not None:

        query += " WHERE status = :status"

        params["status"] = status



    query += " ORDER BY promised_payment_date, commitment_id"



    rows = db.execute(

        text(query),

        params,

    ).mappings().all()



    return {

        "count": len(rows),

        "commitments": [dict(row) for row in rows],

    }





@app.get(

    "/commitments/overdue",

    tags=["Payment Commitments"],

    summary="List overdue payment commitments",

    description="""

Returns payment commitments whose promised date has passed and whose status

indicates they are still outstanding.



**Example:** A promise dated yesterday may appear if it remains pending.



**Important:** An overdue promise does not automatically mean the student

has not paid. Payment records must be checked before scheduling a follow-up call.



This endpoint reads data and does not place calls.

""",

    response_description="A count and list of overdue commitments.",

)

def get_overdue_commitments(

    db: Session = Depends(get_db),

):

    query = text("""

        SELECT

            pc.commitment_id,

            pc.installment_id,

            pc.call_id,

            pc.promised_payment_date,

            pc.status AS commitment_status,

            pc.notes,

            i.installment_amount,

            i.status AS installment_status,

            COALESCE(

                SUM(

                    CASE

                        WHEN p.payment_status = 'verified'

                        THEN p.amount

                        ELSE 0

                    END

                ),

                0

            ) AS verified_paid_amount,

            GREATEST(

                i.installment_amount - COALESCE(

                    SUM(

                        CASE

                            WHEN p.payment_status = 'verified'

                            THEN p.amount

                            ELSE 0

                        END

                    ),

                    0

                ),

                0

            ) AS remaining_balance

        FROM payment_commitments AS pc

        JOIN installments AS i

            ON i.installment_id = pc.installment_id

        LEFT JOIN payments AS p

            ON p.installment_id = i.installment_id

        WHERE pc.status = 'pending'

          AND pc.promised_payment_date < CURRENT_DATE

          AND i.status NOT IN ('paid', 'cancelled')

        GROUP BY

            pc.commitment_id,

            pc.installment_id,

            pc.call_id,

            pc.promised_payment_date,

            pc.status,

            pc.notes,

            i.installment_amount,

            i.status

        HAVING remaining_balance > 0

        ORDER BY pc.promised_payment_date;

    """)



    rows = db.execute(query).mappings().all()



    return {

        "count": len(rows),

        "overdue_commitments": [dict(row) for row in rows],

    }





@app.post(

    "/calls/{call_id}/messages",

    tags=["Call History & Conversations"],

    summary="Save a conversation message",

    description="""

Stores a message associated with a call.



**Path parameter**

- call_id: Existing call record ID, for example 1.



**Request body fields**

- call_id: Call record associated with the message.

- speaker: ai_agent, parent, or system.

- message_text: Message content.

- detected_intent: Optional intent label, such as fee_reminder or payment_promise.



**Important:** This endpoint stores conversation data. Confirm that the call

exists and that the path and body IDs match according to your validation rules.

""",

    response_description="Result of saving the conversation message.",

)



def create_conversation_message(

    call_id: int,

    payload: ConversationMessageCreate,

    db: Session = Depends(get_db),

):

    try:

        # Check that the call exists.

        call = db.execute(

            text("""

                SELECT call_id

                FROM call_records

                WHERE call_id = :call_id

            """),

            {"call_id": call_id},

        ).mappings().first()



        if not call:

            raise HTTPException(

                status_code=404,

                detail="Call not found",

            )



        # Ensure URL and request body use the same call ID.

        



        result = db.execute(

            text("""

                INSERT INTO conversation_messages (

                    call_id,

                    speaker,

                    message_text,

                    detected_intent

                )

                VALUES (

                    :call_id,

                    :speaker,

                    :message_text,

                    :detected_intent

                )

            """),

            {

                "call_id": call_id,

                "speaker": payload.speaker,

                "message_text": payload.message_text,

                "detected_intent": payload.detected_intent,

            },

        )



        message_id = result.lastrowid

        db.commit()



        return {

            "message_id": message_id,

            "call_id": call_id,

            "speaker": payload.speaker,

            "message_text": payload.message_text,

            "detected_intent": payload.detected_intent,

            "message": "Conversation message saved successfully",

        }



    except HTTPException:

        db.rollback()

        raise

    except Exception as exc:

        db.rollback()

        raise HTTPException(

            status_code=500,

            detail="Unable to save conversation message",

        ) from exc





@app.get(

    "/calls/{call_id}/messages",

    tags=["Call History & Conversations"],

    summary="Get conversation history",

    description="""

Returns stored messages for a specified call, including the speaker,

message text, detected intent when available, and creation timestamp.



**Path parameter**

- call_id: Call record ID, for example 1.



This endpoint reads conversation history and does not create messages.

""",

    response_description="Messages stored for the specified call.",

)



def get_conversation_messages(

    call_id: int,

    db: Session = Depends(get_db),

):

    try:

        call = db.execute(

            text("""

                SELECT call_id

                FROM call_records

                WHERE call_id = :call_id

            """),

            {"call_id": call_id},

        ).mappings().first()



        if not call:

            raise HTTPException(

                status_code=404,

                detail="Call not found",

            )



        rows = db.execute(

            text("""

                SELECT

                    message_id,

                    call_id,

                    speaker,

                    message_text,

                    detected_intent,

                    created_at

                FROM conversation_messages

                WHERE call_id = :call_id

                ORDER BY created_at, message_id

            """),

            {"call_id": call_id},

        ).mappings().all()



        return {

            "call_id": call_id,

            "count": len(rows),

            "messages": [dict(row) for row in rows],

        }



    except HTTPException:

        raise

    except Exception as exc:

        raise HTTPException(

            status_code=500,

            detail="Unable to retrieve conversation messages",

        ) from exc



@app.get("/calls")

def get_call_history(

    call_status: str | None = None,

    db: Session = Depends(get_db),

):

    allowed_statuses = {

        "scheduled",

        "in_progress",

        "completed",

        "no_answer",

        "failed",

        "cancelled",

    }



    if call_status is not None and call_status not in allowed_statuses:

        raise HTTPException(

            status_code=400,

            detail=(

                "Invalid call_status. Use scheduled, in_progress, "

                "completed, no_answer, failed, or cancelled."

            ),

        )



    query = """

        SELECT

            cr.call_id,

            cr.installment_id,

            cr.scheduled_at,

            cr.started_at,

            cr.ended_at,

            cr.call_status,

            cr.call_outcome,

            cr.summary,

            i.installment_number,

            i.installment_amount,

            i.due_date,

            i.status AS installment_status,

            s.roll_number,

            s.full_name,

            f.total_fee,

            COALESCE(p.verified_paid_amount, 0) AS verified_paid_amount,

            GREATEST(

                i.installment_amount - COALESCE(p.verified_paid_amount, 0),

                0

            ) AS remaining_balance

        FROM call_records AS cr

        JOIN installments AS i

            ON i.installment_id = cr.installment_id

        JOIN fee_accounts AS f

            ON f.fee_account_id = i.fee_account_id

        JOIN students AS s

            ON s.student_id = f.student_id

        LEFT JOIN (

            SELECT

                installment_id,

                SUM(amount) AS verified_paid_amount

            FROM payments

            WHERE payment_status = 'verified'

            GROUP BY installment_id

        ) AS p

            ON p.installment_id = i.installment_id

    """



    params = {}



    if call_status is not None:

        query += " WHERE cr.call_status = :call_status"

        params["call_status"] = call_status



    query += " ORDER BY cr.scheduled_at DESC, cr.call_id DESC"



    rows = db.execute(

        text(query),

        params,

    ).mappings().all()



    return {

        "count": len(rows),

        "calls": [dict(row) for row in rows],

    }



@app.post(

    "/calls/schedule-reminders",

    tags=["Call Scheduling"],

    summary="Schedule fee reminders",

    description="""

Finds installments that qualify for fee reminders and creates scheduled call

records according to the application's eligibility rules.



**Important**

- This endpoint creates database records.

- It does not place real phone calls.

- Student call consent must be respected.

- Review GET /calls/reminder-preview before scheduling reminders.



**Use:** Execute only when you intend to create scheduled reminder records.

""",

    response_description="Scheduling counts and details of scheduled or skipped reminders.",

)

def schedule_fee_reminders(

    db: Session = Depends(get_db),

):

    """

    Schedule fee-reminder records for eligible installments.



    This endpoint creates database records only.

    It does not place real phone calls.

    """



    current_date = db.execute(

        text("SELECT CURRENT_DATE")

    ).scalar_one()



    lookahead_days = 7



    # Fetch installments and retain ineligible records so the

    # API can explain why each one was skipped.

    candidates = db.execute(

        text("""

            SELECT

                s.student_id,

                s.roll_number,

                s.full_name,

                s.is_active,

                s.call_consent,



                f.fee_account_id,

                f.account_status,



                i.installment_id,

                i.installment_number,

                i.installment_amount,

                i.due_date,

                i.status AS installment_status,

                i.reminder_enabled,



                COALESCE(p.verified_paid_amount, 0)

                    AS verified_paid_amount,



                GREATEST(

                    i.installment_amount

                    - COALESCE(p.verified_paid_amount, 0),

                    0

                ) AS remaining_balance



            FROM students AS s



            JOIN fee_accounts AS f

                ON f.student_id = s.student_id



            JOIN installments AS i

                ON i.fee_account_id = f.fee_account_id



            LEFT JOIN (

                SELECT

                    installment_id,

                    SUM(amount) AS verified_paid_amount

                FROM payments

                WHERE payment_status = 'verified'

                GROUP BY installment_id

            ) AS p

                ON p.installment_id = i.installment_id



            WHERE i.due_date BETWEEN :start_date

                AND DATE_ADD(

                    :start_date,

                    INTERVAL :lookahead_days DAY

                )



            ORDER BY i.due_date, i.installment_id

        """),

        {

            "start_date": current_date,

            "lookahead_days": lookahead_days,

        },

    ).mappings().all()



    scheduled_calls = []

    skipped_calls = []



    for candidate in candidates:

        installment_id = candidate["installment_id"]



        # Check eligibility and provide a specific reason.

        if not candidate["is_active"]:

            reason = "student_inactive"



        elif not candidate["call_consent"]:

            reason = "no_call_consent"



        elif candidate["account_status"] != "active":

            reason = "fee_account_inactive"



        elif not candidate["reminder_enabled"]:

            reason = "reminders_disabled"



        elif candidate["installment_status"] in (

            "paid",

            "cancelled",

        ):

            reason = "installment_not_payable"



        elif Decimal(

            str(candidate["remaining_balance"])

        ) <= Decimal("0.00"):

            reason = "no_outstanding_balance"



        else:

            reason = None



        if reason is not None:

            skipped_calls.append({

                "installment_id": installment_id,

                "student_name": candidate["full_name"],

                "reason": reason,

            })

            continue



        # Lock the installment row before checking for an active

        # call. This helps serialize scheduling for this installment

        # when transactions use the same locking strategy.

        db.execute(

            text("""

                SELECT installment_id

                FROM installments

                WHERE installment_id = :installment_id

                FOR UPDATE

            """),

            {"installment_id": installment_id},

        ).first()



        existing_call = db.execute(

            text("""

                SELECT call_id

                FROM call_records

                WHERE installment_id = :installment_id

                  AND call_status IN (

                      'scheduled',

                      'in_progress'

                  )

                LIMIT 1

            """),

            {"installment_id": installment_id},

        ).mappings().first()



        if existing_call:

            skipped_calls.append({

                "installment_id": installment_id,

                "student_name": candidate["full_name"],

                "reason": "active_call_already_exists",

                "existing_call_id": existing_call["call_id"],

            })

            continue



        scheduled_at = datetime.now(timezone.utc).replace(

            tzinfo=None,

            microsecond=0,

        )



        result = db.execute(

            text("""

                INSERT INTO call_records (

                    installment_id,

                    scheduled_at,

                    call_status,

                    summary

                )

                VALUES (

                    :installment_id,

                    :scheduled_at,

                    'scheduled',

                    :summary

                )

            """),

            {

                "installment_id": installment_id,

                "scheduled_at": scheduled_at,

                "summary": (

                    "Fee reminder scheduled. "

                    "No phone call has been placed."

                ),

            },

        )



        scheduled_calls.append({

            "call_id": result.lastrowid,

            "installment_id": installment_id,

            "student_name": candidate["full_name"],

            "roll_number": candidate["roll_number"],

            "installment_number": candidate["installment_number"],

            "due_date": str(candidate["due_date"]),

            "installment_amount": str(

                candidate["installment_amount"]

            ),

            "verified_paid_amount": str(

                candidate["verified_paid_amount"]

            ),

            "remaining_balance": str(

                candidate["remaining_balance"]

            ),

            "scheduled_at": scheduled_at.isoformat(),

            "call_status": "scheduled",

        })



    db.commit()



    return {

        "message": "Fee reminder scheduling completed",

        "current_date": str(current_date),

        "lookahead_days": lookahead_days,

        "scheduled_count": len(scheduled_calls),

        "skipped_count": len(skipped_calls),

        "scheduled_calls": scheduled_calls,

        "skipped_calls": skipped_calls,

        "note": (

            "Only database records were created. "

            "No real phone calls were placed."

        ),

    }



@app.get(

    "/calls/reminder-preview",

    tags=["Call Scheduling"],

    summary="Preview fee-reminder eligibility",

    description="""

Checks installment eligibility without creating or changing database records.



The response includes:

- Student and installment information

- Verified payments and remaining balance

- Eligibility status and the first applicable reason for exclusion



**Example:** Use this endpoint to check why a student is excluded before running

the reminder scheduler.



This is a read-only preview. It does not place calls.

""",

    response_description="Eligibility results for the installments checked.",

)

def preview_fee_reminders(

    db: Session = Depends(get_db),

):

    """

    Preview fee-reminder eligibility without changing the database.



    This endpoint does not create call records or place phone calls.

    """



    current_date = db.execute(

        text("SELECT CURRENT_DATE")

    ).scalar_one()



    lookahead_days = 7



    rows = db.execute(

        text("""

            SELECT

                s.student_id,

                s.roll_number,

                s.full_name,

                s.is_active,

                s.call_consent,



                f.account_status,



                i.installment_id,

                i.installment_number,

                i.installment_amount,

                i.due_date,

                i.status AS installment_status,

                i.reminder_enabled,



                COALESCE(p.verified_paid_amount, 0)

                    AS verified_paid_amount,



                GREATEST(

                    i.installment_amount

                    - COALESCE(p.verified_paid_amount, 0),

                    0

                ) AS remaining_balance,



                CASE

                    WHEN s.is_active = 0

                        THEN 'student_inactive'

                    WHEN s.call_consent = 0

                        THEN 'no_call_consent'

                    WHEN f.account_status != 'active'

                        THEN 'fee_account_inactive'

                    WHEN i.reminder_enabled = 0

                        THEN 'reminders_disabled'

                    WHEN i.status IN ('paid', 'cancelled')

                        THEN 'installment_not_payable'

                    WHEN GREATEST(

                        i.installment_amount

                        - COALESCE(p.verified_paid_amount, 0),

                        0

                    ) <= 0

                        THEN 'no_outstanding_balance'

                    WHEN EXISTS (

                        SELECT 1

                        FROM call_records AS cr

                        WHERE cr.installment_id = i.installment_id

                          AND cr.call_status IN (

                              'scheduled',

                              'in_progress'

                          )

                    )

                        THEN 'active_call_already_exists'

                    WHEN i.due_date < :start_date

                        THEN 'past_due_outside_current_window'

                    WHEN i.due_date >

                        DATE_ADD(

                            :start_date,

                            INTERVAL :lookahead_days DAY

                        )

                        THEN 'due_outside_current_window'

                    ELSE 'eligible'

                END AS eligibility_reason



            FROM students AS s



            JOIN fee_accounts AS f

                ON f.student_id = s.student_id



            JOIN installments AS i

                ON i.fee_account_id = f.fee_account_id



            LEFT JOIN (

                SELECT

                    installment_id,

                    SUM(amount) AS verified_paid_amount

                FROM payments

                WHERE payment_status = 'verified'

                GROUP BY installment_id

            ) AS p

                ON p.installment_id = i.installment_id



            ORDER BY i.due_date, i.installment_id

        """),

        {

            "start_date": current_date,

            "lookahead_days": lookahead_days,

        },

    ).mappings().all()



    preview = []



    for row in rows:

        item = dict(row)

        item["due_date"] = str(item["due_date"])

        item["installment_amount"] = str(

            item["installment_amount"]

        )

        item["verified_paid_amount"] = str(

            item["verified_paid_amount"]

        )

        item["remaining_balance"] = str(

            item["remaining_balance"]

        )

        item["eligible"] = (

            item["eligibility_reason"] == "eligible"

        )

        preview.append(item)



    return {

        "current_date": str(current_date),

        "lookahead_days": lookahead_days,

        "total_installments": len(preview),

        "eligible_count": sum(

            item["eligible"] for item in preview

        ),

        "ineligible_count": sum(

            not item["eligible"] for item in preview

        ),

        "installments": preview,

        "note": (

            "Read-only preview. No database records were changed "

            "and no phone calls were placed."

        ),

    }
