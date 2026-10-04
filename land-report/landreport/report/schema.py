"""보고서 JSON 구조. 모든 문단은 근거(sources)와 성격(kind)을 가진다."""


def _obj(props: dict, required=None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props),
            "additionalProperties": False}


STR = {"type": "string"}
STRS = {"type": "array", "items": STR}

PARAGRAPH = _obj({
    "text": STR,
    "kind": {"type": "string", "enum": ["fact", "estimate", "opinion"]},
    "sources": STRS,
})

REPORT = _obj({
    "title": STR,
    "summary": {"type": "array", "items": PARAGRAPH},
    "sections": {"type": "array", "items": _obj({
        "heading": STR,
        "paragraphs": {"type": "array", "items": PARAGRAPH},
    })},
    "open_questions": STRS,
    "revision_notes": STRS,  # 반려 의견을 어떻게 반영했는지(초판은 빈 목록)
})

REQUIRED_HEADINGS = [
    "개요",
    "필지 현황",
    "입지와 개발 여건",
    "법적 규제와 활용 가능성",
    "시세 분석과 적정 매도가 범위",
    "매도 전략",
    "세후 수령액 시나리오",
    "리스크와 매수자 고지 사항",
    "데이터 공백과 추가 조사",
]
