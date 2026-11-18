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
