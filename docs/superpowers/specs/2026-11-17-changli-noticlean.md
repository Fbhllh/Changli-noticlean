# 长理通知降噪与智能解析助手 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个默认离线可用、支持可选 OCR 与大模型增强的长理校园通知 Streamlit 解析应用。

**Architecture:** Streamlit 页面与解析核心分离。`parser.py` 负责文本流水线，`dates.py` 负责确定性时间计算，`ocr.py` 和 `llm.py` 作为可失败的适配器，任何可选能力异常都回退到本地结果。

**Tech Stack:** Python 3.10+、Streamlit 1.40+、标准库 `dataclasses/datetime/re/json/urllib`、可选 Pillow/pytesseract、pytest。

## Global Constraints

- 核心运行不依赖 OCR、模型 SDK、API Key 或网络。
- 所有用户界面和输出使用简体中文。
- 不持久化通知正文，不记录 API Key，不在仓库中硬编码接口地址或密钥。
- 字段无法可靠识别时明确提示待确认，不编造信息。
- 倒计时和安全风险始终由本地代码计算。
- 当前目录不是 Git 仓库；不初始化仓库，不执行 Git 提交。
- 单元测试由 `developer-test-agent` 根据用户原始请求独立生成和维护；实现代码不依赖测试替身。

---

### Task 1: 项目骨架与结构化模型

**Files:**
- Create: `requirements.txt`
- Create: `requirements-ocr.txt`
- Create: `requirements-dev.txt`
- Create: `noticlean/__init__.py`
- Create: `noticlean/models.py`
- Test: `tests/`

**Interfaces:**
- Produces: `DeadlineInfo`、`NoticeCard`、`ParseResult` 数据类及 `to_dict()`。
- Produces: `ParseResult(relevant, notices, cleaned_text, safety_warning=None, warnings=[])`。

- [ ] **Step 1: 声明核心、可选和开发依赖**

```text
# requirements.txt
streamlit>=1.40,<2

# requirements-ocr.txt
Pillow>=10,<13
pytesseract>=0.3.10,<1

# requirements-dev.txt
pytest>=8,<10
```

- [ ] **Step 2: 建立可序列化模型**

```python
@dataclass
class DeadlineInfo:
    raw_text: str = ""
    value: datetime | None = None
    date_only: bool = False
    year_inferred: bool = False
    countdown: str = ""
    urgency: str = ""

@dataclass
class NoticeCard:
    event_name: str
    deadline: DeadlineInfo
    audience: str
    location: str
    actions: list[str]
    links: list[str]
    tip: str
    source_text: str

@dataclass
class ParseResult:
    relevant: bool
    notices: list[NoticeCard]
    cleaned_text: str
    safety_warning: str | None = None
    warnings: list[str] = field(default_factory=list)
```

- [ ] **Step 3: 安装依赖并检查导入**

Run: `python -m pip install -r requirements.txt -r requirements-dev.txt`
Run: `python -c "from noticlean.models import ParseResult; print(ParseResult(True, [], ''))"`
Expected: 中文环境无额外配置即可导入，结构字段完整。

### Task 2: 中文截止时间与倒计时

**Files:**
- Create: `noticlean/dates.py`
- Test: 由 `developer-test-agent` 创建对应测试文件。

**Interfaces:**
- Consumes: `DeadlineInfo`。
- Produces: `parse_deadline(text: str, reference: datetime) -> DeadlineInfo`。
- Produces: `format_deadline(deadline: DeadlineInfo) -> str`。

- [ ] **Step 1: 实现绝对日期和中文日期候选提取**

使用命名分组正则统一支持 `YYYY年M月D日`、`YYYY-MM-DD`、无年份日期、`HH:mm`、`下午/晚上` 时段。候选必须构造为合法 `datetime`，非法日期跳过。

```python
def _build_deadline(match: re.Match[str], reference: datetime) -> DeadlineInfo | None:
    parts = match.groupdict()
    year = int(parts["year"]) if parts.get("year") else reference.year
    # 读取月、日、时、分；date_only 时设为 23:59 并保留估算标记。
```

- [ ] **Step 2: 实现相对日和星期表达**

