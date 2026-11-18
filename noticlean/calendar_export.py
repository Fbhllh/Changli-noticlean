from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

from noticlean.models import NoticeCard, PRIORITY_OPTIONS


def _escape(value: object) -> str:
    text = str(value).replace("\\", "\\\\")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def _fold_line(line: str) -> str:
    chunks = []
    current = ""
    for char in line:
        if current and len((current + char).encode("utf-8")) > 74:
            chunks.append(current)
            current = char
        else:
            current += char
    chunks.append(current)
    return "\r\n ".join(chunks)


def calendar_filename(card: NoticeCard, index: int) -> str:
    name = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", card.event_name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name.strip(" _"):
        name = f"通知_{index}"
    return name[:60].rstrip(" .") + ".ics"


def build_ics(card: NoticeCard) -> str:
    start = card.deadline.value
    if not card.calendar_ready or not card.event_name.strip() or start is None or not card.location.strip():
        raise ValueError("事件名称、有效时间和 LLM 地点是生成日历的必要条件")
    identity = f"{card.event_name}|{start.isoformat()}|{card.location}"
    uid = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24] + "@noticlean.local"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if card.deadline.date_only:
        date_start = start.date()
        time_lines = [
            f"DTSTART;VALUE=DATE:{date_start.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(date_start + timedelta(days=1)).strftime('%Y%m%d')}",
        ]
        date_note = "原文仅提供日期，按全天事件记录。"
    else:
        time_lines = [
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{(start + timedelta(minutes=30)).strftime('%Y%m%dT%H%M%S')}",
        ]
        date_note = "按通知时间生成30分钟日历事件。"
    description = "；".join([
        f"分类：{card.category}",
        f"优先级：{card.priority}",
        f"核心行动：{'；'.join(card.actions)}",
        date_note,
    ])
    numeric_priority = {
        PRIORITY_OPTIONS[0]: "1",
        PRIORITY_OPTIONS[1]: "5",
        PRIORITY_OPTIONS[2]: "9",
    }.get(card.priority, "5")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ChangLi NotiClean//Campus Notice Calendar//ZH-CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:长理通知提醒",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{timestamp}",
        *time_lines,
        f"SUMMARY:{_escape(card.event_name)}",
        f"LOCATION:{_escape(card.location)}",
        f"DESCRIPTION:{_escape(description)}",
        f"CATEGORIES:{_escape(card.category)}",
        f"PRIORITY:{numeric_priority}",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold_line(line) for line in lines) + "\r\n"
