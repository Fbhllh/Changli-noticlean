# 通知日历下载与分类优先级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 为长理通知助手增加经 Pydantic 校验的分类/优先级，以及仅由成功 LLM 结果触发的 ICS 日历下载。

**Architecture:** 保留本地解析作为安全回退。`llm.py` 负责结构化校验和字段合并，`calendar_export.py` 独立生成 ICS，`render.py` 只处理白名单样式，`app.py` 根据运行时标记显示下载按钮。

**Tech Stack:** Python 3.10+、Streamlit、Pydantic 2、标准库 datetime/hashlib/re、pytest、Streamlit AppTest。

## Global Constraints

- 仅 LLM 返回有效事件名、时间和地点时允许日历下载。
- 精确时间事件为 30 分钟，仅日期事件为全天。
- 倒计时和 48 小时高优先级约束由本地代码计算。
- ICS 仅使用标准库，不引入日历库。
- 新增核心依赖仅为 `pydantic>=2,<3`。
- 不导出 `source_text`，不注入模型 HTML，不保存 API Key。
- 当前目录不是 Git 仓库；不初始化仓库，不执行提交。
- 单元测试由 `developer-test-agent` 根据用户原始请求独立生成和维护。

---

### Task 1: 恢复源码并扩展卡片模型

**Files:**
- Restore: `noticlean/`
- Modify: `noticlean/models.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `CATEGORY_OPTIONS`、`PRIORITY_OPTIONS`、`DEFAULT_CATEGORY`、`DEFAULT_PRIORITY`。
- Produces: `NoticeCard(..., category=DEFAULT_CATEGORY, priority=DEFAULT_PRIORITY, calendar_ready=False)`。

- [x] **Step 1: 从现有 ZIP 恢复源码**

Run: `unzip -o changli-noticlean.zip 'noticlean/*'`
Expected: 恢复现有倒计时、多地点和渲染代码，不覆盖其他新文档。

- [x] **Step 2: 添加固定枚举和运行时字段**

```python
CATEGORY_OPTIONS = ("教务通知", "院系/班级", "讲座/比赛", "社团/其他")
PRIORITY_OPTIONS = (
    "高-红标（涉及绩点/考试/截止日期在48小时内）",
    "中-黄标（常规通知）",
    "低-绿标（自愿参加/讲座等）",
)
```

将字段添加在 `source_text` 之后并设置默认值，保持已有位置参数构造兼容；`to_dict()` 增加分类和优先级，不导出 `calendar_ready`。

- [x] **Step 3: 声明 Pydantic**

```text
streamlit>=1.40,<2
pydantic>=2,<3
```

### Task 2: 本地时间构造与默认分类优先级

**Files:**
- Modify: `noticlean/dates.py`
- Modify: `noticlean/parser.py`

**Interfaces:**
- Produces: `make_deadline(value: datetime, reference: datetime, raw_text: str = "", date_only: bool = False) -> DeadlineInfo`。
- Produces: `resolve_priority(priority: str, deadline: DeadlineInfo, source_text: str, reference: datetime) -> str`。

- [x] **Step 1: 提供公开时间构造函数**

`make_deadline()` 创建 `DeadlineInfo`，对 `date_only` 统一设置为当天 23:59，并调用现有 `_apply_countdown()`；不得改变 `parse_deadline()` 的公开签名。

- [x] **Step 2: 本地分类**

根据原文关键词依次判断教务、讲座/比赛、院系/班级，最后为社团/其他。关键词判断只影响标签，不修改事实字段。

- [x] **Step 3: 本地和 LLM 共用优先级约束**

`resolve_priority()` 在原文涉及绩点/考试，或截止时间与参考时间之差不超过 48 小时时返回高优先级；其他情况返回传入的合法优先级，非法值回退中优先级。

- [x] **Step 4: 接入本地卡片**

本地 `_parse_notice()` 设置默认分类，并根据截止时间、参考时间和原文计算优先级；`calendar_ready` 保持 `False`。

### Task 3: Pydantic 返回结构与 LLM 合并

**Files:**
- Modify: `noticlean/llm.py`
- Modify: `app.py`

**Interfaces:**
- Produces: `LLMNotice`、`LLMResponse`。
- Consumes: `make_deadline()`、`resolve_priority()`。
- Produces: `enhance_result(result: ParseResult, config: LLMConfig, reference: datetime | None = None) -> ParseResult`。

- [x] **Step 1: 定义校验模型**

使用 `ConfigDict(extra="ignore", str_strip_whitespace=True)`。`event_time` 接受 ISO 本地 datetime 或 `YYYY-MM-DD`，空字符串转为 `None`，带时区值拒绝；分类和优先级使用 `Literal` 限定。

- [x] **Step 2: 优化 System Prompt 和用户提示**

提示词包含参考时间、期望 JSON 示例、全部固定枚举和缺失值规则。仅日期必须 `date_only=true`，不得输出 Markdown、解释或额外通知。

- [x] **Step 3: 校验后合并**

用 `LLMResponse.model_validate()` 替代字典字段直接读取。有效模型时间调用 `make_deadline()`，分类和优先级写入卡片，最后调用 `resolve_priority()`。只有模型事件名、时间、地点均有效时设置 `calendar_ready=True`。

- [x] **Step 4: 保留失败回退**

网络、JSON、Pydantic 和时间异常继续返回深拷贝的本地结果并追加密钥无关警告；页面调用改为 `enhance_result(result, config, reference)`。

### Task 4: ICS 标准库生成器

**Files:**
- Create: `noticlean/calendar_export.py`

**Interfaces:**
- Produces: `build_ics(card: NoticeCard) -> str`。
- Produces: `calendar_filename(card: NoticeCard, index: int) -> str`。

- [x] **Step 1: 实现文本转义和安全文件名**

转义反斜杠、换行、逗号和分号；文件名移除 `<>:"/\|?*`、控制字符和末尾点空格，无法得到名称时使用通知序号。

