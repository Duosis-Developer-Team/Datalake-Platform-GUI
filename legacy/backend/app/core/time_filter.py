from typing import Optional

from fastapi import Query

from app.utils.time_range import default_time_range, preset_to_range


class TimeFilter:
    def __init__(
        self,
        start: Optional[str] = Query(None, description="Başlangıç tarihi (YYYY-MM-DD)"),
        end: Optional[str] = Query(None, description="Bitiş tarihi (YYYY-MM-DD)"),
        preset: Optional[str] = Query(None, description="Preset: 1d, 7d, 30d"),
    ):
        if start and end:
            self.time_range = {"start": start, "end": end, "preset": "custom"}
        elif preset:
            self.time_range = preset_to_range(preset)
        else:
            self.time_range = default_time_range()

    def to_dict(self) -> dict:
        return self.time_range
