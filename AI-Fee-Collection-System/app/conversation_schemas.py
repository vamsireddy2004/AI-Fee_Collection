from pydantic import BaseModel, ConfigDict, Field


class ConversationMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speaker: str = Field(
        description="Who sent the message: ai_agent, parent, or system.",
        examples=["parent"],
    )

    message_text: str = Field(
        min_length=1,
        description="Conversation message, in English, Telugu, or another supported language.",
        examples=["నేను సోమవారం ఫీజు కడతాను."],
    )

    detected_intent: str | None = Field(
        default=None,
        max_length=100,
        description="Optional intent label, such as fee_reminder or payment_promise.",
        examples=["payment_promise"],
    )
