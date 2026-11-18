from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import dataclass
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from noticlean.models import ParseResult


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


def _request_enhancement(result: ParseResult, config: LLMConfig) -> dict:
    if not config.model.strip():
        raise ValueError("模型名称不能为空")
    local_cards = [notice.to_dict() for notice in result.notices]
    prompt = "\n".join([
        "请从校园通知中补充或修正结构化字段，只返回 JSON 对象。",
        '格式为 {"notices":[{"event_name":"...","audience":"...","location":"...","actions":["..."],"tip":"..."}]}。',
        "notices 的顺序和数量必须与本地卡片一致。无法确认的字段返回空字符串或空数组，禁止编造时间、地点、对象、链接或行动。",
        "原始通知：",
        result.cleaned_text,
        "本地卡片：",
        json.dumps(local_cards, ensure_ascii=False),
    ])
    body = json.dumps({
        "model": config.model.strip(),
        "messages": [
            {"role": "system", "content": "你是严谨的校园通知信息提取器，只输出指定 JSON。"},
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


def _clean_text_field(value: object, limit: int = 500) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def enhance_result(result: ParseResult, config: LLMConfig) -> ParseResult:
    if not result.relevant or not result.notices:
        return result
    try:
        payload = _request_enhancement(result, config)
        items = payload.get("notices")
        if not isinstance(items, list):
            raise ValueError("模型响应缺少 notices 数组")
        enhanced = deepcopy(result)
        for card, item in zip(enhanced.notices, items):
            if not isinstance(item, dict):
                continue
            for field_name in ("event_name", "audience", "location", "tip"):
                value = _clean_text_field(item.get(field_name))
                if value:
                    setattr(card, field_name, value)
            actions = item.get("actions")
            if isinstance(actions, list):
                cleaned_actions = [_clean_text_field(action) for action in actions[:10]]
                cleaned_actions = [action for action in cleaned_actions if action]
                if cleaned_actions:
                    card.actions = cleaned_actions
        return enhanced
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        failed = deepcopy(result)
        failed.warnings.append("大模型增强失败，已保留本地解析结果。")
        return failed
