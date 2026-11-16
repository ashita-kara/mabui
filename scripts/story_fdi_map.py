"""地図の試作用データ：日本からの直接投資（国別、年次、ネット）。

入力: data/processed/mof_fdi_by_country.csv（合計の行、outward）
      Natural Earth（国の位置・陸地の点）— story_holdings_map.py と同じ方法
出力: video/data/fdi_map.json
秘匿（X）・該当なし（.）は 0 にせず、null のまま渡す（描画では粒を出さない）。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from story_holdings_map import country_points, land_points

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "processed" / "mof_fdi_by_country.csv"
OUT = ROOT / "video" / "data" / "fdi_map.json"


def main():
    rows = [r for r in csv.DictReader(SRC.open(encoding="utf-8"))
            if r["direction"] == "outward" and r["industry_ja"] == "合計"]
    years = sorted({int(r["year"]) for r in rows})
    pos = country_points()
    countries = {}
    for r in rows:
        iso = r["iso3"]
        if iso not in pos:
            raise SystemExit(f"位置がありません: {iso} {r['name_ja']}")
        c = countries.setdefault(iso, {"iso3": iso, "name_ja": r["name_ja"], "lon": round(pos[iso][0], 3),
                                       "lat": round(pos[iso][1], 3), "net_oku": {}, "status": {}})
        y = int(r["year"])
        c["net_oku"][y] = round(float(r["value_oku_yen"]), 1) if r["value_oku_yen"] else None
        c["status"][y] = r["status"]
    world = {}
    for r in rows:
        if r["value_oku_yen"]:
            world[int(r["year"])] = world.get(int(r["year"]), 0) + float(r["value_oku_yen"])
    out = {
        "title": "日本からの直接投資（国別、ネット、年次）",
        "source": "財務省・日本銀行「対外・対内直接投資（地域別・業種別）」",
        "unit": "億円（実行−回収）",
        "years": years,
        "world_net_oku": {y: round(v, 1) for y, v in world.items()},
        "countries": sorted(countries.values(), key=lambda c: -abs(c["net_oku"].get(years[-1]) or 0)),
        "land": land_points(),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[fdi-map] 国 {len(countries)} / 年 {years}")


if __name__ == "__main__":
    main()
