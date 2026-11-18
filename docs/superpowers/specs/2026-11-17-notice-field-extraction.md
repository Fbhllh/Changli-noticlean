# 通知关键字段提取改进 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 改进事件名称、地点/平台和面向对象的本地提取，使结果完整、有原文证据，并在证据不足时保留待确认提示。

**Architecture:** 保持 `parse_text()` 和 `NoticeCard` 接口不变，仅在 `noticlean/parser.py` 内调整三个字段的候选生成、清理和选择逻辑。每个字段先通过公共入口增加失败测试，再实施最小规则修改，最后运行完整回归和编译检查。

**Tech Stack:** Python 3.10+、标准库 `re`、pytest。

## Global Constraints

- 字段值必须来自当前通知原文，不根据常识生成或补全。
- 无可靠候选时继续返回现有 `MISSING_EVENT`、`MISSING_LOCATION`、`MISSING_AUDIENCE`。
- 不引入新运行时依赖，不修改页面、数据模型、导出格式、日期、链接、安全警告、多通知拆分、行动提取或 LLM 合并逻辑。
- 显式标签保持最高优先级；非显式候选必须具有对应字段的文本证据。
- 当前项目没有 Git 元数据，不执行 `git add` 或 `git commit`，以每个任务的测试结果作为检查点。

## File Structure

- Modify: `noticlean/parser.py` — 三个字段的本地证据驱动提取。
- Create: `tests/conftest.py` — 固定参考时间及公共入口解析夹具。
- Create: `tests/test_event_extraction.py` — 事件名称优先级、正文提取和无证据回归。
- Create: `tests/test_location_extraction.py` — 详细地点、地点边界、平台及无证据回归。
- Create: `tests/test_audience_extraction.py` — 完整对象范围、包含关系去重及无证据回归。

---

### Task 1: 事件名称正文证据提取

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_event_extraction.py`
- Modify: `noticlean/parser.py:165-187`

**Interfaces:**
- Consumes: `parse_text(text: str, reference: datetime) -> ParseResult`。
- Produces: 改进后的 `_extract_event(text: str) -> str`，签名不变；测试夹具 `parse_notice` 返回唯一的 `NoticeCard`。

- [ ] **Step 1: 编写公共解析夹具和事件名称失败测试**

创建 `tests/conftest.py`：

```python
from datetime import datetime

import pytest

from noticlean.parser import parse_text


@pytest.fixture
def parse_notice():
    def parse(text: str):
        result = parse_text(text, datetime(2026, 11, 17, 12, 0))
        assert result.relevant is True
        assert len(result.notices) == 1
        return result.notices[0]

    return parse
```

创建 `tests/test_event_extraction.py`：

```python
import pytest

from noticlean.parser import MISSING_EVENT


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("通知主题：就业指导讲座\n请全体学生参加。", "就业指导讲座"),
        ("关于举办简历指导讲座的通知\n请全体学生参加。", "简历指导讲座"),
        ("【电子设计竞赛】\n请全体学生参加。", "电子设计竞赛"),
        ("【通知】\n11月20日将举办青春杯辩论赛，请全体同学参加。", "青春杯辩论赛"),
        ("就业指导讲座\n请全体学生参加。", "就业指导讲座"),
    ],
)
def test_extract_event_from_supported_evidence(parse_notice, text, expected):
    assert parse_notice(text).event_name == expected


def test_generic_heading_and_action_do_not_become_event(parse_notice):
    card = parse_notice("通知\n请在学校提交材料。")
    assert card.event_name == MISSING_EVENT
```

- [ ] **Step 2: 运行测试并确认新增正文场景失败**

Run: `python -m pytest tests/test_event_extraction.py -v`

Expected: 泛化标题正文场景当前得到`【通知】`，无证据场景当前得到`请在学校提交材料`，相关断言失败；既有显式主题和标题场景应通过。

- [ ] **Step 3: 实现事件候选优先级和首行边界校验**

在 `noticlean/parser.py` 的 `_short_title()` 前增加：

```python
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
```

将 `_extract_event()` 替换为：

```python
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
```

- [ ] **Step 4: 运行事件名称测试并确认通过**

Run: `python -m pytest tests/test_event_extraction.py -v`

Expected: 6 个参数化/独立用例全部通过，事件名均来自原文，泛化标题和行动句不再作为事件名。

---

### Task 2: 地点完整候选与边界提取

**Files:**
- Create: `tests/test_location_extraction.py`
- Modify: `noticlean/parser.py:207-240`

**Interfaces:**
- Consumes: Task 1 的 `parse_notice` 夹具及现有 `extract_links()` 返回的链接列表。
- Produces: 改进后的 `_extract_location(text: str, links: list[str]) -> str`，签名不变。

- [ ] **Step 1: 编写地点和平台失败测试**

创建 `tests/test_location_extraction.py`：

```python
import pytest

from noticlean.parser import MISSING_LOCATION


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("活动地点：云塘校区图书馆报告厅\n请全体学生参加。", "云塘校区图书馆报告厅"),
        ("请到云塘校区体育馆二楼集合，请全体学生参加。", "云塘校区体育馆二楼"),
        ("请到云塘校区12教301集合，请全体学生参加。", "云塘校区12教301"),
        ("云塘校区体育馆2层，请全体学生参加。", "云塘校区体育馆2层"),
        ("活动地点在图书馆报告厅，请全体学生参加。", "图书馆报告厅"),
        ("腾讯会议号：123-456-789\n请全体学生参加线上讲座。", "腾讯会议号：123-456-789"),
    ],
)
def test_extract_complete_location(parse_notice, text, expected):
    assert parse_notice(text).location == expected


