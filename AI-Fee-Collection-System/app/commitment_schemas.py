

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class PaymentCommitmentCreate(BaseModel):
    """
    Request body for recording a parent's payment promise.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "installment_id": 1,
                    "call_id": 1,
                    "promised_payment_date": "2026-10-19",
                    "notes": "Parent promised to pay next Monday.",
                }
            ]
        },
    )

    installment_id: int = Field(
        gt=0,
        description="ID of the installment the parent promises to pay.",
        examples=[1],
    )

    call_id: int = Field(
        gt=0,
        description="ID of the call during which the promise was recorded.",
        examples=[1],
    )

    promised_payment_date: date = Field(
        description="Date on which the parent expects to make payment.",
        examples=["2026-10-19"],
    )

    notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional notes about the parent's payment promise.",
        examples=["Parent promised to pay next Monday."],
    )
