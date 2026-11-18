from __future__ import annotations

from datetime import datetime

import pytest

from noticlean.dates import make_deadline
from noticlean.models import DEFAULT_CATEGORY, DEFAULT_PRIORITY, NoticeCard


@pytest.fixture
def reference() -> datetime:
    return datetime(2026, 11, 17, 12, 0, 0)


@pytest.fixture
def card_factory(reference: datetime):
    def factory(**overrides) -> NoticeCard:
        values = {
            "event_name": "校园讲座",
            "deadline": make_deadline(
                datetime(2026, 11, 20, 18, 0),
                reference,
                "11月20日 18:00",
            ),
            "audience": "全体学生",
            "location": "云塘校区图书馆报告厅",
            "actions": ["提前报名", "按时参加"],
            "links": [],
            "tip": "保存报名凭证",
            "source_text": "校园讲座通知原文",
            "category": DEFAULT_CATEGORY,
            "priority": DEFAULT_PRIORITY,
            "calendar_ready": False,
        }
        values.update(overrides)
        return NoticeCard(**values)

    return factory
