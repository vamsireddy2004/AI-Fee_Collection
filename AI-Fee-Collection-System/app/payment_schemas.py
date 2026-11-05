from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


PositiveAmount = Annotated[
    Decimal,
    Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
        description="Payment amount. Must be greater than zero.",
        examples=["5000.00"],
    ),
]

TransactionReference = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=150,
    ),
]


class PaymentCreate(BaseModel):
    """
    Request schema for recording a payment attempt.

    A newly recorded payment is pending until verified.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "installment_id": 1,
                    "amount": "5000.00",
                    "payment_method": "test",
                    "transaction_reference": "DEMO-TXN-002",
                }
            ]
        }
    )

    installment_id: int = Field(
        gt=0,
        description="ID of the installment receiving the payment.",
        examples=[1],
    )

    amount: PositiveAmount

    payment_method: str | None = Field(
        default=None,
        max_length=50,
        description="Payment method, such as UPI, bank transfer, or test.",
        examples=["test"],
    )

    transaction_reference: TransactionReference | None = Field(
        default=None,
        description="Transaction reference supplied for the payment.",
        examples=["DEMO-TXN-002"],
    )


class PaymentVerification(BaseModel):
    """
    Request schema for the development payment-verification workflow.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "verified": True,
                    "transaction_reference": "DEMO-TXN-002",
                },
                {
                    "verified": False,
                    "transaction_reference": "DEMO-TXN-002",
                },
            ]
        }
    )

    verified: bool = Field(
        description=(
            "Whether the payment should be marked verified "
            "in the current development workflow."
        ),
        examples=[True],
    )

    transaction_reference: TransactionReference | None = Field(
        default=None,
        description="Reference to match against the stored payment.",
        examples=["DEMO-TXN-002"],
    )
