"""단계 실행 함수. CLI 와 테스트가 함께 쓴다."""
from pathlib import Path

from . import checks, render, workspace, writer


def run_draft(analysis: dict, cat: dict, reports_dir: Path, *, client=None) -> Path:
    """새 버전 폴더에 초안을 쓴다. 직전 버전이 반려됐으면 그 의견을 반영해 고쳐 쓴다."""
    prev_dir = workspace.latest(reports_dir)
    previous, feedback = None, None
    if prev_dir is not None:
        review = workspace.read(prev_dir / "review_director.json") or workspace.read(prev_dir / "review_manager.json")
        if review and review.get("decision") == "반려":
            previous = workspace.read(prev_dir / "draft.json")
            feedback = review.get("required_changes", [])
    report = writer.draft(analysis, cat, feedback=feedback, previous=previous, client=client)
    issues = checks.run(report, analysis, cat)
    out = workspace.new_version(reports_dir)
    workspace.write(out / "draft.json", report)
    workspace.write(out / "checks.json", issues)
    note = f"실무자 초안 {out.name} — 결재 전 문서. 기계 점검: 차단 {len(checks.blocking(issues))}건, " \
           f"확인 필요 {len(issues) - len(checks.blocking(issues))}건"
    (out / "draft.md").write_text(render.to_markdown(report, cat, note), encoding="utf-8")
    return out
