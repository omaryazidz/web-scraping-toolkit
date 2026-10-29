"""Uji ketahanan scraper terhadap situs lokal yang sengaja dibuat bermasalah. Jalankan: python run_tests.py"""
import csv
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from scraper.crawl import crawl
from scraper.fetch import Fetcher
from scraper.store import Store
from tests.site import Site


class ScraperTest(unittest.TestCase):
    def setUp(self):
        self.site = Site()
        self.tmp = tempfile.TemporaryDirectory()
        self.sleeps = []  # jeda yang diminta fetcher; dicatat, tidak benar-benar ditunggu
        self.store = Store()

    def tearDown(self):
        self.site.stop()
        self.tmp.cleanup()

    def fetcher(self, **kw):
        kw = {"delay": 0, "retries": 3, "backoff": 0.01, "sleep": self.sleeps.append} | kw
        return Fetcher(**kw)

    def run_crawl(self, fetcher=None, store=None, **kw):
        return crawl(fetcher or self.fetcher(), store or self.store, self.site.start_url, **kw)

    def fake_clock(self):
        """Jam palsu: waktu hanya maju saat fetcher 'tidur', jadi jeda bisa diukur persis tanpa menunggu."""
        t = [0.0]

        def sleep(s):
            self.sleeps.append(s)
            t[0] += s
        return {"clock": lambda: t[0], "sleep": sleep}

    def book_path(self, i):
        return f"/catalogue/book-{i}/index.html"

    # ---------- hasil dasar ----------
    def test_01_semua_halaman_dan_produk_terambil_dengan_tipe_data_benar(self):
        """Crawl 3 halaman -> 12 buku tersimpan; harga Decimal, rating angka, stok, kategori, UPC benar"""
        r = self.run_crawl()
        self.assertEqual((r.pages, r.found, r.new, r.errors), (3, 12, 12, []))
        b = {x["upc"]: x for x in self.store.books()}["upc0001"]
        self.assertEqual(Decimal(b["price"]), Decimal("11.00"))
        self.assertEqual((b["rating"], b["stock_qty"], b["in_stock"]), (2, 11, 1))
        self.assertEqual((b["title"], b["category"], b["currency"]), ("Buku 1", "Sejarah", "GBP"))
        self.assertTrue(b["image_url"].endswith("/media/1.jpg"))

    def test_02_simbol_pound_tidak_rusak_walau_server_tidak_kirim_charset(self):
        """Server tanpa header charset -> simbol mata uang tetap terbaca benar (bukan mojibake), tidak ada harga gagal"""
        self.assertFalse(self.site.charset_header)
        r = self.run_crawl()
        self.assertEqual(r.errors, [])
        self.assertEqual({x["currency"] for x in self.store.books()}, {"GBP"})

    # ---------- sopan santun ----------
    def test_03_halaman_yang_dilarang_robots_txt_tidak_diambil(self):
        """robots.txt melarang /catalogue/book-2/ -> tidak pernah di-request, dilaporkan sebagai blocked"""
        self.site.robots = "User-agent: *\nDisallow: /catalogue/book-2/\n"
        r = self.run_crawl()
        self.assertEqual(self.site.hits[self.book_path(2)], 0)
        self.assertEqual((r.blocked, len(self.store.books())), (1, 11))

    def test_04_crawl_delay_dari_robots_txt_dipatuhi(self):
        """robots.txt meminta Crawl-delay 3 detik -> fetcher menunggu minimal 3 detik antar request"""
        self.site.robots = "User-agent: *\nCrawl-delay: 3\n"
        f = self.fetcher(**self.fake_clock())  # delay bawaan 0, tapi robots.txt meminta 3
        self.run_crawl(f, max_pages=1)
        # request pertama (robots.txt) tidak menunggu; setiap request berikutnya menunggu penuh 3 detik
        self.assertEqual(self.sleeps, [3.0] * (f.requests - 1))

    def test_05_jeda_antar_request_dipatuhi(self):
        """Delay 1 detik -> setiap request setelah yang pertama didahului jeda 1 detik"""
        f = self.fetcher(delay=1.0, **self.fake_clock())
        self.run_crawl(f, max_pages=1)
        self.assertEqual(self.sleeps, [1.0] * (f.requests - 1))

    # ---------- gangguan di jaringan/server ----------
    def test_06_error_503_sementara_dicoba_ulang_sampai_berhasil(self):
        """Server error 503 dua kali lalu pulih -> dicoba ulang otomatis, buku tetap tersimpan"""
        self.site.fail[self.book_path(1)] = [(503, None), (503, None)]
        f = self.fetcher()
        r = self.run_crawl(f)
        self.assertEqual((r.found, len(self.store.books()), r.errors), (12, 12, []))
        self.assertEqual((self.site.hits[self.book_path(1)], f.retried), (3, 2))

    def test_07_header_retry_after_pada_429_dipatuhi(self):
        """Server membalas 429 dengan Retry-After 7 -> fetcher menunggu 7 detik, bukan menebak"""
        self.site.fail[self.book_path(1)] = [(429, 7)]
        self.run_crawl()
        self.assertIn(7.0, self.sleeps)

    def test_08_halaman_yang_terus_error_dilewati_tanpa_menghentikan_crawl(self):
        """Satu buku 503 terus -> dicatat sebagai gagal setelah percobaan habis, 11 buku lain tetap masuk"""
        self.site.fail[self.book_path(5)] = [(503, None)] * 20
        r = self.run_crawl()
        self.assertEqual(len(self.store.books()), 11)
        self.assertEqual(len(r.errors), 1)
        self.assertIn("5/index.html", r.errors[0][0])
        self.assertEqual(self.site.hits[self.book_path(5)], 4)  # 1 + 3 retry, tidak membanjiri server

    def test_09_halaman_tidak_ada_404_tidak_dicoba_ulang(self):
        """Produk 404 -> langsung dicatat gagal, tidak diulang"""
        self.site.fail[self.book_path(3)] = [(404, None)]
        r = self.run_crawl()
        self.assertEqual((self.site.hits[self.book_path(3)], len(r.errors)), (1, 1))

    # ---------- kualitas data ----------
    def test_10_data_satu_produk_rusak_hanya_melewati_produk_itu(self):
        """Harga 'abc' pada satu produk -> produk itu dicatat tidak valid, 11 lainnya tersimpan"""
        self.site.bad_price = {2}
        r = self.run_crawl()
        self.assertEqual(len(self.store.books()), 11)
        self.assertIn("data tidak valid", r.errors[0][1])
        self.assertIsNone(r.aborted)

    def test_11_perubahan_struktur_situs_menghentikan_crawl_tanpa_data_sampah(self):
        """Situs mengubah HTML -> berhenti setelah 3 kegagalan beruntun dengan pesan jelas, 0 data sampah"""
        self.site.layout_v2 = True
        r = self.run_crawl()
        self.assertIn("struktur situs berubah", r.aborted)
        self.assertEqual(len(self.store.books()), 0)
        detail_hits = sum(n for p, n in self.site.hits.items() if "/book-" in p)
        self.assertEqual(detail_hits, 3)  # tidak melanjutkan ke 12 halaman

    def test_12_deskripsi_kosong_adalah_normal(self):
        """Buku tanpa deskripsi tetap diterima (field opsional)"""
        self.site.no_desc = {1}
        r = self.run_crawl()
        self.assertEqual((r.errors, len(self.store.books())), ([], 12))

    def test_13_produk_yang_muncul_di_dua_halaman_hanya_diambil_sekali(self):
        """Buku #1 muncul lagi di halaman 2 -> hanya 1 request detail dan 1 baris data"""
        self.site.dup_on_page2 = True
        r = self.run_crawl()
        self.assertEqual((r.found, len(self.store.books()), self.site.hits[self.book_path(1)]), (12, 12, 1))

    # ---------- efisiensi & pemantauan ----------
    def test_14_crawl_ulang_dari_cache_tidak_memakai_jaringan(self):
        """Crawl kedua memakai cache -> 0 request ke halaman (hanya robots.txt dicek ulang), hasil sama"""
        cache = Path(self.tmp.name) / "cache"
        self.run_crawl(self.fetcher(cache_dir=cache))
        pages_before = sum(n for p, n in self.site.hits.items() if p != "/robots.txt")
        f2 = self.fetcher(cache_dir=cache)
        r = self.run_crawl(f2, store=Store())
        pages_after = sum(n for p, n in self.site.hits.items() if p != "/robots.txt")
        self.assertEqual(pages_after, pages_before)
        self.assertEqual((f2.requests, f2.cache_hits), (1, 15))  # 1 = robots.txt, 15 = 3 daftar + 12 produk
        self.assertEqual((r.found, r.errors), (12, []))

    def test_15_perubahan_harga_terdeteksi_dan_tercatat_di_riwayat(self):
        """Harga buku #1 naik antar crawl -> status 'changed' dan riwayat harga berisi 2 catatan"""
        self.run_crawl()
        self.site.prices[1] = 99.5
        r = self.run_crawl()  # tanpa cache -> ambil ulang
        self.assertEqual((r.new, r.changed, r.same), (0, 1, 11))
        url = self.site.url + self.book_path(1)
        self.assertEqual([h["price"] for h in self.store.history(url)], ["11.00", "99.50"])

    # ---------- ekspor ----------
    def test_16_csv_aman_untuk_koma_kutip_dan_baris_baru(self):
        """Deskripsi berisi koma, tanda kutip, dan baris baru -> CSV tetap utuh saat dibaca kembali"""
        tricky = 'Halo, "dunia"\nbaris kedua'
        self.site.descs[1] = tricky
        self.run_crawl()
        out = Path(self.tmp.name) / "books.csv"
        self.store.export_csv(out)
        rows = list(csv.DictReader(open(out, encoding="utf-8-sig", newline="")))
        self.assertEqual(len(rows), 12)
        # html parser menormalkan spasi putih; isi dan tanda kutip tetap
        self.assertTrue(any(r["description"].startswith('Halo, "dunia"') for r in rows))
        self.assertTrue(all(Decimal(r["price"]) > 0 for r in rows))


if __name__ == "__main__":
    unittest.main()
