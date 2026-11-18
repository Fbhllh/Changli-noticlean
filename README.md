# 长理通知降噪与智能解析助手

一个基于 Python Streamlit 的轻量级校园通知解析 Web 应用，主要面向长沙理工大学学生。它可以从微信群、QQ 群转发的长文本中过滤“收到、谢谢、顶贴”等噪音，提取通知的关键字段，并突出截止时间和下一步行动。

## 主要功能

- 通知降噪：过滤接龙回复、表情和无关转发内容。
- 多通知解析：根据明确分隔线或标题边界拆分多条通知。
- 五要素卡片：提取事件名称、截止时间、面向对象、地点/平台和核心行动。
- 分类与优先级：输出固定分类，并用红、黄、绿标签区分高、中、低优先级。
- 多地点保留：支持多个校区、摊位、教室和平台，按原文顺序去重展示。
- 截止倒计时：支持常见中文日期、相对日期和星期表达，按紧急程度提醒。
- 分钟级显示：不足一小时显示分钟及约等小时数，不再把半小时直接显示为零小时。
- 日历导出：大模型成功补全事件名称、时间和地点后，可下载对应的 `.ics` 文件。
- 风险提示：发现非官方收费、敏感信息或可疑链接时显示安全警告。
- 输入方式：支持粘贴文本、TXT 文件和可选截图 OCR。
- 可选大模型增强：可配置 OpenAI 兼容接口；失败时自动保留本地解析结果。
- 结果导出：支持下载 ICS、Markdown 和 JSON。
- 本地优先：默认不需要 API Key，不将通知正文写入数据库或日志。

## 技术栈

- Python 3.10+
- Streamlit 1.40+
- Pydantic 2：校验大模型返回结构和固定枚举
- 标准库正则、日期、JSON 和 ICS 文本处理
- 可选 Pillow、pytesseract 和 Tesseract OCR

## 项目结构

```text
changli-noticlean/
├─ app.py                 # Streamlit 页面和交互入口
├─ noticlean/
│  ├─ __init__.py         # 包导出
│  ├─ models.py           # 通知、截止时间和解析结果模型
│  ├─ dates.py            # 中文时间解析、倒计时和紧急程度
│  ├─ parser.py           # 降噪、分条、风险检测和五要素提取
│  ├─ render.py           # 卡片、优先级标签、Markdown 和 JSON 输出
│  ├─ llm.py              # Pydantic 校验、大模型增强与失败回退
│  ├─ calendar_export.py  # 标准库 ICS 生成与安全文件名
│  └─ ocr.py              # 可选截图 OCR
├─ tests/                 # 功能与页面回归测试
├─ requirements.txt       # 核心运行依赖
├─ requirements-dev.txt   # 开发和测试依赖
├─ requirements-ocr.txt   # 可选 OCR Python 依赖
└─ docs/                  # 设计与实施文档
```

## 一、在 Windows 上运行

### 1. 准备项目

将项目解压到一个目录，例如：

```text
D:\changli-noticlean
```

确保该目录下能直接看到 `app.py`、`noticlean` 和 `requirements.txt`，不要多套一层同名目录。

### 2. 创建虚拟环境

如果已经通过 PyCharm 创建了 `.venv`，可以跳过创建步骤。

在项目目录打开终端，执行：

```powershell
py -m venv .venv
```

### 3. 安装核心依赖

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
```

验证 Streamlit 是否可用：

```powershell
.venv\Scripts\python -c "import streamlit; print(streamlit.__version__)"
```

### 4. 启动应用

```powershell
.venv\Scripts\python -m streamlit run app.py
```

终端显示服务地址后，在同一台电脑的浏览器中打开：

```text
http://localhost:8501
```

停止应用时，在终端按 `Ctrl+C`。

## 二、在 PyCharm 中配置

1. 使用 PyCharm 打开项目根目录。
2. 进入 `File → Settings → Project → Python Interpreter`。
3. 选择现有解释器 `.venv\Scripts\python.exe`。
4. 打开 PyCharm Terminal，执行核心依赖安装命令。
5. 在 Terminal 中执行启动命令。
6. 浏览器打开本地地址后使用应用。

PyCharm 中的黄色类型检查提示通常不等于运行错误。若出现红色 `No module named 'streamlit'`，优先检查当前解释器是否为项目的 `.venv`，以及依赖是否安装到了同一个环境。

## 三、在 macOS 或 Linux 上运行

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

然后在浏览器打开 `http://localhost:8501`。

## 四、日常使用

### 粘贴通知解析

1. 打开“粘贴通知”页签。
2. 将群通知原文粘贴到输入框。
3. 点击“一键提炼重点”。
4. 查看解析卡片、分类、红黄绿优先级、截止倒计时和安全提醒。
5. 根据需要下载 ICS、Markdown 或 JSON；ICS 按钮的显示条件见下文。

也可以上传 UTF-8 或 GB18030 编码的 `.txt` 文件。点击“填入示例”可以体验多通知拆分，“清空”会重置输入和结果。

### 设置参考时间

侧边栏的参考日期和时间默认取当前系统时间，用于计算倒计时。

- 日常解析：保持默认值。
- 解析历史通知：可将参考时间调整为通知当时的日期和时间。
- 原文没有年份：按参考时间所在年份推定，并在结果中标注。
- 原文只有日期没有时刻：按当天 `23:59` 估算，并明确提示具体时刻未注明。

