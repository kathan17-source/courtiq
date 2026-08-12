from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.app.config import Settings


@dataclass(frozen=True)
class CoachingServiceError(Exception):
    code: str
    message: str
    status_code: int


def generate_coaching_help(question: str, context: str, settings: Settings) -> str:
    if not settings.gemini_api_key:
        raise CoachingServiceError("coaching_not_configured", "Coaching help is not configured yet.", 503)

    prompt = (
        "You are CourtIQ's concise tennis coaching assistant. Use only the supplied context. "
        "Give practical, safe, non-medical guidance in at most 180 words. Do not promise outcomes, "
        "invent video measurements, or claim access to footage. Structure the answer as one short explanation "
        "followed by 2-4 actionable bullets.\n\n"
        f"CourtIQ context: {context}\nUser question: {question}"
    )
    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.35, "maxOutputTokens": 320},
        }
    ).encode("utf-8")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    request = Request(
        endpoint,
        data=body,
        method="POST",
        headers={"content-type": "application/json", "x-goog-api-key": settings.gemini_api_key},
    )
    try:
        with urlopen(request, timeout=settings.gemini_timeout_seconds) as response:  # noqa: S310 - fixed trusted endpoint
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 429:
            raise CoachingServiceError("coaching_rate_limited", "Coaching help is busy. Try again shortly.", 429) from exc
        raise CoachingServiceError("coaching_unavailable", "Coaching help is temporarily unavailable.", 502) from exc
    except (TimeoutError, URLError, json.JSONDecodeError) as exc:
        raise CoachingServiceError("coaching_unavailable", "Coaching help is temporarily unavailable.", 502) from exc

    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    answer = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
    if not answer or len(answer) > 4000:
        raise CoachingServiceError("coaching_invalid_response", "Coaching help returned an unreadable response. Try again.", 502)
    return answer
