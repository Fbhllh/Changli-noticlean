from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from noticlean.dates import make_deadline
from noticlean.models import DEFAULT_CATEGORY, DEFAULT_PRIORITY, ParseResult
from noticlean.parser import resolve_priority

Category = Literal["教务通知", "院系/班级", "讲座/比赛", "社团/其他"]
Priority = Literal[
    "高-红标（涉及绩点/考试/截止日期在48小时内）",
    "中-黄标（常规通知）",
    "低-绿标（自愿参加/讲座等）",
]

SYSTEM_PROMPT = """你是严谨的校园通知结构化提取器。只输出一个 JSON 对象，不要 Markdown、代码围栏或解释。
必须保留输入通知的数量和顺序。无法确认的文本字段返回空字符串，行动返回空数组，时间返回 null，禁止编造。
event_time 必须是不含时区的 ISO 本地时间：精确时间使用 YYYY-MM-DDTHH:mm:ss；只有日期使用 YYYY-MM-DD，并令 date_only=true。
category 只能是：教务通知、院系/班级、讲座/比赛、社团/其他。
priority 只能是：高-红标（涉及绩点/考试/截止日期在48小时内）、中-黄标（常规通知）、低-绿标（自愿参加/讲座等）。
绩点、考试或截止不超过48小时为高优先级；自愿参加、普通讲座且无紧迫截止可为低优先级；其余常规通知为中优先级。"""


class LLMNotice(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    event_name: str = Field(default="", max_length=200)
    event_time: datetime | None = None
    date_only: bool = False
    audience: str = Field(default="", max_length=300)
    location: str = Field(default="", max_length=300)
    actions: list[str] = Field(default_factory=list, max_length=10)
    tip: str = Field(default="", max_length=300)
    category: Category = DEFAULT_CATEGORY
    priority: Priority = DEFAULT_PRIORITY

    @field_validator("event_time", mode="before")
    @classmethod
    def normalize_event_time(cls, value: object) -> object:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                return text + "T23:59:00"
            return text
        return value

    @field_validator("event_time")
    @classmethod
    def require_local_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            raise ValueError("event_time 必须是不含时区的本地时间")
        return value

    @field_validator("actions")
    @classmethod
    def remove_empty_actions(cls, value: list[str]) -> list[str]:
        return [item for item in value if item]


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    notices: list[LLMNotice]


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key: str = ""
    timeout: float = 20.0


def _endpoint(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("接口地址必须使用有效的 HTTP 或 HTTPS 地址")
    return value if value.endswith("/chat/completions") else value + "/chat/completions"


def _decode_content(raw: bytes) -> dict:
    payload = json.loads(raw.decode("utf-8"))
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("模型返回内容不是字符串")
    stripped = content.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL | re.IGNORECASE)
    if fence:
        stripped = fence.group(1)
    try:
        result = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        if start < 0:
            raise
        result = json.JSONDecoder().raw_decode(stripped[start:])[0]
    if not isinstance(result, dict):
        raise ValueError("模型返回 JSON 顶层必须是对象")
    return result


def _request_enhancement(result: ParseResult, config: LLMConfig, reference: datetime) -> dict:
    if not config.model.strip():
        raise ValueError("模型名称不能为空")
    local_cards = [notice.to_dict() for notice in result.notices]
    example = {
        "notices": [{
            "event_name": "示例讲座",
            "event_time": "2026-11-20T18:00:00",
            "date_only": False,
            "audience": "全体学生",
            "location": "云塘校区图书馆报告厅",
            "actions": ["提前报名并按时参加"],
            "tip": "提前保存报名凭证",
            "category": "讲座/比赛",
            "priority": "低-绿标（自愿参加/讲座等）",
        }]
    }
    prompt = "\n".join([
        f"参考本地时间：{reference.isoformat(timespec='minutes')}。解析相对日期时以此为基准。",
        "返回结构示例，仅用于说明字段类型，不要把示例内容带入结果：",
        json.dumps(example, ensure_ascii=False),
        f"必须返回 {len(local_cards)} 条 notices，并保持原有顺序。",
        "原始通知：",
        result.cleaned_text,
        "本地卡片：",
        json.dumps(local_cards, ensure_ascii=False),
    ])
    body = json.dumps({
        "model": config.model.strip(),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    request = Request(_endpoint(config.base_url), data=body, headers=headers, method="POST")
    timeout = min(max(float(config.timeout), 1.0), 120.0)
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("模型响应过大")
    return _decode_content(raw)


def enhance_result(result: ParseResult, config: LLMConfig, reference: datetime | None = None) -> ParseResult:
    if not result.relevant or not result.notices:
        return result
    actual_reference = reference or datetime.now()
    try:
        payload = _request_enhancement(result, config, actual_reference)
        response = LLMResponse.model_validate(payload)
        if len(response.notices) != len(result.notices):
            raise ValueError("模型返回的通知数量与本地解析结果不一致")
        enhanced = deepcopy(result)
        for card, item in zip(enhanced.notices, response.notices):
            for field_name in ("event_name", "audience", "location", "tip"):
                value = getattr(item, field_name)
                if value:
                    setattr(card, field_name, value)
            if item.actions:
                card.actions = item.actions
            card.category = item.category
            card.calendar_ready = False
            if item.event_time is not None:
                card.deadline = make_deadline(
                    item.event_time,
                    actual_reference,
                    item.event_time.isoformat(),
                    item.date_only,
                )
                card.calendar_ready = bool(item.event_name and item.location)
            card.priority = resolve_priority(item.priority, card.deadline, card.source_text, actual_reference)
        return enhanced
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        failed = deepcopy(result)
        failed.warnings.append("大模型增强失败，已保留本地解析结果。")
        return failed
