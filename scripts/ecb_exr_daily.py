"""ECB 為替参照レート（日次）の取得と加工：円・ドル（いずれも対ユーロ）。

使い方:
    python scripts/ecb_exr_daily.py fetch   # 取得し、新しい値・変わった値があれば data/raw/ に保存
    python scripts/ecb_exr_daily.py build   # data/raw/ の全スナップショットから加工データを作る
    python scripts/ecb_exr_daily.py all

取得の仕方:
- 初回は全期間（1999-01-04〜）を取得する。
- 2回目以降は直近 WINDOW_DAYS 日分だけを取得する（毎日全期間を保存すると容量が膨らむため）。
  それまでのスナップショットと比べて、新しい値も変わった値もなければ保存しない。
- build は全スナップショットを古い順に重ね、同じ日付の値が変わっていれば改定履歴に残す。

ECB の再利用条件により、ECB が公表した値はそのままの文字列で残す（丸め・換算をしない）。
円ドル（JPY per USD）は MABUI の計算値として別の列に置く。
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import sys
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

import rawstore

SOURCE_ID = "ecb_exr_daily"
CURRENCIES = ["JPY", "USD"]
API = "https://data-api.ecb.europa.eu/service/data/EXR/D.{cur}.EUR.SP00.A?format=csvdata"
SOURCE_PAGE = "https://data.ecb.europa.eu/data/datasets/EXR"
WINDOW_DAYS = 45
FIRST_DATE = "1999-01-04"

OUT_DIR = rawstore.ROOT / "data" / "processed"
REQUIRED_COLUMNS = [
    "KEY", "FREQ", "CURRENCY", "CURRENCY_DENOM", "EXR_TYPE", "EXR_SUFFIX",
    "TIME_PERIOD", "OBS_VALUE", "OBS_STATUS",
]


class FormatChanged(Exception):
    """ECB の返す CSV が想定と違う。"""


def api_url(start: str | None) -> str:
    url = API.format(cur="+".join(CURRENCIES))
    return url + (f"&startPeriod={start}" if start else "")


# ---------------------------------------------------------------- parse


def parse(body: bytes) -> dict[tuple[str, str], dict]:
    """{(日付, 通貨): {"value": 公表どおりの文字列, "status": OBS_STATUS}}"""
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise FormatChanged(f"列がありません: {missing}")
    obs = {}
    for r in reader:
        if (r["FREQ"], r["CURRENCY_DENOM"], r["EXR_TYPE"], r["EXR_SUFFIX"]) != ("D", "EUR", "SP00", "A"):
            raise FormatChanged(f"想定外の系列: {r['KEY']}")
        if r["CURRENCY"] not in CURRENCIES:
            raise FormatChanged(f"想定外の通貨: {r['CURRENCY']}")
        date = r["TIME_PERIOD"]
        dt.date.fromisoformat(date)  # 日付として読めなければ止まる
        value = r["OBS_VALUE"].strip()
        if value:
            try:
                if Decimal(value) <= 0:
                    raise FormatChanged(f"正でない値: {r['KEY']} {date} {value}")
            except InvalidOperation:
                raise FormatChanged(f"数値として読めません: {r['KEY']} {date} {value!r}")
        key = (date, r["CURRENCY"])
        if key in obs:
            raise FormatChanged(f"重複: {key}")
        obs[key] = {"value": value, "status": r["OBS_STATUS"].strip()}
    if not obs:
        raise FormatChanged("データ行が1行もありません")
    return obs


def merge_all(metas: list[dict]) -> tuple[dict, list[dict]]:
    """スナップショットを古い順に重ねる。値やステータスが変われば改定として記録する。"""
    state: dict[tuple[str, str], dict] = {}
    revisions = []
    for meta in metas:
        for key, new in sorted(parse(rawstore.read_snapshot(meta)).items()):
            old = state.get(key)
            if old is not None and old != new:
                revisions.append({
                    "detected_in_snapshot": meta["file"],
                    "retrieved_at": meta["retrieved_at"],
                    "date": key[0],
                    "currency": key[1],
                    "old_value": old["value"],
                    "new_value": new["value"],
                    "old_status": old["status"],
                    "new_status": new["status"],
                })
            state[key] = new
    return state, revisions


# ---------------------------------------------------------------- fetch


def fetch():
    metas = rawstore.snapshots(SOURCE_ID)
    if metas:
        start = (dt.date.today() - dt.timedelta(days=WINDOW_DAYS)).isoformat()
        mode = "window"
    else:
        start, mode = None, "full"
    url = api_url(start)
    body, headers = rawstore.http_get(url)
    retrieved_at = rawstore.now_utc()
    new_obs = parse(body)

    if metas:
        state, _ = merge_all(metas)
        changed = [k for k, v in new_obs.items() if state.get(k) != v]
        if not changed:
            print("[fetch] 新しい値・変わった値なし")
            return None
        print(f"[fetch] 新しい値・変わった値: {len(changed)}件（最新 {max(changed)[0]}）")

    return rawstore.save_snapshot(
        SOURCE_ID,
        body,
        f"exr_{mode}.csv",
        {
            "url": url,
            **headers,
            "encoding": "utf-8",
            "mode": mode,
            "start_period": start or FIRST_DATE,
        },
        retrieved_at,
    )


# ---------------------------------------------------------------- build


def build():
    metas = rawstore.snapshots(SOURCE_ID)
    if not metas:
        sys.exit("[build] data/raw に元データがありません。先に fetch してください。")
    state, revisions = merge_all(metas)

    dates = sorted({d for d, _ in state})
    rows = []
    for d in dates:
        jpy = state.get((d, "JPY"), {})
        usd = state.get((d, "USD"), {})
        rows.append({
            "date": d,
            "jpy_per_eur": jpy.get("value", ""),
            "jpy_per_eur_status": jpy.get("status", ""),
            "usd_per_eur": usd.get("value", ""),
            "usd_per_eur_status": usd.get("status", ""),
            "jpy_per_usd_mabui_calc": _cross(jpy.get("value"), usd.get("value")),
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / f"{SOURCE_ID}.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    rev_cols = ["detected_in_snapshot", "retrieved_at", "date", "currency",
                "old_value", "new_value", "old_status", "new_status"]
    with (OUT_DIR / f"{SOURCE_ID}_revisions.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rev_cols, lineterminator="\n")
        w.writeheader()
        w.writerows(revisions)

    statuses = {}
    for v in state.values():
        statuses[v["status"]] = statuses.get(v["status"], 0) + 1
    no_value = [r["date"] for r in rows if not r["jpy_per_eur"] and not r["usd_per_eur"]]
    one_side = [r["date"] for r in rows if bool(r["jpy_per_eur"]) != bool(r["usd_per_eur"])]

    latest = metas[-1]
    meta_out = {
        "source_id": SOURCE_ID,
        "title_en": "ECB euro foreign exchange reference rates (daily)",
        "title_ja": "ECB ユーロ為替参照レート（日次）",
        "publisher": "European Central Bank",
        "source_page": SOURCE_PAGE,
        "series": [f"EXR.D.{c}.EUR.SP00.A" for c in CURRENCIES],
        "license": "ESCB statistics reuse policy: free reuse (incl. commercial) with source quoted; statistics and metadata must not be modified",
        "attribution": "Source: ECB statistics. / 出典：欧州中央銀行（ECB）。円ドルは ECB の円・ドルの参照レートから MABUI が計算",
        "units": {
            "jpy_per_eur": "JPY per 1 EUR (as published by ECB)",
            "usd_per_eur": "USD per 1 EUR (as published by ECB)",
            "jpy_per_usd_mabui_calc": "JPY per 1 USD = jpy_per_eur / usd_per_eur, rounded to 4 decimals (MABUI calculation, NOT an ECB statistic)",
        },
        "built_from_snapshots": [m["file"] for m in metas],
        "latest_retrieved_at": latest["retrieved_at"],
        "days": len(rows),
        "first_date": dates[0],
        "last_date": dates[-1],
        "obs_status_counts": statuses,
        "dates_without_value": no_value,
        "dates_with_only_one_currency": one_side,
        "revisions_detected": len(revisions),
        "definitions": "sources/ecb_exr_daily.md",
    }
    (OUT_DIR / f"{SOURCE_ID}.meta.json").write_text(
        json.dumps(meta_out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"[build] {len(rows)}日 ({dates[0]}〜{dates[-1]}) / 改定 {len(revisions)}件 "
        f"/ 値なしの日 {len(no_value)}件 / 片方だけの日 {len(one_side)}件 / OBS_STATUS {statuses}"
    )


def _cross(jpy: str | None, usd: str | None) -> str:
    if not jpy or not usd:
        return ""  # 片方がなければ計算しない（埋めない）
    q = Decimal(jpy) / Decimal(usd)
    return str(q.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN))


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
