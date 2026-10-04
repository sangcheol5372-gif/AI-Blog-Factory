import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from landreport.collectors import land, laws, manual, news, trades
from landreport.config import load_settings
from landreport.store import Store, redact


def settings(**keys):
    s = load_settings()
    s.keys = {"law_oc": "", "vworld": "", "data_go_kr": "", **keys}
    return s


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp)

    def test_redacts_keys_in_saved_url(self):
        doc = self.store.save(source="law", key="농지법", title="농지법",
                              url="https://x/?OC=secret&target=law&serviceKey=abc",
                              reliability="primary", payload={"a": 1})
        saved = json.loads((self.tmp / "raw/law/농지법.json").read_text())
        self.assertEqual(doc, "law:농지법")
        self.assertNotIn("secret", saved["url"])
        self.assertNotIn("abc", saved["url"])
        self.assertEqual(redact("a?key=1&b=2"), "a?key=***&b=2")


class ConfigTest(unittest.TestCase):
    def test_yellow_parcels_match_user_table(self):
        s = load_settings()
        self.assertEqual([p.lot for p in s.parcels], ["408-5", "409-3", "410-2", "423-3", "579"])
        self.assertEqual(sum(p.official_value for p in s.parcels), 268_102_300)
        self.assertEqual(sum(p.appraisal_min for p in s.parcels), 507_565_000)
        self.assertEqual(sum(p.appraisal_max for p in s.parcels), 563_000_000)


class LawsTest(unittest.TestCase):
    def test_skips_without_key(self):
        r = laws.collect(settings(), Store(Path(tempfile.mkdtemp())))
        self.assertTrue(r.skipped)

    def test_find_serial_handles_single_and_list(self):
        many = {"LawSearch": {"law": [
            {"법령일련번호": "1", "법령명한글": "농지법 시행령"},
            {"법령일련번호": "2", "법령명한글": "농지법"}]}}
        one = {"OrdinSearch": {"law": {"자치법규일련번호": "9", "자치법규명": "군산시 도시계획 조례"}}}
        self.assertEqual(laws.find_serial(many, "law", "농지법"), "2")
        self.assertEqual(laws.find_serial(one, "ordin", "군산시 도시계획 조례"), "9")
        self.assertIsNone(laws.find_serial(many, "law", "건축법"))

    def test_collects_with_fake_api(self):
        def fake(url):
            if "lawSearch" in url:
                return {"LawSearch": {"law": [{"법령일련번호": "7", "법령명한글": "농지법"}]}}
            return {"법령": {"조문": "..."}}
        s = settings(law_oc="me")
        store = Store(Path(tempfile.mkdtemp()))
        r = laws.collect(s, store, fetch=fake)
        self.assertIn("law:농지법", r.saved)
        self.assertIn("건축법", r.failed)  # 가짜 검색결과엔 농지법만 있음


class LandTest(unittest.TestCase):
    def test_make_pnu(self):
        self.assertEqual(land.make_pnu("5213012345", 408, 5), "5213012345" "1" "0408" "0005")
        self.assertEqual(land.make_pnu("5213012345", 579, 0, mountain=True), "5213012345205790000")
        with self.assertRaises(ValueError):
            land.make_pnu("123", 1, 0)

    def test_resolves_pnu_by_search_and_saves_three_datasets(self):
        def fake(url):
            if "req/search" in url:
                lot = "408-5" if "408-5" in url or "408-5".replace("-", "%2D") in url else None
                return {"response": {"result": {"items": [
                    {"id": "5213012345104080005", "address": {"parcel": "신관동 408-5"}},
                    {"id": "5213012345104090003", "address": {"parcel": "신관동 409-3"}},
                    {"id": "5213012345104100002", "address": {"parcel": "신관동 410-2"}},
                    {"id": "5213012345104230003", "address": {"parcel": "신관동 423-3"}},
                    {"id": "5213012345105790000", "address": {"parcel": "신관동 579"}},
                ]}}}
            return {"ok": True}
        s = settings(vworld="k")
        s.region["bjd_code"] = ""
        r = land.collect(s, Store(Path(tempfile.mkdtemp())), fetch=fake)
        self.assertEqual(len(r.saved), 5 * 3)
        self.assertEqual(r.failed, [])


class TradesTest(unittest.TestCase):
    def test_months_back_crosses_year(self):
        self.assertEqual(trades.months_back(3, date(2026, 2, 10)), ["202602", "202601", "202512"])

    def test_api_error_is_recorded(self):
        s = settings(data_go_kr="k")
        bad = lambda url: "<response><header><resultCode>30</resultCode></header></response>"
        r = trades.collect(s, Store(Path(tempfile.mkdtemp())), fetch=bad, months=2)
        self.assertEqual(len(r.failed), 2)


class NewsTest(unittest.TestCase):
    RSS = """<rss><channel>
      <item><title>현대차, 새만금에 AI 데이터센터</title><link>http://a</link>
            <pubDate>Mon, 01 Jun 2026 00:00:00 GMT</pubDate><source url="x">연합뉴스</source></item>
      <item><title>둘째</title><link>http://b</link></item>
    </channel></rss>"""

    def test_parse_and_mark_secondary(self):
        self.assertEqual(news.parse_rss(self.RSS, 1)[0]["outlet"], "연합뉴스")
        store = Store(Path(tempfile.mkdtemp()))
        r = news.collect(settings(), store, fetch=lambda url: self.RSS)
        self.assertTrue(r.saved)
        self.assertEqual({row[1] for row in store.summary()}, {"secondary"})


class ManualTest(unittest.TestCase):
    def test_registers_files_with_notes(self):
        d = Path(tempfile.mkdtemp())
        (d / "감정평가_408-5.pdf").write_bytes(b"pdf")
        (d / "감정평가_408-5.pdf.note.txt").write_text("OO감정평가법인, 2026-09")
        (d / "블로그글.txt").write_text("x")
        store = Store(Path(tempfile.mkdtemp()))
        r = manual.collect(settings(), store, manual_dir=d)
        self.assertEqual(len(r.saved), 2)
        self.assertEqual(dict(((s, rel), n) for s, rel, n in store.summary()),
                         {("manual", "primary"): 1, ("manual", "user"): 1})


if __name__ == "__main__":
    unittest.main()
