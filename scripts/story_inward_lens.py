"""動画「円目線とドル目線」用の集計：非居住者による日本の証券の買い越し（年ごと）を、円とドルで比べる。

入力（どちらも build 済みの加工データ）:
    data/processed/mof_itn_weekly.csv   財務省 週次・指定報告機関ベース（億円）
    data/processed/ecb_exr_daily.csv    ECB 参照レートから計算した円ドル
出力:
    video/data/inward_by_year.json

方法:
- 対象は inward_total_net（非居住者による日本の証券の取得超。株式・投資ファンド持分＋中長期債＋短期債）。
- 週の年は week_start の年。対象は全52〜53週がそろう 2005〜2025年（2026年は途中なので除く）。
- ドル換算は週ごと：その週の ECB 営業日の円ドル（MABUI 計算値）の単純平均で割る。
  実際の取引時点のレートではないので、近似である。
- 頑健性：年の割り当て（週の初日／最終日／木曜）と換算レート（週平均／週末の値）を変えた6通りも計算し、出力に残す。
"""

from __future__ import annotations

import bisect
import csv
import datetime as dt
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOF = ROOT / "data" / "processed" / "mof_itn_weekly.csv"
FX = ROOT / "data" / "processed" / "ecb_exr_daily.csv"
OUT = ROOT / "video" / "data" / "inward_by_year.json"
FIRST_YEAR, LAST_YEAR = 2005, 2025
SERIES = "inward_total_net"


def load():
    fx = {
        r["date"]: float(r["jpy_per_usd_mabui_calc"])
        for r in csv.DictReader(FX.open(encoding="utf-8"))
        if r["jpy_per_usd_mabui_calc"]
    }
    weeks = list(csv.DictReader(MOF.open(encoding="utf-8")))
    return fx, weeks


def aggregate(fx, weeks, year_rule="start", rate_rule="mean"):
    days = sorted(fx)
    jpy = defaultdict(int)       # 億円
    usd = defaultdict(float)     # 10億ドル
    rate_sum, n = defaultdict(float), defaultdict(int)
    for w in weeks:
        s = dt.date.fromisoformat(w["week_start"])
        e = dt.date.fromisoformat(w["week_end"])
        year = {"start": s.year, "end": e.year, "thu": (s + dt.timedelta(days=4)).year}[year_rule]
        if not FIRST_YEAR <= year <= LAST_YEAR:
            continue
        if rate_rule == "mean":
            rs = [fx[k] for k in ((s + dt.timedelta(days=i)).isoformat() for i in range(7)) if k in fx]
            if not rs:
                raise ValueError(f"レートのない週: {w['week_start']}")  # 埋めない
            rate = statistics.mean(rs)
        else:
            rate = fx[days[bisect.bisect_right(days, e.isoformat()) - 1]]
        v = int(w[SERIES])
        jpy[year] += v
        usd[year] += v * 1e8 / rate / 1e9
        rate_sum[year] += rate
        n[year] += 1
    return jpy, usd, {y: rate_sum[y] / n[y] for y in n}, n


def rank(d, year):
    return sorted(d, key=lambda y: -d[y]).index(year) + 1


def main():
    fx, weeks = load()
    jpy, usd, avg_rate, n = aggregate(fx, weeks)
    years = list(range(FIRST_YEAR, LAST_YEAR + 1))

    robustness = []
    for yr in ("start", "end", "thu"):
        for rr in ("mean", "weekend"):
            j, u, _, _ = aggregate(fx, weeks, yr, rr)
            top_j = max(j, key=j.get)
            top_u = max(u, key=u.get)
            robustness.append({
                "year_rule": yr, "rate_rule": rr,
                "jpy_top": top_j, "jpy_rank_2025": rank(j, 2025),
                "usd_top": top_u, "usd_rank_2025": rank(u, 2025),
                "usd_2025_vs_top": round(u[2025] / u[top_u], 3),
            })

    out = {
        "title": "非居住者による日本の証券の買い越し（年計）— 円とドル",
        "series": SERIES,
        "method": __doc__.strip(),
        "sources": [
            "財務省「対外及び対内証券売買契約等の状況（週次・指定報告機関ベース）」",
            "ECB euro foreign exchange reference rates (Source: ECB statistics.)",
        ],
        "built_from": {
            "mof": json.loads((MOF.with_suffix(".meta.json")).read_text(encoding="utf-8"))["built_from_snapshot"],
            "ecb_latest_retrieved_at": json.loads((FX.with_suffix(".meta.json")).read_text(encoding="utf-8"))["latest_retrieved_at"],
        },
        "years": [
            {
                "year": y,
                "weeks": n[y],
                "jpy_trillion": round(jpy[y] / 1e4, 2),        # 兆円
                "usd_billion": round(usd[y], 1),               # 10億ドル
                "avg_jpy_per_usd": round(avg_rate[y], 2),
                "rank_jpy": rank(jpy, y),
                "rank_usd": rank(usd, y),
            }
            for y in years
        ],
        "robustness": robustness,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    y25 = next(r for r in out["years"] if r["year"] == 2025)
    print(f"[story] 2025: {y25['jpy_trillion']}兆円（円で{y25['rank_jpy']}位）/ "
          f"{y25['usd_billion']}十億ドル（ドルで{y25['rank_usd']}位）")
    for r in robustness:
        print("  ", r)


if __name__ == "__main__":
    main()
