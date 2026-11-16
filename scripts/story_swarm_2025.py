"""群れの試作用：2025年の週ごとの「海外の投資家による日本の株や債券の買い越し」（円）。

入力: data/processed/mof_itn_weekly.csv（inward_total_net、億円）
出力: video/data/inward_weekly_2025.json
値は元データのまま（億円）。補間・平滑化はしない。
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "processed" / "mof_itn_weekly.csv"
OUT = ROOT / "video" / "data" / "inward_weekly_2025.json"


def main():
    weeks = [
        {"week_start": r["week_start"], "week_end": r["week_end"], "net_oku_yen": int(r["inward_total_net"])}
        for r in csv.DictReader(SRC.open(encoding="utf-8"))
        if r["week_start"].startswith("2025-")
    ]
    out = {
        "series": "inward_total_net",
        "unit": "億円",
        "source": "財務省「対外及び対内証券売買契約等の状況（週次・指定報告機関ベース）」",
        "built_from": json.loads(SRC.with_suffix(".meta.json").read_text(encoding="utf-8"))["built_from_snapshot"],
        "weeks": weeks,
        "total_oku_yen": sum(w["net_oku_yen"] for w in weeks),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[swarm] {len(weeks)}週 / 合計 {out['total_oku_yen']}億円")


if __name__ == "__main__":
    main()
