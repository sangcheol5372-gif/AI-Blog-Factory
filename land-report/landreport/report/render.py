"""보고서 JSON → 읽기용 Markdown. 근거는 [n] 각주로 달고 끝에 근거 목록을 붙인다."""

KIND_MARK = {"fact": "", "estimate": " *(추정)*", "opinion": " *(의견)*"}


def to_markdown(report: dict, cat: dict, header_note: str = "") -> str:
    refs: dict[str, int] = {}

    def cite(srcs):
        nums = []
        for s in srcs:
            refs.setdefault(s, len(refs) + 1)
            nums.append(refs[s])
        return "".join(f"[{n}]" for n in nums)

    def para(p):
        return f"{p['text']}{KIND_MARK.get(p.get('kind'), '')} {cite(p.get('sources', []))}".rstrip()

    L = [f"# {report.get('title', '보고서')}", ""]
    if header_note:
        L += [f"> {header_note}", ""]
    L += ["## 요약", ""] + [f"- {para(p)}" for p in report.get("summary", [])]
    for s in report.get("sections", []):
        L += ["", f"## {s['heading']}", ""]
        for p in s.get("paragraphs", []):
            L += [para(p), ""]
    if report.get("open_questions"):
        L += ["", "## 의뢰인 확인 사항", ""] + [f"- {q}" for q in report["open_questions"]]
    if report.get("revision_notes"):
        L += ["", "## 수정 내역", ""] + [f"- {n}" for n in report["revision_notes"]]
    if refs:
        L += ["", "## 근거 자료", ""]
        for s, n in sorted(refs.items(), key=lambda x: x[1]):
            info = cat.get(s, {})
            L.append(f"{n}. `{s}` {info.get('title', '(목록에 없음)')} — {info.get('reliability', '?')}")
    return "\n".join(L).rstrip() + "\n"
