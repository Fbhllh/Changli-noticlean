from __future__ import annotations

from datetime import datetime
from pathlib import Path

from streamlit.testing.v1 import AppTest

from noticlean.dates import make_deadline
from noticlean.models import NoticeCard, PRIORITY_OPTIONS, ParseResult

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _new_app() -> AppTest:
    app = AppTest.from_file(str(APP_PATH), default_timeout=20)
    app.run()
    assert not app.exception
    return app


def test_local_parse_has_cards_and_no_ics_download() -> None:
    app = _new_app()

    app.button[0].click().run()
    app.button[2].click().run()

    result = app.session_state.parse_result
    assert result is not None and result.relevant
    assert len(result.notices) == 2
    assert all(not card.calendar_ready for card in result.notices)
    download_labels = [item.label for item in app.get("download_button")]
    assert download_labels == ["下载 Markdown", "下载 JSON"]
    assert not app.exception


def test_llm_ready_card_shows_ics_download_and_priority_style(reference: datetime) -> None:
    app = _new_app()
    card = NoticeCard(
        event_name="缓考申请",
        deadline=make_deadline(datetime(2026, 11, 18, 12, 0), reference),
        audience="2024级本科生",
        location="云塘校区教务办公室",
        actions=["提交申请"],
        links=[],
        tip="保留提交凭证",
        source_text="原文",
        category="教务通知",
        priority=PRIORITY_OPTIONS[0],
        calendar_ready=True,
    )

    app.session_state.parse_result = ParseResult(True, [card], "清理后的通知")
    app.run()

    downloads = app.get("download_button")
    assert [item.label for item in downloads] == [
        "下载 缓考申请（.ics）",
        "下载 Markdown",
        "下载 JSON",
    ]
    assert downloads[0].key == "calendar_download_1"
    assert any("#e5484d" in item.value for item in app.markdown)
    assert not app.exception
