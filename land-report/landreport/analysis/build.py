"""원자료 → analysis.json(3단계 입력) + analysis.md(사람이 읽는 요약)."""
import json
from datetime import date, datetime, timezone

from . import laws as law_an
from . import parcels as pa
from . import tax
from . import trades as tr

FARMLAND = ("전", "답", "과수원")


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise AssertionError


def deadlines(inherit_date: str) -> list[dict]:
    if not inherit_date:
        return []
    d = date.fromisoformat(inherit_date)
    return [
        {"label": "상속재산 평가기간 종료(상속개시일 후 6개월)", "date": add_months(d, 6).isoformat(),
         "why": "이 기간 안의 매매가액은 상속재산 시가로 평가될 수 있음 → 양도차익은 줄고 상속세 과세가액은 늘어남",
         "basis": "상속세 및 증여세법 제60조, 시행령 제49조"},
        {"label": "자경기간 승계 양도 기한(상속개시일 후 3년)", "date": add_months(d, 36).isoformat(),
         "why": "상속인이 경작하지 않아도 피상속인 경작기간을 승계해 자경감면 판단",
         "basis": "조세특례제한법 시행령 제66조"},
        {"label": "상속농지 비사업용 토지 예외 기한(상속개시일 후 5년)", "date": add_months(d, 60).isoformat(),
         "why": "기한 내 양도 시 비사업용 토지 중과(+10%p) 배제",
         "basis": "소득세법 시행령 제168조의8"},
    ]


def _group_land(store) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for doc in store.documents("land"):
        m = doc.get("meta", {})
        out.setdefault(m.get("lot"), {})[m.get("dataset")] = doc
    return out


def analyze_parcels(settings, store, gaps: list[str]) -> list[dict]:
    land = _group_land(store)
    verified_sites = [s for s in settings.sites if s.get("verified") and s.get("lat") and s.get("lon")]
    result = []
    for p in settings.parcels:
        docs = land.get(p.lot, {})
        row = {"lot": p.lot, "zoning_user": p.zoning, "official_value": p.official_value,
               "appraisal_min": p.appraisal_min, "appraisal_max": p.appraisal_max, "sources": []}
        if "characteristics" in docs:
            row.update(pa.characteristics(docs["characteristics"]["payload"]))
            row["sources"].append(docs["characteristics"]["doc_id"])
        else:
            gaps.append(f"{p.lot}: 토지특성(지목·면적·도로접면) 없음 → VWORLD_KEY 로 land 수집 필요")
        prices = pa.land_prices(docs["land_price"]["payload"]) if "land_price" in docs else []
        row["land_prices"] = prices
        row["price_growth"] = pa.price_growth(prices)
        if prices:
            row["sources"].append(docs["land_price"]["doc_id"])
            if not row.get("area_m2"):
                row["area_m2_estimated"] = round(p.official_value / prices[-1]["won_per_m2"], 1)
        row["land_uses"] = pa.land_uses(docs["land_use"]["payload"]) if "land_use" in docs else []
        if "land_use" in docs:
            row["sources"].append(docs["land_use"]["doc_id"])
        c = pa.coord(docs["coord"]["payload"]) if "coord" in docs else None
        row["coord"] = c
        row["distances_km"] = [
            {"site": s["name"], "km": round(pa.haversine_km(c, (s["lat"], s["lon"])), 1), "source": s.get("source", "")}
            for s in verified_sites
        ] if c else []
        result.append(row)
    if not verified_sites:
        gaps.append("확인된 개발 호재 지점(좌표·1차 출처) 없음 → config/parcels.toml [[sites]] 에 입력")
    return result


def analyze_trades(settings, store, parcels: list[dict], gaps: list[str]) -> dict:
    deals = []
    for doc in store.documents("trade"):
        try:
            deals.extend(tr.parse_trades(doc["payload"], doc["doc_id"]))
        except Exception as e:
            gaps.append(f"실거래 원자료 파싱 실패 {doc['doc_id']}: {e!r}")
    if not deals:
        gaps.append("실거래가 자료 없음 → DATA_GO_KR_KEY 로 trade 수집 필요")
        return {"by_jimok": {}, "total_deals": 0}
    jimoks = sorted({p.get("jimok", "") for p in parcels}) or [""]
    by_jimok = {j or "전체": tr.comparables(deals, settings.region["dong"], jimok=j) for j in jimoks}
    for j, comp in by_jimok.items():
        if comp["chosen"] is None:
            gaps.append(f"비교사례 부족(지목 {j}): 어느 비교군도 5건 미만")
    return {"by_jimok": by_jimok, "total_deals": len(deals), "_deals": deals}


