import requests, json, datetime, os, html, re

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "tr-TR,tr;q=0.9",
    "Origin": "https://www.kap.org.tr",
    "Referer": "https://www.kap.org.tr/tr",
}

bugun = datetime.date.today()
kutular = []


def ekle(ad, durum, detay):
    kutular.append((ad, durum, detay))
    print(ad, durum, detay[:300])


# 1) KAP ana sayfasında gömülü bildirim verisi var mı
try:
    r = requests.get("https://www.kap.org.tr/tr", headers=H, timeout=40)
    t = r.text
    anahtarlar = ["__NEXT_DATA__", "disclosureIndex", "stockCode", "publishDate",
                  "disclosureBasic", "relatedStocks", "summary", "bildirim"]
    sayim = {a: t.count(a) for a in anahtarlar}
    ornek = ""
    for a in ["disclosureIndex", "stockCode", "publishDate"]:
        i = t.find(a)
        if i >= 0:
            ornek = t[max(0, i - 200): i + 600]
            break
    ekle("KAP ana sayfa içeriği", r.status_code,
         "anahtar sayıları: " + json.dumps(sayim) + " | örnek: " + ornek)
except Exception as e:
    ekle("KAP ana sayfa içeriği", "HATA", str(e))

# 2) KAP API uzun bekleme ve farklı biçimler
bas = (bugun - datetime.timedelta(days=3)).isoformat()
body = {
    "fromDate": bas, "toDate": bugun.isoformat(), "year": "", "prd": "", "term": "",
    "ruleType": "", "bdkReview": "", "disclosureClass": "", "index": "",
    "market": "", "isLate": "", "subjectList": [], "mkkMemberOidList": [],
    "inactiveMkkMemberOidList": [], "bdkMemberOidList": [], "mainSector": "",
    "sector": "", "subSector": "", "memberType": "IGS", "fromSrc": "N",
    "srcCategory": "", "discIndex": []
}
adaylar = [
    ("POST memberDisclosureQuery (60 sn)", "POST", "https://www.kap.org.tr/tr/api/memberDisclosureQuery", body),
    ("POST disclosure/list/main boş", "POST", "https://www.kap.org.tr/tr/api/disclosure/list/main", {}),
    ("POST disclosure/list/main tarihli", "POST", "https://www.kap.org.tr/tr/api/disclosure/list/main", body),
    ("GET disclosures", "GET", "https://www.kap.org.tr/tr/api/disclosures", None),
    ("GET bildirim-sorgu sayfası", "GET", "https://www.kap.org.tr/tr/bildirim-sorgu", None),
]
for ad, yontem, url, b in adaylar:
    try:
        if yontem == "POST":
            r = requests.post(url, json=b, headers=dict(H, **{"Content-Type": "application/json"}), timeout=60)
        else:
            r = requests.get(url, headers=H, timeout=60)
        ek = ""
        try:
            j = r.json()
            if isinstance(j, list):
                ek = f"JSON liste {len(j)} kayıt | ilk: " + json.dumps(j[0], ensure_ascii=False)[:500] if j else "JSON boş liste"
            elif isinstance(j, dict):
                ek = "JSON anahtarlar: " + ", ".join(list(j.keys())[:15])
        except Exception:
            ek = r.text[:300].replace("\n", " ")
        ekle(ad, r.status_code, f"boyut {len(r.text)} | {ek}")
    except Exception as e:
        ekle(ad, "HATA", str(e)[:200])


# 3) Google Haberler RSS: eski tarih ve hisse bazlı
def rss(q):
    url = "https://news.google.com/rss/search?q=" + requests.utils.quote(q) + "&hl=tr&gl=TR&ceid=TR:tr"
    r = requests.get(url, headers=H, timeout=40)
    items = re.findall(r"<item>(.*?)</item>", r.text, flags=re.S)
    out = []
    for it in items[:8]:
        ti = re.search(r"<title>(.*?)</title>", it, flags=re.S)
        pd = re.search(r"<pubDate>(.*?)</pubDate>", it, flags=re.S)
        out.append((pd.group(1) if pd else "?") + " | " + (ti.group(1) if ti else "?"))
    return r.status_code, len(items), out


for ad, q in [
    ("Haber: eski tarih (Mart 2025) genel", "KAP hisse tavan after:2025-03-03 before:2025-03-08"),
    ("Haber: INFO eylül sonu", "INFO hisse after:2026-09-25 before:2026-10-03"),
    ("Haber: IZFAS son hafta", "IZFAS after:2026-09-28 before:2026-10-08"),
]:
    try:
        kod, n, out = rss(q)
        ekle(ad, kod, f"{n} haber | " + " || ".join(out))
    except Exception as e:
        ekle(ad, "HATA", str(e)[:200])

os.makedirs("docs", exist_ok=True)
with open("docs/kaptest.html", "w", encoding="utf-8") as f:
    f.write("<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>")
    f.write("<body style='background:#111;color:#eee;font-family:sans-serif;padding:12px'>")
    f.write(f"<h3>KAP erişim testi 2 {datetime.datetime.now():%d.%m.%Y %H:%M}</h3>")
    for ad, durum, detay in kutular:
        renk = "#4c4" if durum == 200 else "#e55"
        f.write("<div style='border:1px solid #333;border-radius:8px;padding:8px;margin:8px 0'>")
        f.write(f"<b>{html.escape(ad)}</b> <span style='color:{renk}'>[{durum}]</span><br>")
        f.write(f"<small style='color:#bbb'>{html.escape(detay[:1500])}</small></div>")
    f.write("</body>")
