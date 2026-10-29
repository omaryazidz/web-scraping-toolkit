"""Penyimpanan SQLite: upsert, riwayat harga, ekspor CSV (bisa dibuka Excel) dan JSON."""
import csv
import json
import sqlite3
from dataclasses import asdict

from .parse import Book

COLUMNS = ["url", "upc", "title", "category", "price", "currency", "in_stock", "stock_qty",
           "rating", "description", "image_url", "first_seen", "last_seen"]


class Store:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """CREATE TABLE IF NOT EXISTS books(
                 url TEXT PRIMARY KEY, upc TEXT, title TEXT, category TEXT, price TEXT, currency TEXT,
                 in_stock INTEGER, stock_qty INTEGER, rating INTEGER, description TEXT, image_url TEXT,
                 first_seen TEXT, last_seen TEXT);
               CREATE TABLE IF NOT EXISTS price_history(url TEXT, price TEXT, seen_at TEXT);"""
        )

    def upsert(self, b: Book, now: str) -> str:
        """Simpan buku. Kembalikan 'new', 'changed' (harga berubah), atau 'same'."""
        row = self.db.execute("SELECT price FROM books WHERE url=?", (b.url,)).fetchone()
        d = asdict(b) | {"price": str(b.price), "in_stock": int(b.in_stock)}
        if row is None:
            self.db.execute(
                f"INSERT INTO books({','.join(COLUMNS)}) VALUES({','.join('?' * len(COLUMNS))})",
                [d.get(c) for c in COLUMNS[:-2]] + [now, now])
            self.db.execute("INSERT INTO price_history VALUES(?,?,?)", (b.url, d["price"], now))
            status = "new"
        else:
            sets = ",".join(f"{c}=?" for c in COLUMNS[1:-2])
            self.db.execute(f"UPDATE books SET {sets}, last_seen=? WHERE url=?",
                            [d[c] for c in COLUMNS[1:-2]] + [now, b.url])
            status = "same"
            if row["price"] != d["price"]:
                self.db.execute("INSERT INTO price_history VALUES(?,?,?)", (b.url, d["price"], now))
                status = "changed"
        return status  # commit dilakukan per halaman oleh crawl(): 1 commit per buku terlalu lambat

    def commit(self):
        self.db.commit()

    def books(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM books ORDER BY url")]

    def history(self, url) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM price_history WHERE url=? ORDER BY rowid", (url,))]

    def duplicate_upcs(self) -> int:
        """Jumlah UPC yang muncul di lebih dari satu URL (indikasi produk ganda di sumber)."""
        return self.db.execute(
            "SELECT count(*) FROM (SELECT upc FROM books GROUP BY upc HAVING count(*) > 1)").fetchone()[0]

    def export_csv(self, path):
        with open(path, "w", newline="", encoding="utf-8-sig") as f:  # BOM supaya Excel membaca UTF-8 dengan benar
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(self.books())

    def export_json(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.books(), f, ensure_ascii=False, indent=2)
