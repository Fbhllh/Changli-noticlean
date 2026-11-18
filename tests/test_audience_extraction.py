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
        ("通知：\n各位文体委员大家好！\n请各班文体委员及时将通知转发至班级群，鼓励同学们积极报名。", "文体委员"),
    ],
)
def test_extract_complete_audience(parse_notice, text, expected):
    assert parse_notice(text).audience == expected


def test_missing_audience_does_not_infer_from_action(parse_notice):
    card = parse_notice("通知\n请在学校提交材料。")
    assert card.audience == MISSING_AUDIENCE
