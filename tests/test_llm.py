from __future__ import annotations

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

import noticlean.llm as llm_module
from noticlean.llm import (
    SYSTEM_PROMPT,
    LLMConfig,
    LLMNotice,
    LLMResponse,
    _decode_content,
    _endpoint,
    _request_enhancement,
    enhance_result,
)
from noticlean.models import CATEGORY_OPTIONS, PRIORITY_OPTIONS, ParseResult


def _notice_payload(**overrides) -> dict:
    values = {
        "event_name": "考研讲座",
        "event_time": "2026-11-18T12:00:00",
        "date_only": False,
        "audience": "全体学生",
        "location": "云塘校区图书馆报告厅",
        "actions": ["提前报名", "按时参加"],
        "tip": "保存凭证",
        "category": CATEGORY_OPTIONS[2],
        "priority": PRIORITY_OPTIONS[2],
    }
    values.update(overrides)
    return values


def _wrapped_payload(**overrides) -> dict:
    return {"notices": [_notice_payload(**overrides)]}


def test_llm_notice_validates_complete_structure_and_strips_actions() -> None:
    item = LLMNotice.model_validate(
        _notice_payload(actions=[" 提前报名 ", "", "按时参加"], ignored="忽略额外字段")
    )

    assert item.event_name == "考研讲座"
    assert item.event_time == datetime(2026, 11, 18, 12, 0)
    assert item.actions == ["提前报名", "按时参加"]
    assert item.category == "讲座/比赛"
    assert item.priority.startswith("低-绿标")
    assert not hasattr(item, "ignored")


def test_llm_notice_normalizes_date_only_and_empty_time() -> None:
    date_only = LLMNotice.model_validate(_notice_payload(event_time="2026-11-20", date_only=True))
    missing = LLMNotice.model_validate(_notice_payload(event_time="  "))

    assert date_only.event_time == datetime(2026, 11, 20, 23, 59)
    assert date_only.date_only is True
    assert missing.event_time is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("category", "随意分类"),
        ("priority", "非常紧急"),
        ("event_time", "2026-02-30T10:00:00"),
        ("event_time", "2026-11-20T10:00:00+08:00"),
        ("event_name", "长" * 201),
    ],
)
def test_llm_notice_rejects_invalid_values(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        LLMNotice.model_validate(_notice_payload(**{field: value}))


def test_llm_response_requires_notice_list() -> None:
    with pytest.raises(ValidationError):
        LLMResponse.model_validate({})


def test_system_prompt_defines_json_time_category_and_priority_contract() -> None:
    assert "只输出一个 JSON 对象" in SYSTEM_PROMPT
    assert "YYYY-MM-DDTHH:mm:ss" in SYSTEM_PROMPT
    for option in (*CATEGORY_OPTIONS, *PRIORITY_OPTIONS):
        assert option in SYSTEM_PROMPT
    assert "48小时" in SYSTEM_PROMPT


def test_enhance_result_merges_valid_fields_and_enables_calendar(
    monkeypatch: pytest.MonkeyPatch,
    card_factory,
    reference: datetime,
) -> None:
    local = ParseResult(True, [card_factory()], "原始通知")
    monkeypatch.setattr(llm_module, "_request_enhancement", lambda *args: _wrapped_payload())

    enhanced = enhance_result(local, LLMConfig("https://example.com/v1", "model"), reference)

    card = enhanced.notices[0]
    assert card.event_name == "考研讲座"
    assert card.location == "云塘校区图书馆报告厅"
    assert card.actions == ["提前报名", "按时参加"]
    assert card.deadline.value == datetime(2026, 11, 18, 12, 0)
    assert card.category == "讲座/比赛"
    assert card.priority == PRIORITY_OPTIONS[0], "24 小时内截止必须由本地规则提升为高优先级"
    assert card.calendar_ready is True
    assert local.notices[0].calendar_ready is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"event_name": ""},
        {"event_time": None},
        {"location": ""},
    ],
)
def test_enhance_result_does_not_enable_calendar_when_llm_field_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    card_factory,
    reference: datetime,
    overrides: dict,
) -> None:
    local = ParseResult(True, [card_factory()], "原始通知")
    monkeypatch.setattr(
        llm_module,
        "_request_enhancement",
        lambda *args: _wrapped_payload(**overrides),
    )

    enhanced = enhance_result(local, LLMConfig("https://example.com/v1", "model"), reference)

    assert enhanced.notices[0].calendar_ready is False
    assert enhanced.warnings == []


