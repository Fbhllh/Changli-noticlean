from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from noticlean.dates import format_deadline, make_deadline, parse_deadline
from noticlean.models import CATEGORY_OPTIONS, PRIORITY_OPTIONS, DeadlineInfo
from noticlean.parser import (
    clean_text,
    detect_safety_risk,
    extract_links,
    parse_text,
    resolve_priority,
    split_notices,
)


def test_parse_text_extracts_category_location_actions_and_high_priority(reference: datetime) -> None:
    text = """【缓考申请通知】
面向对象：2024级本科生
截止时间：11月18日 11:00
地点：云塘校区教务办公室
请提交缓考申请材料。"""

    result = parse_text(text, reference)
    card = result.notices[0]

    assert result.relevant is True
    assert card.event_name == "缓考申请通知"
    assert card.category == CATEGORY_OPTIONS[0]
    assert card.priority == PRIORITY_OPTIONS[0]
    assert card.deadline.value == datetime(2026, 11, 18, 11, 0)
    assert "云塘校区" in card.location
    assert any("提交缓考申请材料" in action for action in card.actions)
    assert card.calendar_ready is False


def test_parse_text_marks_voluntary_future_lecture_low(reference: datetime) -> None:
    text = """【学术讲座通知】
面向对象：全体学生
时间：11月25日 10:00
地点：云塘校区图书馆报告厅
自愿参加，请提前报名。"""

    card = parse_text(text, reference).notices[0]

    assert card.category == CATEGORY_OPTIONS[2]
    assert card.priority == PRIORITY_OPTIONS[2]


def test_parse_text_marks_regular_class_notice_medium(reference: datetime) -> None:
    text = """1. 班级班会通知
参与对象：2024级本科生
时间：11月25日 10:00
地点：云塘校区教学楼101
请按时参加。"""

    card = parse_text(text, reference).notices[0]

    assert card.category == CATEGORY_OPTIONS[1]
    assert card.priority == PRIORITY_OPTIONS[1]


def test_parse_text_splits_multiple_notices_and_preserves_order(reference: datetime) -> None:
    text = """【讲座报名通知】
对象：全体学生
截止：11月25日 18:00
地点：图书馆
请报名。
---
【考试安排通知】
对象：2024级学生
截止：11月18日 18:00
地点：教学楼101
请携带证件。"""

    result = parse_text(text, reference)

    assert len(result.notices) == 2
    assert result.notices[0].category == CATEGORY_OPTIONS[2]
    assert result.notices[1].category == CATEGORY_OPTIONS[0]
    assert result.notices[1].priority == PRIORITY_OPTIONS[0]


def test_clean_text_removes_noise_and_split_notices_handles_separator() -> None:
    cleaned = clean_text("收到\n谢谢老师\n【比赛通知】\n请报名\n---\n【考试通知】\n请准备证件\n顶顶顶")

    assert "收到" not in cleaned
    assert "谢谢老师" not in cleaned
    assert len(split_notices(cleaned)) == 2


def test_irrelevant_text_has_no_cards(reference: datetime) -> None:
    result = parse_text("今天天气不错，晚上一起吃饭", reference)

    assert result.relevant is False
    assert result.notices == []


def test_safety_risk_and_link_extraction() -> None:
    text = "请转账押金，详情 http://192.168.1.1/pay，官网 https://example.edu.cn/a。"

    assert detect_safety_risk(text) is not None
    assert extract_links(text) == ["http://192.168.1.1/pay", "https://example.edu.cn/a"]


def test_resolve_priority_enforces_exam_deadline_and_valid_default(reference: datetime) -> None:
    within_48 = make_deadline(reference + timedelta(hours=48), reference)
    beyond_48 = make_deadline(reference + timedelta(hours=48, seconds=1), reference)
    past = make_deadline(reference - timedelta(days=1), reference)

    assert resolve_priority(PRIORITY_OPTIONS[2], within_48, "普通讲座", reference) == PRIORITY_OPTIONS[0]
    assert resolve_priority(PRIORITY_OPTIONS[2], beyond_48, "普通讲座", reference) == PRIORITY_OPTIONS[2]
    assert resolve_priority(PRIORITY_OPTIONS[1], past, "普通通知", reference) == PRIORITY_OPTIONS[0]
    assert resolve_priority("非法", beyond_48, "普通通知", reference) == PRIORITY_OPTIONS[1]
    assert resolve_priority(PRIORITY_OPTIONS[2], beyond_48, "考试说明讲座", reference) == PRIORITY_OPTIONS[0]


def test_parse_deadline_supports_relative_afternoon_and_date_only(reference: datetime) -> None:
    precise = parse_deadline("请于明天下午6点提交", reference)
    date_only = parse_deadline("截止：11月20日", reference)

    assert precise.value == datetime(2026, 11, 18, 18, 0)
    assert precise.date_only is False
    assert date_only.value == datetime(2026, 11, 20, 23, 59)
    assert date_only.date_only is True
    assert date_only.year_inferred is True
    assert "具体时刻未注明" in format_deadline(date_only)


def test_format_deadline_handles_missing_and_expired(reference: datetime) -> None:
    missing = DeadlineInfo()
    expired = make_deadline(reference - timedelta(minutes=1), reference)

    assert "未在通知中找到明确截止时间" in format_deadline(missing)
    assert "已截止" in format_deadline(expired)


def test_make_deadline_rejects_timezone(reference: datetime) -> None:
    with pytest.raises(ValueError, match="不含时区"):
        make_deadline(datetime(2026, 11, 20, tzinfo=timezone.utc), reference)
