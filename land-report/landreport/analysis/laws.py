"""국가법령정보센터 법령 JSON 에서 지정한 조문 원문을 뽑는다."""


def _texts(node) -> list[str]:
    """'...내용' 키의 문자열을 문서 순서대로 모은다(조문내용 → 항내용 → 호내용 → 목내용)."""
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k.endswith("내용") and isinstance(v, str):
                out.append(v.strip())
            elif isinstance(v, list) and k.endswith("내용"):  # 표 등 문자열 목록
                out.extend(str(x).strip() for x in v if isinstance(x, str))
            else:
                out.extend(_texts(v))
    elif isinstance(node, list):
        for x in node:
            out.extend(_texts(x))
    return [t for t in out if t]


def _units(payload) -> list[dict]:
    def walk(node):
        if isinstance(node, dict):
            if "조문단위" in node:
                u = node["조문단위"]
                return u if isinstance(u, list) else [u]
            for v in node.values():
                if found := walk(v):
                    return found
        elif isinstance(node, list):
            for v in node:
                if found := walk(v):
                    return found
        return []
    return walk(payload)


def article(payload, number: str) -> str | None:
    """number: '84' 또는 '168의8'. 조문 원문(항·호 포함)을 반환한다."""
    main, _, branch = number.partition("의")
    for u in _units(payload):
        if u.get("조문여부", "조문") != "조문":
            continue  # 장·절 제목 행
        if str(u.get("조문번호", "")).strip() != main:
            continue
        if str(u.get("조문가지번호", "") or "").strip() != branch:
            continue
        return "\n".join(_texts(u))
    return None


def excerpts(law_docs: list[dict], wanted: dict[str, list[str]]) -> tuple[list[dict], list[str]]:
    """wanted: {법령명: [조문번호...]}. (발췌 목록, 못 찾은 항목) 반환."""
    by_title = {d["title"]: d for d in law_docs}
    found, missing = [], []
    for name, numbers in wanted.items():
        doc = by_title.get(name)
        for no in numbers:
            text = article(doc["payload"], no) if doc else None
            label = f"{name} 제{no.replace('의', '조의') if '의' in no else no + '조'}"
            if text:
                found.append({"law": name, "article": no, "label": label, "text": text,
                              "source": doc["doc_id"]})
            else:
                missing.append(label)
    return found, missing
