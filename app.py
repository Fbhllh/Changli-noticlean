from __future__ import annotations

from datetime import datetime

import streamlit as st

from noticlean.calendar_export import build_ics, calendar_filename
from noticlean.llm import LLMConfig, enhance_result
from noticlean.ocr import OCRUnavailableError, ocr_image
from noticlean.parser import parse_text
from noticlean.render import (
    UNRELATED_MESSAGE,
    render_card,
    render_markdown,
    render_priority_badge,
    result_to_json,
)

SAMPLE_TEXT = """@所有人
【2026华为开发者大赛报名】
面向对象：计算机、电气等工科专业全体在校学生
截止时间：11月20日 18:00
地点/平台：华为官方赛事平台
请登录赛事平台组队，并在截止前提交作品代码和项目说明。
收到
---
1. 体测补测通知
参与对象：2023级、2024级未完成体测的本科生
请于11月22日下午14:30前到云塘校区体育馆二楼集合。
需携带校园卡和身份证，穿运动鞋，提前十分钟签到。
谢谢老师
"""

st.set_page_config(page_title="长理通知降噪助手", page_icon="📌", layout="wide")

st.markdown("""
<style>
:root {
    --campus-blue: #185a9d;
    --campus-orange: #e9833a;
}
.stApp {
    background: linear-gradient(180deg, #f4f8fc 0%, #ffffff 38%);
}
.hero {
    padding: 1.35rem 1.5rem;
    border-radius: 18px;
    color: white;
    background: linear-gradient(120deg, #123f70, #2278b8);
    box-shadow: 0 12px 30px rgba(24, 90, 157, 0.14);
    margin-bottom: 1.2rem;
}
.hero h1 {
    font-size: 1.75rem;
    margin: 0 0 0.35rem 0;
}
.hero p {
    margin: 0;
    opacity: 0.9;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(255, 255, 255, 0.94);
    border-radius: 14px;
}
.stButton > button[kind="primary"] {
    background: var(--campus-blue);
}
@media (max-width: 640px) {
    .hero { padding: 1rem; }
    .hero h1 { font-size: 1.4rem; }
}
</style>
<div class="hero">
<h1>📌 长理通知降噪助手</h1>
<p>剥离群聊噪音，把截止时间、地点和下一步行动讲清楚。</p>
</div>
""", unsafe_allow_html=True)

for key, default in (("notice_text", ""), ("ocr_text", ""), ("parse_result", None), ("upload_version", 0)):
    if key not in st.session_state:
        st.session_state[key] = default

with st.sidebar:
    st.header("解析设置")
    now = datetime.now()
    reference_date = st.date_input("参考日期", value=now.date())
    reference_time = st.time_input("参考时间", value=now.time().replace(microsecond=0))
    reference = datetime.combine(reference_date, reference_time)
    st.caption("倒计时以该时间为基准；缺少年份时取参考年份。")
    st.divider()
    use_llm = st.toggle("启用大模型增强", value=False, help="默认关闭；失败时自动保留本地结果。")
    llm_base_url = ""
    llm_model = ""
    llm_api_key = ""
    if use_llm:
        llm_base_url = st.text_input("OpenAI 兼容接口地址", placeholder="https://你的接口地址/v1")
        llm_model = st.text_input("模型名称", placeholder="你的模型名称")
        llm_api_key = st.text_input("API Key", type="password", placeholder="本地接口可留空")
        st.caption("开启后，当前通知会发送到你配置的接口。Key 仅用于当次请求，不写入文件。")
    st.divider()
    st.markdown("**启动方式**")
    st.code("streamlit run app.py", language="bash")
    st.markdown("**可选截图 OCR**")
    st.code("pip install -r requirements-ocr.txt", language="bash")
    st.caption("还需安装 Tesseract 和 chi_sim 中文语言包。通知正文不会写入数据库或日志。")


def fill_sample() -> None:
    st.session_state.notice_text = SAMPLE_TEXT
    st.session_state.parse_result = None


def clear_inputs() -> None:
    st.session_state.notice_text = ""
    st.session_state.ocr_text = ""
    st.session_state.upload_version += 1
    st.session_state.parse_result = None


