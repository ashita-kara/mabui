"""地図の試作用データ：日本の投資家が持つ外国の証券の残高（国別・年末）を、円とドルで。

入力:
    data/processed/boj_portfolio_assets_by_country.csv  日本銀行（億円、年末残高、発行者の所在国別）
    data/processed/ecb_exr_daily.csv                    ECB 参照レートから計算した円ドル
    video/data/geo/raw/ne_110m_admin_0_countries.geojson   Natural Earth（陸地の点を作る）
    video/data/geo/raw/ne_50m_admin_0_countries.geojson    Natural Earth（国の位置：LABEL_X/Y）
    video/data/geo/raw/ne_50m_admin_0_tiny_countries.geojson  Natural Earth（小さな地域の位置）
出力:
    video/data/holdings_map.json

方法:
- ドル換算は、その年の最後の ECB 営業日の円ドル（MABUI 計算値）で割る。日本銀行の年末評価に使われた
  レートそのものではないので近似。
- 国の位置は Natural Earth の LABEL_X/LABEL_Y（地図上で国名を置く位置）。無い小地域は tiny_countries の点。
- 陸地の点：1.5度ごとの格子点のうち、陸地（110m の国境ポリゴンの内側）にあるもの。南極（南緯60度以南）は除く。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOLD = ROOT / "data" / "processed" / "boj_portfolio_assets_by_country.csv"
FX = ROOT / "data" / "processed" / "ecb_exr_daily.csv"
GEO = ROOT / "video" / "data" / "geo" / "raw"
OUT = ROOT / "video" / "data" / "holdings_map.json"
GRID = 1.5


def point_in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def land_points():
    g = json.loads((GEO / "ne_110m_admin_0_countries.geojson").read_text(encoding="utf-8"))
    polys = []
    for f in g["features"]:
        geom = f["geometry"]
        parts = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for p in parts:
            ring = p[0]
            xs = [c[0] for c in ring]
            ys = [c[1] for c in ring]
            polys.append((min(xs), max(xs), min(ys), max(ys), p))
    pts = []
    lat = 84.0
    while lat > -60:
        lon = -180.0 + GRID / 2
        while lon < 180:
            for x0, x1, y0, y1, p in polys:
                if x0 <= lon <= x1 and y0 <= lat <= y1 and point_in_ring(lon, lat, p[0]) \
                        and not any(point_in_ring(lon, lat, h) for h in p[1:]):
                    pts.append([round(lon, 2), round(lat, 2)])
                    break
            lon += GRID
        lat -= GRID
    return pts


def country_points():
    pos = {}
    g = json.loads((GEO / "ne_50m_admin_0_countries.geojson").read_text(encoding="utf-8"))
    for f in g["features"]:
        p = f["properties"]
        for k in ("ADM0_A3", "ISO_A3", "ISO_A3_EH"):
            if p.get(k) and p[k] != "-99":
                pos.setdefault(p[k], (p["LABEL_X"], p["LABEL_Y"]))
    t = json.loads((GEO / "ne_50m_admin_0_tiny_countries.geojson").read_text(encoding="utf-8"))
    for f in t["features"]:
        pos.setdefault(f["properties"]["ADM0_A3"], tuple(f["geometry"]["coordinates"]))
    return pos


def year_end_rates(years):
    fx = [(r["date"], float(r["jpy_per_usd_mabui_calc"]))
          for r in csv.DictReader(FX.open(encoding="utf-8")) if r["jpy_per_usd_mabui_calc"]]
    out = {}
    for y in years:
        d, v = max((d, v) for d, v in fx if d <= f"{y}-12-31")
        out[y] = {"date": d, "jpy_per_usd": v}
    return out


def main():
    rows = list(csv.DictReader(HOLD.open(encoding="utf-8")))
    years = sorted({int(r["year"]) for r in rows})
    rates = year_end_rates(years)
    pos = country_points()

    countries = {}
    for r in rows:
        if r["level"] != "country" or not r["total"]:
            continue
        iso = r["iso3"]
        if iso not in pos:
            raise SystemExit(f"位置がありません: {iso} {r['name_ja']}")
        c = countries.setdefault(iso, {
            "iso3": iso, "name_ja": r["name_ja"], "name_en": r["name_en"],
            "lon": round(pos[iso][0], 3), "lat": round(pos[iso][1], 3), "jpy_oku": {}, "usd_oku": {},
        })
        y = int(r["year"])
        v = float(r["total"])
        c["jpy_oku"][y] = round(v, 1)                                  # 億円
        c["usd_oku"][y] = round(v * 1e8 / rates[y]["jpy_per_usd"] / 1e8, 2)  # 億ドル

    totals = {int(r["year"]): float(r["total"]) for r in rows if r["level"] == "total"}
    unlocated = {int(r["year"]): float(r["total"]) for r in rows if r["level"] == "region" and r["name_ja"] == "国際機関"}
    out = {
        "title": "日本の投資家が持つ外国の証券（年末残高、発行者の所在国別）",
        "method": __doc__.strip(),
        "sources": [
            "日本銀行・財務省「証券投資残高地域別統計（資産）（全地域ベース）」",
            "ECB euro foreign exchange reference rates (Source: ECB statistics.)",
            "Natural Earth (public domain) — 地図",
        ],
        "years": years,
        "year_end_rates": rates,
        "total_jpy_oku": {y: round(totals[y], 1) for y in years},
        "total_usd_oku": {y: round(totals[y] / rates[y]["jpy_per_usd"], 1) for y in years},
        "international_org_jpy_oku": {y: round(unlocated.get(y, 0), 1) for y in years},
        "countries": sorted(countries.values(), key=lambda c: -c["jpy_oku"].get(years[-1], 0)),
        "land": land_points(),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[map] 国 {len(countries)} / 陸地の点 {len(out['land'])}")
    for y in years:
        print(f"  {y}: {out['total_jpy_oku'][y] / 1e4:.1f}兆円 / {out['total_usd_oku'][y] / 1e4:.2f}兆ドル "
              f"(1ドル={rates[y]['jpy_per_usd']:.2f}円 {rates[y]['date']})")
    for c in out["countries"][:8]:
        print("  ", c["name_ja"], c["jpy_oku"])


if __name__ == "__main__":
    main()
