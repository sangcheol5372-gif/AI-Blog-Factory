import tempfile
import unittest
from datetime import date
from pathlib import Path

from landreport.analysis import build, laws, parcels, tax, trades
from landreport.config import load_settings
from landreport.store import Store


def trade_xml(rows):
    items = "".join(
        f"<item><umdNm>{d}</umdNm><jibun>4**</jibun><jimok>{j}</jimok><landUse>{z}</landUse>"
        f"<dealArea>{a}</dealArea><dealAmount>{amt:,}</dealAmount><dealYear>2026</dealYear>"
        f"<dealMonth>{m}</dealMonth><dealDay>1</dealDay><cdealType>{c}</cdealType>"
        f"<shareDealingType>{s}</shareDealingType></item>"
        for d, j, z, a, amt, m, c, s in rows
    )
    return f"<response><header><resultCode>000</resultCode></header><body><items>{items}</items></body></response>"


GREEN = "자연녹지지역"
ROWS = [
    # 동, 지목, 용도지역, 면적, 금액(만원), 월, 해제, 지분
    ("신관동", "답", GREEN, 1000, 20_000, 1, "", ""),   # 200,000원/㎡
    ("신관동", "답", GREEN, 1000, 25_000, 2, "", ""),   # 250,000
    ("신관동", "답", GREEN, 1000, 30_000, 3, "", ""),   # 300,000
    ("신관동", "답", GREEN, 1000, 35_000, 4, "", ""),   # 350,000
    ("신관동", "답", GREEN, 1000, 40_000, 5, "", ""),   # 400,000
    ("신관동", "답", GREEN, 1000, 99_000, 6, "O", ""),  # 해제 → 제외
    ("신관동", "답", GREEN, 1000, 99_000, 7, "", "지분"),  # 지분 → 제외
    ("나운동", "답", "제1종일반주거지역", 100, 50_000, 1, "", ""),
]


class TradesTest(unittest.TestCase):
    def test_parse_and_comparables_exclude_cancelled_and_share(self):
        deals = trades.parse_trades(trade_xml(ROWS), "trade:x")
        self.assertEqual(len(deals), 8)
        self.assertEqual(deals[0]["price_won"], 200_000_000)
        comp = trades.comparables(deals, "신관동", jimok="답")
        self.assertEqual(comp["chosen_tier"], "동일 동·용도지역·지목")
        self.assertEqual(comp["chosen"]["n"], 5)
        self.assertEqual(comp["chosen"]["median_won_per_m2"], 300_000)
        self.assertEqual(comp["excluded"], {"cancelled": 1, "share_deal": 1})

    def test_falls_back_to_wider_tier(self):
        deals = trades.parse_trades(trade_xml(ROWS), "t")
        comp = trades.comparables(deals, "신관동", jimok="전")  # 같은 지목 없음
        self.assertEqual(comp["chosen_tier"], "동일 동·용도지역")

    def test_percentile(self):
        deals = trades.parse_trades(trade_xml(ROWS[:5]), "t")
        self.assertEqual(trades.percentile_of(325_000, deals), 60.0)  # 20만·25만·30만 < 32.5만


class TaxTest(unittest.TestCase):
    def test_hand_calculated_single_heir(self):
        r = tax.transfer_tax(1_100_000_000, 268_102_300, heirs=1)
        # (1.1억 - 268,102,300 - 250만) × 42% - 3,594만 = 312,407,034 → 감면 1억 → ×1.1
        self.assertEqual(r.tax_before_relief_per_heir, 312_407_034)
        self.assertEqual(r.total_tax, 233_647_737)
        self.assertEqual(r.total_tax_conservative, 243_647_737)

    def test_relief_covers_small_tax(self):
        r = tax.transfer_tax(1_100_000_000, 563_000_000, heirs=4)
        self.assertEqual(r.total_tax, 0)
        self.assertGreater(r.total_tax_conservative, 0)

    def test_non_business_surcharge_and_no_gain(self):
        a = tax.transfer_tax(500_000_000, 100_000_000, self_farming=False)
        b = tax.transfer_tax(500_000_000, 100_000_000, self_farming=False, non_business=True)
        self.assertAlmostEqual(b.national_per_heir - a.national_per_heir, (400_000_000 - 2_500_000) * 0.10, delta=1)
        self.assertEqual(tax.transfer_tax(100, 200).total_tax, 0)


