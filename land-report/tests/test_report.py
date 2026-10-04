import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from landreport.report import checks, llm, pipeline, render, workspace, writer
from landreport.report.schema import REQUIRED_HEADINGS

ANALYSIS = {
    "valuation": {"appraisal_total": [507_565_000, 563_000_000], "target_total": 1_100_000_000},
    "news": [{"title": "현대차 새만금 투자", "source": "news:현대차 새만금"}],
    "regulations": {"excerpts": [{"source": "law:농지법", "text": "제8조"}]},
}


def P(text, kind="fact", sources=("analysis:valuation",)):
    return {"text": text, "kind": kind, "sources": list(sources)}


def good_report():
    return {
        "title": "신관동 토지 매각 기초 용역보고서",
        "summary": [P("감정 합계는 약 5억 760만원~5억 6,300만원이다.")],
        "sections": [{"heading": h, "paragraphs": [P(f"{h} 내용", kind="opinion", sources=[])]}
                     for h in REQUIRED_HEADINGS],
        "open_questions": ["상속개시일은?"],
        "revision_notes": [],
    }


class FakeStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


class FakeClient:
    """client.beta.messages.stream(...) 만 흉내낸다. 받은 인자는 calls 에 남긴다."""

    def __init__(self, payloads, stop_reason="end_turn"):
        self.payloads, self.stop_reason, self.calls = list(payloads), stop_reason, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kw):
        self.calls.append(kw)
        text = json.dumps(self.payloads.pop(0), ensure_ascii=False)
        return FakeStream(SimpleNamespace(stop_reason=self.stop_reason, stop_details=None,
                                          content=[SimpleNamespace(type="text", text=text)]))


class AmountTest(unittest.TestCase):
    def test_extract_amounts(self):
        self.assertEqual(checks.extract_amounts("11억"), [1_100_000_000])
        self.assertEqual(checks.extract_amounts("5억 6,300만원"), [563_000_000])
        self.assertEqual(checks.extract_amounts("563,000,000원"), [563_000_000])
        self.assertEqual(checks.extract_amounts("2027년 3월, 제104조, 20%"), [])


class ChecksTest(unittest.TestCase):
    def setUp(self):
        self.cat = checks.catalog(ANALYSIS)

    def test_good_report_has_no_blocking(self):
        self.assertEqual(checks.blocking(checks.run(good_report(), ANALYSIS, self.cat)), [])

    def test_catalog_marks_news_secondary(self):
        self.assertEqual(self.cat["news:현대차 새만금"]["reliability"], "secondary")
        self.assertEqual(self.cat["law:농지법"]["reliability"], "primary")

    def test_flags(self):
        r = good_report()
        r["sections"][0]["paragraphs"] = [
            P("근거 없는 사실", sources=[]),
            P("없는 근거", sources=["law:없는법"]),
            P("현대차 공장이 들어선다", sources=["news:현대차 새만금"]),
            P("수익 보장 토지", kind="opinion", sources=[]),
            P("시세는 7억이다", kind="estimate"),
        ]
        r["sections"] = r["sections"][:-1]  # 마지막 필수 장 삭제
        msgs = [(i["severity"], i["message"]) for i in checks.run(r, ANALYSIS, self.cat)]
        text = " | ".join(m for _, m in msgs)
        self.assertIn("필수 장 누락: 데이터 공백과 추가 조사", text)
        self.assertIn("사실(fact) 문단에 근거 없음", text)
        self.assertIn("존재하지 않는 근거 ID: law:없는법", text)
        self.assertIn("보도(2차 자료)만으로 사실 단정", text)
        self.assertIn("과장·단정 표현: '보장'", text)
        self.assertIn(("warn", "분석 결과에서 찾을 수 없는 수치: 700,000,000"), msgs)


class LLMTest(unittest.TestCase):
    def test_request_shape(self):
        fc = FakeClient([{"ok": 1}])
        self.assertEqual(llm.call_json("sys", "user", {"type": "object"}, client=fc), {"ok": 1})
        kw = fc.calls[0]
        self.assertEqual(kw["model"], "claude-opus-5-5")
        self.assertEqual(kw["fallbacks"], "default")
        self.assertEqual(kw["betas"], ["server-side-fallback-2026-07-01"])
        self.assertEqual(kw["output_config"]["format"]["type"], "json_schema")
        self.assertNotIn("thinking", kw)

    def test_refusal_and_truncation_raise(self):
        for reason in ("refusal", "max_tokens"):
            with self.assertRaises(llm.LLMError):
                llm.call_json("s", "u", {}, client=FakeClient([{}], stop_reason=reason))


    def test_missing_credentials_message(self):
        def boom(**kw):
            raise TypeError("Could not resolve authentication method.")
        fc = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=boom)))
        with self.assertRaisesRegex(llm.LLMError, "ANTHROPIC_API_KEY"):
            llm.call_json("s", "u", {}, client=fc)


class PipelineTest(unittest.TestCase):
    def test_draft_then_revision_uses_rejection_feedback(self):
        root = Path(tempfile.mkdtemp())
        cat = checks.catalog(ANALYSIS)
        fc = FakeClient([good_report(), {**good_report(), "revision_notes": ["리스크 장 보강"]}])
        v1 = pipeline.run_draft(ANALYSIS, cat, root, client=fc)
        self.assertEqual(v1.name, "v1")
        self.assertIn("기계 점검: 차단 0건", (v1 / "draft.md").read_text())
        self.assertNotIn("previous_draft", fc.calls[0]["messages"][0]["content"])

        workspace.write(v1 / "review_manager.json", {"decision": "반려", "required_changes": [
            {"where": "리스크", "change": "맹지 여부를 고지 사항에 추가"}]})
        v2 = pipeline.run_draft(ANALYSIS, cat, root, client=fc)
        self.assertEqual(v2.name, "v2")
        prompt = fc.calls[1]["messages"][0]["content"]
        self.assertIn("<previous_draft>", prompt)
        self.assertIn("맹지 여부를 고지 사항에 추가", prompt)
        self.assertIn("리스크 장 보강", (v2 / "draft.md").read_text())

    def test_system_prompt_lists_all_headings(self):
        for h in REQUIRED_HEADINGS:
            self.assertIn(h, writer.SYSTEM)


class RenderTest(unittest.TestCase):
    def test_footnotes(self):
        md = render.to_markdown(good_report(), checks.catalog(ANALYSIS), "초안")
        self.assertIn("[1]", md)
        self.assertIn("1. `analysis:valuation` 시세 추정·목표가 검증 — derived", md)
        self.assertIn("*(의견)*", md)


if __name__ == "__main__":
    unittest.main()
