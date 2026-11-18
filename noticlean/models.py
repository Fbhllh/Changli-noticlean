from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

CATEGORY_OPTIONS = ("教务通知", "院系/班级", "讲座/比赛", "社团/其他")
PRIORITY_OPTIONS = (
    "高-红标（涉及绩点/考试/截止日期在48小时内）",
    "中-黄标（常规通知）",
    "低-绿标（自愿参加/讲座等）",
)
DEFAULT_CATEGORY = CATEGORY_OPTIONS[3]
DEFAULT_PRIORITY = PRIORITY_OPTIONS[1]


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
    category: str = DEFAULT_CATEGORY
    priority: str = DEFAULT_PRIORITY
    calendar_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_name": self.event_name,
            "deadline": self.deadline.to_dict(),
            "audience": self.audience,
            "location": self.location,
            "actions": list(self.actions),
            "links": list(self.links),
            "tip": self.tip,
            "category": self.category,
            "priority": self.priority,
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
