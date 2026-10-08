# swing.py - gevşek kurallı swing testi (price action + destek/direnç + trend + hacim + volatilite + piyasa yönü + pozisyon kuralı)
import os, re, ast, json, time, datetime as dt
import numpy as np
import pandas as pd

COST = 0.3        # gidiş-dönüş maliyet %
MAXH = 15         # en fazla tutma (işlem günü)
COOL = 10         # aynı hissede sinyaller arası bekleme
PERIOD = "3y"
TARGET_R = 2.0    # hedef = 2R
MIN_TL = 500000   # günlük ort. işlem hacmi alt sınırı (TL)
OUT = "docs/swing.html"


def get_tickers():
    best = []
    for f in ["scan.py"]:
        if not os.path.exists(f):
            continue
        try:
            tree = ast.parse(open(f, encoding="utf-8").read())
        except Exception as e:
            print("scan.py okunamadi:", e)
            continue
        for node in ast.walk(tree):
            cand = []
            if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
                vals = [n.value for n in node.elts if isinstance(n, ast.Constant) and isinstance(n.value, str)]
                if len(vals) == len(node.elts):
                    cand = vals
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 400:
                cand = [t for t in re.split(r"[\s,;]+", node.value.strip()) if t]
            if len(cand) >= 100 and all(re.fullmatch(r"[A-Za-z0-9]{2,7}(\.IS)?", t) for t in cand):
                if len(cand) > len(best):
                    best = cand
