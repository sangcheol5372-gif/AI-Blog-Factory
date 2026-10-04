"""VWorld 원자료에서 필지별 사실(지목·면적·도로접면·용도지역·공시지가·좌표)을 뽑는다."""
import math


def _fields(payload) -> list[dict]:
    """VWorld ned 응답은 {"<복수형이름>": {"field": [...]}} 형태다."""
    if not isinstance(payload, dict):
        return []
    for v in payload.values():
        if isinstance(v, dict) and "field" in v:
            f = v["field"]
            return f if isinstance(f, list) else [f]
    return []


def characteristics(payload) -> dict:
    rows = _fields(payload)
    if not rows:
        return {}
    r = max(rows, key=lambda x: str(x.get("stdrYear", "")))  # 최신 기준연도
    area = r.get("lndpclAr")
    return {
        "jimok": r.get("lndcgrCodeNm", ""),
        "area_m2": float(area) if area not in (None, "") else None,
        "road_side": r.get("roadSideCodeNm", ""),
        "shape": r.get("tpgrphFrmCodeNm", ""),
        "terrain": r.get("tpgrphHgCodeNm", ""),
        "zoning": r.get("prposArea1Nm", ""),
        "base_year": r.get("stdrYear", ""),
    }


def land_prices(payload) -> list[dict]:
    """연도별 개별공시지가(원/㎡), 오래된 순."""
    out = []
    for r in _fields(payload):
        try:
            out.append({"year": int(r["stdrYear"]), "won_per_m2": int(r["pblntfPclnd"])})
        except (KeyError, ValueError, TypeError):
            continue
    return sorted(out, key=lambda x: x["year"])


def land_uses(payload) -> list[dict]:
    """용도지역·지구·구역 및 저촉 여부."""
    return [
        {"name": r.get("prposAreaDstrcCodeNm", ""), "status": r.get("cnflcAtNm", "")}
        for r in _fields(payload) if r.get("prposAreaDstrcCodeNm")
    ]


def coord(payload) -> tuple[float, float] | None:
    try:
        p = payload["response"]["result"]["point"]
        return float(p["y"]), float(p["x"])  # (lat, lon)
    except (KeyError, TypeError, ValueError):
        return None


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def price_growth(prices: list[dict]) -> dict | None:
    """공시지가 연평균 상승률(CAGR)."""
    if len(prices) < 2:
        return None
    first, last = prices[0], prices[-1]
    years = last["year"] - first["year"]
    if years <= 0 or first["won_per_m2"] <= 0:
        return None
    cagr = (last["won_per_m2"] / first["won_per_m2"]) ** (1 / years) - 1
    return {"from": first["year"], "to": last["year"], "cagr_pct": round(cagr * 100, 2)}
