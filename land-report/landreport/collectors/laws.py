"""국가법령정보센터 Open API 로 현행 법령·자치법규 원문을 수집한다.

OC 값은 open.law.go.kr 에서 무료 신청한 계정 ID(이메일 @ 앞부분)이다.
"""
from ..http import build_url, get_json
from . import Result

SEARCH = "https://www.law.go.kr/DRF/lawSearch.do"
SERVICE = "https://www.law.go.kr/DRF/lawService.do"

# target 별 검색결과의 (일련번호 필드, 이름 필드)
FIELDS = {
    "law": ("법령일련번호", "법령명한글"),
    "ordin": ("자치법규일련번호", "자치법규명"),
}


def _items(obj) -> list[dict]:
    """응답 JSON 구조가 target 마다 달라 첫 번째 dict 목록을 찾아 반환한다."""
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj):
            return obj
        for x in obj:
            if found := _items(x):
                return found
    elif isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, dict) and not any(isinstance(x, (dict, list)) for x in v.values()):
                return [v]  # 결과가 1건이면 목록 대신 dict 로 온다
            if found := _items(v):
                return found
    return []


def find_serial(search_result, target: str, name: str) -> str | None:
    serial_f, name_f = FIELDS[target]
    norm = lambda s: s.replace(" ", "").replace("ㆍ", "·")
    for item in _items(search_result):
        if norm(str(item.get(name_f, ""))) == norm(name):
            return str(item.get(serial_f))
    return None


def collect(settings, store, fetch=get_json) -> Result:
    res = Result("법령")
    oc = settings.keys["law_oc"]
    if not oc:
        res.skipped = "LAW_OC 미설정 (open.law.go.kr 에서 Open API 신청)"
        return res
    jobs = [("law", x) for x in settings.sources.get("laws", [])]
    jobs += [("ordin", x) for x in settings.sources.get("ordinances", [])]
    for target, item in jobs:
        name = item["name"]
        url = build_url(SEARCH, {"OC": oc, "target": target, "type": "JSON", "query": name, "display": 20})
        try:
            serial = find_serial(fetch(url), target, name)
            if not serial:
                raise LookupError("검색 결과에서 정확히 일치하는 이름을 찾지 못함")
            url = build_url(SERVICE, {"OC": oc, "target": target, "type": "JSON", "MST": serial})
            body = fetch(url)
            source = "law" if target == "law" else "ordinance"
            res.saved.append(store.save(
                source=source, key=name, title=name, url=url, reliability="primary",
                payload=body, meta={"serial": serial, "purpose": item.get("purpose", "")},
            ))
        except Exception as e:
            store.error(source="law", title=name, url=url, error=repr(e))
            res.failed.append(name)
    return res
