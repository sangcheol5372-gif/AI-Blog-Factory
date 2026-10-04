"""국토교통부 토지 매매 실거래가 API(공공데이터포털)로 군산시 토지 거래를 월별 수집한다.

응답은 XML 이며 원문 그대로 저장한다. 신관동·자연녹지 필터링은 2단계(분석)에서 한다.
"""
from datetime import date

from ..http import build_url, get_text
from . import Result

ENDPOINT = "https://apis.data.go.kr/1613000/RTMSDataSvcLandTrade/getRTMSDataSvcLandTrade"


def months_back(n: int, today: date | None = None) -> list[str]:
    """이번 달부터 거슬러 n 개월의 YYYYMM 목록(최근 순)."""
    today = today or date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def collect(settings, store, fetch=get_text, months: int = 36) -> Result:
    res = Result("토지 실거래가")
    key = settings.keys["data_go_kr"]
    if not key:
        res.skipped = "DATA_GO_KR_KEY 미설정 (data.go.kr '국토교통부_토지 매매 실거래가 자료' 활용신청)"
        return res
    lawd = settings.region["lawd_cd"]
    for ym in months_back(months):
        url = build_url(ENDPOINT, {
            "serviceKey": key, "LAWD_CD": lawd, "DEAL_YMD": ym, "pageNo": 1, "numOfRows": 1000,
        })
        try:
            body = fetch(url)
            if "<resultCode>" in body and not any(
                f"<resultCode>{ok}</resultCode>" in body for ok in ("00", "000")
            ):
                raise RuntimeError(body[:300])
            res.saved.append(store.save(
                source="trade", key=f"{lawd}-{ym}", title=f"{settings.region['sigungu']} 토지 실거래 {ym}",
                url=url, reliability="primary", payload=body, meta={"lawd_cd": lawd, "deal_ym": ym},
            ))
        except Exception as e:
            store.error(source="trade", title=ym, url=url, error=repr(e))
            res.failed.append(ym)
    return res
