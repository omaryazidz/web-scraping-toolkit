"""Situs toko buku palsu (server lokal) yang bisa disetel rusak: 503, 429, robots.txt, layout berubah, dll."""
import collections
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CATEGORIES = ["Fiksi", "Sejarah"]


class Site:
    def __init__(self, pages=3, per_page=4):
        self.pages, self.per_page = pages, per_page
        self.hits = collections.Counter()  # path -> jumlah request yang diterima
        self.fail = {}  # path -> [(status, retry_after), ...] dikembalikan berurutan sebelum jawaban normal
        self.robots = None  # teks robots.txt; None = 404
        self.layout_v2 = False  # True: situs mengubah HTML (selector harga hilang)
        self.prices = {}  # id -> harga yang menimpa
        self.bad_price = set()  # id dengan harga "abc"
        self.no_desc = set()
        self.descs = {}  # id -> deskripsi khusus
        self.dup_on_page2 = False  # halaman 2 mengulang produk #1
        self.charset_header = False
        site = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                with site.lock:
                    site.hits[self.path] += 1
                    plan = site.fail.get(self.path)
                    failure = plan.pop(0) if plan else None
                if failure:
                    code, retry_after = failure
                    self.send_response(code)
                    if retry_after is not None:
                        self.send_header("Retry-After", str(retry_after))
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                code, body = site.render(self.path)
                data = body.encode("utf-8")
                self.send_response(code)
                ct = "text/html" + ("; charset=utf-8" if site.charset_header else "")
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.lock = threading.Lock()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, args=(0.05,), daemon=True).start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    @property
    def start_url(self):
        return self.url + "/catalogue/page-1.html"

    # --- halaman ---
    def render(self, path):
        if path == "/robots.txt":
            return (200, self.robots) if self.robots is not None else (404, "")
        if m := re.fullmatch(r"/catalogue/page-(\d+)\.html", path):
            return self.listing(int(m.group(1)))
        if m := re.fullmatch(r"/catalogue/book-(\d+)/index\.html", path):
            return self.detail(int(m.group(1)))
        return 404, "tidak ada"

    def listing(self, n):
        if not 1 <= n <= self.pages:
            return 404, "tidak ada"
        ids = list(range((n - 1) * self.per_page + 1, n * self.per_page + 1))
        if n == 2 and self.dup_on_page2:
            ids.append(1)
        cards = "".join(
            f'<article class="product_pod"><h3><a href="book-{i}/index.html" title="Buku {i}">Buku {i}</a></h3></article>'
            for i in ids)
        nxt = f'<li class="next"><a href="page-{n + 1}.html">next</a></li>' if n < self.pages else ""
        return 200, f"<html><body>{cards}<ul class='pager'>{nxt}</ul></body></html>"

    def detail(self, i):
        if i < 1 or i > self.pages * self.per_page:
            return 404, "tidak ada"
        price = "abc" if i in self.bad_price else f"£{self.prices.get(i, 10 + i):.2f}"
        price_tag = f'<span class="price">{price}</span>' if self.layout_v2 else f'<p class="price_color">{price}</p>'
        rating = ["One", "Two", "Three", "Four", "Five"][i % 5]
        desc = "" if i in self.no_desc else (
            '<div id="product_description" class="sub-header"><h2>Product Description</h2></div>'
            f"<p>{self.descs.get(i, f'Deskripsi buku {i}')}</p>")
        return 200, f"""<html><body>
<ul class="breadcrumb"><li><a href="../../index.html">Home</a></li><li><a href="../c.html">Books</a></li>
<li><a href="../c.html">{CATEGORIES[i % 2]}</a></li><li class="active">Buku {i}</li></ul>
<div class="item active"><img src="../../media/{i}.jpg"></div>
<h1>Buku {i}</h1>{price_tag}
<p class="instock availability"><i></i> In stock ({10 + i} available)</p>
<p class="star-rating {rating}"></p>{desc}
<table><tr><th>UPC</th><td>upc{i:04d}</td></tr></table>
</body></html>"""
