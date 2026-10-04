"""보고서 버전 폴더 관리: data/reports/v1, v2, ...

각 버전 폴더:
  draft.json / draft.md   실무자 초안
  checks.json             기계 점검 결과
  review_manager.json     과장 검토(4단계)
  review_director.json    부장 검토(5단계)
"""
import json
import re
from pathlib import Path


def versions(root: Path) -> list[Path]:
    if not root.exists():
        return []
    vs = [p for p in root.iterdir() if p.is_dir() and re.fullmatch(r"v\d+", p.name)]
    return sorted(vs, key=lambda p: int(p.name[1:]))


def latest(root: Path) -> Path | None:
    vs = versions(root)
    return vs[-1] if vs else None


def new_version(root: Path) -> Path:
    last = latest(root)
    n = int(last.name[1:]) + 1 if last else 1
    p = root / f"v{n}"
    p.mkdir(parents=True)
    return p


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