def valuation(settings, parcels: list[dict], trades: dict, gaps: list[str]) -> dict:
    rows, totals = [], {"p25": 0, "median": 0, "p75": 0}
    complete = True
    for p in parcels:
        area = p.get("area_m2") or p.get("area_m2_estimated")
        comp = trades.get("by_jimok", {}).get(p.get("jimok") or "전체")
        if not area or not comp or not comp.get("chosen"):
            complete = False
            rows.append({"lot": p["lot"], "estimate": None})
            continue
        ch = comp["chosen"]
        est = {k: round(area * ch[f"{k}_won_per_m2"]) for k in totals}
        for k in totals:
            totals[k] += est[k]
        rows.append({"lot": p["lot"], "area_m2": area, "area_is_estimated": not p.get("area_m2"),
                     "comparable_tier": comp["chosen_tier"], "estimate": est, "sources": comp["sources"]})
    target = settings.assumptions.get("target_sale_total")
    out = {"parcels": rows, "totals": totals if complete else None,
           "appraisal_total": [sum(p["appraisal_min"] for p in parcels), sum(p["appraisal_max"] for p in parcels)],
           "target_total": target}
    total_area = sum((p.get("area_m2") or p.get("area_m2_estimated") or 0) for p in parcels)
    if target and total_area and all((p.get("area_m2") or p.get("area_m2_estimated")) for p in parcels):
        need = target / total_area
        all_deals = trades.get("_deals", [])
        zone_deals = [d for d in all_deals if "자연녹지" in d["zoning"] and not d["cancelled"] and not d["share_deal"]]
        out["target_check"] = {
            "required_won_per_m2": round(need),
            "required_won_per_pyeong": round(need * tr.M2_PER_PYEONG),
            "percentile_in_city_natural_green": tr.percentile_of(need, zone_deals),
        }
    else:
        gaps.append("목표가(11억) 검증 불가: 필지 면적 미확보")
    if not complete:
        gaps.append("시세 기반 추정가 산출 불가: 면적 또는 비교사례 부족")
    return out


def regulations(settings, store, parcels: list[dict], gaps: list[str]) -> dict:
    wanted = {x["name"]: x.get("articles", []) for x in settings.sources.get("laws", []) if x.get("articles")}
    found, missing = law_an.excerpts(store.documents("law"), wanted)
    if missing:
        gaps.append(f"법령 조문 {len(missing)}건 미확보 → LAW_OC 로 law 수집 필요")
    issues = []
    jimoks = {p.get("jimok") for p in parcels if p.get("jimok")}
    if jimoks & set(FARMLAND) or not jimoks:
        issues += [
            {"topic": "매수자 농지취득자격증명", "basis": "농지법 제8조",
             "note": "매수자가 농업인이 아니면 농업경영계획서 등 요건 필요 → 매수자 범위·가격에 직접 영향"},
            {"topic": "농지전용 가능성", "basis": "농지법 제34조, 시행령 제32·33조",
             "note": "전용 허가 가능 여부가 '개발 가능한 땅' 가격의 핵심 근거"},
            {"topic": "상속농지 소유 상한", "basis": "농지법 제7조", "note": "비농업인 상속인의 소유 한도 확인"},
        ]
    issues += [
        {"topic": "자연녹지지역 건축 가능 용도·밀도", "basis": "국토계획법 시행령 제71조(별표17)·제84조·제85조, 군산시 도시계획 조례",
         "note": "건폐율·용적률·허용 건축물이 매수자의 활용 가치(=가격)를 결정"},
        {"topic": "개발행위허가 기준", "basis": "국토계획법 제56·58조, 군산시 도시계획 조례",
         "note": "경사도·도로·배수 요건 충족 여부"},
        {"topic": "접도 요건", "basis": "건축법 제44조", "note": "건축법상 도로 2m 이상 접하지 않으면 건축 불가 → 가격 큰 폭 하락 요인"},
        {"topic": "토지거래허가구역 여부", "basis": "부동산 거래신고 등에 관한 법률 제10·11조",
         "note": "지정 시 매수자 실수요 요건·허가 필요"},
    ]
    if not jimoks:
        gaps.append("지목 미확인: 농지 관련 쟁점을 모두 포함해 둠 (지목 확인 후 정리)")
    restricted = [{"lot": p["lot"], **u} for p in parcels for u in p.get("land_uses", []) if "저촉" in u.get("status", "")]
    return {"excerpts": found, "missing_articles": missing, "issues": issues, "restricted_zones": restricted}