### 使用截图 OCR

截图 OCR 是可选功能，核心文本解析不依赖它。

安装 Python OCR 依赖：

```powershell
.venv\Scripts\python -m pip install -r requirements-ocr.txt
```

还需要在系统中安装 Tesseract OCR 和 `chi_sim` 中文语言包，并确保 Tesseract 可在系统 PATH 中找到。仅安装 `pytesseract` 并不等于安装了 OCR 引擎。

配置完成后：

1. 打开“上传截图”页签。
2. 上传 PNG、JPG 或 JPEG 图片，大小不超过 10 MB。
3. 点击“识别截图文字”。
4. 检查并修改 OCR 文本。
5. 点击“解析截图通知”。

如果 OCR 不可用或识别效果较差，可以直接粘贴通知文本。

### 可选大模型增强

默认仅使用本地规则，不需要联网或 API Key。需要增强复杂通知的字段理解时，可在侧边栏开启“大模型增强”，填写：

- OpenAI 兼容接口地址
- 模型名称
- API Key；本地接口无鉴权时可留空

开启后，当前通知文本会发送到所配置的接口。API Key 不写入项目文件，通知正文不保存到数据库。接口超时、返回异常、通知数量不一致或 Pydantic 校验失败时，页面会保留本地解析结果。

请勿在源码中硬编码 API Key，也不要把包含敏感信息的通知发送到不可信接口。

### 分类、优先级与 ICS 日历

`category` 只能取以下固定值：

- `教务通知`
- `院系/班级`
- `讲座/比赛`
- `社团/其他`

`priority` 只能取以下固定值：

- `高-红标（涉及绩点/考试/截止日期在48小时内）`：红色标签。
- `中-黄标（常规通知）`：黄色标签。
- `低-绿标（自愿参加/讲座等）`：绿色标签。

本地代码会将涉及绩点、考试或截止时间在 48 小时内的通知强制提升为高优先级，避免大模型低估紧急程度。

ICS 下载按钮仅在启用大模型增强后，且模型成功返回非空事件名称、有效本地时间和非空地点时显示。仅本地规则解析成功不会显示 ICS 按钮；模型失败或字段不完整时会安全回退。

- 精确到时刻：生成从该时间开始的 30 分钟事件。
- 只有日期：生成对应日期的全天事件，不把用于倒计时估算的 `23:59` 当作精确开始时间。
- 多条通知：每张符合条件的卡片有独立下载按钮。
- 文件使用 UTF-8 编码和标准 CRLF 换行，包含事件名称、地点、行动说明、分类和优先级。

## 五、解析规则说明

支持的时间表达包括：

- `2026年11月20日 18:00`
- `2026-11-20 18:00`
- `11月20日下午6点`
- `今天、明天、后天、大后天`
- `本周五、下周三` 等常见表达

紧急程度按以下规则划分：

- 已截止：提示确认是否可以补交或补报名。
- 24 小时以内：时间紧急。
- 24 至 72 小时：请抓紧。
- 超过 72 小时：时间充裕。

不足一分钟显示“距截止不足 1 分钟”；不足一小时显示分钟及约等小时数；更长时间保留天、小时和剩余分钟。

无法可靠识别的字段会标记为待确认，不会强行补全。安全提示表示需要核实来源，不代表系统已经确认通知属于诈骗。最终安排应以学校、学院或老师的官方通知为准。

## 六、常见问题

### 提示 `No module named 'streamlit'`

在当前项目环境重新安装依赖：

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
```

不要在一个环境安装依赖，却用另一个 Python 解释器启动应用。

### 提示无法导入 `parse_deadline`

检查 `noticlean/dates.py` 是否为完整当前版本。该文件应包含顶层函数：

```python
def parse_deadline(text: str, reference: datetime) -> DeadlineInfo:
```

不要随意只复制函数的一部分，因为它还依赖同文件中的辅助函数。替换为完整文件后重启 Streamlit；如仍读取旧内容，可删除 `noticlean/__pycache__` 再启动。

### 浏览器无法访问 localhost

- 确认终端中的 Streamlit 仍在运行。
- 使用终端实际显示的地址和端口。
- `localhost` 指的是启动应用的电脑，远程服务器上的 localhost 不能直接当作本机地址使用。
- 本地正常运行时不需要关闭 CORS；代理预览配置与本地使用应分开处理。

### OCR 识别失败

检查是否同时安装了：

- `requirements-ocr.txt` 中的 Python 依赖
- Tesseract OCR 程序
- `chi_sim` 中文语言包

截图应尽量清晰，避免文字过小、倾斜或被遮挡。识别后可先修改文本，再执行解析。

### 启动后页面没有更新

修改源码后先停止旧进程，再重新执行启动命令。浏览器可强制刷新，避免继续使用旧页面资源。

## 隐私与使用边界

- 默认解析在本地完成，不保存通知历史。
- OCR 使用本地 Tesseract 时，不需要上传截图到第三方服务。
- 大模型增强是可选功能，启用后会产生外部数据传输。
- 规则解析无法保证覆盖所有自然语言表达，请核对原始通知。
- 涉及缴费、验证码、银行卡或个人敏感信息时，应通过学校官方渠道再次确认。
