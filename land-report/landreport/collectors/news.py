"""Google News RSS 로 개발 호재·규제 관련 보도를 수집한다(키 불필요).

뉴스는 reliability=secondary 로 저장한다. 보고서에서 사실로 쓰려면
보도자료·공시 등 1차 출처로 다시 확인해야 한다(4단계 과장 검토에서 점검).
"""
import xml.etree.ElementTree as ET

from ..http import build_url, get_text
from . import Result

RSS = "https://news.google.com/rss/search"


def parse_rss(xml_text: str, limit: int) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = []
    for it in root.iter("item"):
        src = it.find("source")
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "published": (it.findtext("pubDate") or "").strip(),
            "outlet": src.text.strip() if src is not None and src.text else "",
        })
        if len(items) >= limit:
            break
    return items


def collect(settings, store, fetch=get_text) -> Result:
    res = Result("뉴스")
    cfg = settings.sources.get("news", {})
    limit = cfg.get("max_items_per_query", 30)
    for q in cfg.get("queries", []):
        url = build_url(RSS, {"q": q, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
        try:
            items = parse_rss(fetch(url), limit)
            res.saved.append(store.save(
                source="news", key=q, title=f"뉴스 검색: {q}", url=url,
                reliability="secondary", payload=items, meta={"query": q, "count": len(items)},
            ))
        except Exception as e:
            store.error(source="news", title=q, url=url, error=repr(e))
            res.failed.append(q)
    return res
