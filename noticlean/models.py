from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DeadlineInfo:
    raw_text: str = ""
    value: datetime | None = None
    date_only: bool = False
    year_inferred: bool = False
    countdown: str = ""
    urgency: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["value"] = self.value.isoformat() if self.value else None
        return data


@dataclass
class NoticeCard:
    event_name: str
    deadline: DeadlineInfo
    audience: str
    location: str
    actions: list[str]
    links: list[str]
    tip: str
    source_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_name": self.event_name,
            "deadline": self.deadline.to_dict(),
            "audience": self.audience,
            "location": self.location,
            "actions": list(self.actions),
            "links": list(self.links),
            "tip": self.tip,
        }


@dataclass
class ParseResult:
    relevant: bool
    notices: list[NoticeCard]
    cleaned_text: str
    safety_warning: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "relevant": self.relevant,
            "notices": [notice.to_dict() for notice in self.notices],
            "safety_warning": self.safety_warning,
            "warnings": list(self.warnings),
        }
