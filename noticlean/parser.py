from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from urllib.parse import urlsplit

from noticlean.dates import parse_deadline
from noticlean.models import NoticeCard, ParseResult

SAFETY_WARNING = "检测到该通知可能涉及非官方收费或敏感链接，请务必通过学校官网或官方渠道二次核实，谨防受骗！"
MISSING_AUDIENCE = "未在通知中找到明确面向对象，建议向发通知的老师/班长二次确认！"
MISSING_LOCATION = "未在通知中找到明确地点或平台，建议向发通知的老师/班长二次确认！"
MISSING_ACTION = "未找到明确行动要求，请查看原通知并向发通知的老师/班长确认下一步操作。"
MISSING_EVENT = "未明确事件名称（请查看原通知）"

_NOISE_LINE = re.compile(
    r"^(?:(?:收到|谢谢(?:大家|老师|学长|学姐)?|感谢(?:大家|老师)?|顶+|d+|\+1)[\W_]*)+$",
    re.IGNORECASE,
)
_SEPARATOR = re.compile(r"^\s*(?:-{3,}|—{3,}|={3,})\s*$")
_TITLE_WORDS = re.compile(r"通知|报名|比赛|竞赛|讲座|体测|补测|答疑|考试|选课|答辩|招聘|征集")
_ACTION_WORDS = re.compile(r"请|报名|提交|填写|加入|扫码|点击|登录|组队|携带|准备|材料|群号|链接|务必|需要|应于|逾期|上传|发送")
_CAMPUS_WORDS = re.compile(r"长理|长沙理工|学校|学院|大学|校区|云塘|金盆岭|同学|学生|老师|辅导员|教务|宿舍|课程|专业|年级|班级|讲座|比赛|竞赛|体测|实验|奖学金|图书馆|学工|考试|选课|学分")
_NOTICE_WORDS = re.compile(r"通知|报名|截止|提交|参加|集合|填写|讲座|比赛|考试|补测|答疑|材料|群号|选课|答辩")
_URL = re.compile(r"https?://[^\s<>\[\]【】\"'，。；！、]+", re.IGNORECASE)
_SHORT_HOSTS = {"t.cn", "url.cn", "dwz.cn", "bit.ly", "tinyurl.com", "suo.im", "shorturl.at"}


