"""
Online Retail II (UCI): загрузка с проверкой SHA-256 и очистка.

Chen D. 2012. Online Retail II. UCI Machine Learning Repository, CC BY 4.0.
https://archive.ics.uci.edu/dataset/502/online+retail+ii
"""

import hashlib
import io
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "online_retail_ii.zip"
CACHE = ROOT / "data" / "cache" / "raw.parquet"
URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
SHA256 = "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(dest=RAW):
    dest = Path(dest)
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print("скачиваю Online Retail II (43,5 МБ) …")
        urllib.request.urlretrieve(URL, dest)
    if sha256(dest) != SHA256:
        dest.unlink()
        raise RuntimeError("контрольная сумма не совпала — файл удалён")
    return dest


def load_raw():
    """Все строки обоих листов как есть (кэш parquet: xlsx читается ~1,5 минуты)."""
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    with zipfile.ZipFile(fetch()) as z:
        sheets = pd.read_excel(io.BytesIO(z.read("online_retail_II.xlsx")), sheet_name=None,
                               dtype={"Invoice": str, "StockCode": str, "Description": str})
    df = pd.concat(sheets.values(), ignore_index=True)
    df.columns = ["invoice", "stock_code", "description", "quantity", "invoice_date", "price",
                  "customer_id", "country"]
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE)
    return df
