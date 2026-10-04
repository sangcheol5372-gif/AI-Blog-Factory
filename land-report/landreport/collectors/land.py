"""VWorld(국토교통부 공간정보) API 로 필지별 공부 자료를 수집한다.

- 토지이용계획(용도지역·지구, 규제)
- 토지특성(지목, 면적, 도로접면, 형상, 지형)
- 개별공시지가(연도별)
"""
from ..http import build_url, get_json
from . import Result

NED = "https://api.vworld.kr/ned/data"
SEARCH = "https://api.vworld.kr/req/search"
GEOCODE = "https://api.vworld.kr/req/address"

DATASETS = {
    "land_use": ("getLandUseAttr", "토지이용계획"),
    "characteristics": ("getLandCharacteristics", "토지특성"),
    "land_price": ("getIndvdLandPriceAttr", "개별공시지가"),
}


def make_pnu(bjd_code: str, main: int, sub: int, mountain: bool = False) -> str:
    """법정동코드(10) + 대장구분(1: 일반, 2: 산) + 본번(4) + 부번(4)."""
    if len(bjd_code) != 10 or not bjd_code.isdigit():
        raise ValueError(f"법정동코드는 10자리 숫자여야 함: {bjd_code!r}")
    return f"{bjd_code}{2 if mountain else 1}{main:04d}{sub:04d}"


def resolve_pnu(settings, parcel, fetch=get_json) -> str:
    if parcel.pnu:
        return parcel.pnu
    if settings.region.get("bjd_code"):
        return make_pnu(settings.region["bjd_code"], *parcel.main_sub)
    query = f"{settings.address_prefix} {parcel.lot}"
    data = fetch(build_url(SEARCH, {
        "service": "search", "request": "search", "type": "ADDRESS", "category": "PARCEL",
        "query": query, "format": "json", "size": 10, "key": settings.keys["vworld"],
    }))
    items = data.get("response", {}).get("result", {}).get("items", [])
    for it in items:
        pid = str(it.get("id", ""))
        parcel_txt = str(it.get("address", {}).get("parcel", ""))
        if len(pid) == 19 and parcel_txt.endswith(parcel.lot):
            return pid
    raise LookupError(f"PNU 조회 실패: {query}")


def collect(settings, store, fetch=get_json) -> Result:
    res = Result("필지 공부자료")
    key = settings.keys["vworld"]
    if not key:
        res.skipped = "VWORLD_KEY 미설정 (vworld.kr 에서 인증키 발급)"
        return res
    for parcel in settings.parcels:
        try:
            pnu = resolve_pnu(settings, parcel, fetch)
        except Exception as e:
            store.error(source="land", title=parcel.lot, url=SEARCH, error=repr(e))
            res.failed.append(f"{parcel.lot}:pnu")
            continue
        for ds, (endpoint, label) in DATASETS.items():
            url = build_url(f"{NED}/{endpoint}", {
                "pnu": pnu, "format": "json", "numOfRows": 100, "key": key,
            })
            title = f"신관동 {parcel.lot} {label}"
            try:
                res.saved.append(store.save(
                    source="land", key=f"{parcel.lot}-{ds}", title=title, url=url,
                    reliability="primary", payload=fetch(url),
                    meta={"lot": parcel.lot, "pnu": pnu, "dataset": ds},
                ))
            except Exception as e:
                store.error(source="land", title=title, url=url, error=repr(e))
                res.failed.append(f"{parcel.lot}:{ds}")
        # 호재 지점과의 거리 계산용 좌표(WGS84)
        url = build_url(GEOCODE, {
            "service": "address", "request": "getcoord", "type": "parcel", "crs": "epsg:4326",
            "address": f"{settings.address_prefix} {parcel.lot}", "format": "json", "key": key,
        })
        try:
            res.saved.append(store.save(
                source="land", key=f"{parcel.lot}-coord", title=f"신관동 {parcel.lot} 좌표", url=url,
                reliability="primary", payload=fetch(url),
                meta={"lot": parcel.lot, "pnu": pnu, "dataset": "coord"},
            ))
        except Exception as e:
            store.error(source="land", title=f"{parcel.lot} 좌표", url=url, error=repr(e))
            res.failed.append(f"{parcel.lot}:coord")
    return res
