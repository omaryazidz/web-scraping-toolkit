"""Orkestrasi crawl: ikuti paginasi, ambil tiap produk, simpan, dan laporkan apa yang terjadi."""
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .fetch import Blocked, Fetcher, FetchError, HttpError
from .parse import DataError, LayoutChanged, parse_detail, parse_listing
from .store import Store


@dataclass
class Report:
    pages: int = 0
    found: int = 0
    new: int = 0
    changed: int = 0
    same: int = 0
    blocked: int = 0
    errors: list = field(default_factory=list)  # (url, alasan)
    aborted: str | None = None
    requests: int = 0
    cache_hits: int = 0
    retried: int = 0
    seconds: float = 0.0


def crawl(fetcher: Fetcher, store: Store, start_url: str, max_pages: int | None = None,
          max_layout_errors: int = 3, log=lambda m: None) -> Report:
    """Berhenti dengan pesan jelas kalau struktur situs berubah (max_layout_errors kegagalan beruntun),
    daripada menyimpan data sampah atau terus membebani server."""
    r = Report()
    t0 = time.time()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    seen: set[str] = set()
    layout_streak = 0
    url = start_url

    while url and not r.aborted and (max_pages is None or r.pages < max_pages):
        try:
            page = fetcher.get(url)
            product_urls, next_url = parse_listing(page.text, url)
        except Blocked:
            r.blocked += 1
            r.errors.append((url, "dilarang robots.txt"))
            break
        except (FetchError, HttpError) as e:
            r.errors.append((url, str(e)))
            break  # tanpa halaman daftar, paginasi tidak bisa dilanjutkan
        except LayoutChanged as e:
            r.aborted = f"struktur halaman daftar berubah: {e}"
            break
        r.pages += 1
        log(f"halaman {r.pages}: {len(product_urls)} produk")

        for pu in product_urls:
            if pu in seen:  # produk yang sama muncul di dua halaman daftar
                continue
            seen.add(pu)
            r.found += 1
            try:
                book = parse_detail(fetcher.get(pu).text, pu)
            except Blocked:
                r.blocked += 1
                continue
            except (FetchError, HttpError) as e:
                r.errors.append((pu, str(e)))
                continue
            except DataError as e:
                r.errors.append((pu, f"data tidak valid: {e}"))
                layout_streak = 0
                continue
            except LayoutChanged as e:
                r.errors.append((pu, f"struktur berubah: {e}"))
                layout_streak += 1
                if layout_streak >= max_layout_errors:
                    r.aborted = (f"struktur situs berubah ({layout_streak} halaman produk beruntun gagal diurai): {e}. "
                                 "Crawl dihentikan, tidak ada data sampah yang disimpan.")
                    break
                continue
            layout_streak = 0
            status = store.upsert(book, now)
            setattr(r, status, getattr(r, status) + 1)
        store.commit()  # satu commit per halaman daftar; kalau crawl mati, paling banyak 1 halaman yang diulang
        url = next_url

    store.commit()
    r.requests, r.cache_hits, r.retried = fetcher.requests, fetcher.cache_hits, fetcher.retried
    r.seconds = round(time.time() - t0, 1)
    return r