def _unique(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        cleaned = item.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def extract_links(text: str) -> list[str]:
    return _unique([match.group(0).rstrip(".,;:!?)）]") for match in _URL.finditer(text)])


def _is_noise_line(line: str) -> bool:
    compact = re.sub(r"\s+", "", line)
    if not compact:
        return True
    if _SEPARATOR.fullmatch(line):
        return False
    if _NOISE_LINE.fullmatch(compact):
        return True
    if re.fullmatch(r"(?:\[(?:表情|图片|动画表情|视频|文件)\]|【(?:表情|图片)】)+", compact):
        return True
    return not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", compact)


def clean_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", normalized)
    lines = []
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        line = re.sub(r"^(?:\[[^\]]{1,30}\]\s*)?(?:转发(?:聊天记录)?|聊天记录)[:：]?\s*", "", line)
        if _is_noise_line(line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def is_campus_notice(text: str) -> bool:
    if not text.strip():
        return False
    campus_hits = len(set(_CAMPUS_WORDS.findall(text)))
    notice_hits = len(set(_NOTICE_WORDS.findall(text)))
    if campus_hits and notice_hits:
        return True
    return notice_hits >= 3 and bool(re.search(r"时间|地点|对象|截止|链接", text))


def _suspicious_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if host in _SHORT_HOSTS:
            return True
        if parsed.scheme == "http" and host and not host.endswith(".edu.cn"):
            return True
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            return False
    except ValueError:
        return True
    return False


def detect_safety_risk(text: str) -> str | None:
    payment = re.search(r"转账|押金|保证金|银行卡|验证码|扫码付款|缴费|付费|收费|个人账户|红包返利|刷单|兼职佣金", text)
    credential = re.search(r"身份证(?:号|号码)|密码|短信验证码|屏幕共享|下载.{0,8}(?:远程|控制)", text)
    if payment or credential or any(_suspicious_url(url) for url in extract_links(text)):
        return SAFETY_WARNING
    return None


def _heading_indices(lines: list[str]) -> list[int]:
    indices = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        numbered = re.match(r"^(?:\d{1,2}|[一二三四五六七八九十]+)[、.．]\s*", stripped)
        bracketed = re.match(r"^【[^】]{1,50}】", stripped)
        if not numbered and not bracketed:
            continue
        if not _TITLE_WORDS.search(stripped):
            continue
        if re.match(r"^(?:\d{1,2}|[一二三四五六七八九十]+)[、.．]\s*(?:请|点击|填写|提交|加入|登录|携带)", stripped):
            continue
        if "http" in stripped.lower() or len(stripped) > 60:
            continue
        indices.append(index)
    return indices


def split_notices(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    lines = stripped.splitlines()
    if any(_SEPARATOR.fullmatch(line) for line in lines):
        chunks = []
        current = []
        for line in lines:
            if _SEPARATOR.fullmatch(line):
                if current:
                    chunks.append("\n".join(current).strip())
                    current = []
            else:
                current.append(line)
        if current:
            chunks.append("\n".join(current).strip())
        return [chunk for chunk in chunks if chunk]
    indices = _heading_indices(lines)
    if len(indices) < 2:
        return [stripped]
    chunks = []
    for position, start in enumerate(indices):
        end = indices[position + 1] if position + 1 < len(indices) else len(lines)
        segment = lines[start:end]
        if position == 0 and start:
            segment = lines[:start] + segment
        chunk = "\n".join(segment).strip()
        if chunk:
            chunks.append(chunk)
    return chunks or [stripped]


_EVENT_TERM = re.compile(
    r"大赛|比赛|竞赛|讲座|活动|会议|考试|体测|补测|答疑|答辩|招聘|征集|选拔|培训|展览|演出|沙龙|论坛|晚会|课程|实践|赛"
)
_GENERIC_EVENT_HEADING = re.compile(
    r"^(?:【)?(?:重要|紧急|校园|群)?通知(?:】)?[!！。]?$"
)
_EVENT_IN_BODY = re.compile(
    r"(?:举办|开展|举行|组织)\s*"
    r"([^，。；;：:\n]{2,48}?(?:大赛|比赛|竞赛|讲座|活动|会议|考试|体测|补测|答疑|答辩|招聘会|招聘|征集|选拔|培训|展览|演出|沙龙|论坛|晚会|赛))"
    r"(?=$|[，,。；;])"
)


def _short_title(value: str) -> str:
    title = re.sub(r"^[@＠]所有人\s*", "", value.strip())
    title = re.sub(r"^(?:各位|亲爱的)(?:老师|同学|同学们|大家)[，,:：\s]*", "", title)
    title = re.split(r"[。；;]", title)[0].strip(" ，,：:")
    return title[:48].strip() if title else ""


def _extract_event(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        explicit = re.search(r"(?:通知主题|活动主题|活动名称|赛事名称|主题|事项)[:：]\s*([^\n]{2,60})", line)
        if explicit:
            return _short_title(explicit.group(1))
    for line in lines:
        about = re.search(r"关于(?:举办|开展|组织|进行)?([^，。；\n]{2,48}?)(?:的)?(?:通知|安排)(?:$|[，。；])", line)
        if about:
            return _short_title(about.group(1))
    for line in lines:
        bracketed = re.match(r"^【([^】]{2,50})】", line)
        if bracketed and not re.fullmatch(r"(?:重要|紧急|校园|群)?通知", bracketed.group(1)):
            return _short_title(bracketed.group(1))
    for line in lines:
        body_event = _EVENT_IN_BODY.search(line)
        if body_event:
            return _short_title(body_event.group(1))
    for line in lines:
        if _GENERIC_EVENT_HEADING.fullmatch(line):
            continue
        if re.fullmatch(r"(?:@所有人|各位同学|同学们|大家好|请查收)[:：，,!！。\s]*", line):
            continue
        if re.match(r"^(?:截止时间|截止日期|时间|地点|活动地点|面向对象|参与对象|活动对象|报名对象|适用对象|对象|链接|平台)\s*[:：]", line):
            continue
        if "http" in line.lower():
            continue
        title = _short_title(line)
        if not title or not _EVENT_TERM.search(title):
            continue
        if re.match(r"^(?:请|务必|应于|逾期|点击|填写|提交|加入|登录|携带|准备|上传|发送)", title):
            continue
        return title
    return MISSING_EVENT


def _extract_audience(text: str) -> str:
    explicit = re.search(r"(?:面向对象|参与对象|活动对象|报名对象|适用对象|对象)[:：]\s*([^\n。；]{2,80})", text)
    if explicit:
        return explicit.group(1).strip(" ，,")
    people = r"(?:学生|同学|本科生|研究生|应届毕业生|毕业生)"
    patterns = [
        r"(?:长理|长沙理工)?全体(?:在校)?" + people,
        r"全校(?:全体)?(?:在校)?" + people,
        r"[\u4e00-\u9fff]{2,14}学院(?:20\d{2}级|大[一二三四五六]|[一二三四五六]年级)?(?:的)?(?:全体)?(?:在校)?" + people,
        r"[\u4e00-\u9fff]{2,14}(?:、[\u4e00-\u9fff]{1,12})*(?:等[\u4e00-\u9fff]{0,8})?专业(?:的)?(?:全体)?(?:在校)?" + people,
        r"(?:20\d{2}级|大[一二三四五六]|[一二三四五六]年级)[^，。；\n]{0,24}?" + people,
        r"(?:本科生|研究生|应届毕业生|毕业生|团支书|班长|学习委员)",
    ]
    spans = []
    for pattern in patterns:
        spans.extend((match.start(), match.end(), match.group(0)) for match in re.finditer(pattern, text))
    spans = list(dict.fromkeys(spans))
    kept = []
    for start, end, value in spans:
        contained = any(
            (other_start, other_end) != (start, end)
            and other_start <= start
            and end <= other_end
            and other_end - other_start > end - start
            for other_start, other_end, _ in spans
        )
        if not contained:
            kept.append((start, end, value))
    kept.sort(key=lambda item: (item[0], item[1]))
    matches = _unique([value for _, _, value in kept])
    return "；".join(matches) if matches else MISSING_AUDIENCE


def _clean_location_candidate(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"^(?:(?:活动|集合|会议|提交|报名)?地点|场所)(?:在|为|是)", "", cleaned)
    cleaned = re.sub(r"^(?:请)?(?:大家)?(?:到|去|在)", "", cleaned)
    return cleaned.strip(" ，,：:")


def _extract_location(text: str, links: list[str]) -> str:
    explicit = re.search(r"(?:活动地点|集合地点|提交地点|报名地点|会议地点|线上平台|平台|地点)[:：]\s*([^\n。；]{2,100})", text)
    if explicit:
        return explicit.group(1).strip(" ，,")
    suffix = r"(?:[一二三四五六七八九十\d]+(?:楼|层)|[A-Za-z]?\d{1,5}[A-Za-z]?)?"
    campus_pattern = re.compile(
        r"(?:云塘|金盆岭|金村)(?:校区)?"
        r"(?:[A-Za-z]?\d+[A-Za-z]?摊位|"
        r"[A-Za-z0-9]{1,8}教(?:学楼)?[A-Za-z0-9-]{0,8}|"
        r"[\u4e00-\u9fff]{0,12}(?:教学楼|实验楼|图书馆|体育馆|报告厅|会议室|教室|田径场|篮球场|足球场|操场|楼|馆|中心)" + suffix + r")"
    )
    campuses = _unique([
        _clean_location_candidate(match.group(0))
        for match in campus_pattern.finditer(text)
    ])
    if campuses:
        return "；".join(campuses)
    rooms = _unique([
        _clean_location_candidate(match.group(0))
        for match in re.finditer(
            r"[\u4e00-\u9fff]{0,12}(?:教学楼|实验楼|图书馆|体育馆|报告厅|会议室|教室)[\u4e00-\u9fffA-Za-z0-9_-]{0,16}",
            text,
        )
    ])
    if rooms:
        return "；".join(rooms)
    campus_names = _unique([
        match.group(0)
        for match in re.finditer(r"(?:云塘|金盆岭|金村)(?:校区)?", text)
    ])
    if campus_names:
        return "；".join(campus_names)
    platforms = _unique([
        match.group(0)
        for match in re.finditer(
            r"腾讯会议(?:号)?\s*[:：]?\s*\d[\d -]{4,}|学习通|雨课堂|超星|中国大学MOOC|华为官方赛事平台|线上平台",
            text,
            re.IGNORECASE,
        )
    ])
    if platforms:
        return "；".join(platforms)
    if links and re.search(r"线上|平台|官网|报名链接|提交链接", text):
        return links[0]
    return MISSING_LOCATION


def _extract_actions(text: str, links: list[str]) -> list[str]:
    actions = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or len(line) < 4:
            continue
        sentences = re.split(r"(?<=[。；;])", line)
        for sentence in sentences:
            item = sentence.strip(" \t。；;")
            if len(item) < 4 or not _ACTION_WORDS.search(item):
                continue
            if re.fullmatch(r"(?:报名|比赛|竞赛|讲座|体测|补测|答疑|考试)?通知", item):
                continue
            actions.append(item)
    actions = _unique(actions)
    if not actions and links:
        actions.append("查看通知中的链接并核对下一步要求")
    return actions[:5] if actions else [MISSING_ACTION]


def _build_tip(text: str, card: NoticeCard, has_risk: bool) -> str:
    if has_risk:
        return "涉及费用或敏感信息时先核实官方来源，不要急着转账或提交个人凭证。"
    if card.deadline.value is None:
        return "截止时间未明确，先向老师或班长确认，别只等群里的后续接龙。"
    if card.deadline.urgency == "🔴 已截止":
        return "先确认是否有补交或补报名通道，再以官方回复为准。"
    if re.search(r"材料|附件|文件|命名|格式", text):
        return "提交前核对材料格式、命名和文件大小，并保留提交成功凭证。"
    if card.links or re.search(r"线上|平台|官网", text):
        return "提前检查平台账号与权限，截止前预留提交时间，并保存成功截图。"
    return "建议将截止时间加入日历，并以学院或老师的最新通知为准。"


def _parse_notice(text: str, reference: datetime, has_risk: bool) -> NoticeCard:
    links = extract_links(text)
    card = NoticeCard(
        event_name=_extract_event(text),
        deadline=parse_deadline(text, reference),
        audience=_extract_audience(text),
        location=_extract_location(text, links),
        actions=_extract_actions(text, links),
        links=links,
        tip="",
        source_text=text,
    )
    card.tip = _build_tip(text, card, has_risk)
    return card


def parse_text(text: str, reference: datetime) -> ParseResult:
    cleaned = clean_text(text)
    if not cleaned:
        return ParseResult(False, [], "")
    relevant = is_campus_notice(cleaned)
    safety_warning = detect_safety_risk(cleaned)
    if not relevant:
        return ParseResult(False, [], cleaned, safety_warning)
    chunks = split_notices(cleaned)
    notices = [_parse_notice(chunk, reference, safety_warning is not None) for chunk in chunks]
    return ParseResult(True, notices, cleaned, safety_warning)