class ParcelsTest(unittest.TestCase):
    def test_vworld_parsing(self):
        ch = {"landCharacteristicss": {"field": [
            {"stdrYear": "2025", "lndcgrCodeNm": "답", "lndpclAr": "900", "roadSideCodeNm": "맹지"},
            {"stdrYear": "2026", "lndcgrCodeNm": "답", "lndpclAr": "1000", "roadSideCodeNm": "세로한면(가)",
             "prposArea1Nm": "자연녹지지역"}]}}
        c = parcels.characteristics(ch)
        self.assertEqual((c["jimok"], c["area_m2"], c["road_side"]), ("답", 1000.0, "세로한면(가)"))
        pr = parcels.land_prices({"indvdLandPrices": {"field": [
            {"stdrYear": "2026", "pblntfPclnd": "121000"}, {"stdrYear": "2024", "pblntfPclnd": "100000"}]}})
        self.assertEqual([x["year"] for x in pr], [2024, 2026])
        self.assertAlmostEqual(parcels.price_growth(pr)["cagr_pct"], 10.0)
        self.assertEqual(parcels.coord({"response": {"result": {"point": {"x": "126.7", "y": "35.97"}}}}), (35.97, 126.7))
        self.assertAlmostEqual(parcels.haversine_km((35.0, 127.0), (36.0, 127.0)), 111.2, delta=0.2)


class LawsTest(unittest.TestCase):
    PAYLOAD = {"법령": {"조문": {"조문단위": [
        {"조문번호": "168", "조문여부": "전문", "조문내용": "제3장 양도"},
        {"조문번호": "168", "조문가지번호": "8", "조문여부": "조문", "조문내용": "제168조의8(농지의 범위 등)",
         "항": [{"항내용": "① 첫째 항", "호": [{"호내용": "1. 상속받은 농지"}]}]},
        {"조문번호": "168", "조문여부": "조문", "조문내용": "제168조(본조)"},
    ]}}}

    def test_article_with_branch(self):
        self.assertEqual(laws.article(self.PAYLOAD, "168의8"), "제168조의8(농지의 범위 등)\n① 첫째 항\n1. 상속받은 농지")
        self.assertEqual(laws.article(self.PAYLOAD, "168"), "제168조(본조)")
        self.assertIsNone(laws.article(self.PAYLOAD, "169"))
        found, missing = laws.excerpts([{"title": "소득세법 시행령", "doc_id": "law:x", "payload": self.PAYLOAD}],
                                       {"소득세법 시행령": ["168의8", "999"]})
        self.assertEqual(found[0]["label"], "소득세법 시행령 제168조의8")
        self.assertEqual(missing, ["소득세법 시행령 제999조"])


class BuildTest(unittest.TestCase):
    def test_deadlines(self):
        d = build.deadlines("2026-08-31")
        self.assertEqual([x["date"] for x in d], ["2027-02-28", "2029-08-31", "2031-08-31"])
        self.assertEqual(build.add_months(date(2026, 1, 31), 1), date(2026, 2, 28))

    def test_end_to_end_with_fake_store(self):
        s = load_settings()
        s.inheritance["date"] = "2026-08-31"
        store = Store(Path(tempfile.mkdtemp()))
        store.save(source="trade", key="m1", title="t", url="u", reliability="primary", payload=trade_xml(ROWS))
        for p in s.parcels:
            store.save(source="land", key=f"{p.lot}-characteristics", title="c", url="u", reliability="primary",
                       payload={"landCharacteristicss": {"field": [
                           {"stdrYear": "2026", "lndcgrCodeNm": "답", "lndpclAr": "500", "roadSideCodeNm": "맹지"}]}},
                       meta={"lot": p.lot, "dataset": "characteristics"})
        a = build.build(s, store)
        v = a["valuation"]
        self.assertEqual(v["totals"]["median"], 5 * 500 * 300_000)
        self.assertEqual(v["target_check"]["required_won_per_m2"], 1_100_000_000 // 2500)
        self.assertEqual(a["price_levers"][0]["status"], "해당")  # 맹지 → 진입로 확보 해당
        self.assertTrue(any("실거래 중위 추정" == x["sale_basis"] for x in a["tax"]["scenarios"]))
        self.assertTrue(all("doc_id" not in g for g in a["gaps"]))
        md = build.render_md(a)
        self.assertIn("2027-02-28", md)
        self.assertIn("440,000원/㎡", md)


if __name__ == "__main__":
    unittest.main()
