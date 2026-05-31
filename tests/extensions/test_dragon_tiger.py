import pathlib

from aegis_alpha.extensions.dragon_tiger import (
    classify_seat,
    load_seat_whitelist,
    parse_dragon_tiger_payload,
)


CONFIG_PATH = pathlib.Path(__file__).resolve().parents[2] / "config" / "dragon_tiger_seats.yaml"


def test_load_whitelist_known_alias():
    whitelist = load_seat_whitelist(str(CONFIG_PATH))
    classification = classify_seat(
        "国泰君安证券深圳益田路荣超商务中心证券营业部",
        whitelist,
    )
    assert classification == ("hot_money_known", "章盟主")


def test_classify_institution_seat():
    whitelist = load_seat_whitelist(str(CONFIG_PATH))
    seat_type, alias = classify_seat("机构专用", whitelist)
    assert seat_type == "institution"
    assert alias == ""


def test_classify_unknown_seat_falls_back_to_hot_money_unknown():
    whitelist = load_seat_whitelist(str(CONFIG_PATH))
    seat_type, alias = classify_seat("某营业部", whitelist)
    assert seat_type == "hot_money_unknown"
    assert alias == ""


def test_parse_dragon_tiger_payload_extracts_top_seats():
    raw = {
        "symbol": "600519",
        "name": "贵州茅台",
        "trading_day": "2026-05-30",
        "list_reason": "日涨幅偏离值达 7%",
        "buy_seats": [
            {"seat_name": "国泰君安证券深圳益田路荣超商务中心证券营业部", "amount": 12000000},
            {"seat_name": "机构专用", "amount": 8000000},
        ],
        "sell_seats": [
            {"seat_name": "某营业部", "amount": 5000000},
        ],
    }
    record = parse_dragon_tiger_payload(
        raw, whitelist=load_seat_whitelist(str(CONFIG_PATH)), provider="mock"
    )
    assert record.symbol == "600519"
    assert record.total_buy_cny == 20_000_000.0
    assert record.total_sell_cny == 5_000_000.0
    assert record.net_amount_cny == 15_000_000.0
    assert {s.seat_type for s in record.seats} == {
        "hot_money_known",
        "institution",
        "hot_money_unknown",
    }
    aliases = {s.hot_money_alias for s in record.seats if s.hot_money_alias}
    assert "章盟主" in aliases
