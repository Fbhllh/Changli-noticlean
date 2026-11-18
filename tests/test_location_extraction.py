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
