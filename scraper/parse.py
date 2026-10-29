"""Ekstraksi data dari HTML. Membedakan 'struktur situs berubah' dari 'data satu item rusak'."""
import re
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urljoin

from bs4 import BeautifulSoup

RATING = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
CURRENCY = {"£": "GBP", "$": "USD", "€": "EUR", "": ""}


class LayoutChanged(Exception):
    """Elemen yang wajib ada tidak ditemukan: kemungkinan besar situs mengubah struktur HTML."""


class DataError(Exception):
    """Elemen ada, tapi isinya tidak bisa dipahami (harga 'abc', dll). Hanya item ini yang dilewati."""


@dataclass
class Book:
    url: str
    title: str
    price: Decimal
    currency: str
    in_stock: bool
    stock_qty: int | None
    rating: int
    category: str
    upc: str
    description: str
    image_url: str


def _soup(html):
    return BeautifulSoup(html, "html.parser")


def _need(node, selector, what):
    found = node.select_one(selector)
    if found is None:
        raise LayoutChanged(f"selector '{selector}' ({what}) tidak ditemukan")
    return found


def parse_listing(html: str, page_url: str) -> tuple[list[str], str | None]:
    """Kembalikan (daftar URL produk, URL halaman berikutnya atau None)."""
    soup = _soup(html)
    links = [urljoin(page_url, a["href"]) for a in soup.select("article.product_pod h3 a[href]")]
    if not links:
        raise LayoutChanged("tidak ada produk di halaman daftar (selector 'article.product_pod h3 a')")
    nxt = soup.select_one("li.next a[href]")
    return links, urljoin(page_url, nxt["href"]) if nxt else None


def parse_price(text: str) -> tuple[Decimal, str]:
    m = re.fullmatch(r"\s*([£$€]?)\s*(\d+(?:\.\d{1,2})?)\s*", text)
    if not m:
        raise DataError(f"format harga tidak dikenal: {text!r}")
    return Decimal(m.group(2)), CURRENCY[m.group(1)]


def parse_detail(html: str, url: str) -> Book:
    soup = _soup(html)
    title = _need(soup, "h1", "judul").get_text(strip=True)
    price, currency = parse_price(_need(soup, "p.price_color", "harga").get_text())

    stock_text = _need(soup, "p.availability", "stok").get_text(" ", strip=True)
    qty = re.search(r"(\d+)\s+available", stock_text)

    star = _need(soup, "p.star-rating", "rating")
    rating = next((RATING[c] for c in star.get("class", []) if c in RATING), None)
    if rating is None:
        raise DataError(f"rating tidak dikenal: {star.get('class')}")

    crumbs = [a.get_text(strip=True) for a in soup.select("ul.breadcrumb li a")]
    if len(crumbs) < 2:
        raise LayoutChanged("breadcrumb kategori tidak ditemukan")

    upc = next((td.get_text(strip=True) for th in soup.select("table th") if th.get_text(strip=True) == "UPC"
                for td in [th.find_next_sibling("td")] if td), None)
    if not upc:
        raise LayoutChanged("kolom UPC di tabel produk tidak ditemukan")

    desc = soup.select_one("#product_description ~ p")  # deskripsi memang opsional
    img = soup.select_one("div.item.active img, .thumbnail img")
    return Book(
        url=url, title=title, price=price, currency=currency,
        in_stock="in stock" in stock_text.lower(), stock_qty=int(qty.group(1)) if qty else None,
        rating=rating, category=crumbs[-1], upc=upc,
        description=desc.get_text(strip=True) if desc else "",
        image_url=urljoin(url, img["src"]) if img and img.get("src") else "",
    )
