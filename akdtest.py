import requests, re, os
import html as H
from io import StringIO
import pandas as pd

UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Mobile Safari/537.36",
      "Accept-Language": "tr-TR,tr;q=0.9"}
LISTE = ["https://www.hisse.net/haber/borsa/turkiye-borsasi",
         "https://www.hisse.net/haber"]
KEY = re.compile(r"(aldi|alim|satti|satis|arac|kurum|dagilim|gun-sonu|toplan"
                 r"|bofa|tera|hsbc|is-yatirim|yatirim)")

out = []
P = out.append
links = []
for u in LISTE:
    try:
        r = requests.get(u, headers=UA, timeout=30)
        P(f"{u} -> HTTP {r.status_code}, {len(r.text)} karakter")
        if r.status_code != 200:
            continue
        for m in re.findall(r'href="((?:https://www\.hisse\.net)?/haber/[^"#?]+)"', r.text):
            if m.startswith("/"):
                m = "https://www.hisse.net" + m
            m = m.replace("/haber/amp/", "/haber/")
            if re.search(r"-\d{4,6}$", m) and KEY.search(m) and m not in links:
                links.append(m)
    except Exception as e:
        P(f"{u} -> HATA {e}")

P("")
P(f"Aday haber linki: {len(links)}")
for u in links[:15]:
    try:
        r = requests.get(u, headers=UA, timeout=30)
        t = re.search(r"<title>(.*?)</title>", r.text, re.S)
        ad = H.unescape(t.group(1)).strip() if t else "?"
        try:
            tb = pd.read_html(StringIO(r.text))
        except Exception:
            tb = []
        P(f"- HTTP {r.status_code} · tablo {len(tb)} · {ad[:90]}")
        P(f"  {u}")
        for x in tb[:2]:
            P("  " + x.head(6).to_string(index=False).replace("\n", "\n  "))
    except Exception as e:
        P(f"- HATA {u} {e}")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>AKD test</title><style>body{font:11px/1.45 monospace;padding:12px;"
        "background:#0e1116;color:#e8eaed}pre{overflow-x:auto}</style></head>"
        "<body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/akdtest.html", "w", encoding="utf-8").write(page)