def test_enhance_result_rejects_mismatched_notice_count(
    monkeypatch: pytest.MonkeyPatch,
    card_factory,
    reference: datetime,
) -> None:
    local = ParseResult(True, [card_factory(), card_factory(event_name="另一通知")], "两条通知")
    monkeypatch.setattr(llm_module, "_request_enhancement", lambda *args: _wrapped_payload())

    enhanced = enhance_result(local, LLMConfig("https://example.com/v1", "model"), reference)

    assert enhanced.warnings == ["大模型增强失败，已保留本地解析结果。"]
    assert [card.event_name for card in enhanced.notices] == ["校园讲座", "另一通知"]
    assert all(not card.calendar_ready for card in enhanced.notices)


def test_enhance_result_falls_back_on_invalid_enum(
    monkeypatch: pytest.MonkeyPatch,
    card_factory,
    reference: datetime,
) -> None:
    local = ParseResult(True, [card_factory()], "原始通知")
    monkeypatch.setattr(
        llm_module,
        "_request_enhancement",
        lambda *args: _wrapped_payload(category="非法分类"),
    )

    enhanced = enhance_result(local, LLMConfig("https://example.com/v1", "model"), reference)

    assert enhanced is not local
    assert enhanced.notices[0].event_name == local.notices[0].event_name
    assert enhanced.warnings == ["大模型增强失败，已保留本地解析结果。"]


def test_enhance_result_short_circuits_irrelevant_result(card_factory) -> None:
    local = ParseResult(False, [], "")

    assert enhance_result(local, LLMConfig("", "")) is local


def test_request_enhancement_builds_prompt_and_decodes_response(
    monkeypatch: pytest.MonkeyPatch,
    card_factory,
    reference: datetime,
) -> None:
    captured = {}
    response_body = {
        "choices": [{"message": {"content": json.dumps(_wrapped_payload(), ensure_ascii=False)}}]
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, size: int) -> bytes:
            assert size == 2_000_001
            return json.dumps(response_body, ensure_ascii=False).encode("utf-8")

    def fake_urlopen(request, timeout: float):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(llm_module, "urlopen", fake_urlopen)
    local = ParseResult(True, [card_factory()], "原始通知")

    payload = _request_enhancement(
        local,
        LLMConfig("https://example.com/v1/", "test-model", "secret", timeout=1000),
        reference,
    )

    request = captured["request"]
    body = json.loads(request.data.decode("utf-8"))
    assert payload["notices"][0]["event_name"] == "考研讲座"
    assert request.full_url == "https://example.com/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer secret"
    assert captured["timeout"] == 120.0
    assert body["model"] == "test-model"
    assert body["temperature"] == 0
    assert body["messages"][0]["content"] == SYSTEM_PROMPT
    assert "参考本地时间：2026-11-17T12:00" in body["messages"][1]["content"]
    assert "必须返回 1 条 notices" in body["messages"][1]["content"]


def test_request_enhancement_rejects_empty_model(card_factory, reference: datetime) -> None:
    local = ParseResult(True, [card_factory()], "原始通知")

    with pytest.raises(ValueError, match="模型名称不能为空"):
        _request_enhancement(local, LLMConfig("https://example.com/v1", " "), reference)


def test_endpoint_validation() -> None:
    assert _endpoint("https://example.com/v1/chat/completions") == "https://example.com/v1/chat/completions"
    with pytest.raises(ValueError, match="HTTP 或 HTTPS"):
        _endpoint("file:///tmp/model")


def test_decode_content_accepts_fence_and_embedded_json() -> None:
    fenced = json.dumps({"choices": [{"message": {"content": "```json\n{\"notices\": []}\n```"}}]}).encode()
    embedded = json.dumps({"choices": [{"message": {"content": "前缀 {\"notices\": []} 后缀"}}]}).encode()

    assert _decode_content(fenced) == {"notices": []}
    assert _decode_content(embedded) == {"notices": []}


def test_decode_content_rejects_non_object_and_non_string_content() -> None:
    array = json.dumps({"choices": [{"message": {"content": "[]"}}]}).encode()
    non_string = json.dumps({"choices": [{"message": {"content": []}}]}).encode()

    with pytest.raises(ValueError, match="顶层必须是对象"):
        _decode_content(array)
    with pytest.raises(ValueError, match="不是字符串"):
        _decode_content(non_string)
