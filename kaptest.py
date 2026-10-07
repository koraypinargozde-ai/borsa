import requests, json, datetime, os, html

H = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "tr-TR,tr;q=0.9",
}

bugun = datetime.date.today()
bas = (bugun - datetime.timedelta(days=7)).isoformat()
son = bugun.isoformat()

kap_body = {
    "fromDate": bas, "toDate": son, "year": "", "prd": "", "term": "",
    "ruleType": "", "bdkReview": "", "disclosureClass": "", "index": "",
    "market": "", "isLate": "", "subjectList": [], "mkkMemberOidList": [],
    "inactiveMkkMemberOidList": [], "bdkMemberOidList": [], "mainSector": "",
    "sector": "", "subSector": "", "memberType": "IGS", "fromSrc": "N",
    "srcCategory": "", "discIndex": []
}

TESTLER = [
    ("KAP ana sayfa", "GET", "https://www.kap.org.tr/tr", None),
    ("KAP bildirim sorgu API (son 7 gün)", "POST",
     "https://www.kap.org.tr/tr/api/memberDisclosureQuery", kap_body),
    ("KAP son bildirimler API", "GET",
     "https://www.kap.org.tr/tr/api/disclosure/list/main", None),
    ("KAP eski tarih (2025-03-03 / 2025-03-07)", "POST",
     "https://www.kap.org.tr/tr/api/memberDisclosureQuery",
     dict(kap_body, fromDate="2025-03-03", toDate="2025-03-07")),
    ("Google News RSS (KAP hisse)", "GET",
     "https://news.google.com/rss/search?q=KAP+bildirim+hisse&hl=tr&gl=TR&ceid=TR:tr", None),
    ("hisse.net ana sayfa", "GET", "https://www.hisse.net/", None),
    ("Is Yatirim ana sayfa", "GET", "https://www.isyatirim.com.tr/", None),
]

satirlar = []
for ad, yontem, url, body in TESTLER:
    try:
        if yontem == "POST":
            r = requests.post(url, json=body, headers=dict(H, **{"Content-Type": "application/json"}), timeout=25)
        else:
            r = requests.get(url, headers=H, timeout=25)
        metin = r.text[:600].replace("\n", " ")
        ct = r.headers.get("Content-Type", "")
        ek = ""
        try:
            j = r.json()
            if isinstance(j, list):
                ek = f"JSON liste, {len(j)} kayıt"
                if j:
                    ek += " | ilk: " + json.dumps(j[0], ensure_ascii=False)[:500]
            elif isinstance(j, dict):
                ek = "JSON sözlük, anahtarlar: " + ", ".join(list(j.keys())[:15])
        except Exception:
            pass
        satirlar.append((ad, url, r.status_code, ct, len(r.text), ek, metin))
        print(ad, r.status_code, ct, len(r.text), ek[:200])
    except Exception as e:
        satirlar.append((ad, url, "HATA", "", 0, str(e)[:300], ""))
        print(ad, "HATA", e)

os.makedirs("docs", exist_ok=True)
with open("docs/kaptest.html", "w", encoding="utf-8") as f:
    f.write("<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>")
    f.write("<body style='background:#111;color:#eee;font-family:sans-serif;padding:12px'>")
    f.write(f"<h3>KAP erişim testi {datetime.datetime.now():%d.%m.%Y %H:%M}</h3>")
    for ad, url, kod, ct, n, ek, metin in satirlar:
        renk = "#4c4" if kod == 200 else "#e55"
        f.write(f"<div style='border:1px solid #333;border-radius:8px;padding:8px;margin:8px 0'>")
        f.write(f"<b>{html.escape(ad)}</b> <span style='color:{renk}'>[{kod}]</span><br>")
        f.write(f"<small>{html.escape(url)}</small><br>")
        f.write(f"<small>tür: {html.escape(ct)} | boyut: {n}</small><br>")
        if ek:
            f.write(f"<small>{html.escape(ek)}</small><br>")
        f.write(f"<small style='color:#999'>{html.escape(metin[:300])}</small></div>")
    f.write("</body>")