def decode_text_file(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("文本编码无法识别，请转为 UTF-8 后重试。")


def run_parser(text: str) -> None:
    if not text.strip():
        st.warning("请先粘贴通知、上传文本，或完成截图 OCR。")
        return
    with st.spinner("正在剥离噪音并提炼重点…"):
        result = parse_text(text, reference)
        if use_llm and result.relevant:
            config = LLMConfig(llm_base_url, llm_model, llm_api_key)
            result = enhance_result(result, config, reference)
    st.session_state.parse_result = result


text_tab, image_tab = st.tabs(["粘贴通知", "上传截图"])

with text_tab:
    st.text_area(
        "把群通知长文本甩到这里",
        key="notice_text",
        height=280,
        placeholder="支持多条通知混合文本，会自动过滤“收到、谢谢、顶顶顶”等噪音…",
    )
    uploaded_text = st.file_uploader(
        "也可以上传 TXT 文本",
        type=["txt"],
        key=f"notice_file_{st.session_state.upload_version}",
    )
    sample_col, clear_col, parse_col = st.columns([1, 1, 2])
    with sample_col:
        st.button("填入示例", use_container_width=True, on_click=fill_sample)
    with clear_col:
        st.button("清空", use_container_width=True, on_click=clear_inputs)
    with parse_col:
        parse_text_clicked = st.button("一键提炼重点", type="primary", use_container_width=True)
    if parse_text_clicked:
        source_text = st.session_state.notice_text
        if not source_text.strip() and uploaded_text is not None:
            try:
                source_text = decode_text_file(uploaded_text.getvalue())
            except ValueError as error:
                st.warning(str(error))
                source_text = ""
        run_parser(source_text)

with image_tab:
    uploaded_image = st.file_uploader(
        "上传清晰的群通知截图",
        type=["png", "jpg", "jpeg"],
        key=f"notice_image_{st.session_state.upload_version}",
    )
    if uploaded_image is not None:
        st.image(uploaded_image, caption="待识别截图", use_container_width=True)
    if st.button("识别截图文字", disabled=uploaded_image is None):
        if uploaded_image.size > 10 * 1024 * 1024:
            st.warning("截图不能超过 10 MB，请压缩后重试。")
        else:
            with st.spinner("正在识别截图文字…"):
                try:
                    st.session_state.ocr_text = ocr_image(uploaded_image.getvalue())
                    if not st.session_state.ocr_text:
                        st.info("未识别到文字，请换一张更清晰的截图或直接粘贴文本。")
                except OCRUnavailableError as error:
                    st.warning(str(error))
    st.text_area("OCR 结果（可修改后再解析）", key="ocr_text", height=220)
    if st.button("解析截图通知", type="primary", key="parse_ocr"):
        run_parser(st.session_state.ocr_text)

result = st.session_state.parse_result
if result is not None:
    st.subheader("解析结果")
    for warning in result.warnings:
        st.warning(warning)
    if not result.relevant:
        st.info(UNRELATED_MESSAGE)
    else:
        if result.safety_warning:
            st.warning(f"🚨 【安全提示】：{result.safety_warning}")
        for index, card in enumerate(result.notices, 1):
            with st.container(border=True):
                st.markdown(render_priority_badge(card), unsafe_allow_html=True)
                st.markdown(render_card(card, index if len(result.notices) > 1 else None))
        calendar_cards = [(index, card) for index, card in enumerate(result.notices, 1) if card.calendar_ready]
        if calendar_cards:
            st.subheader("日历提醒")
            st.caption("日历时间来自大模型解析；精确时间生成 30 分钟事件，仅日期生成全天事件。")
            for index, card in calendar_cards:
                st.download_button(
                    f"下载 {card.event_name}（.ics）",
                    data=build_ics(card).encode("utf-8"),
                    file_name=calendar_filename(card, index),
                    mime="text/calendar; charset=utf-8",
                    key=f"calendar_download_{index}",
                    use_container_width=True,
                )
        markdown_result = render_markdown(result)
        json_result = result_to_json(result)
        markdown_col, json_col = st.columns(2)
        with markdown_col:
            st.download_button(
                "下载 Markdown",
                data=markdown_result,
                file_name="长理通知解析.md",
                mime="text/markdown; charset=utf-8",
                use_container_width=True,
            )
        with json_col:
            st.download_button(
                "下载 JSON",
                data=json_result,
                file_name="长理通知解析.json",
                mime="application/json; charset=utf-8",
                use_container_width=True,
            )
        with st.expander("复制解析卡片"):
            st.code(markdown_result, language="markdown")

st.caption("长理 NotiClean · 信息提取结果请以学校、学院或老师的官方通知为准。")
