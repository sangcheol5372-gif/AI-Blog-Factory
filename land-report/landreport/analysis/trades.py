"""토지 실거래 XML 파싱과 비교사례 통계."""
import statistics
import xml.etree.ElementTree as ET

M2_PER_PYEONG = 3.305785

# 2024년 이후 영문 태그, 이전 한글 태그를 모두 지원한다.
FIELD_ALIASES = {
    "dong": ("umdNm", "법정동"),
    "jibun": ("jibun", "지번"),
    "jimok": ("jimok", "지목"),
    "zoning": ("landUse", "용도지역"),
    "area": ("dealArea", "거래면적"),
    "amount": ("dealAmount", "거래금액"),
    "year": ("dealYear", "년"),
    "month": ("dealMonth", "월"),
    "day": ("dealDay", "일"),
    "cancel": ("cdealType", "해제여부"),
    "share": ("shareDealingType", "지분거래구분"),
}


def _get(item, key: str) -> str:
    for tag in FIELD_ALIASES[key]:
        v = item.findtext(tag)
        if v is not None and v.strip():
            return v.strip()
    return ""


def parse_trades(xml_text: str, doc_id: str = "") -> list[dict]:
    root = ET.fromstring(xml_text)
    out = []
    for item in root.iter("item"):
        try:
            area = float(_get(item, "area").replace(",", ""))
            amount_won = int(_get(item, "amount").replace(",", "")) * 10_000  # 만원 단위
        except ValueError:
            continue
        if area <= 0:
            continue
        y, m, d = _get(item, "year"), _get(item, "month"), _get(item, "day")
        out.append({
            "dong": _get(item, "dong"),
            "jibun": _get(item, "jibun"),
            "jimok": _get(item, "jimok"),
            "zoning": _get(item, "zoning"),
            "area_m2": area,
            "price_won": amount_won,
            "won_per_m2": amount_won / area,
            "date": f"{y}-{int(m or 0):02d}-{int(d or 0):02d}",
            "cancelled": _get(item, "cancel") == "O",
            "share_deal": "지분" in _get(item, "share"),
            "source": doc_id,
        })
    return out


def _stats(deals: list[dict]) -> dict:
    vals = sorted(d["won_per_m2"] for d in deals)
    n = len(vals)
    if n == 0:
        return {"n": 0}
    q = statistics.quantiles(vals, n=4) if n >= 2 else [vals[0]] * 3
    return {
        "n": n,
        "median_won_per_m2": round(statistics.median(vals)),
        "p25_won_per_m2": round(q[0]),
        "p75_won_per_m2": round(q[2]),
        "min_won_per_m2": round(vals[0]),
        "max_won_per_m2": round(vals[-1]),
        "median_won_per_pyeong": round(statistics.median(vals) * M2_PER_PYEONG),
    }


def comparables(deals: list[dict], dong: str, jimok: str = "", zoning_kw: str = "자연녹지",
                min_n: int = 5) -> dict:
    """가까운 조건부터 넓혀가며 비교군을 만든다. 해제 거래·지분 거래는 제외한다."""
    clean = [d for d in deals if not d["cancelled"] and not d["share_deal"]]
    in_zone = [d for d in clean if zoning_kw in d["zoning"]]
    tiers = [
        ("동일 동·용도지역·지목", [d for d in in_zone if d["dong"] == dong and (not jimok or d["jimok"] == jimok)]),
        ("동일 동·용도지역", [d for d in in_zone if d["dong"] == dong]),
        ("시 전체·동일 용도지역·지목", [d for d in in_zone if not jimok or d["jimok"] == jimok]),
        ("시 전체·동일 용도지역", in_zone),
    ]
    tier_stats = [{"tier": name, **_stats(ds)} for name, ds in tiers]
    chosen = next((i for i, t in enumerate(tier_stats) if t["n"] >= min_n), None)
    chosen_deals = tiers[chosen][1] if chosen is not None else []
    return {
        "excluded": {"cancelled": sum(d["cancelled"] for d in deals),
                     "share_deal": sum(d["share_deal"] for d in deals)},
        "tiers": tier_stats,
        "chosen_tier": tier_stats[chosen]["tier"] if chosen is not None else None,
        "chosen": tier_stats[chosen] if chosen is not None else None,
        "deals": sorted(chosen_deals, key=lambda d: d["date"], reverse=True)[:30],
        "sources": sorted({d["source"] for d in chosen_deals}),
    }


def percentile_of(value: float, deals: list[dict]) -> float | None:
    """value 가 비교사례 ㎡당 가격 분포에서 몇 % 지점인지(0~100)."""
    if not deals:
        return None
    below = sum(1 for d in deals if d["won_per_m2"] < value)
    return round(100 * below / len(deals), 1)
