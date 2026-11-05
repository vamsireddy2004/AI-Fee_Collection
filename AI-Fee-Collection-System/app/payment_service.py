from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session


def get_installment_balance(db: Session, installment_id: int):
    """
    Calculate the installment balance using only verified payments.

    Money values are returned as strings to preserve decimal precision.
    """

    installment = db.execute(
        text("""
            SELECT
                installment_id,
                installment_amount,
                status
            FROM installments
            WHERE installment_id = :installment_id
            FOR UPDATE
        """),
        {"installment_id": installment_id},
    ).mappings().first()

    if not installment:
        raise HTTPException(
            status_code=404,
            detail="Installment not found",
        )

    paid_amount = db.execute(
        text("""
            SELECT COALESCE(SUM(amount), 0)
            FROM payments
            WHERE installment_id = :installment_id
              AND payment_status = 'verified'
        """),
        {"installment_id": installment_id},
    ).scalar_one()

    installment_amount = Decimal(
        str(installment["installment_amount"])
    )
    paid_amount = Decimal(str(paid_amount))

    balance = max(
        Decimal("0.00"),
        installment_amount - paid_amount,
    )

    return {
        "installment_id": installment_id,
        "installment_amount": str(installment_amount),
        "verified_paid_amount": str(paid_amount),
        "balance": str(balance),
        "status": installment["status"],
    }


def refresh_installment_status(
    db: Session,
    installment_id: int,
):
    """
    Update installment status based on verified payments.

    Cancelled installments are not modified.
    """

    result = get_installment_balance(db, installment_id)

    balance = Decimal(result["balance"])
    paid_amount = Decimal(result["verified_paid_amount"])

    if balance == Decimal("0.00"):
        new_status = "paid"
    elif paid_amount > Decimal("0.00"):
        new_status = "partially_paid"
    else:
        new_status = "pending"

    db.execute(
        text("""
            UPDATE installments
            SET status = :status
            WHERE installment_id = :installment_id
              AND status != 'cancelled'
        """),
        {
            "status": new_status,
            "installment_id": installment_id,
        },
    )

    return new_status
