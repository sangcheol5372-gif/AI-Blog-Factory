from dataclasses import dataclass, field


@dataclass
class Result:
    name: str
    saved: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: str = ""  # 키 미설정 등으로 통째로 건너뛴 이유

    def line(self) -> str:
        if self.skipped:
            return f"[{self.name}] 건너뜀: {self.skipped}"
        return f"[{self.name}] 저장 {len(self.saved)}건, 실패 {len(self.failed)}건"
