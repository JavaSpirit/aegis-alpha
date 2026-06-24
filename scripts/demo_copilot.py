"""Demo: 直接在 Copilot 中操控 Aegis Alpha"""
from __future__ import annotations
import os, json

os.environ["AEGIS_ALPHA_MARKET_DATA_PROVIDER"] = "tdx"

from aegis_alpha.mcp.server import get_market_sentiment_gate, get_second_board_candidates_compact, get_promotion_dossier

# 1. 市场情绪
gate = get_market_sentiment_gate()
print("=== 市场情绪闸门 ===")
print(f"  涨停: {gate['limit_up_count']}家 | 炸板率: {gate['break_board_rate']:.0%}")
print(f"  连板存活率: {gate['consecutive_boards_alive_rate']:.0%} | 一进二晋级率: {gate['first_to_second_promotion_rate']:.0%}")
print(f"  热点题材: {gate['hot_theme_count']}个 | 结论: {gate['conclusion']}")

# 2. 二板候选
print("\n=== 二板候选 TOP 3 ===")
candidates = get_second_board_candidates_compact(limit=3)
for c in candidates:
    print(f"  {c['symbol']} {c['name']} | 题材:{c['theme']} | 阶段:{c.get('theme_lifecycle_stage','?')} | 市值:{c.get('free_float_market_cap_cny',0)/1e8:.0f}亿 | 炸板:{c.get('break_board_count',0)}次")

# 3. 对第一只候选获取完整 Dossier
if candidates:
    sym = candidates[0]["symbol"]
    dossier = get_promotion_dossier(sym)
    print(f"\n=== {sym} 5因子 Dossier ===")
    for key in ["market_emotion", "theme_position", "float_size", "volume_energy", "reseal_strength"]:
        print(f"  [{key}] {json.dumps(dossier.get(key, {}), ensure_ascii=False)[:150]}")
