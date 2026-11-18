from __future__ import annotations

import re
from datetime import datetime

import pytest

from noticlean.calendar_export import build_ics, calendar_filename
from noticlean.dates import make_deadline
from noticlean.models import DeadlineInfo, PRIORITY_OPTIONS


def _unfold(ics: str) -> list[str]:
    return ics.replace("\r\n ", "").split("\r\n")


def test_build_ics_creates_precise_thirty_minute_event(card_factory) -> None:
    card = card_factory(calendar_ready=True, priority=PRIORITY_OPTIONS[0])

    ics = build_ics(card)

    assert ics.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n")
    assert ics.endswith("END:VEVENT\r\nEND:VCALENDAR\r\n")
    assert "DTSTART:20261120T180000\r\n" in ics
    assert "DTEND:20261120T183000\r\n" in ics
    assert "SUMMARY:校园讲座\r\n" in ics
    assert "LOCATION:云塘校区图书馆报告厅\r\n" in ics
    assert "CATEGORIES:社团/其他\r\n" in ics
    assert "PRIORITY:1\r\n" in ics
    assert "STATUS:CONFIRMED\r\n" in ics
    assert re.search(r"DTSTAMP:\d{8}T\d{6}Z\r\n", ics)


def test_build_ics_escapes_text_and_folds_utf8_lines(card_factory) -> None:
    card = card_factory(
        event_name="考试,报名;第二场\nA\\B",
        location="云塘校区" + "很长的地点" * 30,
        actions=["填写材料,核对格式；保留凭证"],
        calendar_ready=True,
    )

    ics = build_ics(card)
    unfolded = _unfold(ics)

    assert "SUMMARY:考试\\,报名\\;第二场\\nA\\\\B" in unfolded
    assert any(line.startswith("DESCRIPTION:") and "填写材料\\,核对格式；保留凭证" in line for line in unfolded)
    assert all(len(line.encode("utf-8")) <= 75 for line in ics.split("\r\n"))
    assert "\r\n " in ics
    assert ics.encode("utf-8").decode("utf-8") == ics


def test_build_ics_creates_all_day_event_for_date_only(card_factory, reference: datetime) -> None:
    deadline = make_deadline(
        datetime(2026, 11, 20, 23, 59),
        reference,
        "2026-11-20",
        date_only=True,
    )
    card = card_factory(deadline=deadline, calendar_ready=True, priority=PRIORITY_OPTIONS[2])

    ics = build_ics(card)

    assert "DTSTART;VALUE=DATE:20261120\r\n" in ics
    assert "DTEND;VALUE=DATE:20261121\r\n" in ics
    assert "DTSTART:20261120T235900" not in ics
    assert "PRIORITY:9\r\n" in ics
    assert "原文仅提供日期，按全天事件记录。" in _unfold(ics)[-8]


def test_build_ics_uses_medium_numeric_priority_by_default(card_factory) -> None:
    card = card_factory(calendar_ready=True, priority="未知优先级")

    assert "PRIORITY:5\r\n" in build_ics(card)


def test_build_ics_has_deterministic_uid(card_factory) -> None:
    card = card_factory(calendar_ready=True)

    first = re.search(r"UID:([^\r\n]+)", build_ics(card)).group(1)
    second = re.search(r"UID:([^\r\n]+)", build_ics(card)).group(1)

    assert first == second
    assert re.fullmatch(r"[0-9a-f]{24}@noticlean\.local", first)


@pytest.mark.parametrize(
    "overrides",
    [
        {"calendar_ready": False},
        {"calendar_ready": True, "event_name": "  "},
        {"calendar_ready": True, "deadline": DeadlineInfo()},
        {"calendar_ready": True, "location": ""},
    ],
)
def test_build_ics_rejects_incomplete_calendar_data(card_factory, overrides: dict) -> None:
    with pytest.raises(ValueError, match="必要条件"):
        build_ics(card_factory(**overrides))


def test_calendar_filename_sanitizes_truncates_and_provides_fallback(card_factory) -> None:
    assert calendar_filename(card_factory(event_name=" 考试:报名/2026 "), 1) == "考试_报名_2026.ics"
    assert calendar_filename(card_factory(event_name='<>:"/\\|?*'), 3) == "通知_3.ics"

    long_name = calendar_filename(card_factory(event_name="测" * 80), 1)

    assert long_name.endswith(".ics")
    assert len(long_name.removesuffix(".ics")) == 60
