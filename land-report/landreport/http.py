import json
import time
import urllib.parse
import urllib.request

USER_AGENT = "Mozilla/5.0 (land-report collector)"


def build_url(base: str, params: dict) -> str:
    return f"{base}?{urllib.parse.urlencode(params)}"


def get_text(url: str, *, retries: int = 3, timeout: int = 20) -> str:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                charset = r.headers.get_content_charset() or "utf-8"
                return r.read().decode(charset, errors="replace")
        except Exception as e:  # 네트워크 오류는 재시도 후 호출자에게 넘긴다
            last = e
            time.sleep(2 ** attempt)
    raise last


def get_json(url: str, **kw):
    return json.loads(get_text(url, **kw))
