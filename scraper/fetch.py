"""Pengambil halaman yang sopan dan tahan gangguan: robots.txt, rate limit, retry + backoff, cache disk."""
import hashlib
import re
import time
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_WAIT = 30.0  # batas jeda retry (detik), termasuk dari header Retry-After


class FetchError(Exception):
    """Gagal setelah semua percobaan (jaringan putus, timeout, atau 5xx terus-menerus)."""


class HttpError(Exception):
    """Server menjawab dengan status yang tidak layak dicoba ulang (404, 403, ...)."""

    def __init__(self, status, url):
        super().__init__(f"HTTP {status} {url}")
        self.status = status


class Blocked(Exception):
    """Dilarang oleh robots.txt."""


@dataclass
class Response:
    url: str
    text: str
    from_cache: bool


def decode(body: bytes, content_type: str = "") -> str:
    """Tentukan encoding dari header, lalu <meta>, lalu utf-8. Mencegah 'Â£' akibat salah tebak."""
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I) or re.search(
        rb"charset=[\"']?([\w-]+)", body[:2048], re.I
    )
    if m:
        name = m.group(1)
        try:
            return body.decode(name.decode() if isinstance(name, bytes) else name)
        except (LookupError, UnicodeDecodeError):
            pass
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("cp1252", errors="replace")


class Fetcher:
    def __init__(self, user_agent="scraper-portofolio/1.0", delay=0.5, retries=4, backoff=0.5,
                 timeout=15.0, cache_dir=None, respect_robots=True, sleep=time.sleep, clock=time.monotonic):
        self.ua = user_agent
        self.delay = delay  # jeda minimum antar request ke host yang sama
        self.retries = retries
        self.backoff = backoff
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.respect_robots = respect_robots
        self.sleep, self.clock = sleep, clock
        self.requests = self.cache_hits = self.retried = 0
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # --- jaringan ---
    def _once(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept": "text/html,*/*"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def _wait(self, url):
        host = urlsplit(url).netloc
        delay = self.delay
        rp = self._robots.get(self._root(url))
        if rp and rp.crawl_delay(self.ua):
            delay = max(delay, float(rp.crawl_delay(self.ua)))
        last = self._last.get(host)
        if last is not None and (gap := self.clock() - last) < delay:
            self.sleep(delay - gap)
        self._last[host] = self.clock()

    def _fetch(self, url):
        """Kembalikan (headers, body) untuk status 200. Retry untuk 429/5xx/timeout dengan backoff."""
        for attempt in range(self.retries + 1):
            self._wait(url)
            self.requests += 1
            retry_after = None
            try:
                status, headers, body = self._once(url)
            except OSError as e:  # URLError, timeout, koneksi putus
                err = str(e)
            else:
                if status == 200:
                    return headers, body
                if status not in RETRY_STATUS:
                    raise HttpError(status, url)
                err = f"HTTP {status}"
                ra = headers.get("Retry-After", "")
                retry_after = float(ra) if ra.isdigit() else None
            if attempt == self.retries:
                raise FetchError(f"{url}: {err} setelah {attempt + 1} percobaan")
            self.retried += 1
            self.sleep(min(retry_after if retry_after is not None else self.backoff * 2**attempt, MAX_WAIT))

    # --- robots.txt ---
    @staticmethod
    def _root(url):
        sp = urlsplit(url)
        return f"{sp.scheme}://{sp.netloc}"

    def _robots_for(self, url):
        root = self._root(url)
        if root not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                headers, body = self._fetch(root + "/robots.txt")
                rp.parse(decode(body, headers.get("Content-Type", "")).splitlines())
            except HttpError as e:
                if e.status in (401, 403):
                    rp.disallow_all = True
                else:
                    rp.allow_all = True  # 404: situs tidak punya aturan
            except FetchError:
                rp.disallow_all = True  # robots.txt tidak terbaca (5xx): bersikap hati-hati
            self._robots[root] = rp
        return self._robots[root]

    # --- publik ---
    def get(self, url, refresh=False) -> Response:
        if self.respect_robots and not self._robots_for(url).can_fetch(self.ua, url):
            raise Blocked(url)
        path = self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".html") if self.cache_dir else None
        if path and path.exists() and not refresh:
            self.cache_hits += 1
            return Response(url, path.read_text("utf-8"), True)
        headers, body = self._fetch(url)
        text = decode(body, headers.get("Content-Type", ""))
        if path:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(text, "utf-8")
            tmp.replace(path)  # atomik: cache setengah jadi tidak pernah terbaca
        return Response(url, text, False)
