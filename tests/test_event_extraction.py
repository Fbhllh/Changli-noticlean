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
