"""Privacy-preserving audit logging for MCP invocations."""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator


logger = logging.getLogger("gestionale_mcp.audit")


class AuditSpan:
    def __init__(self, tool: str, operation_id: str, parameter_names: list[str]):
        self.trace_id = uuid.uuid4().hex
        self.tool = tool
        self.operation_id = operation_id
        self.parameter_names = sorted(set(parameter_names))
        self.started = time.perf_counter()
        self.status = "ok"

    def fail(self) -> None:
        self.status = "error"

    def close(self) -> None:
        payload = {
            "event": "mcp_tool_call",
            "trace_id": self.trace_id,
            "tool": self.tool,
            "operation_id": self.operation_id,
            "parameter_names": self.parameter_names,
            "status": self.status,
            "duration_ms": round((time.perf_counter() - self.started) * 1000, 2),
        }
        logger.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


@asynccontextmanager
async def audit_span(
    tool: str, operation_id: str, parameter_names: list[str]
) -> AsyncIterator[AuditSpan]:
    """Log metadata only: never values, credentials, PDF text or base64."""
    span = AuditSpan(tool, operation_id, parameter_names)
    try:
        yield span
    except Exception:
        span.fail()
        raise
    finally:
        span.close()
