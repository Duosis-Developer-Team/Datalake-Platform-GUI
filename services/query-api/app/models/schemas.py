from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


class QueryResult(BaseModel):
    result_type: Optional[str] = None
    value: Any = None
    columns: Optional[List[str]] = None
    data: Optional[List[Any]] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    db_pool: str
