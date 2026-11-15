# ECB ユーロ為替参照レート（日次）— 円・ドル

| 項目 | 内容 |
|---|---|
| 公表者 | 欧州中央銀行（ECB） |
| データセット | EXR（Exchange Rates）https://data.ecb.europa.eu/data/datasets/EXR |
| 系列 | `EXR.D.JPY.EUR.SP00.A`（1ユーロあたりの円）、`EXR.D.USD.EUR.SP00.A`（1ユーロあたりのドル） |
| 取得先 | ECB Data Portal API `https://data-api.ecb.europa.eu/service/data/EXR/D.JPY+USD.EUR.SP00.A?format=csvdata` |
| 期間 | 1999-01-04〜（ユーロ導入から） |
| 公表 | TARGET 営業日の 16:00 CET ごろ（レートは 14:15 CET 時点） |
| 取得スクリプト | `scripts/ecb_exr_daily.py` |
| 元データ | `data/raw/ecb_exr_daily/`（初回は全期間、以後は直近45日分。新しい値か変わった値があるときだけ保存） |
| 加工データ | `data/processed/ecb_exr_daily.csv`（＋ `.meta.json`、改定履歴 `_revisions.csv`） |

## 利用規約（2026-11-15 確認）
- ESCB 統計の再利用方針（https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html ）：
  公表された統計は、**商用・非商用を問わず無料で再利用できる**。条件は
  **出典を示すこと**（例 “Source: ECB statistics.”）と、**統計（メタデータを含む）を改変しないこと**。
- ECB サイトの免責・著作権（https://www.ecb.europa.eu/services/disclaimer/html/index.en.html ）：
  再配布するときは正確に載せ、ECB を出典として示す。**有料の資料に組み込む場合は、購入者に
  「この情報は ECB のサイトで無料で手に入る」と、支払い前と閲覧のたびに伝える必要がある**（将来ストア版で注意）。
- ECB はレートの利用による損失に責任を負わない。

**MABUI での出典表記：**
> Source: ECB statistics. ／ 出典：欧州中央銀行（ECB）。円ドルは、ECB の円・ドルの参照レートから MABUI が計算。

## 列の定義（`data/processed/ecb_exr_daily.csv`）
- `date`：レートの日付。
- `jpy_per_eur`：1ユーロ＝何円か。**ECB の公表値を文字列のまま**（丸め・換算なし）。
- `usd_per_eur`：1ユーロ＝何ドルか。同上。
- `*_status`：ECB の OBS_STATUS。`A`＝通常の値、`H`＝休日などで値なし（このとき値は空欄）。
- `jpy_per_usd_mabui_calc`：1ドル＝何円か。**ECB の統計ではなく MABUI の計算値。**
  `jpy_per_eur ÷ usd_per_eur` を小数第4位に丸めた値（偶数丸め）。どちらかが空欄の日は空欄のまま（埋めない）。

## このデータで言えること・言えないこと
**言えること**
- 毎営業日 14:15 CET 時点の、円・ドルの対ユーロの水準と、その変化。
- 1999年からの長い期間を、同じ方法で比べられる。

**言えないこと・注意**
- **取引レートではない。** ECB は「情報提供のための参照レート」としており、実際の売買の値段とは違う。
- **1日の動きはわからない。** 1日1回（14:15 CET）の値だけ。東京やニューヨークの時間帯の値とはずれる。
- **円ドルは間接的に計算した値。** ユーロを経由した計算なので、市場の円ドルの値や FRB（H.10、ニューヨーク正午）の値と
  小数点以下で一致しない。円ドルの公表値が必要なときは FRB のデータを加える。
- **為替の変化は資金の移動ではない。** レートが動いても、どれだけのお金がどちらへ動いたかはわからない。
  資金の流れは、財務省の証券売買の統計など、流れを測った統計で示す。
- TARGET の休日（元日、聖金曜日、復活祭の月曜日、5月1日、12月25日・26日など）は値がない。補間しない。

## 取得の注意（TLS 証明書）
`data-api.ecb.europa.eu` は、`Sectigo Public Server Authentication Root E46` までの証明書チェーンを送ってくる。
このルートは Python や Ubuntu の標準の証明書一覧に入っていないため、そのままでは接続に失敗する。
そこで、Sectigo が公開している USERTrust ECC で署名された同じ証明書（`scripts/certs/extra_intermediates.pem`、
出所・指紋・有効期限はファイル内に記載）を中間証明書として補い、標準で信頼されている USERTrust ECC ルートまで検証する。
**検証は切っていない**（`scripts/rawstore.py` の `_ssl_context`）。
