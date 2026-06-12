"""Investigation trace — record of every tool attempted during a chat turn."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from app.services.tool_registry import ToolResult


@dataclass
class InvestigationEntry:
    tool: str
    status: str
    rows: Optional[int] = None
    source: Optional[str] = None
    error: Optional[str] = None


@dataclass
class InvestigationTrace:
    entries: list[InvestigationEntry] = field(default_factory=list)

    def record(self, result: ToolResult) -> None:
        self.entries.append(
            InvestigationEntry(
                tool=result.name,
                status=result.status,
                rows=result.rows,
                source=result.source,
                error=result.error,
            )
        )

    def as_context(self) -> list[dict[str, Any]]:
        return [asdict(e) for e in self.entries]

    def summary_line(self) -> str:
        n = len(self.entries)
        if n == 0:
            return "No tools were executed."
        ok = sum(1 for e in self.entries if e.status == "success")
        with_rows = sum(1 for e in self.entries if (e.rows or 0) > 0)
        return f"{n} source(s) checked ({ok} succeeded, {with_rows} returned rows)."

    def tool_names(self) -> list[str]:
        return [e.tool for e in self.entries]

    def merge(self, other: InvestigationTrace) -> None:
        """Append entries from another trace (map-reduce workers)."""
        self.entries.extend(other.entries)
