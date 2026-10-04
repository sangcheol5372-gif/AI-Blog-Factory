"""3단계: 실무자 — 분석 결과로 기초 용역보고서(내부용) 초안을 쓴다."""
import json

from . import llm
from .schema import REPORT, REQUIRED_HEADINGS

SYSTEM = f"""당신은 부동산 개발·매각 컨설팅사의 실무 담당자다. 의뢰인(매도인)이 상속받을 토지를
가장 높은, 그러나 근거로 방어할 수 있는 가격에 팔 수 있도록 내부용 '기초 용역보고서'를 쓴다.
이 보고서는 과장·부장 검토를 거친 뒤 매수자용 자료의 원본이 된다.

작성 원칙
1. 제공된 분석 결과(analysis)와 근거 목록(source_catalog)에 있는 내용만 쓴다. 기억이나 추측으로
   사실·수치·계획·날짜를 만들어내지 않는다.
2. 모든 문단에 kind 를 붙인다: fact(근거로 확인된 사실), estimate(계산·추정), opinion(판단·제안).
   fact 와 estimate 문단은 sources 에 근거 ID 를 하나 이상 넣는다. 근거 ID 는 source_catalog 의 키만 쓴다.
3. reliability 가 secondary 인 자료(뉴스)는 '…라고 보도되었다'로만 쓰고, 그것만으로 fact 를 만들지 않는다.
   개발 호재와 대상 토지의 연결은 거리·시기·확정 여부를 함께 적는다. 확인되지 않은 연결은 opinion 으로,
   불확실성을 명시한다.
4. 매도인에게 불리한 사실(규제, 맹지 여부, 비교사례 대비 높은 목표가, 세금 등)도 빠짐없이 쓴다.
   매수자에게 고지해야 할 사항은 '리스크와 매수자 고지 사항' 장에 모은다. 불리한 사실을 감추면
   계약 취소·손해배상 위험이 생겨 결국 매도인의 손해가 된다.
5. '확정', '보장', '무조건', '반드시 오른다', '수익률 ○%' 같은 단정·과장·수익 약속 표현을 쓰지 않는다.
6. 자료가 없으면 '자료 미확보'라고 쓰고 '데이터 공백과 추가 조사' 장에 무엇이 필요한지 적는다.
7. 금액은 분석 결과의 숫자를 그대로(또는 억 단위로 반올림해 '약'을 붙여) 쓴다. 새 계산이 필요하면
   계산식을 문장에 적고 kind 를 estimate 로 한다.
8. 세금은 간이 추정이며 세무사 확인이 필요하다고 밝힌다.

장 구성(이 순서, 제목에 아래 문구를 포함): {", ".join(REQUIRED_HEADINGS)}
summary 는 의사결정자가 1분 안에 읽을 핵심 3~6문단이다.
open_questions 에는 의뢰인에게 확인받아야 할 질문을 쓴다.
"""


def build_user_prompt(analysis: dict, cat: dict, feedback: list[dict] | None = None,
                      previous: dict | None = None) -> str:
    parts = [
        "<analysis>\n" + json.dumps(analysis, ensure_ascii=False, sort_keys=True) + "\n</analysis>",
        "<source_catalog>\n" + json.dumps(cat, ensure_ascii=False, sort_keys=True) + "\n</source_catalog>",
    ]
    if previous is not None:
        parts.append("<previous_draft>\n" + json.dumps(previous, ensure_ascii=False) + "\n</previous_draft>")
        parts.append("<review_feedback>\n" + json.dumps(feedback or [], ensure_ascii=False) + "\n</review_feedback>")
        parts.append("위 검토 의견을 모두 반영해 보고서를 고쳐 다시 써라. 각 의견을 어떻게 반영했는지 "
                     "revision_notes 에 한 줄씩 적어라. 반영할 수 없는 의견은 이유를 적어라.")
    else:
        parts.append("위 자료로 기초 용역보고서 초안을 작성하라. revision_notes 는 빈 목록으로 둔다.")
    return "\n\n".join(parts)


def draft(analysis: dict, cat: dict, *, feedback=None, previous=None, client=None) -> dict:
    return llm.call_json(SYSTEM, build_user_prompt(analysis, cat, feedback, previous), REPORT,
                         effort="high", client=client)
