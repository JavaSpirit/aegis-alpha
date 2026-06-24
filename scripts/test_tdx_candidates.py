"""Test TDX candidate pool."""
import os, json
os.environ["AEGIS_ALPHA_MARKET_DATA_PROVIDER"] = "tdx"

from aegis_alpha.mcp.server import get_second_board_candidates_compact, get_market_sentiment_gate, get_promotion_dossier

print("=== 市场情绪 (TDX) ===")
gate = get_market_sentiment_gate()
print(f"  模式: {gate['data_mode']} | 热点: {gate['hot_theme_count']}个 | 备注: {gate.get('conclusion','')[:80]}")

print("\n=== 二板候选 (TDX 真实数据) ===")
candidates = get_second_board_candidates_compact(limit=8)
print(f"  共 {len(candidates)} 只")
for c in candidates:
    print(f"  {c['symbol']} | 涨跌幅:{c.get('current_change_pct',0):.1f}% | 题材:{c.get('theme','?')[:12]} | 成交额:{c.get('turnover_cny',0)/1e8:.1f}亿 | 模式:{c.get('data_mode','?')}")

if candidates:
    sym = candidates[0]["symbol"]
    print(f"\n=== Top1 Dossier: {sym} ===")
    d = get_promotion_dossier(sym)
    for k in ["market_emotion","theme_position","float_size","volume_energy","reseal_strength"]:
        v = d.get(k, {})
        print(f"  [{k}] mode={v.get('data_mode','?') if isinstance(v,dict) else '?'}")