def price_levers(parcels: list[dict]) -> list[dict]:
    """가격을 실질적으로 올릴 수 있는 수단. 공부 자료로 해당 여부를 판단한다."""
    def status(cond):
        return "확인 필요" if cond is None else ("해당" if cond else "해당 없음")
    road = [p.get("road_side", "") for p in parcels]
    no_road = None if not any(road) else any("맹지" in r for r in road)
    farmland = None if not any(p.get("jimok") for p in parcels) else any(p.get("jimok") in FARMLAND for p in parcels)
    return [
        {"lever": "진입로·도로 접면 확보", "status": status(no_road),
         "why": "맹지 해소는 토지 가격에 가장 큰 영향. 인접 필지 통행권·도로 개설 검토", "basis": "건축법 제44조"},
        {"lever": "농지전용·개발행위허가 사전 확보(또는 가능성 검토서)", "status": status(farmland),
         "why": "매수자의 인허가 리스크를 매도인이 제거하면 가격 협상력 상승", "basis": "농지법 제34조, 국토계획법 제56조"},
        {"lever": "인접 필지 합필·일괄 매각", "status": "확인 필요",
         "why": "408-5·409-3·410-2 는 지번이 연속 — 인접 여부 확인 후 하나의 개발 단위로 묶어 팔면 활용도·단가 상승 가능",
         "basis": "공간정보관리법 제80조"},
        {"lever": "매도 시점(6개월·3년·5년 기한) 설계", "status": "해당",
         "why": "같은 가격이라도 시점에 따라 세후 수령액이 크게 달라짐", "basis": "상증법 제60조, 조특법 시행령 제66조, 소득세법 시행령 제168조의8"},
    ]


def news_digest(store) -> list[dict]:
    seen, out = set(), []
    for doc in store.documents("news"):
        for it in doc["payload"]:
            if it["title"] in seen:
                continue
            seen.add(it["title"])
            out.append({**it, "query": doc["meta"].get("query"), "source": doc["doc_id"], "reliability": "secondary"})
    return out


def build(settings, store) -> dict:
    gaps: list[str] = []
    parcels = analyze_parcels(settings, store, gaps)
    trades = analyze_trades(settings, store, parcels, gaps)
    val = valuation(settings, parcels, trades, gaps)
    inh = settings.inheritance
    if not inh.get("date"):
        gaps.append("상속개시일 미입력 → 6개월·3년·5년 기한 계산 불가 (config/parcels.toml [inheritance] date)")
    sale_prices = {"목표가(11억)": settings.assumptions["target_sale_total"],
                   "감정 최대 합계": val["appraisal_total"][1]}
    if val.get("totals"):
        sale_prices["실거래 중위 추정"] = val["totals"]["median"]
    acquisitions = {"기준시가": sum(p["official_value"] for p in parcels),
                    "감정 최소": val["appraisal_total"][0], "감정 최대": val["appraisal_total"][1]}
    news = news_digest(store)
    if not news:
        gaps.append("뉴스 자료 없음 → news 수집 필요(네트워크 허용 필요)")
    trades.pop("_deals", None)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "region": settings.region,
        "parcels": parcels,
        "deadlines": deadlines(inh.get("date", "")),
        "comparables": trades,
        "valuation": val,
        "tax": {
            "assumptions": tax.ASSUMPTIONS,
            "scenarios": tax.scenarios(sale_prices, acquisitions, inh.get("heir_scenarios", [1]),
                                       self_farming=settings.assumptions.get("self_farming_relief", True)),
            "note_6_months": "상속개시일 후 6개월 안에 매도하면 그 매매가가 상속재산 평가액(=양도 시 취득가액)이 되어 "
                             "양도차익이 거의 0 이 될 수 있다. 대신 상속세 과세가액이 늘어나므로 상속공제 규모와 비교해 "
                             "세무사와 판단해야 한다.",
        },
        "regulations": regulations(settings, store, parcels, gaps),
        "price_levers": price_levers(parcels),
        "news": news,
        "gaps": gaps,
    }


def won(n) -> str:
    return "-" if n is None else f"{int(n):,}원"


