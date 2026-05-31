from aegis_alpha.extensions.limitup_driver import classify_limitup_driver, LimitupDriverInputs


def _inputs(**overrides):
    base = dict(
        symbol="600519",
        concept_tags=[],
        topic_tags=[],
        list_reason="",
        net_amount_cny=0.0,
        previous_consecutive_boards=0,
        recent_earnings_surprise=False,
        recent_policy_keywords=[],
    )
    base.update(overrides)
    return LimitupDriverInputs(**base)


def test_earnings_driver_when_recent_surprise():
    out = classify_limitup_driver(_inputs(recent_earnings_surprise=True))
    assert out == "earnings"


def test_policy_driver_when_topic_matches_policy_keyword():
    out = classify_limitup_driver(_inputs(topic_tags=["国务院发布", "新基建"]))
    assert out == "policy"


def test_hot_money_driver_when_dragon_tiger_net_buy_and_no_policy():
    out = classify_limitup_driver(
        _inputs(
            net_amount_cny=15_000_000.0,
            previous_consecutive_boards=2,
        )
    )
    assert out == "hot_money"


def test_theme_driver_default_when_concept_tags_present():
    out = classify_limitup_driver(_inputs(concept_tags=["AI", "机器人"]))
    assert out == "theme"


def test_unknown_driver_when_nothing_matches():
    out = classify_limitup_driver(_inputs())
    assert out == "unknown"
