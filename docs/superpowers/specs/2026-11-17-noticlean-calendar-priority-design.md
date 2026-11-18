# 通知日历下载与分类优先级设计文档

- 日期：2026-11-17
- 状态：已获用户确认
- 目标项目：长理通知降噪与智能解析助手

## 1. 目标

在现有 Streamlit 与 `noticlean` 架构上增加：

1. 使用 Pydantic 校验大模型返回的事件、时间、地点、分类和优先级。
2. 仅当大模型成功返回有效事件名、时间和地点时，显示对应通知的 ICS 日历下载按钮。
3. 使用 Python 标准库生成合法 ICS 文本，不引入日历库。
4. 在页面卡片和导出结果中展示固定分类与红黄绿优先级。

## 2. 范围与约束

- 保留现有本地解析、分钟倒计时、多地点、OCR 和失败回退行为。
- ICS 精确时间事件时长固定为 30 分钟；只有日期时生成全天事件。
- 本地规则单独解析成功时不显示 ICS 按钮。
- 大模型失败、字段缺失、时间无效或枚举非法时不显示 ICS 按钮。
- 新增核心依赖仅为 `pydantic>=2,<3`。
- 不在 ICS 中写入 API Key、完整原始通知或敏感配置。

## 3. 数据模型

现有 `NoticeCard` 增加：

- `category: str`，默认 `社团/其他`。
- `priority: str`，默认 `中-黄标（常规通知）`。
- `calendar_ready: bool`，默认 `False`，仅供运行时使用，不作为模型事实导出。

`category` 固定为：

- `教务通知`
- `院系/班级`
- `讲座/比赛`
- `社团/其他`

`priority` 固定为：

- `高-红标（涉及绩点/考试/截止日期在48小时内）`
- `中-黄标（常规通知）`
- `低-绿标（自愿参加/讲座等）`

JSON 导出增加分类和优先级；卡片源码中的 `source_text` 继续禁止导出。

## 4. Pydantic 与大模型流程

在 `noticlean/llm.py` 定义：

- `LLMNotice`：单条通知的返回模型。
- `LLMResponse`：包含 `notices: list[LLMNotice]` 的顶层模型。

`LLMNotice` 字段：

- `event_name: str`
- `event_time: datetime | None`
- `date_only: bool`
- `audience: str`
- `location: str`
- `actions: list[str]`
- `tip: str`
- `category: Literal[...]`
- `priority: Literal[...]`

System Prompt 要求：

1. 只输出 JSON，不输出 Markdown 或解释。
2. 通知数量和顺序与本地卡片一致。
3. 无法确认的文本字段返回空字符串，行动返回空数组，时间返回 `null`。
4. 精确时间使用 `YYYY-MM-DDTHH:mm:ss`；只有日期使用 `YYYY-MM-DD` 并设置 `date_only=true`。
5. 时间使用页面参考时间对应的本地日期，不返回时区偏移。
6. 分类和优先级只能使用固定枚举，禁止编造事实。

`enhance_result()` 增加可选 `reference` 参数，由页面传入当前参考时间。Pydantic 校验成功后：

- 非空文本字段补充或修正本地卡片。
- 分类和优先级写入卡片。
- 有效模型时间通过本地函数重新构造 `DeadlineInfo` 并计算倒计时。
- 截止不超过 48 小时或原文涉及绩点/考试时，本地代码强制提升为高优先级。
- 三项日历条件全部满足时设置 `calendar_ready=True`。

任何请求、JSON、Pydantic 或时间异常均返回原本地结果并保留警告，不产生日历按钮。

## 5. ICS 生成

新增 `noticlean/calendar_export.py`：

- `build_ics(card: NoticeCard) -> str`
- `calendar_filename(card: NoticeCard, index: int) -> str`

格式：

- `BEGIN:VCALENDAR`、`VERSION:2.0`、`PRODID`、`CALSCALE:GREGORIAN`、`METHOD:PUBLISH`。
- 每个通知生成一个 `VEVENT`。
- 使用确定性 UID 和 UTC `DTSTAMP`。
- 精确时间使用本地浮动 `DTSTART`，结束时间为开始后 30 分钟。
- 仅日期使用 `DTSTART;VALUE=DATE`，`DTEND` 为次日。
- 写入 `SUMMARY`、`LOCATION`、`DESCRIPTION`、`CATEGORIES` 和数值 `PRIORITY`。
- 使用 CRLF；转义反斜杠、逗号、分号和换行；按 UTF-8 字节安全折叠长行。
- 文件名移除 Windows 非法字符，无法得到名称时使用通知序号。

页面为每张 `calendar_ready=True` 的卡片生成独立下载按钮，数据使用 UTF-8 编码，MIME 为 `text/calendar; charset=utf-8`。

## 6. 分类与优先级渲染

本地解析使用关键词和截止时间生成默认分类与优先级；大模型返回后再按校验结果更新，并保留 48 小时高优先级约束。

`render.py` 增加白名单样式映射：

- 高优先级：红色背景、深红文字和左边框。
- 中优先级：黄色背景、深黄文字和左边框。
- 低优先级：绿色背景、深绿文字和左边框。

页面仅对固定枚举和 HTML 转义后的分类使用 `unsafe_allow_html=True`；事件正文继续使用普通 Markdown，避免模型 HTML 注入。Markdown 导出增加分类与优先级文本行。

## 7. 异常与边界

- 模型返回空事件名或空地点：保留本地文本字段，但不生成日历。
- 模型返回非法日期、时区时间或非法枚举：整体回退本地结果。
- 多通知：每张卡片独立判断，不因为一个卡片缺少时间而阻断其他卡片。
- 只有日期：全天事件，不把估算的 23:59 当成精确开始时间。
- 卡片已过期：仍可生成日历记录，但优先级保持高，不伪造未来倒计时。
- ICS 特殊字符和长中文：转义并按字节折叠，不能按字符数截断 UTF-8。

## 8. 验证与交付

验证：

1. Pydantic 接受合法返回并拒绝非法分类、优先级和日期。
2. LLM 成功且三项完整时 `calendar_ready=True`，缺项或失败时为 `False`。
3. 48 小时内截止和绩点/考试通知强制高优先级。
4. ICS 包含正确事件时间、地点、转义、CRLF 和折叠行。
5. Streamlit 仅为合格卡片提供下载按钮。
6. 现有倒计时和多地点行为保持正确。

交付包括源码、依赖声明、最终测试、README、设计/计划文档和更新后的项目 ZIP。当前目录不是 Git 仓库，不执行提交。
