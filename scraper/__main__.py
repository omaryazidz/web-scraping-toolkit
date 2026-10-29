"""CLI: python -m scraper --start https://books.toscrape.com/catalogue/page-1.html --out data"""
import argparse
import sys
from pathlib import Path

from .crawl import crawl
from .fetch import Fetcher
from .store import Store


def main(argv=None):
    p = argparse.ArgumentParser(description="Crawler buku yang sopan: robots.txt, rate limit, retry, cache.")
    p.add_argument("--start", default="https://books.toscrape.com/catalogue/page-1.html")
    p.add_argument("--out", default="data", help="folder keluaran (database, CSV, JSON, cache)")
    p.add_argument("--delay", type=float, default=0.5, help="jeda minimum antar request (detik)")
    p.add_argument("--max-pages", type=int, default=None, help="batasi jumlah halaman daftar (untuk uji coba)")
    p.add_argument("--user-agent", default="scraper-portofolio/1.0",
                   help="cantumkan kontak Anda, mis. 'NamaBot/1.0 (+kontak@domain.com)'")
    p.add_argument("--no-cache", action="store_true", help="abaikan cache, ambil ulang semua halaman")
    a = p.parse_args(argv)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    fetcher = Fetcher(user_agent=a.user_agent, delay=a.delay, cache_dir=None if a.no_cache else out / "cache")
    store = Store(out / "books.db")
    r = crawl(fetcher, store, a.start, max_pages=a.max_pages, log=lambda m: print(" ", m, flush=True))
    store.export_csv(out / "books.csv")
    store.export_json(out / "books.json")

    print(f"\n== Ringkasan ({r.seconds} detik) ==")
    print(f"halaman daftar : {r.pages}")
    print(f"produk ditemukan: {r.found}  (baru {r.new}, harga berubah {r.changed}, tetap {r.same})")
    print(f"request jaringan: {r.requests}  (dari cache {r.cache_hits}, diulang {r.retried})")
    print(f"gagal/dilewati  : {len(r.errors)}")
    for url, why in r.errors[:10]:
        print(f"  - {url}: {why}")
    print(f"UPC ganda       : {store.duplicate_upcs()}")
    print(f"hasil           : {out / 'books.csv'}")
    if r.aborted:
        print(f"\nDIHENTIKAN: {r.aborted}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
