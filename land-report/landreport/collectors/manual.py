"""data/manual/ 에 직접 넣은 파일(감정평가서, 토지대장 PDF, 타 보고서, 보도자료 등)을 등록한다.

파일 자체는 그대로 두고, 저장소에는 경로·해시·메모만 남긴다.
같은 이름의 '<파일명>.note.txt' 가 있으면 출처 메모로 함께 기록한다.
"""
import hashlib

from ..config import DATA_DIR
from . import Result

MANUAL_DIR = DATA_DIR / "manual"
# 1차 공적자료로 취급할 파일명 접두어. 예: "공문_새만금개발청_2026.pdf"
PRIMARY_PREFIXES = ("공문_", "보도자료_", "공부_", "감정평가_")


def collect(settings, store, manual_dir=MANUAL_DIR) -> Result:
    res = Result("직접 넣은 자료")
    manual_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(manual_dir.iterdir()):
        if not f.is_file() or f.name.endswith(".note.txt") or f.name.startswith(".") or f.name == "README.md":
            continue
        note_file = f.with_name(f.name + ".note.txt")
        note = note_file.read_text(encoding="utf-8").strip() if note_file.exists() else ""
        res.saved.append(store.save(
            source="manual", key=f.name, title=f.stem, url=f"file://{f}",
            reliability="primary" if f.name.startswith(PRIMARY_PREFIXES) else "user",
            payload={"file": f.name, "note": note},
            meta={"file_sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "bytes": f.stat().st_size},
        ))
    return res
