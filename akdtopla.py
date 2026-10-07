import requests, re, os, json, time
import html as H
from io import StringIO
from datetime import datetime, timedelta, timezone
import pandas as pd

TR = timezone(timedelta(hours=3))
NOW = datetime.now(TR)
UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Mobile Safari/537.36",
      "Accept-Language": "tr-TR,tr;q=0.9"}
LISTE = ["https://www.hisse.net/haber/borsa/turkiye-borsasi",
         "https://www.hisse.net/haber"]
KEY = re.compile(r"(araci|aldi|alim|satti|satis|toplan|bofa|tera|hsbc|yatirim|"
                 r"ziraat|vakif|yapi-kredi|karsi|kurum|gun-sonu|hisseler)")
KURUMLAR = ["İş Yatırım", "TERA", "Bank of America", "BofA", "HSBC", "Yapı Kredi",
            "Ziraat", "Ak Yatırım", "Vakıf", "Garanti", "QNB", "Midas", "Deniz",
            "Gedik", "Tacirler", "Halk", "Info", "Fiba", "Marbaş", "Alternatif",
            "Yatırım Finansman", "Oyak", "Pusula", "Şeker"]
DT = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}:\d{2})")
src = open("scan.py", encoding="utf-8").read()
TICK = set(re.search(r'T = """(.*?)"""', src, re.S).group(1).split())

os.makedirs("docs", exist_ok=True)


def yukle(p, vars_):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return vars_


def duz(txt):
    p = re.sub(r"(?is)<(script|style).*?</\1>", " ", txt)
    p = re.sub(r"<[^>]+>", " ", p)
    return re.sub(r"\s+", " ", H.unescape(p))


REC = yukle("docs/akd.json", [])
SEEN = yukle("docs/akd_seen.json", {})
# tarihi güvenilmeyen / eski biçimli kayıtları temizle, yeniden çekilsin
bozuk = {r["u"] for r in REC if r.get("g") != 1 or "w" not in r}
REC = [r for r in REC if r["u"] not in bozuk]
for u in bozuk:
    SEEN.pop(u, None)
keys = {r["key"] for r in REC}


def num(s):
    m = re.search(r"-?[\d\.,]+", str(s))
    if not m:
        return None
    t = m.group(0).strip(".,")
    if not t:
        return None
    try:
        return float(t.replace(".", "").replace(",", "."))
    except Exception:
        return None


def tablo(df):
    cols = [(" ".join(map(str, c)) if isinstance(c, tuple) else str(c)).strip().lower()
            for c in df.columns]
    if len(cols) < 2:
        return None
    yon = None
    for c in cols[1:]:
        if re.search(r"net\s*al[ıi]", c):
            yon = "alim"
        elif re.search(r"net\s*sat[ıi]", c):
            yon = "satis"
    if not yon:
        return None
    if "hisse" in cols[0]:
        tip = "kurum"
    elif "arac" in cols[0] or "kurum" in cols[0]:
        tip = "hisse"
    else:
        return None
    rows = []
    for _, r in df.iterrows():
        ad = str(r.iloc[0]).strip()
        v = str(r.iloc[1])
        tutar = num(v)
        if tutar is None or not ad or ad.lower() == "nan":
            continue
        birim = "lot" if "lot" in v.lower() else ("TL" if "tl" in v.lower() else "?")
        pay = num(r.iloc[2]) if len(r) > 2 else None
        mal = num(r.iloc[3]) if len(r) > 3 else None
        rows.append([ad, tutar, birim, pay, mal])
    return (tip, yon, rows) if rows else None


# 1) haber linkleri
links = []
for u in LISTE:
    try:
        r = requests.get(u, headers=UA, timeout=30)
        print(u, r.status_code)
        if r.status_code != 200:
            continue
        for m in re.findall(r'href="((?:https://www\.hisse\.net)?/haber/[^"#?]+)"', r.text):
            if m.startswith("/"):
                m = "https://www.hisse.net" + m
            m = m.replace("/haber/amp/", "/haber/")
            if re.search(r"-\d{4,6}$", m) and KEY.search(m) and m not in links:
                links.append(m)
    except Exception as e:
        print("liste hata", u, e)

