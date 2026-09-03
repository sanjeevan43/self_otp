from typing import Any

from pydantic import BaseModel


class MetaWebhookPayload(BaseModel):
    object: str | None = None
    entry: list[dict[str, Any]] | None = None
