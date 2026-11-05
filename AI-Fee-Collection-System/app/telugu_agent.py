
import json
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/ai",
    tags=["Telugu AI Agent"],
)

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL_NAME = "llama3.2:latest"

SYSTEM_PROMPT = """
నీవు కళాశాల ఫీజుల గురించి తల్లిదండ్రులతో మాట్లాడే తెలుగు సహాయకుడివి.
తెలుగు లిపిలో మాత్రమే సమాధానం ఇవ్వాలి.
మర్యాదగా, సహజంగా, చిన్న వాక్యాల్లో మాట్లాడాలి.
ఫీజు మొత్తాన్ని లేదా చెల్లింపు స్థితిని ఊహించకూడదు.
ఇప్పటికే చెల్లించామని చెబితే మళ్లీ చెల్లించమని ఒత్తిడి చేయకూడదు.
నిజమైన ఫీజు వివరాలు అందుబాటులో లేకపోతే కళాశాల కార్యాలయాన్ని
సంప్రదించమని చెప్పాలి.
రెండు లేదా మూడు చిన్న వాక్యాల్లో సమాధానం ఇవ్వాలి.
"""


class TeluguChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class TeluguChatResponse(BaseModel):
    reply: str
    model: str


@router.post("/telugu-chat", response_model=TeluguChatResponse)
def telugu_chat(payload: TeluguChatRequest):
    body = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": payload.message},
        ],
        "stream": False,
        "options": {"temperature": 0.3},
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))

        reply = result.get("message", {}).get("content", "").strip()

        if not reply:
            raise HTTPException(
                status_code=502,
                detail="The local AI returned an empty response.",
            )

        return TeluguChatResponse(reply=reply, model=MODEL_NAME)

    except urllib.error.URLError as exc:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to Ollama. Make sure it is running.",
        ) from exc
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Invalid response from the local AI.",
        ) from exc
