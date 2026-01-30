import json
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AiDecision:
    is_prohibited: bool
    label: str
    confidence: float
    reason: str


class AiModerator:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            timeout=settings.OPENROUTER_TIMEOUT_SEC,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def classify_text(self, text: str) -> Optional[AiDecision]:
        if not settings.OPENROUTER_API_KEY:
            return None

        system = "You are a content moderation classifier. Return ONLY valid JSON. No markdown."
        labels = settings.AI_PROHIBITED_LABELS
        user = (
            "Your task is NOT to flag mentions alone."
            "You must determine whether the message PROMOTES, ENCOURAGES, or ADVERTISES prohibited content."

            "Important rules:"
            "- If gambling/scam is mentioned ONLY to criticize, complain, warn, or discuss negatively,"
            "  it is NOT prohibited."
            "- Mention without promotion = allowed."
            "- Promotion, encouragement, instruction, or advertisement = prohibited."
            "Classify the following message (Uzbek/Russian possible). "
            "Detect prohibited topics: gambling/1xBet/betting/casino, or fraud/scam/deception/fake investment. "
            f"Allowed labels: {labels}.\n\n"
            "Return JSON with schema: {"
            '"is_prohibited": boolean, "label": "gambling"|"fraud"|"other"|"none", '
            '"confidence": number, "reason": string(must be in uzbek) }\n\n'
            f"Message: {text}"
        )

        payload = {
            "model": settings.OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": 200,
        }

        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        }

        for attempt in range(2):
            try:
                resp = await self._client.post("/chat/completions", headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    return None
                is_prohibited = bool(parsed.get("is_prohibited"))
                label = str(parsed.get("label", "none"))
                confidence = float(parsed.get("confidence", 0))
                reason = str(parsed.get("reason", ""))[:160]
                return AiDecision(
                    is_prohibited=is_prohibited,
                    label=label,
                    confidence=confidence,
                    reason=reason,
                )
            except Exception:
                logger.exception("AI moderation request failed (attempt %s)", attempt + 1)
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                return None
