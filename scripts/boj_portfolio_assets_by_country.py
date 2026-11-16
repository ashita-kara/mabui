"""証券投資残高地域別統計（資産）（全地域ベース）の取得と加工。

日本の居住者が持っている外国の証券（株式・投資ファンド持分・債券）の年末残高を、
証券の「発行者の所在国」別にまとめた統計。日本銀行が作成し、財務省のページに掲載されている。

使い方:
    python scripts/boj_portfolio_assets_by_country.py fetch
    python scripts/boj_portfolio_assets_by_country.py build
    python scripts/boj_portfolio_assets_by_country.py all

依存: xlrd==2.0.1（古い .xls 形式を読むため。requirements.txt）
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys

import rawstore

SOURCE_ID = "boj_portfolio_assets_by_country"
PAGE = "https://www.mof.go.jp/policy/international_policy/reference/iip/data/index.htm"
BASE = "https://www.mof.go.jp/policy/international_policy/reference/iip/"
# 掲載場所が年によって違う（古い年は一つ上の階層）
FILES = {
    2021: "rdip_all2021.xls",
    2022: "rdip_all2022.xls",
    2023: "rdip_all2023.xls",
    2024: "data/rdip_all2024.xls",
    2025: "data/rdip_all2025.xls",
}
SHEET_INDEX = 1  # 2枚目が証券投資（1枚目は直接投資）
OUT_DIR = rawstore.ROOT / "data" / "processed"

# 列（0始まり）: 2=証券投資合計, 3=株式・投資ファンド持分, 4=株式, 5=投資ファンド持分, 6=債券, 7=中長期債, 8=短期債
VALUE_COLS = {
    "total": 2,
    "equity_and_fund": 3,
    "equity": 4,
    "investment_fund": 5,
    "debt": 6,
    "debt_longterm": 7,
    "debt_shortterm": 8,
}
EXPECTED_HEADER = {13: {4: "株式", 5: "投資ファンド持分", 7: "中長期債", 8: "短期債"}}

# 元データの英語名 → ISO 3166-1 alpha-3（地図に置くため）。未登録の名前が出たら止まる。
ISO3 = {
    "Albania": "ALB", "Andorra": "AND", "Angola": "AGO", "Argentina": "ARG", "Armenia": "ARM",
    "Australia": "AUS", "Austria": "AUT", "Azerbaijan": "AZE", "Bahamas": "BHS", "Bahrain": "BHR",
    "Bangladesh": "BGD", "Barbados": "BRB", "Belarus": "BLR", "Belgium": "BEL", "Benin": "BEN",
    "Bermuda": "BMU", "Bolivia": "BOL", "Brazil": "BRA", "British Virgin Islands": "VGB",
    "Bulgaria": "BGR", "Cameroon": "CMR", "Canada": "CAN", "Cayman Islands": "CYM", "Chile": "CHL",
    "Colombia": "COL", "Costa Rica": "CRI", "Cote d’Ivoire": "CIV", "Croatia": "HRV", "Cuba": "CUB",
    "Curacao": "CUW", "Cyprus": "CYP", "Czech": "CZE", "Denmark": "DNK", "Dominican Republic": "DOM",
    "Ecuador": "ECU", "Egypt": "EGY", "El Salvador": "SLV", "Estonia": "EST", "Ethiopia": "ETH",
    "Finland": "FIN", "France": "FRA", "Gabon": "GAB", "Germany": "DEU", "Ghana": "GHA",
    "Gibraltar": "GIB", "Greece": "GRC", "Guatemala": "GTM", "Guernsey": "GGY", "Honduras": "HND",
    "Hong Kong": "HKG", "Hungary": "HUN", "Iceland": "ISL", "India": "IND", "Indonesia": "IDN",
    "Iraq": "IRQ", "Ireland": "IRL", "Isle of Man": "IMN", "Israel": "ISR", "Italy": "ITA",
    "Jamaica": "JAM", "Jersey": "JEY", "Jordan": "JOR", "Kazakhstan": "KAZ", "Kenya": "KEN",
    "Kuwait": "KWT", "Kyrgyz Republic": "KGZ", "Latvia": "LVA", "Lebanon": "LBN", "Liberia": "LBR",
    "Liechtenstein": "LIE", "Lithuania": "LTU", "Luxembourg": "LUX", "Macau": "MAC", "Malaysia": "MYS",
    "Malta": "MLT", "Marshall": "MHL", "Mauritius": "MUS", "Mexico": "MEX", "Mongolia": "MNG",
    "Montenegro": "MNE", "Morocco": "MAR", "Mozambique": "MOZ", "Namibia": "NAM", "Nepal": "NPL",
    "Netherlands": "NLD", "New Zealand": "NZL", "Nigeria": "NGA", "North Macedonia": "MKD",
    "Norway": "NOR", "Oman": "OMN", "Pakistan": "PAK", "Panama": "PAN", "Papua New Guinea": "PNG",
    "Paraguay": "PRY", "People’s Republic of China": "CHN", "Peru": "PER", "Philippines": "PHL",
    "Poland": "POL", "Portugal": "PRT", "Puerto Rico": "PRI", "Qatar": "QAT",
    "Republic of Congo": "COG", "Republic of Korea": "KOR", "Republic of South Africa": "ZAF",
    "Romania": "ROU", "Russia": "RUS", "Rwanda": "RWA", "Saint Lucia": "LCA", "Saudi Arabia": "SAU",
    "Senegal": "SEN", "Serbia": "SRB", "Singapore": "SGP", "Slovakia": "SVK", "Slovenia": "SVN",
    "Spain": "ESP", "Sri Lanka": "LKA", "Suriname": "SUR", "Sweden": "SWE", "Switzerland": "CHE",
    "Taiwan": "TWN", "Tajikistan": "TJK", "Thailand": "THA", "Togo": "TGO",
    "Trinidad and Tobago": "TTO", "Tunisia": "TUN", "Turkey": "TUR", "Turkmenistan": "TKM",
    "Ukraine": "UKR", "United Arab Emirates": "ARE", "United Kingdom": "GBR",
    "United States Virgin Islands": "VIR", "United States of America": "USA", "Uruguay": "URY",
    "Uzbekistan": "UZB", "Vanuatu": "VUT", "Venezuela": "VEN", "Viet Nam": "VNM", "Zambia": "ZMB",
}


class FormatChanged(Exception):
    pass


# ---------------------------------------------------------------- fetch


def fetch():
    metas = rawstore.snapshots(SOURCE_ID)
    for year, rel in FILES.items():
        url = BASE + rel
        body, headers = rawstore.http_get(url)
        parse(body, year)  # 保存前に読めるか確かめる
        sha = hashlib.sha256(body).hexdigest()
        same = [m for m in metas if m.get("year") == year]
        if same and same[-1]["sha256"] == sha:
            print(f"[fetch] {year}年末: 変化なし")
            continue
        rawstore.save_snapshot(
            SOURCE_ID, body, f"rdip_all{year}.xls",
            {"url": url, "page": PAGE, "year": year, **headers},
            rawstore.now_utc(),
        )


# ---------------------------------------------------------------- parse


def _num(v):
    s = str(v).strip()
    if s in ("", "--", "-", "…"):
        return None  # 該当なし・秘匿などは空欄のまま（埋めない）
    try:
        return float(s)
    except ValueError:
        raise FormatChanged(f"数値として読めません: {v!r}")


def parse(body: bytes, year: int) -> list[dict]:
    import xlrd  # 遅延 import（fetch/build 以外では不要）

    book = xlrd.open_workbook(file_contents=body)
    sh = book.sheet_by_index(SHEET_INDEX)
    if "証券投資残高地域別統計" not in "".join(str(c.value) for c in sh.row(0)):
        raise FormatChanged("2枚目が証券投資残高の表ではありません")
    if f"{year}年末" not in "".join(str(c.value) for c in sh.row(1)):
        raise FormatChanged(f"{year}年末の表ではありません")
    for r, cols in EXPECTED_HEADER.items():
        for c, word in cols.items():
            if str(sh.cell_value(r, c)).strip() != word:
                raise FormatChanged(f"見出し({r},{c})が {word} ではありません")

    rows, region = [], None
    for r in range(sh.nrows):
        a, b = str(sh.cell_value(r, 0)).strip(), str(sh.cell_value(r, 1)).strip()
        if a.startswith("（注"):
            break
        if a == "合計":
            level, name_ja = "total", "合計"
            name_en = "Total"
        elif a and not b and r > 14:
            level, name_ja = "region", a
            name_en = str(sh.cell_value(r, 9)).strip()
            region = (a, name_en)
        elif b and region:
            level, name_ja = "country", b
            name_en = str(sh.cell_value(r, 10)).strip()
        else:
            continue
        rec = {
            "year": year,
            "level": level,
            "region_ja": region[0] if region and level != "total" else "",
            "region_en": region[1] if region and level != "total" else "",
            "name_ja": name_ja,
            "name_en": name_en,
            "iso3": "",
        }
        if level == "country":
            if name_en not in ISO3:
                raise FormatChanged(f"ISO3 未登録の国名: {name_en!r}（{name_ja}）")
            rec["iso3"] = ISO3[name_en]
        for k, c in VALUE_COLS.items():
            rec[k] = _num(sh.cell_value(r, c))
        rows.append(rec)
    if not rows or rows[0]["level"] != "total":
        raise FormatChanged("合計の行が見つかりません")
    return rows


def check(rows: list[dict]) -> list[str]:
    """地域の小計＝その地域の国の和、合計＝地域の和 を確かめる（±1億円）。値は直さない。"""
    issues = []
    total = next(r for r in rows if r["level"] == "total")
    regions = [r for r in rows if r["level"] == "region"]
    s = sum(r["total"] or 0 for r in regions)
    if abs(s - total["total"]) > 1:
        issues.append(f"{total['year']}: 地域の和 {s:.0f} ≠ 合計 {total['total']:.0f}")
    for reg in regions:
        cs = sum(r["total"] or 0 for r in rows if r["level"] == "country" and r["region_ja"] == reg["name_ja"])
        if reg["name_ja"] != "国際機関" and abs(cs - reg["total"]) > 1:
            issues.append(f"{reg['year']} {reg['name_ja']}: 国の和 {cs:.0f} ≠ 小計 {reg['total']:.0f}")
    return issues


# ---------------------------------------------------------------- build


def build():
    metas = rawstore.snapshots(SOURCE_ID)
    if not metas:
        sys.exit("[build] data/raw に元データがありません。先に fetch してください。")
    latest = {}
    for m in metas:  # 年ごとに最新のスナップショットを使う（古いものも raw に残る）
        latest[m["year"]] = m
    all_rows, issues = [], []
    for year in sorted(latest):
        rows = parse(rawstore.read_snapshot(latest[year]), year)
        issues += check(rows)
        all_rows += rows

    cols = ["year", "level", "region_ja", "region_en", "name_ja", "name_en", "iso3", *VALUE_COLS]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / f"{SOURCE_ID}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in all_rows:
            w.writerow({k: ("" if r[k] is None else (round(r[k], 4) if isinstance(r[k], float) else r[k])) for k in cols})

    meta = {
        "source_id": SOURCE_ID,
        "title_ja": "証券投資残高地域別統計（資産）（全地域ベース）",
        "title_en": "Regional Portfolio Investment Position (Assets) (all countries basis)",
        "publisher": "日本銀行（財務省ホームページに掲載）",
        "source_page": PAGE,
        "license": "公共データ利用規約（第1.0版）(PDL1.0)（財務省サイト掲載コンテンツ）",
        "attribution": "出典：日本銀行・財務省「証券投資残高地域別統計（資産）」を加工して作成",
        "unit": "100 million JPY (億円), year-end position",
        "classification": "発行者の所在国別 (residence of the issuer)",
        "years": sorted(latest),
        "snapshots_used": {y: latest[y]["file"] for y in sorted(latest)},
        "consistency_warnings": issues,
        "definitions": f"sources/{SOURCE_ID}.md",
    }
    (OUT_DIR / f"{SOURCE_ID}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n_c = sum(1 for r in all_rows if r["level"] == "country")
    print(f"[build] {len(latest)}年分 / 国の行 {n_c} / 検算の警告 {len(issues)}件")
    for i in issues[:10]:
        print("  警告", i)


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "all"
    if cmd not in ("fetch", "build", "all"):
        sys.exit(__doc__)
    if cmd in ("fetch", "all"):
        fetch()
    if cmd in ("build", "all"):
        build()


if __name__ == "__main__":
    main(sys.argv)
