"""data/raw/ への元データ保存（全ソース共通）。

- 取得したバイト列を加工せず、取得日時つきのファイル名で保存する（上書きしない）
- 同じ名前の .meta.json に、URL・取得日時・sha256 などを記録する
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import ssl
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "mabui-data-fetcher/0.1 (+public-data observatory)"


def raw_dir(source_id: str) -> Path:
    return ROOT / "data" / "raw" / source_id


EXTRA_INTERMEDIATES = Path(__file__).resolve().parent / "certs" / "extra_intermediates.pem"


def _ssl_context() -> ssl.SSLContext:
    """標準の検証に、サーバーが送ってこない中間証明書だけを補う。

    検証は切らない。PARTIAL_CHAIN を外すので、補った証明書そのものは信頼の起点にならず、
    必ず Python / OS が元から信頼しているルート証明書までたどれた場合だけ通る。
    """
    ctx = ssl.create_default_context()
    if hasattr(ssl, "VERIFY_X509_PARTIAL_CHAIN"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
    if EXTRA_INTERMEDIATES.exists():
        ctx.load_verify_locations(cafile=str(EXTRA_INTERMEDIATES))
    return ctx


def http_get(url: str, timeout: int = 120) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        body = resp.read()
        headers = {
            "http_last_modified": resp.headers.get("Last-Modified"),
            "http_content_type": resp.headers.get("Content-Type"),
        }
    return body, headers


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def save_snapshot(
    source_id: str,
    body: bytes,
    suffix: str,
    meta: dict,
    retrieved_at: dt.datetime,
) -> Path:
    d = raw_dir(source_id)
    d.mkdir(parents=True, exist_ok=True)
    stamp = retrieved_at.strftime("%Y%m%dT%H%M%SZ")
    path = d / f"{stamp}_{suffix}"
    if path.exists():
        raise FileExistsError(path)  # 上書きはしない
    path.write_bytes(body)
    full_meta = {
        "source_id": source_id,
        "file": path.name,
        "retrieved_at": retrieved_at.isoformat().replace("+00:00", "Z"),
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
        **meta,
    }
    meta_path = path.with_name(path.stem + ".meta.json")
    meta_path.write_text(
        json.dumps(full_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[fetch] 保存: {path.relative_to(ROOT)}")
    return path


def snapshots(source_id: str) -> list[dict]:
    """保存済みスナップショットの meta を、取得日時の古い順に返す。"""
    d = raw_dir(source_id)
    if not d.exists():
        return []
    metas = [json.loads(p.read_text(encoding="utf-8")) for p in d.glob("*.meta.json")]
    return sorted(metas, key=lambda m: m["retrieved_at"])


def read_snapshot(meta: dict) -> bytes:
    return (raw_dir(meta["source_id"]) / meta["file"]).read_bytes()
