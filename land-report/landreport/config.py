import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"


@dataclass
class Parcel:
    lot: str
    zoning: str
    official_value: int
    appraisal_min: int
    appraisal_max: int
    pnu: str = ""

    @property
    def main_sub(self) -> tuple[int, int]:
        """'408-5' -> (408, 5), '579' -> (579, 0)."""
        main, _, sub = self.lot.partition("-")
        return int(main), int(sub or 0)


@dataclass
class Settings:
    region: dict
    parcels: list[Parcel]
    assumptions: dict
    sources: dict
    keys: dict = field(default_factory=dict)
    inheritance: dict = field(default_factory=dict)
    sites: list[dict] = field(default_factory=list)

    @property
    def address_prefix(self) -> str:
        r = self.region
        return f"{r['sido']} {r['sigungu']} {r['dong']}"


def load_env(path: Path) -> None:
    """KEY=VALUE 형식의 .env 를 읽어 아직 없는 환경변수만 채운다."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if v.startswith("#"):
            v = ""
        elif " #" in v:  # 줄 끝 주석
            v = v.split(" #", 1)[0].strip()
        os.environ.setdefault(k.strip(), v.strip('"').strip("'"))


def load_settings(config_dir: Path = CONFIG_DIR) -> Settings:
    load_env(config_dir.parent / ".env")
    with open(config_dir / "parcels.toml", "rb") as f:
        p = tomllib.load(f)
    with open(config_dir / "sources.toml", "rb") as f:
        s = tomllib.load(f)
    return Settings(
        region=p["region"],
        parcels=[Parcel(**x) for x in p["parcels"]],
        assumptions=p.get("assumptions", {}),
        sources=s,
        inheritance=p.get("inheritance", {}),
        sites=p.get("sites", []),
        keys={
            "law_oc": os.environ.get("LAW_OC", ""),
            "vworld": os.environ.get("VWORLD_KEY", ""),
            "data_go_kr": os.environ.get("DATA_GO_KR_KEY", ""),
        },
    )
