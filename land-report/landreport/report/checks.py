"""보고서 기계 점검. 과장·부장 검토 전에 항상 돌리고, 결과를 검토자에게 함께 넘긴다.

block: 이 문제가 남아 있으면 결재 불가
warn : 검토자가 직접 확인해야 하는 항목
"""
import re

from .schema import REQUIRED_HEADINGS

# 분석 결과 각 부분을 가리키는 근거 ID
ANALYSIS_SOURCES = {
    "analysis:parcels": "필지 현황 분석",
    "analysis:comparables": "실거래 비교사례 분석",
    "analysis:valuation": "시세 추정·목표가 검증",
    "analysis:deadlines": "상속 관련 기한",
    "analysis:tax": "양도세 간이 추정",
    "analysis:regulations": "법적 쟁점·조문 발췌",
    "analysis:price_levers": "가격 제고 수단",
    "analysis:gaps": "데이터 공백",
    "user:inheritance_table": "사용자 제공 상속재산 표(기준시가·감정 범위·11억 가정)",
}

# 매수자 오인을 부를 수 있는 표현. 표시광고법·공인중개사법상 허위·과장 위험.
HYPE_PATTERNS = [
    r"확정(?!일자|판결|된\s*사실)", r"무조건", r"보장", r"반드시\s*(오|상승|올)", r"100\s*%",
    r"확실한\s*(수익|투자|상승)", r"대박", r"폭등", r"최고의\s*투자", r"원금", r"손해\s*볼\s*일",
    r"놓치면\s*후회", r"마지막\s*기회", r"수익률\s*\d", r"[0-9]+\s*배\s*(상승|오를)",
]
HYPE_RE = re.compile("|".join(HYPE_PATTERNS))

UNIT = {"억": 100_000_000, "천만": 10_000_000, "만": 10_000, "": 1}
COMBINED_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*억\s*(\d[\d,]*)\s*만")
SINGLE_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(억|천만|만)?")


def catalog(analysis: dict, store=None) -> dict[str, dict]:
    """사용 가능한 근거 ID → {title, reliability}."""
    cat = {k: {"title": v, "reliability": "user" if k.startswith("user:") else "derived"}
           for k, v in ANALYSIS_SOURCES.items()}
    if store is not None:
        rows = store.db.execute("SELECT doc_id, title, reliability FROM documents")
        for doc_id, title, rel in rows:
            cat[doc_id] = {"title": title, "reliability": rel}
    for doc_id in _source_ids(analysis):  # 저장소 없이 분석 결과만 있을 때
        cat.setdefault(doc_id, {"title": doc_id,
                                "reliability": "secondary" if doc_id.startswith("news:") else "primary"})
    return cat


def _source_ids(node) -> set[str]:
    out = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "source" and isinstance(v, str) and ":" in v:
                out.add(v)
            elif k == "sources" and isinstance(v, list):
                out.update(x for x in v if isinstance(x, str) and ":" in x)
            else:
                out |= _source_ids(v)
    elif isinstance(node, list):
        for x in node:
            out |= _source_ids(x)
    return out


def _numbers_in(node) -> list[float]:
    out = []
    if isinstance(node, bool):
        return out
    if isinstance(node, (int, float)):
        out.append(abs(float(node)))
    elif isinstance(node, str):
        out.extend(extract_amounts(node))
    elif isinstance(node, dict):
        for v in node.values():
            out.extend(_numbers_in(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_numbers_in(v))
    return out


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def extract_amounts(text: str) -> list[float]:
    """'11억', '5억 6,300만원', '563,000,000원' 같은 금액·큰 수를 원 단위로 뽑는다.
    1000 미만, 단위 없는 연도(1900~2100)는 제외."""
    vals = []
    for m in COMBINED_RE.finditer(text):
        vals.append(_num(m.group(1)) * UNIT["억"] + _num(m.group(2)) * UNIT["만"])
    rest = COMBINED_RE.sub(" ", text)
    for m in SINGLE_RE.finditer(rest):
        v = _num(m.group(1)) * UNIT[m.group(2) or ""]
        if v < 1000 or (not m.group(2) and 1900 <= v <= 2100 and "," not in m.group(1)):
            continue
        vals.append(v)
    return vals


def _traceable(v: float, known: list[float], tol: float = 0.01) -> bool:
    return any(abs(v - k) <= max(1.0, k * tol) for k in known)


def paragraphs(report: dict):
    for i, p in enumerate(report.get("summary", [])):
        yield f"요약 {i + 1}", p
    for s in report.get("sections", []):
        for i, p in enumerate(s.get("paragraphs", [])):
            yield f"{s.get('heading', '?')} {i + 1}", p


def run(report: dict, analysis: dict, cat: dict) -> list[dict]:
    issues = []

    def add(sev, where, msg):
        issues.append({"severity": sev, "where": where, "message": msg})

    headings = [s.get("heading", "") for s in report.get("sections", [])]
    for h in REQUIRED_HEADINGS:
        if not any(h in x for x in headings):
            add("block", "구성", f"필수 장 누락: {h}")
    if not report.get("summary"):
        add("block", "요약", "요약이 비어 있음")

    known = _numbers_in(analysis)
    for where, p in paragraphs(report):
        text, kind, srcs = p.get("text", ""), p.get("kind"), p.get("sources", [])
        unknown = [s for s in srcs if s not in cat]
        if unknown:
            add("block", where, f"존재하지 않는 근거 ID: {', '.join(unknown)}")
        if kind == "fact" and not srcs:
            add("block", where, "사실(fact) 문단에 근거 없음")
        if kind == "fact" and srcs and all(cat.get(s, {}).get("reliability") == "secondary" for s in srcs):
            add("block", where, "보도(2차 자료)만으로 사실 단정 — '~로 보도됨'으로 쓰거나 1차 출처 필요")
        if m := HYPE_RE.search(text):
            add("block", where, f"과장·단정 표현: '{m.group(0)}'")
        for v in extract_amounts(text):
            if not _traceable(v, known):
                add("warn", where, f"분석 결과에서 찾을 수 없는 수치: {v:,.0f}")
    return issues


def blocking(issues: list[dict]) -> list[dict]:
    return [i for i in issues if i["severity"] == "block"]