支持 `今天、明天、后天、大后天`、`本周/这周/下周 + 星期/周`。星期以参考时间所在周一为起点，下周增加七天；无年份使用参考年份并设置 `year_inferred=True`。

- [ ] **Step 3: 优先选择截止语境中的时间**

先扫描 `截止、截至、之前、前完成、前提交、逾期` 附近候选；若没有候选，再扫描全文。没有候选时返回 `value=None` 的 `DeadlineInfo`，不得默认当前时间。

- [ ] **Step 4: 计算展示文本和紧急程度**

时间差小于等于零为已截止；其余按完整天和剩余小时生成倒计时，阈值为 24 和 72 小时。只有日期时返回估算说明，缺时间时返回角色约定的二次确认提示。

- [ ] **Step 5: 委托并运行时间模块测试**

调用 `developer-test-agent`，原样传入用户请求，由其对已实现的公开接口生成测试。
Run: `python -m pytest tests -v`
Expected: 时间模块相关测试通过；失败时仅修正已确认的公开行为并重新运行。

### Task 3: 本地通知解析流水线

**Files:**
- Create: `noticlean/parser.py`
- Modify: `noticlean/__init__.py`
- Test: 由 `developer-test-agent` 创建对应测试文件。

**Interfaces:**
- Consumes: `parse_deadline()` 和全部模型。
- Produces: `clean_text(text: str) -> str`。
- Produces: `is_campus_notice(text: str) -> bool`。
- Produces: `detect_safety_risk(text: str) -> str | None`。
- Produces: `split_notices(text: str) -> list[str]`。
- Produces: `parse_text(text: str, reference: datetime) -> ParseResult`。

- [ ] **Step 1: 实现保守降噪**

仅删除整行噪音、纯表情回应、连续转发前缀和多余空行。包含时间、链接或行动词的行必须保留。

```python
NOISE_LINE = re.compile(r"^(?:收到[啦呀!！~。]*|谢谢(?:大家|老师|学长|学姐)?[!！~。]*|顶+|dd|\+1)$", re.I)
```

- [ ] **Step 2: 实现相关性和风险检测**

校园场景词与通知行为词组合判定相关性；纯代码、闲聊无通知要素时返回 `relevant=False`。风险检测返回固定安全文案，不修改原文，不宣称已经确认诈骗。

- [ ] **Step 3: 实现强边界分条**

支持 `---` 分隔、独占一行的序号标题，以及后续块再次出现独立主题和截止时间的边界。没有强边界时返回完整文本的一个块。

- [ ] **Step 4: 实现五要素提取**

事件名优先使用“主题/通知/关于”标题，其次使用首个有效句；对象、地点、行动分别通过明确关键词和链接提取。所有行动句去重，缺失字段使用统一待确认文案。

- [ ] **Step 5: 组装结果并导出公共入口**

`parse_text()` 依次完成降噪、相关性、风险、分条、单条解析；每条卡片独立调用 `parse_deadline()`。在包入口导出 `parse_text` 和模型。

- [ ] **Step 6: 委托并运行解析测试**

调用 `developer-test-agent`，原样传入用户请求，由其验证公开流水线。
Run: `python -m pytest tests -v`
Expected: 本地解析不依赖网络或 OCR，全部相关测试通过。

### Task 4: 卡片渲染与安全导出

**Files:**
- Create: `noticlean/render.py`
- Test: 由 `developer-test-agent` 创建对应测试文件。

**Interfaces:**
- Consumes: `ParseResult`、`NoticeCard`。
- Produces: `render_card(card: NoticeCard, index: int | None = None) -> str`。
- Produces: `render_markdown(result: ParseResult) -> str`。
- Produces: `result_to_json(result: ParseResult) -> str`。

- [ ] **Step 1: 生成角色约定的五要素卡片**

输出固定标题、事件、截止、对象、地点、行动和“长理学姐贴心提示”。多卡片使用 `---` 分隔，行动列表和链接不能丢失。

- [ ] **Step 2: 处理无关输入与全局警告**

无关输入返回规定引导语；风险警告置于卡片之前。JSON 使用 `ensure_ascii=False` 和 ISO 格式时间，不输出 `source_text`，避免导出不必要的原始内容。

- [ ] **Step 3: 委托并运行渲染测试**

