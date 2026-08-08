"""Strict input/output schemas shared by all MCP tools."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ToolResult(StrictModel):
    ok: bool
    operation_id: str
    data: Any = None
    count: int | None = None
    has_more: bool | None = None
    next_cursor: str | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    trace_id: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


class Capability(StrictModel):
    operation_id: str
    domain: str
    description: str
    method: Literal["GET", "POST", "PUT", "PATCH"]
    read_only: bool
    path_parameters: list[str] = Field(default_factory=list)
    query_parameters: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False


class PreparedAction(StrictModel):
    proposal_id: str
    action_id: str
    summary: str
    reason: str
    expires_at: str
    confirmation_phrase: str
    payload_sha256: str
