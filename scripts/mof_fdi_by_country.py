"""対外・対内直接投資（国別・業種別、年次）の取得と加工。

財務省「対外・対内直接投資（地域別・業種別）」に掲載されている年次の Excel（日本銀行・財務省作成）。
- シート3：対外直接投資（日本 → 外国）国別・業種別
- シート4：対内直接投資（外国 → 日本）国別・業種別
値はネット（実行 − 回収）、億円。親子関係原則で集計（国際収支統計の直接投資とは一致しない）。

使い方:
    python scripts/mof_fdi_by_country.py fetch | build | all
依存: openpyxl==3.1.5（requirements.txt）
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys

import rawstore
from countries import iso3, norm

SOURCE_ID = "mof_fdi_by_country"
PAGE = "https://www.mof.go.jp/policy/international_policy/reference/balance_of_payments/bpfdii.htm"
BASE = "https://www.mof.go.jp/policy/international_policy/reference/balance_of_payments/revised/"
YEARS = range(2020, 2026)
SHEETS = {"outward": (2, "対外直接投資"), "inward": (3, "対内直接投資")}
HEADER_JA_ROW, HEADER_EN_ROW, FIRST_COL = 8, 10, 5
OUT_DIR = rawstore.ROOT / "data" / "processed"


class FormatChanged(Exception):
    pass


def reiwa(year: int) -> str:
    return "令和元年" if year == 2019 else f"令和{year - 2018}年"


# ---------------------------------------------------------------- fetch


def fetch():
    metas = rawstore.snapshots(SOURCE_ID)
    for year in YEARS:
        url = f"{BASE}fdi{year}.xlsx"
        body, headers = rawstore.http_get(url)
        parse(body, year)
        sha = hashlib.sha256(body).hexdigest()
        same = [m for m in metas if m.get("year") == year]
        if same and same[-1]["sha256"] == sha:
            print(f"[fetch] {year}年: 変化なし")
            continue
        rawstore.save_snapshot(SOURCE_ID, body, f"fdi{year}.xlsx",
                               {"url": url, "page": PAGE, "year": year, **headers}, rawstore.now_utc())


# ---------------------------------------------------------------- parse


def _cell(v):
    """数値 / 'X'（秘匿：報告3件未満）/ '.'（該当なし）を区別して返す。値は埋めない。"""
    if v is None:
        return None, "blank"
    s = str(v).strip()
    if s in ("X", "Ｘ"):
        return None, "confidential"
    if s in (".", "．"):
        return None, "none"
    try:
        return float(s), "ok"
    except ValueError:
        raise FormatChanged(f"数値として読めません: {v!r}")


def parse(body: bytes, year: int) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    first = "".join(str(v) for v in next(wb.worksheets[0].iter_rows(values_only=True)) if v)
    if reiwa(year) not in first:
        raise FormatChanged(f"{year}年（{reiwa(year)}）の表ではありません: {first[:30]}")
    out = []
    for direction, (si, title) in SHEETS.items():
        rows = list(wb.worksheets[si].iter_rows(values_only=True))
        head = "".join(str(v) for r in rows[:8] for v in r if v)
        if title not in head or "国別" not in head:
            raise FormatChanged(f"シート{si + 1}が {title}（国別）ではありません")
        ja = [str(v).replace("\n", "") if v else "" for v in rows[HEADER_JA_ROW]]
        en = [norm(v) if v else "" for v in rows[HEADER_EN_ROW]]
        # 業種の行：日本語ラベルの行（次の行が英語ラベル）
        industries = []
        for i in range(HEADER_EN_ROW + 1, len(rows) - 1):
            lab = "".join(str(v) for v in rows[i][:5] if v).strip()
            if lab.startswith("(備考") or lab.startswith("（備考"):
                break
            if lab and not lab.isascii():
                en_lab = "".join(str(v) for v in rows[i + 1][:5] if v).strip()
                industries.append((i, lab, en_lab))
        if not any(l == "合計" for _, l, _ in industries):
            raise FormatChanged(f"シート{si + 1}に合計の行がありません")
        for c in range(FIRST_COL, len(en)):
            if not en[c]:
                continue
            code = iso3(en[c])
            for i, lab, en_lab in industries:
                v, status = _cell(rows[i][c] if c < len(rows[i]) else None)
                out.append({
                    "year": year, "direction": direction, "name_ja": ja[c], "name_en": en[c], "iso3": code,
                    "industry_ja": lab.replace(" ", "").replace("　", ""), "industry_en": en_lab,
                    "value_oku_yen": v, "status": status,
                })
    return out


def world_totals(body: bytes) -> dict:
    """シート1・2の「全世界」の合計（検算用）。"""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    res = {}
    for direction, si in (("outward", 0), ("inward", 1)):
        for r in wb.worksheets[si].iter_rows(values_only=True):
            lab = "".join(str(v) for v in r[:5] if v).strip()
            if lab == "合計":
                res[direction] = float(r[5])
                break
    return res


# ---------------------------------------------------------------- build


def build():
    metas = rawstore.snapshots(SOURCE_ID)
    if not metas:
        sys.exit("[build] data/raw に元データがありません。先に fetch してください。")
    latest = {}
    for m in metas:
        latest[m["year"]] = m
    rows, checks = [], []
    for year in sorted(latest):
        body = rawstore.read_snapshot(latest[year])
        r = parse(body, year)
        rows += r
        wt = world_totals(body)
        for d in ("outward", "inward"):
            listed = sum(x["value_oku_yen"] or 0 for x in r
                         if x["direction"] == d and x["industry_ja"] == "合計")
            checks.append({"year": year, "direction": d, "world_total": wt.get(d),
                           "sum_of_listed_countries": round(listed, 1),
                           "not_listed_or_confidential": round(wt.get(d, 0) - listed, 1)})

    cols = ["year", "direction", "name_ja", "name_en", "iso3", "industry_ja", "industry_en", "value_oku_yen", "status"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / f"{SOURCE_ID}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for x in rows:
            w.writerow({k: ("" if x[k] is None else (round(x[k], 4) if isinstance(x[k], float) else x[k])) for k in cols})
    meta = {
        "source_id": SOURCE_ID,
        "title_ja": "対外・対内直接投資（国別・業種別、年次）",
        "publisher": "日本銀行・財務省（財務省ホームページに掲載）",
        "source_page": PAGE,
        "license": "公共データ利用規約（第1.0版）(PDL1.0)",
        "attribution": "出典：財務省・日本銀行「対外・対内直接投資（地域別・業種別）」を加工して作成",
        "unit": "100 million JPY (億円), net (実行−回収), calendar year",
        "principle": "親子関係原則（directional principle）。国際収支統計の直接投資（資産負債原則）とは一致しない",
        "status_codes": {"ok": "数値", "confidential": "X（報告3件未満で秘匿）", "none": "．（該当なし）", "blank": "空欄"},
        "years": sorted(latest),
        "snapshots_used": {y: latest[y]["file"] for y in sorted(latest)},
        "world_vs_listed": checks,
        "definitions": f"sources/{SOURCE_ID}.md",
    }
    (OUT_DIR / f"{SOURCE_ID}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n_tot = sum(1 for x in rows if x["industry_ja"] == "合計")
    print(f"[build] {len(latest)}年分 / 行 {len(rows)}（国×合計 {n_tot}）")
    for c in checks:
        print(f"  {c['year']} {c['direction']:8s} 全世界 {c['world_total']:>10.0f} / 国の和 {c['sum_of_listed_countries']:>10.0f} / 差 {c['not_listed_or_confidential']:>8.0f}")


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
