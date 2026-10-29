# Web Scraping & Data Extraction: Crawler yang Sopan dan Tahan Gangguan

Crawler yang mengambil data produk dari sebuah situs, membersihkannya, dan menyimpannya ke **CSV (bisa dibuka Excel), JSON, dan SQLite**, lengkap dengan riwayat perubahan harga.

Scraping yang asal jalan biasanya gagal diam-diam: situs mengubah tampilan lalu data jadi kosong, server memblokir karena terlalu agresif, atau simbol mata uang rusak menjadi `Â£`. Project ini dibuat untuk **tidak gagal diam-diam**: kalau ada yang salah, ia berhenti dengan pesan yang jelas atau melewati item bermasalah dan melaporkannya.

Target demo: [books.toscrape.com](https://books.toscrape.com), situs yang memang dibuat untuk latihan scraping.

## Hasil di situs sungguhan

```
python -m scraper
== Ringkasan (1238.8 detik) ==
halaman daftar : 50
produk ditemukan: 1000  (baru 1000, harga berubah 0, tetap 0)
request jaringan: 1051  (dari cache 0, diulang 0)
gagal/dilewati  : 0
UPC ganda       : 0
```

**1.000 buku dari 50 halaman, 0 gagal.** Hasilnya ada di [results/books.csv](results/books.csv) dan [results/books.json](results/books.json). Pemeriksaan kualitas datanya ([results/data-quality.txt](results/data-quality.txt)):

- 1.000 URL unik dan 1.000 UPC unik, tidak ada kolom wajib yang kosong
- Harga £10,00 sampai £59,99, rating tersebar di 1 sampai 5, 50 kategori
- Simbol `£` terbaca benar. Ada 1 deskripsi yang berisi teks rusak, tapi itu berasal dari **sumbernya** (byte mentah dari server sudah rusak), bukan dari scraper. Penjelasannya ada di file kualitas data.

**Crawl ulang tidak membebani server.** Menjalankan perintah yang sama lagi hanya memakai **1 request** (mengecek `robots.txt`), sedangkan 1.050 halaman lain diambil dari cache. Waktunya 8,4 detik, dibanding 20 menit untuk crawl pertama ([results/crawl-cached.log](results/crawl-cached.log)).

Crawl pertama memakan 20 menit karena server situs itu sendiri lambat (sekitar 1 detik per halaman), bukan karena crawler. Jeda sopan 0,5 detik antar request sudah termasuk.

## Hasil tes ketahanan

```
python run_tests.py     ->  16/16 lulus
```

Tes berjalan melawan server palsu di komputer sendiri yang sengaja dibuat bermasalah, jadi hasilnya sama setiap kali dan tidak menyentuh situs orang lain.

| Masalah di dunia nyata | Perilaku yang terbukti |
|---|---|
| `robots.txt` melarang satu bagian | Halaman itu tidak pernah di-request, dilaporkan sebagai *blocked* |
| `robots.txt` meminta `Crawl-delay` | Jeda mengikuti permintaan situs |
| Server error 503 sementara | Dicoba ulang dengan backoff, lalu berhasil |
| Server membalas 429 + `Retry-After` | Menunggu sesuai angka dari server |
| Satu halaman error terus-menerus | Dilewati setelah percobaan habis (4 request, tidak membanjiri), 11 lainnya tetap masuk |
| Halaman 404 | Langsung dicatat gagal, tidak diulang |
| Server tidak mengirim `charset` | Simbol mata uang tetap benar (bukan `Â£`) |
| Harga satu produk rusak ("abc") | Produk itu dilewati dan dilaporkan, yang lain tetap tersimpan |
| **Situs mengubah struktur HTML** | **Berhenti setelah 3 kegagalan beruntun dengan pesan jelas, 0 data sampah tersimpan** |
| Produk muncul di dua halaman | Hanya diambil satu kali |
| Harga naik antar-crawl | Terdeteksi (`changed`) dan tercatat di riwayat harga |
| Deskripsi berisi koma, kutip, baris baru | CSV tetap utuh saat dibaca kembali |

### Apakah tesnya benar-benar menangkap bug?

Uji mutasi ([`tools/mutation_check.py`](tools/mutation_check.py)) merusak kode dengan sengaja di 12 tempat, dan tiap kerusakan harus membuat minimal satu tes gagal. **12 dari 12 tertangkap** ([results/mutation.txt](results/mutation.txt)), termasuk mengabaikan robots.txt, mematikan retry, mengabaikan `Retry-After`, salah decode, mematikan cache, dan tidak berhenti saat struktur situs berubah.

## Pemakaian

Butuh Python 3.10+ dan satu library (`beautifulsoup4`).

```bash
python -m venv .venv
./.venv/Scripts/pip install -r requirements.txt     # Linux/Mac: ./.venv/bin/pip
./.venv/Scripts/python -m scraper --out data         # crawl penuh
./.venv/Scripts/python -m scraper --out demo --max-pages 2     # uji coba kecil
```

Opsi: `--delay` (jeda antar request, default 0,5 detik), `--max-pages`, `--no-cache` (ambil ulang semua), dan `--user-agent`. **Isi `--user-agent` dengan kontak Anda** (mis. `NamaBot/1.0 (+kontak@domain.com)`) agar pemilik situs bisa menghubungi bila perlu. Itu etika dasar crawler.

## Cara kerja

```
Fetcher   robots.txt -> jeda antar request -> retry + backoff (429/5xx/timeout) -> cache disk
Parser    daftar produk -> halaman detail -> Book (harga Decimal, rating, stok, kategori, UPC)
          elemen wajib hilang  = LayoutChanged  (struktur situs berubah, hitung beruntun)
          isi elemen tidak valid = DataError    (lewati item itu saja)
Store     SQLite (upsert, riwayat harga) -> ekspor CSV (UTF-8 + BOM agar Excel benar) dan JSON
```

## Batasan

- **Menyesuaikan dengan situs klien perlu kerja tambahan.** Selector di [`scraper/parse.py`](scraper/parse.py) khusus untuk struktur books.toscrape.com. Untuk situs lain, bagian itu ditulis ulang, sedangkan fetcher, cache, penyimpanan, dan laporan bisa dipakai ulang apa adanya.
- **Hanya halaman HTML statis.** Situs yang memuat data lewat JavaScript (React/SPA) butuh browser headless atau pemanggilan API internalnya. Belum dicakup.
- **Tidak menembus perlindungan anti-bot** (CAPTCHA, login, Cloudflare), dan memang tidak dimaksudkan begitu. Cek syarat penggunaan dan robots.txt situs target, dan hanya ambil data yang boleh diambil.
- Format harga yang dipahami baru `£51.77`, `$10`, dan `€5.00` (titik sebagai desimal). Format koma desimal (`€5,00`) dan rupiah (`Rp1.250.000`) belum didukung dan perlu ditambah di `parse_price`.
- Satu proses, satu host, berurutan. Cukup untuk ribuan halaman. Skala jutaan halaman butuh antrean dan banyak worker.
- Data demo ini milik books.toscrape.com dan dipakai hanya sebagai contoh.

## Struktur

```
scraper/fetch.py     robots.txt, rate limit, retry, cache
scraper/parse.py     ekstraksi + pembeda LayoutChanged/DataError
scraper/store.py     SQLite, riwayat harga, ekspor CSV/JSON
scraper/crawl.py     orkestrasi, laporan, penghentian saat struktur berubah
tests/               16 uji + situs palsu yang bisa disetel rusak
tools/               uji mutasi
results/             hasil crawl asli (1.000 buku), log, kualitas data
```
