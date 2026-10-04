"""수집 원자료 저장소.

모든 원자료는 출처 URL·수집시각·해시와 함께 저장한다. 이후 과장·부장 검토 단계는
보고서의 각 주장을 이 저장소의 문서 ID 로 역추적해 사실 여부를 확인한다.
"""
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SECRET_PARAMS = re.compile(r"((?:OC|key|serviceKey|apiKey)=)[^&]+", re.IGNORECASE)


def redact(url: str) -> str:
    """저장·출력하는 URL 에서 API 키를 지운다."""
    return SECRET_PARAMS.sub(r"\1***", url)


class Store:
    def __init__(self, data_dir: Path):
        self.raw_dir = data_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(data_dir / "index.sqlite")
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,      -- law / ordinance / land / trade / news / manual
                title TEXT NOT NULL,
                url TEXT,
                reliability TEXT NOT NULL, -- primary(공적 1차자료) / secondary(보도·2차자료) / user(사용자 제공)
                fetched_at TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                path TEXT NOT NULL,
                meta TEXT
            )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS errors (
                source TEXT, title TEXT, url TEXT, error TEXT, at TEXT
            )"""
        )
        self.db.commit()

    def save(self, *, source: str, key: str, title: str, url: str, reliability: str,
             payload, meta: dict | None = None) -> str:
        """같은 key 는 덮어쓴다(최신본 유지). doc_id 를 반환한다."""
        doc_id = f"{source}:{key}"
        body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2)
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        safe_key = re.sub(r"[^\w.-]+", "_", key)
        path = self.raw_dir / source / f"{safe_key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "doc_id": doc_id, "source": source, "title": title, "url": redact(url),
            "reliability": reliability, "fetched_at": now, "sha256": sha,
            "meta": meta or {}, "payload": payload,
        }
        path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
        self.db.execute(
            "INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?)",
            (doc_id, source, title, redact(url), reliability, now, sha,
             str(path.relative_to(self.raw_dir.parent)), json.dumps(meta or {}, ensure_ascii=False)),
        )
        self.db.commit()
        return doc_id

    def error(self, *, source: str, title: str, url: str, error: str) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.db.execute("INSERT INTO errors VALUES (?,?,?,?,?)", (source, title, redact(url), error, now))
        self.db.commit()

    def summary(self) -> list[tuple]:
        return self.db.execute(
            "SELECT source, reliability, COUNT(*) FROM documents GROUP BY source, reliability ORDER BY source"
        ).fetchall()

    def recent_errors(self, limit: int = 20) -> list[tuple]:
        return self.db.execute(
            "SELECT at, source, title, error FROM errors ORDER BY at DESC LIMIT ?", (limit,)
        ).fetchall()