调用 `developer-test-agent`，原样传入用户请求。
Run: `python -m pytest tests -v`
Expected: 导出内容可读取、中文不转义、全部测试通过。

### Task 5: 可选 OCR 与大模型适配器

**Files:**
- Create: `noticlean/ocr.py`
- Create: `noticlean/llm.py`
- Test: 由 `developer-test-agent` 创建对应测试文件。

**Interfaces:**
- Produces: `OCRUnavailableError`、`ocr_image(image_bytes: bytes, lang: str = "chi_sim+eng") -> str`。
- Produces: `LLMConfig(base_url: str, model: str, api_key: str = "", timeout: float = 20.0)`。
- Produces: `enhance_result(result: ParseResult, config: LLMConfig) -> ParseResult`。

- [ ] **Step 1: 实现惰性 OCR 导入与明确异常**

在函数内部导入 Pillow/pytesseract，使用 `BytesIO` 读取图片并执行中文识别。缺少依赖、可执行程序、语言包或图片无效时抛出 `OCRUnavailableError`，由页面转换为用户提示。

- [ ] **Step 2: 实现有限超时的兼容接口请求**

验证 `base_url` 仅使用 HTTP/HTTPS，拼接 `/chat/completions`，使用 `urllib.request` 发送有限长度请求。API Key 非空时添加 Bearer 请求头，响应限制为 2 MB，不打印请求头或正文。

- [ ] **Step 3: 严格解析模型 JSON**

接受返回对象中的 `choices[0].message.content`，去除 JSON 代码围栏后解析。仅合并 `event_name、audience、location、actions、tip`，按通知索引对应；忽略未知字段、错误类型和多余项。

- [ ] **Step 4: 保持本地安全不变量**

增强失败时返回原本地结果并追加运行警告；增强成功也不修改 `deadline`、`safety_warning`、`relevant`。任何模型缺失字段保持本地值。

- [ ] **Step 5: 委托并运行适配器测试**

调用 `developer-test-agent`，原样传入用户请求；外部请求使用本地替身，不访问真实服务。
Run: `python -m pytest tests -v`
Expected: 未安装 OCR 不妨碍导入，模型失败不抛出到页面，全部测试通过。

### Task 6: Streamlit 页面与端到端验证

**Files:**
- Create: `app.py`
- Test: 由 `developer-test-agent` 创建页面测试文件。

**Interfaces:**
- Consumes: `parse_text()`、`render_markdown()`、`result_to_json()`、`ocr_image()`、`enhance_result()`。
- Produces: 可通过 `streamlit run app.py` 启动的完整应用。

- [ ] **Step 1: 构建输入和参考时间界面**

设置页面标题和校园色 CSS；提供粘贴/截图两个输入页签、示例、清空、文本上传、OCR 编辑框和解析按钮。侧边栏组合 `st.date_input`、`st.time_input` 为带当前日期的 `datetime`。

- [ ] **Step 2: 接入解析及可选增强**

空输入显示提示；正常输入调用 `parse_text()`，用户主动开启且配置完整时才调用 `enhance_result()`。捕获可选能力异常并保留可用结果，将最终结果放入 `st.session_state`。

- [ ] **Step 3: 展示结果与下载**

无关输入显示引导；安全警告使用 `st.warning`；卡片使用分隔容器展示；提供 UTF-8 Markdown 和 JSON 下载。页面不渲染模型返回的 HTML，不显示 API Key。

- [ ] **Step 4: 添加运行说明**

在应用侧边栏给出启动命令、OCR 可选依赖说明和隐私说明，不额外创建未要求的文档。

- [ ] **Step 5: 委托页面测试并执行完整验证**

调用 `developer-test-agent`，原样传入用户请求，由其生成 Streamlit AppTest 冒烟测试。
Run: `python -m pytest tests -v`
Run: `python -m compileall app.py noticlean`
Run: `streamlit run app.py --server.headless true`
Expected: 测试与编译通过，服务成功启动；使用页面自动化或 AppTest 完成文本输入到卡片展示的验证后停止服务。

- [ ] **Step 6: 声明最终交付物**

将 `app.py`、核心包、依赖文件、最终测试及设计/计划文档声明为交付物，不声明缓存、临时脚本或构建产物。
