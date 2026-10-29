"""Uji mutasi: rusak kode satu per satu di salinan; setiap kerusakan harus membuat minimal satu tes gagal.
Jalankan: python tools/mutation_check.py"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

SRC = pathlib.Path(__file__).resolve().parent.parent
MUTATIONS = {
    "abaikan robots.txt": ("fetch.py", "if self.respect_robots and not self._robots_for(url).can_fetch(self.ua, url):", "if False:"),
    "tanpa retry": ("fetch.py", "if attempt == self.retries:", "if True:"),
    "abaikan header Retry-After": ("fetch.py", 'retry_after = float(ra) if ra.isdigit() else None', "retry_after = None"),
    "404 ikut dicoba ulang": ("fetch.py", "if status not in RETRY_STATUS:", "if False:"),
    "salah decode (latin-1)": ("fetch.py", 'return body.decode("utf-8")\n    except', 'return body.decode("latin-1")\n    except'),
    "abaikan jeda antar request": ("fetch.py", "if last is not None and (gap := self.clock() - last) < delay:", "if False:"),
    "abaikan Crawl-delay robots": ("fetch.py", "if rp and rp.crawl_delay(self.ua):", "if False:"),
    "cache dimatikan": ("fetch.py", "if path and path.exists() and not refresh:", "if False:"),
    "tidak berhenti saat layout berubah": ("crawl.py", "if layout_streak >= max_layout_errors:", "if False:"),
    "produk ganda diambil dua kali": ("crawl.py", "if pu in seen:", "if False:"),
    "riwayat harga tidak dicatat": ("store.py", 'if row["price"] != d["price"]:', "if False:"),
    "satu data rusak menghentikan semua": ("crawl.py", 'r.errors.append((pu, f"data tidak valid: {e}"))', 'r.aborted = "x"; r.errors.append((pu, f"data tidak valid: {e}"))'),
}
for name, (fname, old, new) in MUTATIONS.items():
    with tempfile.TemporaryDirectory() as d:
        shutil.copytree(SRC, d, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".git", ".venv", "data"))
        f = pathlib.Path(d, "scraper", fname)
        t = f.read_text(encoding="utf-8")
        assert old in t, f"pola tidak ketemu: {name}"
        f.write_text(t.replace(old, new, 1), encoding="utf-8")
        try:
            out = subprocess.run([sys.executable, "run_tests.py"], cwd=d, capture_output=True, text=True,
                                 encoding="utf-8", timeout=120).stdout
        except subprocess.TimeoutExpired:
            out = "[FAIL] TIMEOUT"
        failed = len(re.findall(r"\[(FAIL|ERROR)\]", out))
        print(f"{'TERTANGKAP' if failed else 'LOLOS (tes lemah!)':20} {name}  ({failed} tes gagal)")
