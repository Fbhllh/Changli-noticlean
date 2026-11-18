from __future__ import annotations

import json

import pytest

from noticlean.models import CATEGORY_OPTIONS, PRIORITY_OPTIONS, ParseResult
from noticlean.render import (
    UNRELATED_MESSAGE,
    render_card,
    render_markdown,
    render_priority_badge,
    result_to_json,
)


@pytest.mark.parametrize(
    "priority,color",
    [
        (PRIORITY_OPTIONS[0], "#e5484d"),
        (PRIORITY_OPTIONS[1], "#e6a817"),
        (PRIORITY_OPTIONS[2], "#30a46c"),
    ],
)
def test_render_priority_badge_uses_red_yellow_green_styles(card_factory, priority: str, color: str) -> None:
    card = card_factory(priority=priority, category=CATEGORY_OPTIONS[0])

    html = render_priority_badge(card)

    assert color in html
    assert "border-left:5px solid" in html
    assert priority in html
    assert "分类：教务通知" in html


def test_render_priority_badge_falls_back_and_does_not_inject_html(card_factory) -> None:
    card = card_factory(priority="<script>alert(1)</script>", category="<img src=x>")

    html = render_priority_badge(card)

    assert PRIORITY_OPTIONS[1] in html
    assert CATEGORY_OPTIONS[3] in html
    assert "<script>" not in html
    assert "<img" not in html


def test_render_card_contains_structured_fields_actions_and_links(card_factory) -> None:
    card = card_factory(
        category=CATEGORY_OPTIONS[2],
        priority=PRIORITY_OPTIONS[2],
        links=["https://example.edu.cn/register"],
    )

    markdown = render_card(card, 2)

    assert "【通知解析卡片 2】" in markdown
    assert "事件名称**：校园讲座" in markdown
    assert "分类/优先级**：讲座/比赛 ｜ 低-绿标" in markdown
    assert "1. 提前报名<br>2. 按时参加" in markdown
    assert "相关链接：https://example.edu.cn/register" in markdown
    assert "2026年11月20日 18:00" in markdown


def test_render_markdown_handles_safety_and_multiple_cards(card_factory) -> None:
    result = ParseResult(
        True,
        [card_factory(), card_factory(event_name="第二条通知")],
        "清理后的通知",
        safety_warning="请核实来源",
    )

    markdown = render_markdown(result)

    assert "【安全提示】" in markdown
    assert "【通知解析卡片 1】" in markdown
    assert "第二条通知" in markdown
    assert "\n\n---\n\n" in markdown


def test_render_markdown_returns_unrelated_message() -> None:
    assert render_markdown(ParseResult(False, [], "闲聊")) == UNRELATED_MESSAGE


def test_result_to_json_exports_new_fields_but_not_runtime_or_source(card_factory) -> None:
    result = ParseResult(True, [card_factory(calendar_ready=True)], "原始通知")

    payload = json.loads(result_to_json(result))
    notice = payload["notices"][0]

    assert notice["category"] == CATEGORY_OPTIONS[3]
    assert notice["priority"] == PRIORITY_OPTIONS[1]
    assert notice["deadline"]["value"] == "2026-11-20T18:00:00"
    assert "source_text" not in notice
    assert "calendar_ready" not in notice
    assert "cleaned_text" not in payload