def test_missing_location_does_not_use_generic_school_word(parse_notice):
    card = parse_notice("通知\n请在学校提交材料。")
    assert card.location == MISSING_LOCATION
```

- [ ] **Step 2: 运行测试并确认新增地点场景失败**

Run: `python -m pytest tests/test_location_extraction.py -v`

Expected: `12教301`被截成校区、`2层`被截成裸数字、引导词混入及带冒号会议号无法识别等断言失败。

- [ ] **Step 3: 实现详细校区、通用场所和平台候选**

在 `_extract_location()` 前增加：

```python
def _clean_location_candidate(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"^(?:(?:活动|集合|会议|提交|报名)?地点|场所)(?:在|为|是)", "", cleaned)
    cleaned = re.sub(r"^(?:请)?(?:大家)?(?:到|去|在)", "", cleaned)
    return cleaned.strip(" ，,：:")
```

将 `_extract_location()` 替换为：

```python
def _extract_location(text: str, links: list[str]) -> str:
    explicit = re.search(r"(?:活动地点|集合地点|提交地点|报名地点|会议地点|线上平台|平台|地点)[:：]\s*([^\n。；]{2,100})", text)
    if explicit:
        return explicit.group(1).strip(" ，,")
    suffix = r"(?:[A-Za-z]?\d{1,5}[A-Za-z]?|[一二三四五六七八九十\d]+(?:楼|层))?"
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
```

- [ ] **Step 4: 运行地点测试并确认通过**

Run: `python -m pytest tests/test_location_extraction.py -v`

Expected: 7 个参数化/独立用例全部通过；详细地点优先于校区兜底，平台号码和标点完整保留。

---

### Task 3: 面向对象完整范围与包含关系去重

**Files:**
- Create: `tests/test_audience_extraction.py`
- Modify: `noticlean/parser.py:190-204`

**Interfaces:**
- Consumes: Task 1 的 `parse_notice` 夹具及现有 `_unique(items: list[str]) -> list[str]`。
- Produces: 改进后的 `_extract_audience(text: str) -> str`，签名不变。

- [ ] **Step 1: 编写面向对象失败测试**

创建 `tests/test_audience_extraction.py`：

```python
import pytest

from noticlean.parser import MISSING_AUDIENCE


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("面向对象：计算机学院2023级本科生\n请全体学生参加。", "计算机学院2023级本科生"),
        ("全体学生请按时提交材料。", "全体学生"),
        ("2023级学生请按时提交材料。", "2023级学生"),
        ("选课通知\n全校本科生须完成选课。", "全校本科生"),
        ("计算机学院2023级本科生需参加。", "计算机学院2023级本科生"),
        ("计算机、电气等工科专业全体在校学生均可报名。", "计算机、电气等工科专业全体在校学生"),
    ],
)
def test_extract_complete_audience(parse_notice, text, expected):
    assert parse_notice(text).audience == expected


def test_missing_audience_does_not_infer_from_action(parse_notice):
    card = parse_notice("通知\n请在学校提交材料。")
    assert card.audience == MISSING_AUDIENCE
```

- [ ] **Step 2: 运行测试并确认新增对象场景失败**

Run: `python -m pytest tests/test_audience_extraction.py -v`

Expected: `全校本科生`丢失全校范围，学院加年级产生重复宽泛项，专业枚举只保留后半段等断言失败。

- [ ] **Step 3: 实现组合范围候选并按原文区间去重**

将 `_extract_audience()` 替换为：

```python
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
```

- [ ] **Step 4: 运行面向对象测试并确认通过**

Run: `python -m pytest tests/test_audience_extraction.py -v`

Expected: 7 个参数化/独立用例全部通过；完整范围保留，被包含的宽泛候选不再重复输出。

---

### Task 4: 全量回归与交付检查

**Files:**
- Test: `tests/test_event_extraction.py`
- Test: `tests/test_location_extraction.py`
- Test: `tests/test_audience_extraction.py`
- Verify: `noticlean/parser.py`

**Interfaces:**
- Consumes: 前三个任务的全部实现和测试。
- Produces: 可交付的本地解析改进及实际验证结果。

- [ ] **Step 1: 运行全部自动化测试**

Run: `python -m pytest tests -v`

Expected: 所有测试通过，无公共入口相关性断言失败或字段回归。

- [ ] **Step 2: 运行语法编译检查**

Run: `python -m compileall app.py noticlean`

Expected: 命令退出码为 0，无语法错误。

- [ ] **Step 3: 检查变更范围和交付文件**

确认产品代码变更仅限 `noticlean/parser.py`，新增测试仅限 `tests/`，设计/计划文档位于 `docs/superpowers/`。不声明 `__pycache__`、`.pyc`、`.pytest_cache` 或覆盖率产物为交付文件。

Expected: 页面、模型和导出代码未修改；交付说明列出三项字段改进、测试数量和实际命令结果。
