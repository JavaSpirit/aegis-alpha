"""Probe tdxmcp data structure for candidate pool assembly."""
from aegis_alpha.adapters.tdx import client as tdx
import json

# 1. blocks
b = tdx.blocks()
print("=== Blocks ===")
if b:
    sample = b[0]
    print("keys:", list(sample.keys()))
    print("blockname:", sample.get("blockname", "?"))
    stocks = sample.get("stocks", [])
    print("stocks count:", len(stocks), "sample:", stocks[:5])

# 2. quotes batch
print("\n=== Quotes batch ===")
try:
    qs = tdx.quotes(["sh600519", "sz000001"])
    print("type:", type(qs).__name__)
    if isinstance(qs, dict):
        print("keys:", list(qs.keys()))
        vals = list(qs.values())[0] if qs else None
        if isinstance(vals, list) and vals:
            print("first item type:", type(vals[0]).__name__)
            print("first item:", str(vals[0])[:200])
    elif isinstance(qs, list) and qs:
        print("len:", len(qs))
        q = qs[0]
        qd = q.get("quote", q)
        price = float(qd.get("price", 0))
        last_close = float(qd.get("last_close", 1))
        chg = (price / last_close - 1) * 100 if last_close else 0
        print(f"  {q.get('symbol','?')} price={price} chg={chg:.1f}%")
except Exception as e:
    import traceback
    traceback.print_exc()

# 3. finance
print("\n=== Finance (600519) ===")
try:
    fin = tdx.finance("sh600519")
    if isinstance(fin, dict):
        print("keys:", list(fin.keys())[:10])
except Exception as e:
    print("Error:", e)

# 4. stock info 
print("\n=== Stock Info (600519) ===")
try:
    info = tdx.stock_info("sh600519")
    if isinstance(info, dict):
        print("keys:", list(info.keys())[:10])
except Exception as e:
    print("Error:", e)
