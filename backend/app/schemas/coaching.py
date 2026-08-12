from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CoachingHelpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=500)
    context: str = Field(default="CourtIQ general coaching", max_length=1200)

    @field_validator("question", "context")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.split())


class CoachingHelpResponse(BaseModel):
    status: str = "ok"
    answer: str
    provider: str = "Gemini"
    disclaimer: str = "Educational tennis guidance, not medical advice or a guarantee of results."