- [x] **Step 2: 实现事件时间**

精确时间写入本地浮动 `DTSTART` 和 30 分钟后的 `DTEND`；仅日期写入 `DTSTART;VALUE=DATE` 和次日 `DTEND;VALUE=DATE`。

- [x] **Step 3: 生成完整 VCALENDAR**

写入确定性 UID、UTC DTSTAMP、SUMMARY、LOCATION、DESCRIPTION、CATEGORIES 和 1/5/9 数值优先级。缺少必要条件时抛出 `ValueError`，页面在调用前通过 `calendar_ready` 避免该异常。

- [x] **Step 4: 处理 ICS 行格式**

所有行使用 CRLF，末尾保留 CRLF；按 UTF-8 字节安全折叠，续行以单个空格开始，不按字符截断中文。

### Task 5: 页面标签和条件下载按钮

**Files:**
- Modify: `noticlean/render.py`
- Modify: `app.py`

**Interfaces:**
- Produces: `render_priority_badge(card: NoticeCard) -> str`。
- Consumes: `build_ics()`、`calendar_filename()`。

- [x] **Step 1: 添加白名单样式和导出字段**

红黄绿样式只由固定优先级选择；分类经 `html.escape()` 后生成标签。`render_card()` 增加分类/优先级行，正文仍使用普通 Markdown。

- [x] **Step 2: 在卡片容器渲染标签**

`app.py` 在现有卡片容器内先调用 `render_priority_badge()`，仅该静态白名单 HTML 使用 `unsafe_allow_html=True`。

- [x] **Step 3: 添加逐卡片日历下载**

在结果下方遍历通知，仅对 `calendar_ready=True` 的卡片显示 `st.download_button`，数据为 `build_ics(card).encode("utf-8")`，文件名由 `calendar_filename()` 生成，每个按钮使用稳定且不同的 key。

### Task 6: 验证、文档和下载包

**Files:**
- Create: `tests/` 中由测试子代理生成的最终测试
- Modify: `README.md`
- Modify: `changli-noticlean.zip`

- [x] **Step 1: 生成并运行测试**

调用 `developer-test-agent`，原样传入用户请求。运行 `python -m pytest tests -v`；覆盖模型校验、成功/失败按钮条件、48 小时规则、ICS 全天/定时/转义/折叠和页面展示。

- [x] **Step 2: 执行回归与页面验证**

Run: `python -m compileall app.py noticlean tests`
Run: `streamlit run app.py --server.headless true`
Expected: 编译通过，健康接口正常，AppTest 验证本地结果无日历按钮，模拟成功 LLM 后出现下载按钮。

- [x] **Step 3: 更新 README 和 ZIP**

补充 Pydantic 依赖、日历生成条件、30 分钟/全天规则、分类和优先级说明。将最终源码、测试、文档和依赖写入 ZIP，并验证压缩包完整性。
