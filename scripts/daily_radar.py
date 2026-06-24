"""今日二板候选全面分析 (2026-06-23)"""
from __future__ import annotations
import os, json

os.environ["AEGIS_ALPHA_MARKET_DATA_PROVIDER"] = "mock"

from aegis_alpha.mcp.server import (
    get_market_sentiment_gate,
    get_second_board_candidates_compact,
    get_promotion_dossier,
    get_theme_leaders,
    get_top_themes_today,
)

# ═══ 1. 市场闸门 ═══
gate = get_market_sentiment_gate()

# ═══ 2. 今日题材 ═══
themes = get_top_themes_today()
theme_names = [t["theme"] for t in themes[:5]] if themes else ["无热点"]

# ═══ 3. 二板候选 ═══
candidates = get_second_board_candidates_compact(limit=8)

# ═══ 4. 获取每只候选的完整 dossier ═══
dossiers = []
for c in candidates:
    try:
        d = get_promotion_dossier(c["symbol"])
        dossiers.append(d)
    except Exception:
        pass

# ═══ 5. 输出 ═══
print("=" * 66)
print(f"  二板雷达 · 今日分析  |  {gate['trading_day']}")
print(f"  数据模式: {gate.get('data_mode','?')}  提供方: {gate.get('provider','?')}")
print("=" * 66)

print(f"\n  📊 市场情绪闸门")
print(f"     涨停 {gate['limit_up_count']} 家  |  炸板率 {gate['break_board_rate']:.0%}")
print(f"     连板存活率 {gate.get('consecutive_boards_alive_rate',0):.0%}")
print(f"     一进二晋级率 {gate.get('first_to_second_promotion_rate',0):.0%}")
print(f"     二进三晋级率 {gate.get('second_to_third_promotion_rate',0):.0%}")
print(f"     最高连板 {gate.get('max_height_today',0)} 板  |  热点题材 {gate['hot_theme_count']} 个")
risk = gate.get('risk_flags', [])
if risk:
    print(f"     ⚠️ 风险: {', '.join(risk)}")
pos = gate.get('positive_signals', [])
if pos:
    print(f"     ✅ 积极: {', '.join(pos)}")
print(f"     结论: {gate['conclusion']}")

print(f"\n  🔥 今日热点题材: {', '.join(theme_names)}")

print(f"\n  ──────────────────────────────────────────────────")
print(f"  二板候选共 {len(candidates)} 只，逐因子分析如下：")
print(f"  ──────────────────────────────────────────────────")

# ── 对每只候选做 5 因子分析 ──
STAGE_LABEL = {
    "launch": "启动", "fermenting": "发酵", "climax": "高潮",
    "divergence": "分歧", "ebb": "退潮", "unknown": "未知",
}
ROLE_LABEL = {"leader": "🐉龙头", "follower": "跟风", "unknown": "未分类"}

results = []

for i, (c, d) in enumerate(zip(candidates, dossiers)):
    sym = c["symbol"]
    name = c["name"]
    theme = c.get("theme", "?")
    stage = c.get("theme_lifecycle_stage", "unknown")
    stage_cn = STAGE_LABEL.get(stage, stage)
    role = c.get("theme_role", "unknown")
    role_cn = ROLE_LABEL.get(role, role)
    cap = c.get("free_float_market_cap_cny", 0)
    turnover = c.get("turnover_cny", 0)
    avg_t = c.get("avg_turnover_10d_cny", 1)
    shrink = c.get("prev_day_volume_shrink_ratio", 0)
    break_ct = c.get("break_board_count", 0)
    reseal_ct = c.get("reseal_count", 0)
    max_seal = c.get("max_seal_amount_cny", 0)
    final_seal = c.get("final_seal_time", "?")
    big_order = c.get("big_order_net_inflow_ratio", 0)
    orderbook = c.get("orderbook_quality_score", 50)

    # ── 按 SKILL.md 规则判定 ──
    if stage == "ebb":
        grade = "REJECT"
        likelihood = "low"
        stage_note = "🚫 退潮期，依规必须 REJECT"
    elif stage == "divergence":
        grade = "B"
        likelihood = "medium"
        stage_note = "⚠️ 分歧期，grade 上限 B，likelihood 上限 medium"
    elif stage == "climax":
        # climax: vol 强 + reseal 强 → high，否则 medium
        if turnover / max(avg_t, 1) > 1.3 and reseal_ct >= 2 and max_seal > 5e8:
            grade = "A"
            likelihood = "high"
            stage_note = "高潮期但量能+回封双强，可给 high"
        else:
            grade = "B"
            likelihood = "medium"
            stage_note = "高潮期兑现风险高，量能/回封不满足双强条件"
    else:
        # launch / fermenting
        score = 0
        if big_order > 0.05: score += 1
        if orderbook > 65: score += 1
        if shrink < 0.7: score += 1
        if reseal_ct >= 2 and max_seal > 5e8: score += 1
        if cap < 5e9: score += 1

        if score >= 4:
            grade = "A"; likelihood = "high"
        elif score >= 2:
            grade = "B"; likelihood = "medium"
        else:
            grade = "C"; likelihood = "low"
        stage_note = f"{stage_cn}期，综合评分 {score}/5"

    results.append((sym, name, theme, stage_cn, grade, likelihood))

    cap_str = f"{cap/1e8:.0f}亿" if cap else "?"
    print(f"\n  {'─'*60}")
    print(f"  #{i+1}  {sym}  {name}")
    print(f"  {'─'*60}")
    print(f"  题材: {theme} | {stage_cn} | {role_cn} | {stage_note}")
    print(f"  F1 市场情绪: {gate['limit_up_count']}涨停/{gate['break_board_rate']:.0%}炸板 → {'偏暖' if gate['limit_up_count']>40 else '中性'}")
    print(f"  F2 题材位置: {stage_cn}期 → {'✅ 有利' if stage in ('launch','fermenting') else '⚠️ 需谨慎' if stage=='climax' else '🚫 降权'}")
    print(f"  F3 股本大小: 流通市值 {cap_str} → {'小盘弹性好' if cap<5e9 else '中盘适中' if cap<10e9 else '大盘封板难'}")
    vol_ratio = turnover / max(avg_t, 1)
    print(f"  F4 量能资金: 换手{turnover/1e8:.1f}亿/{vol_ratio:.1f}x均量 | 缩量{shrink:.0%} | 大单比{big_order:+.0%} | 盘口{orderbook:.0f}")
    print(f"  F5 回封力度: 炸{break_ct}次/回封{reseal_ct}次 | 封单{max_seal/1e8:.1f}亿 | 尾封{final_seal}")
    print(f"  >>> grade: {grade}  |  promotion_likelihood: {likelihood}")

# ═══ 汇总 ═══
print(f"\n{'='*66}")
print(f"  📋 汇总排序")
print(f"{'='*66}")
grade_order = {"A": 1, "B": 2, "C": 3, "REJECT": 4}
results.sort(key=lambda x: grade_order.get(x[4], 99))
for r in results:
    icon = {"A": "🟢", "B": "🟡", "C": "🟠", "REJECT": "🔴"}.get(r[4], "⚪")
    print(f"  {icon} {r[4]:6s} | {r[2]:12s} | {r[0]:10s} {r[1]} | {r[3]}")
print(f"\n  免责声明: 仅供研究观察，不构成投资建议。Mock 数据，非真实行情。")
