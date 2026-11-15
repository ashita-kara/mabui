"""財務省「対外及び対内証券売買契約等の状況（週次・指定報告機関ベース）」の取得と加工。

使い方:
    python scripts/mof_itn_weekly.py fetch   # 元データを取得し、変化があれば data/raw/ に保存
    python scripts/mof_itn_weekly.py build   # data/raw/ の全スナップショットから加工データを作る
    python scripts/mof_itn_weekly.py all     # fetch → build

データ憲章（DATA_CHARTER.md）に従い:
- 元データは加工せず、取得日時つきのファイル名で保存する（上書きしない）
- 加工はこのコードだけで行い、raw から誰でも同じ結果を再現できる
- 欠けている値は埋めない。検算が合わない行は警告として記録し、値は直さない
- 過去の値の改定は、スナップショット同士の比較で改定履歴に残す

標準ライブラリのみを使う。
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import re
import sys
from pathlib import Path

import rawstore

SOURCE_ID = "mof_itn_weekly"
SOURCE_URL = (
    "https://www.mof.go.jp/policy/international_policy/reference/"
    "itn_transactions_in_securities/week.csv"
)
SOURCE_PAGE = (
    "https://www.mof.go.jp/policy/international_policy/reference/"
    "itn_transactions_in_securities/index.htm"
)
ENCODING = "cp932"

ROOT = rawstore.ROOT
RAW_DIR = rawstore.raw_dir(SOURCE_ID)
OUT_DIR = ROOT / "data" / "processed"

# 元CSVの22列（期間の列を除く）を、この順で読む。
# outward = 対外証券投資（居住者による外国証券の取得・処分）
# inward  = 対内証券投資（非居住者による日本の証券の取得・処分）
_SIDE_COLUMNS = [
    "equity_acquisition",
    "equity_disposition",
    "equity_net",
    "longterm_debt_acquisition",
    "longterm_debt_disposition",
    "longterm_debt_net",
    "subtotal_net",
    "shortterm_debt_acquisition",
    "shortterm_debt_disposition",
    "shortterm_debt_net",
    "total_net",
]
VALUE_COLUMNS = [f"outward_{c}" for c in _SIDE_COLUMNS] + [
    f"inward_{c}" for c in _SIDE_COLUMNS
]
OUTPUT_COLUMNS = ["week_start", "week_end", "period_label"] + VALUE_COLUMNS

# 元CSVの書式が変わったら、黙って読み違えずに止まるための目印
_EXPECTED_HEADER_MARKERS = ["対外証券投資", "対内証券投資", "取得", "処分", "ネット", "億円"]

_PERIOD_RE = re.compile(
    r"^\s*(\d{4})．\s*(\d{1,2})．\s*(\d{1,2})\s*[～〜~]\s*"
    r"(?:(\d{4})．)?\s*(\d{1,2})．\s*(\d{1,2})\s*$"
)


# ---------------------------------------------------------------- fetch


def fetch() -> Path | None:
    """元データを取得する。前回保存分と中身が同じなら保存せず None を返す。"""
    body, headers = rawstore.http_get(SOURCE_URL)
    retrieved_at = rawstore.now_utc()
    sha256 = hashlib.sha256(body).hexdigest()

    # 取得できた中身が想定どおりか、保存前に確かめる
    parse(body)

    metas = rawstore.snapshots(SOURCE_ID)
    if metas and metas[-1]["sha256"] == sha256:
        print(f"[fetch] 変化なし（{metas[-1]['file']} と同一）")
        return None

    return rawstore.save_snapshot(
        SOURCE_ID,
        body,
        "week.csv",
        {
            "url": SOURCE_URL,
            **headers,
            "encoding": ENCODING,
            "publisher_final_update": _final_update_label(body),
        },
        retrieved_at,
    )


def _final_update_label(body: bytes) -> str | None:
    first = body.decode(ENCODING).splitlines()[0]
    m = re.search(r"最終更新日\s*([^,]+)", first)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------- parse


class FormatChanged(Exception):
    """元CSVの書式が想定と違う。"""


def parse_period(label: str) -> tuple[dt.date, dt.date]:
    m = _PERIOD_RE.match(label)
    if not m:
        raise FormatChanged(f"期間の書式を読めません: {label!r}")
    y1, m1, d1, y2, m2, d2 = m.groups()
    start = dt.date(int(y1), int(m1), int(d1))
    end_year = int(y2) if y2 else int(y1)
    end = dt.date(end_year, int(m2), int(d2))
    if end < start:  # 年の書かれていない年またぎ
        end = dt.date(end_year + 1, int(m2), int(d2))
    if (end - start).days != 6:
        raise FormatChanged(f"7日間ではない期間: {label!r} ({start}〜{end})")
    return start, end


def parse_number(text: str) -> int | None:
    t = text.strip().replace(",", "").replace("－", "-").replace("−", "-")
    if t == "":
        return None  # 欠損は欠損のまま
    if not re.fullmatch(r"-?\d+", t):
        raise FormatChanged(f"数値として読めません: {text!r}")
    return int(t)


def parse(body: bytes) -> list[dict]:
    text = body.decode(ENCODING)
    head = text[:4000]
    missing = [w for w in _EXPECTED_HEADER_MARKERS if w not in head]
    if missing:
        raise FormatChanged(f"見出しに想定の語がありません: {missing}")

    rows = []
    for rec in csv.reader(io.StringIO(text)):
        if not rec or not re.match(r"^\s*\d{4}．", rec[0]):
            continue
        if len(rec) < 1 + len(VALUE_COLUMNS):
            raise FormatChanged(f"列数が足りません（{len(rec)}列）: {rec[0]!r}")
        start, end = parse_period(rec[0])
        row = {
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "period_label": rec[0].strip(),
        }
        for col, cell in zip(VALUE_COLUMNS, rec[1 : 1 + len(VALUE_COLUMNS)]):
            row[col] = parse_number(cell)
        rows.append(row)

    if not rows:
        raise FormatChanged("データ行が1行もありません")
    starts = [r["week_start"] for r in rows]
    if len(set(starts)) != len(starts):
        raise FormatChanged("同じ週が重複しています")
    if starts != sorted(starts):
        raise FormatChanged("週が時系列順に並んでいません")
    return rows


# ---------------------------------------------------------------- checks


def check_row(row: dict) -> list[str]:
    """元データ自身の内訳と合計が合うかを確かめる（四捨五入のため ±2 億円まで許容）。

    値は直さない。合わなければ警告として残すだけ。
    """
    tol = 2
    issues = []

    def v(name):
        return row[name]

    for side in ("outward", "inward"):
        for kind in ("equity", "longterm_debt", "shortterm_debt"):
            a, d, n = (v(f"{side}_{kind}_{x}") for x in ("acquisition", "disposition", "net"))
            if None not in (a, d, n) and abs((a - d) - n) > tol:
                issues.append(f"{side}_{kind}: 取得-処分={a - d} ≠ ネット={n}")
        e, lt, sub = v(f"{side}_equity_net"), v(f"{side}_longterm_debt_net"), v(f"{side}_subtotal_net")
        if None not in (e, lt, sub) and abs(e + lt - sub) > tol:
            issues.append(f"{side}: 株式+中長期債={e + lt} ≠ 小計={sub}")
        st, tot = v(f"{side}_shortterm_debt_net"), v(f"{side}_total_net")
        if None not in (sub, st, tot) and abs(sub + st - tot) > tol:
            issues.append(f"{side}: 小計+短期債={sub + st} ≠ 合計={tot}")
    return issues


# ---------------------------------------------------------------- build


def build() -> None:
    metas = rawstore.snapshots(SOURCE_ID)
    if not metas:
        sys.exit("[build] data/raw に元データがありません。先に fetch してください。")

    # すべてのスナップショットを古い順に読み、前回との差を改定履歴にする
    revisions = []
    prev: dict[str, dict] | None = None
    for meta in metas:
        rows = parse(rawstore.read_snapshot(meta))
        cur = {r["week_start"]: r for r in rows}
        if prev is not None:
            for week, old in prev.items():
                new = cur.get(week)
                if new is None:
                    revisions.append(_rev(meta, week, "(row)", "present", "removed"))
                    continue
                for col in VALUE_COLUMNS:
                    if old[col] != new[col]:
                        revisions.append(_rev(meta, week, col, old[col], new[col]))
        prev = cur

    latest = metas[-1]
    rows = list(prev.values())

    warnings = []
    for r in rows:
        for issue in check_row(r):
            warnings.append({"week_start": r["week_start"], "issue": issue})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data_path = OUT_DIR / f"{SOURCE_ID}.csv"
    with data_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r[k] is None else r[k]) for k in OUTPUT_COLUMNS})

    rev_path = OUT_DIR / f"{SOURCE_ID}_revisions.csv"
    with rev_path.open("w", encoding="utf-8", newline="") as f:
        cols = ["detected_in_snapshot", "retrieved_at", "week_start", "column", "old", "new"]
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(revisions)

    meta_out = {
        "source_id": SOURCE_ID,
        "title_ja": "対外及び対内証券売買契約等の状況（週次・指定報告機関ベース）",
        "title_en": "International Transactions in Securities (Weekly; based on reports from designated major investors)",
        "publisher": "財務省 (Ministry of Finance, Japan)",
        "source_page": SOURCE_PAGE,
        "source_url": SOURCE_URL,
        "license": "公共データ利用規約（第1.0版）(PDL1.0)",
        "attribution": "出典：財務省「対外及び対内証券売買契約等の状況（週次・指定報告機関ベース）」を加工して作成",
        "unit": "100 million JPY (億円)",
        "sign": "net > 0 = 取得超 (net acquisition) / net < 0 = 処分超 (net disposition)",
        "built_from_snapshot": latest["file"],
        "retrieved_at": latest["retrieved_at"],
        "publisher_final_update": latest.get("publisher_final_update"),
        "raw_sha256": latest["sha256"],
        "snapshots_used": len(metas),
        "weeks": len(rows),
        "first_week_start": rows[0]["week_start"],
        "last_week_start": rows[-1]["week_start"],
        "revisions_detected": len(revisions),
        "consistency_warnings": warnings,
        "definitions": "sources/mof_itn_weekly.md",
    }
    (OUT_DIR / f"{SOURCE_ID}.meta.json").write_text(
        json.dumps(meta_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"[build] {len(rows)}週 ({rows[0]['week_start']}〜{rows[-1]['week_end']}) "
        f"/ 改定 {len(revisions)}件 / 検算の警告 {len(warnings)}件"
    )
    for wn in warnings[:10]:
        print(f"  警告 {wn['week_start']}: {wn['issue']}")


def _rev(meta: dict, week: str, col: str, old, new) -> dict:
    return {
        "detected_in_snapshot": meta["file"],
        "retrieved_at": meta["retrieved_at"],
        "week_start": week,
        "column": col,
        "old": "" if old is None else old,
        "new": "" if new is None else new,
    }


# ---------------------------------------------------------------- main


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else "all"
    if cmd in ("fetch", "all"):
        fetch()
    if cmd in ("build", "all"):
        build()
    if cmd not in ("fetch", "build", "all"):
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
