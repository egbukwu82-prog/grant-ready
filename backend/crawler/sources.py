"""Generic fetch layer: URL in, extracted text out, plus fetch metadata.

Nothing in this module knows about grants — the fetch/text mechanism is
reusable for any source a differ wants to watch.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Optional

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 GrantReadyCrawler/0.1"
)

_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "head"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._chunks = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self._chunks.append(re.sub(r"\s+", " ", data).strip())

    def text(self) -> str:
        return "\n".join(self._chunks)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


@dataclass
class FetchResult:
    url: str
    fetched_at: str  # ISO 8601 UTC
    http_status: Optional[int] = None
    text: str = ""
    content_hash: str = ""
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return (
            self.error is None
            and self.http_status is not None
            and 200 <= self.http_status < 300
        )


class Source:
    """A single URL to watch. fetch() never raises — failures land in FetchResult.error."""

    def __init__(self, url: str, timeout: float = 30.0):
        self.url = url
        self.timeout = timeout

    def fetch(self) -> FetchResult:
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            resp = httpx.get(
                self.url,
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
        except Exception as exc:
            return FetchResult(
                url=self.url,
                fetched_at=fetched_at,
                error="{}: {}".format(type(exc).__name__, exc),
            )

        content_type = resp.headers.get("content-type", "text/html")
        text = html_to_text(resp.text) if "html" in content_type else resp.text
        result = FetchResult(
            url=self.url,
            fetched_at=fetched_at,
            http_status=resp.status_code,
            text=text,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
        if not result.ok:
            result.error = "HTTP {}".format(resp.status_code)
        return result
