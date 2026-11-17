from __future__ import annotations

import re
from datetime import datetime, timedelta

from noticlean.models import DeadlineInfo

_TIME_PATTERN = r"(?:\s*(?P<period>凌晨|早上|上午|中午|下午|晚上))?\s*(?:(?P<hour>[01]?\d|2[0-3])\s*(?::|：|点|时)\s*(?P<minute>[0-5]?\d)?\s*分?)?"
_ABSOLUTE_DATE = re.compile(
    r"(?:(?P<year>20\d{2})\s*(?:年|[-/.])\s*)?"
    r"(?P<month>1[0-2]|0?[1-9])\s*(?:月|[-/.])\s*"
    r"(?P<day>3[01]|[12]\d|0?[1-9])(?:\s*[日号])?" + _TIME_PATTERN
)
_RELATIVE_DATE = re.compile(
    r"(?P<relative>大后天|后天|明天|今天|今日)" + _TIME_PATTERN
)
_WEEK_DATE = re.compile(
    r"(?:(?P<week>下周|下星期|本周|这周|本星期))?\s*(?:周|星期)"
    r"(?P<weekday>[一二三四五六日天])" + _TIME_PATTERN
)
_WEEKDAYS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_RELATIVE_DAYS = {"今天": 0, "今日": 0, "明天": 1, "后天": 2, "大后天": 3}
_DEADLINE_CONTEXT = re.compile(r"截止|截至|逾期|之前|以前|前完成|前提交|前报名|前发送|前上传|前填写")


def _adjusted_hour(hour: int, period: str | None) -> int:
    if period in {"下午", "晚上"} and hour < 12:
        return hour + 12
    if period == "中午" and 1 <= hour <= 5:
        return hour + 12
    if period == "凌晨" and hour == 12:
        return 0
    return hour


def _time_parts(match: re.Match[str]) -> tuple[int, int, bool]:
    hour_text = match.groupdict().get("hour")
    if hour_text is None:
        return 23, 59, True
    hour = _adjusted_hour(int(hour_text), match.groupdict().get("period"))
    minute = int(match.groupdict().get("minute") or 0)
    return hour, minute, False


def _safe_datetime(year: int, month: int, day: int, hour: int, minute: int) -> datetime | None:
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def _absolute_candidate(match: re.Match[str], reference: datetime) -> DeadlineInfo | None:
    parts = match.groupdict()
    hour, minute, date_only = _time_parts(match)
    year_inferred = not parts.get("year")
    value = _safe_datetime(
        int(parts["year"]) if parts.get("year") else reference.year,
        int(parts["month"]),
        int(parts["day"]),
        hour,
        minute,
    )
    if value is None:
        return None
    return DeadlineInfo(match.group(0).strip(), value, date_only, year_inferred)


def _relative_candidate(match: re.Match[str], reference: datetime) -> DeadlineInfo:
    hour, minute, date_only = _time_parts(match)
    target = reference + timedelta(days=_RELATIVE_DAYS[match.group("relative")])
    value = datetime(target.year, target.month, target.day, hour, minute)
    return DeadlineInfo(match.group(0).strip(), value, date_only, True)


def _week_candidate(match: re.Match[str], reference: datetime) -> DeadlineInfo:
    hour, minute, date_only = _time_parts(match)
    target_weekday = _WEEKDAYS[match.group("weekday")]
    week = match.group("week")
    if week in {"下周", "下星期"}:
        days = 7 - reference.weekday() + target_weekday
    elif week in {"本周", "这周", "本星期"}:
        days = target_weekday - reference.weekday()
    else:
        days = (target_weekday - reference.weekday()) % 7
    target = reference + timedelta(days=days)
    value = datetime(target.year, target.month, target.day, hour, minute)
    return DeadlineInfo(match.group(0).strip(), value, date_only, True)


def _candidates(text: str, reference: datetime) -> list[tuple[int, int, DeadlineInfo]]:
    candidates: list[tuple[int, int, DeadlineInfo]] = []
    for match in _ABSOLUTE_DATE.finditer(text):
        candidate = _absolute_candidate(match, reference)
        if candidate:
            candidates.append((match.start(), match.end(), candidate))
    for match in _RELATIVE_DATE.finditer(text):
        candidates.append((match.start(), match.end(), _relative_candidate(match, reference)))
    for match in _WEEK_DATE.finditer(text):
        candidates.append((match.start(), match.end(), _week_candidate(match, reference)))
    candidates.sort(key=lambda item: item[0])
    return candidates


def _score_candidate(text: str, start: int, end: int) -> int:
    before = text[max(0, start - 24):start]
    after = text[end:min(len(text), end + 24)]
    context = before + after
    score = 0
    if _DEADLINE_CONTEXT.search(context):
        score += 4
    if re.search(r"截止|截至|至|到|—|–|~|～", before[-10:]):
        score += 3
    if re.search(r"前\s*$", after[:4]):
        score += 2
    if re.search(r"开始|开幕|举行时间|活动时间", before[-12:]):
        score -= 2
    return score


def _apply_countdown(deadline: DeadlineInfo, reference: datetime) -> None:
    if deadline.value is None:
        return
    remaining = (deadline.value - reference).total_seconds()
    if remaining <= 0:
        deadline.urgency = "🔴 已截止"
        deadline.countdown = "已截止，请确认是否仍可补交或补报名"
        return
    if remaining < 60:
        deadline.countdown = "距截止不足 1 分钟"
    elif remaining < 3600:
        minutes = int(remaining // 60)
        decimal_hours = f"{minutes / 60:.2f}".rstrip("0").rstrip(".")
        deadline.countdown = f"距截止还有 {minutes} 分钟（约 {decimal_hours} 小时）"
    else:
        days = int(remaining // 86400)
        hours = int((remaining % 86400) // 3600)
        minutes = int((remaining % 3600) // 60)
        parts = []
        if days:
            parts.append(f"{days} 天")
        if hours:
            parts.append(f"{hours} 小时")
        if minutes:
            parts.append(f"{minutes} 分钟")
        deadline.countdown = "距截止还有 " + " ".join(parts)
    if remaining <= 86400:
        deadline.urgency = "🚨 时间紧急"
    elif remaining <= 259200:
        deadline.urgency = "⚠️ 请抓紧"
    else:
        deadline.urgency = "⏳ 时间充裕"


def parse_deadline(text: str, reference: datetime) -> DeadlineInfo:
    candidates = _candidates(text, reference)
    if not candidates:
        return DeadlineInfo()
    start, end, deadline = max(
        candidates,
        key=lambda item: (_score_candidate(text, item[0], item[1]), -item[0]),
    )
    _apply_countdown(deadline, reference)
    return deadline


def format_deadline(deadline: DeadlineInfo) -> str:
    if deadline.value is None:
        return "⚠️ 未在通知中找到明确截止时间，建议向发通知的老师/班长二次确认！"
    formatted = deadline.value.strftime("%Y年%m月%d日 %H:%M")
    summary = f"{formatted} ｜ {deadline.urgency}：{deadline.countdown}"
    notes = []
    if deadline.date_only:
        notes.append("具体时刻未注明，倒计时按当日 23:59 估算")
    if deadline.year_inferred:
        notes.append("年份按参考时间推定")
    if notes:
        summary += "（" + "；".join(notes) + "）"
    return summary