yeni, atla = 0, 0
for u in links[:50]:
    ilk = SEEN.get(u)
    if ilk:
        try:
            if NOW - datetime.fromisoformat(ilk) > timedelta(hours=12):
                atla += 1
                continue
        except Exception:
            pass
    try:
        time.sleep(1)
        r = requests.get(u, headers=UA, timeout=30)
        if r.status_code != 200:
            continue
        txt = r.text
        SEEN.setdefault(u, NOW.isoformat())
        t = re.search(r"<title>(.*?)</title>", txt, re.S)
        ad = H.unescape(t.group(1)).strip() if t else ""
        plain = duz(txt)
        d = NOW.strftime("%Y-%m-%d %H:%M")
        gk = 0
        govde = plain[:3000]
        m = DT.search(plain)
        if m:
            try:
                dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=TR)
                if timedelta(days=-400) < dt - NOW < timedelta(days=1):
                    d = f"{m.group(3)}-{m.group(2)}-{m.group(1)} {m.group(4)}"
                    gk = 1
                    govde = plain[m.end():m.end() + 1500]
            except Exception:
                pass
        hafta = 1 if "hafta" in (ad + " " + govde).casefold() else 0
        try:
            tb = pd.read_html(StringIO(txt))
        except Exception:
            tb = []
        hisse = next((x for x in re.findall(r"\b([A-Z]{3,6})\b", ad) if x in TICK), None)
        cf = ad.casefold()
        kurum = next((k for k in KURUMLAR if k.casefold() in cf), None)
        for i, df in enumerate(tb):
            x = tablo(df)
            if not x:
                continue
            tip, yon, rows = x
            key = f"{u}|{d}|{tip}|{yon}|{i}"
            if key in keys:
                continue
            keys.add(key)
            REC.append({"key": key, "u": u, "t": ad[:120], "d": d, "g": gk, "w": hafta,
                        "tip": tip, "y": yon, "k": kurum if tip == "kurum" else None,
                        "h": hisse if tip == "hisse" else None, "r": rows,
                        "f": NOW.strftime("%Y-%m-%d %H:%M")})
            yeni += 1
    except Exception as e:
        print("hata", u, e)

print(f"link {len(links)} · yeni kayıt {yeni} · atlanan {atla}")
json.dump(REC, open("docs/akd.json", "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))
json.dump(SEEN, open("docs/akd_seen.json", "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))

# 2) özet sayfa
out = []
P = out.append
P("HİSSE.NET AKD TOPLAMA ÖZETİ")
P(f"Son çalışma: {NOW:%d.%m.%Y %H:%M} · toplam kayıt: {len(REC)} · bu çalışmada yeni: {yeni}")
P("kurum tipi = bir kurumun ilk 5 alım/satım hissesi · hisse tipi = bir hissenin ilk 5 alıcı/satıcı kurumu")
P("Günlük ve haftalık yazılar ayrı sayılır (haftalık = 'hafta' geçen yazılar).")
P("")
gun = {}
for r in REC:
    if r["w"] == 1:
        continue
    d = r["d"][:10]
    s = gun.setdefault(d, {"kurum": 0, "hisse": 0, "hs": set(), "bk": {}})
    s[r["tip"]] += 1
    if r["y"] != "alim":
        continue
    if r["tip"] == "kurum":
        for row in r["r"]:
            s["hs"].add(row[0])
            s["bk"].setdefault(row[0], set()).add(r["k"] or "?")
    else:
        h = r["h"] or "?"
        s["hs"].add(h)
        for row in r["r"]:
            s["bk"].setdefault(h, set()).add(row[0])
P("=== GÜNLÜK YAZILAR ===")
P(f"{'gün':<12}{'kurum':>7}{'hisse':>7}{'farklı hisse(alım)':>20}")
for d in sorted(gun, reverse=True)[:14]:
    s = gun[d]
    P(f"{d:<12}{s['kurum']:>7}{s['hisse']:>7}{len(s['hs']):>20}")
if not gun:
    P("Henüz günlük kayıt yok.")
P("")
P("=== SON 3 GÜN: EN ÇOK FARKLI KURUMUN ALIM LİSTESİNDE GEÇEN HİSSELER (günlük) ===")
son = sorted(gun, reverse=True)[:3]
topl = {}
for d in son:
    for h, ks in gun[d]["bk"].items():
        topl.setdefault(h, set()).update(ks)
for h, ks in sorted(topl.items(), key=lambda a: -len(a[1]))[:15]:
    P(f"{h:<8}{len(ks)} kurum: {', '.join(sorted(ks))[:70]}")
if not topl:
    P("Henüz veri yok.")
P("")
P("=== HAFTALIK KAYITLAR (son 10) ===")
hk = [r for r in REC if r["w"] == 1]
for r in sorted(hk, key=lambda r: r["d"], reverse=True)[:10]:
    ad = ", ".join(x[0] for x in r["r"])
    P(f"{r['d'][:10]} · {r['tip']} · {r['y']} · {r['k'] or r['h'] or '?'} · {ad[:60]}")
if not hk:
    P("Henüz haftalık kayıt yok.")
P("")
P("=== SON 12 KAYIT ===")
for r in sorted(REC, key=lambda r: r["d"], reverse=True)[:12]:
    P(f"{r['d']} · {'H' if r['w'] else 'G'} · {r['tip']} · {r['y']} · "
      f"{r['k'] or r['h'] or '?'} · {len(r['r'])} satır · {r['t'][:45]}")

text = "\n".join(out)
print(text)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>AKD toplama</title><style>body{font:11px/1.45 monospace;padding:12px;"
        "background:#0e1116;color:#e8eaed}pre{overflow-x:auto}</style></head>"
        "<body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/akd.html", "w", encoding="utf-8").write(page)
