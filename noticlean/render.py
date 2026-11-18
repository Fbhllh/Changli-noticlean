from __future__ import annotations

import json

from noticlean.dates import format_deadline
from noticlean.models import NoticeCard, ParseResult

UNRELATED_MESSAGE = "同学，我是长理通知降噪 Bot 🤖，目前专职帮大家解析各类校园通知、比赛和讲座信息哦！请把你的群通知截图或长文本甩给我，我来帮你提炼重点~"


def render_card(card: NoticeCard, index: int | None = None) -> str:
    suffix = f" {index}" if index is not None else ""
    actions = "<br>".join(f"{position}. {action}" for position, action in enumerate(card.actions, 1))
    if card.links:
        actions += "<br>相关链接：" + "；".join(card.links)
    return "\n".join([
        f"📌 **【通知解析卡片{suffix}】**",
        f"- **📋 事件名称**：{card.event_name}",
        f"- **⏰ 截止时间**：{format_deadline(card.deadline)}",
        f"- **🎯 面向对象**：{card.audience}",
        f"- **📍 地点/平台**：{card.location}",
        f"- **💡 核心行动**：{actions}",
        "---",
        f"💡 **长理学姐贴心提示**：{card.tip}",
    ])


def render_markdown(result: ParseResult) -> str:
    if not result.relevant:
        return UNRELATED_MESSAGE
    sections = []
    if result.safety_warning:
        sections.append(f"🚨 **【安全提示】**：{result.safety_warning}")
    sections.extend(
        render_card(card, index if len(result.notices) > 1 else None)
        for index, card in enumerate(result.notices, 1)
    )
    return "\n\n---\n\n".join(sections)


def result_to_json(result: ParseResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