def render_md(a: dict) -> str:
    L = [f"# 2단계 분석 결과 — {a['region']['sigungu']} {a['region']['dong']}", "",
         f"생성: {a['generated_at']}  ", "모든 수치는 근거 doc_id 와 함께 analysis.json 에 있음.", ""]
    L += ["## 1. 데이터 공백 (판단 보류 항목)", ""]
    L += [f"- {g}" for g in a["gaps"]] or ["- 없음"]
    L += ["", "## 2. 필지 현황", "", "| 지번 | 지목 | 면적(㎡) | 도로접면 | 용도지역 | 기준시가 | 감정 범위 | 공시지가 연상승률 |",
          "|---|---|---|---|---|---|---|---|"]
    for p in a["parcels"]:
        area = p.get("area_m2") or (f"~{p['area_m2_estimated']}(추정)" if p.get("area_m2_estimated") else "?")
        g = p.get("price_growth")
        growth = f"{g['cagr_pct']}% ({g['from']}~{g['to']})" if g else "?"
        L.append(f"| {p['lot']} | {p.get('jimok') or '?'} | {area} | {p.get('road_side') or '?'} | "
                 f"{p.get('zoning') or p['zoning_user']} | {won(p['official_value'])} | "
                 f"{won(p['appraisal_min'])}~{won(p['appraisal_max'])} | {growth} |")
    v = a["valuation"]
    L += ["", "## 3. 시세 추정과 목표가 검증", "",
          f"- 감정 합계: {won(v['appraisal_total'][0])} ~ {won(v['appraisal_total'][1])}",
          f"- 목표가: {won(v['target_total'])}"]
    if v.get("totals"):
        t = v["totals"]
        L.append(f"- 실거래 비교사례 기반: {won(t['p25'])} (하위25%) / {won(t['median'])} (중위) / {won(t['p75'])} (상위25%)")
    else:
        L.append("- 실거래 비교사례 기반 추정: 자료 부족으로 보류")
    if v.get("target_check"):
        tc = v["target_check"]
        L.append(f"- 목표가 달성에 필요한 단가: {won(tc['required_won_per_m2'])}/㎡ "
                 f"({won(tc['required_won_per_pyeong'])}/평), 군산 자연녹지 거래 중 상위 {100 - (tc['percentile_in_city_natural_green'] or 0):.0f}% 수준")
    if a["deadlines"]:
        L += ["", "## 4. 기한", ""] + [f"- **{d['date']}** {d['label']} — {d['why']} ({d['basis']})" for d in a["deadlines"]]
    L += ["", "## 5. 양도세 추정 (간이, 세무사 확인 필요)", "",
          "| 매도가 기준 | 취득가 기준 | 상속인 | 세액(낙관) | 세액(보수) | 세후 수령액(보수) |", "|---|---|---|---|---|---|"]
    for s in a["tax"]["scenarios"]:
        L.append(f"| {s['sale_basis']} {won(s['sale_price'])} | {s['acquisition_basis']} {won(s['acquisition'])} | "
                 f"{s['heirs']}인 | {won(s['total_tax'])} | {won(s['total_tax_conservative'])} | "
                 f"{won(s['net_proceeds_conservative'])} |")
    L += ["", "전제: " + " / ".join(a["tax"]["assumptions"]), "", f"> {a['tax']['note_6_months']}"]
    L += ["", "## 6. 법적 쟁점", ""] + [f"- **{i['topic']}** ({i['basis']}): {i['note']}" for i in a["regulations"]["issues"]]
    if a["regulations"]["restricted_zones"]:
        L += ["", "저촉 규제:"] + [f"- {r['lot']}: {r['name']} ({r['status']})" for r in a["regulations"]["restricted_zones"]]
    L += ["", f"조문 원문 확보 {len(a['regulations']['excerpts'])}건 / 미확보 {len(a['regulations']['missing_articles'])}건"]
    L += ["", "## 7. 가격 제고 수단", ""] + [f"- [{x['status']}] **{x['lever']}** — {x['why']} ({x['basis']})" for x in a["price_levers"]]
    L += ["", "## 8. 관련 보도 (2차 자료 — 1차 출처 확인 전에는 사실로 인용 금지)", ""]
    L += [f"- {n['published'][:16]} {n['outlet']}: {n['title']}" for n in a["news"][:40]] or ["- 없음"]
    return "\n".join(L) + "\n"


def write(a: dict, out_dir) -> tuple:
    out_dir.mkdir(parents=True, exist_ok=True)
    j, m = out_dir / "analysis.json", out_dir / "analysis.md"
    j.write_text(json.dumps(a, ensure_ascii=False, indent=2), encoding="utf-8")
    m.write_text(render_md(a), encoding="utf-8")
    return j, m
