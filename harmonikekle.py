import os, re, json
import datetime as dt
import html as H
import harmonik as hk

DOSYA = "docs/harmonik.json"
GECMIS = "docs/harmonik_gecmis.json"
SAYFA = "docs/index.html"
ISARET = ("<!--HARM-->", "<!--/HARM-->")
GRUPLAR = ("Gartley", "Cypher")
SON_BAR = 25      # son 25 işlem günündeki sinyaller
YENILE_DK = 120   # taramayı en fazla 2 saatte bir yap
SURUM = 2         # kayıt biçimi değişince artır, kutu kendini yeniler
DUSUK_ESIK = 0.62 # D→onay 4 gün ort. hacim / 20g ort. bu değerin altı = düşük hacim


def simdi():
    return dt.datetime.now(dt.timezone.utc)


def eski_mi():
    try:
        j = json.load(open(DOSYA, encoding="utf-8"))
        if j.get("v") != SURUM:
            return True, j
        t = dt.datetime.fromisoformat(j["t"])
        return (simdi() - t).total_seconds() / 60 >= YENILE_DK, j
    except Exception:
        return True, None


def kapali(x):
    return x.get("giris") is not None and x.get("durum") != "açık"


def gecmis_yukle():
    try:
        return json.load(open(GECMIS, encoding="utf-8"))
    except Exception:
        return {}


def gecmis_kaydet(g):
    os.makedirs("docs", exist_ok=True)
    json.dump(g, open(GECMIS, "w", encoding="utf-8"), ensure_ascii=False)


def hacim_orani(v, sb):
    d = sb - hk.PIVOT_N
    if d < 21 or sb < 21:
        return None
    a = v[d - 20:d].mean()
    if a <= 0:
        return None
    return float(v[d:sb + 1].mean() / a)


def tara():
    src = open("scan.py", encoding="utf-8").read()
    T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
    tick = [t + ".IS" for t in dict.fromkeys(T)]
    hk.PERIOD = "1y"
    veri = hk.indir(tick)
    if not veri:
        return None
    kayit = []
    for hisse, x in veri.items():
        o, h, l, c = (x[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
        try:
            v = x["Volume"].values.astype(float)
        except Exception:
            v = None
        N = len(o)
        if N < 80:
            continue
        for (sb, yon, nm, X, A, D) in hk.detect(h, l):
            if yon != 1 or nm not in GRUPLAR:
                continue
            if N - 1 - sb > SON_BAR:
                continue
            stop, Tg = hk.seviyeler(yon, X, A, D)
            hv = hacim_orani(v, sb) if v is not None else None
            r = dict(hisse=hisse, ad=nm, tarih=x.index[sb].strftime("%d.%m.%y"),
                     sb=int(N - 1 - sb), stop=float(stop), T=[float(t) for t in Tg],
                     son=float(c[-1]), vt=x.index[-1].strftime("%d.%m.%y"),
                     hv=hv, dh=bool(hv is not None and hv <= DUSUK_ESIK))
            if sb + 1 >= N:
                if not (stop < c[-1] < Tg[0]):
                    continue
                r.update(durum="giriş bekliyor", giris=None, cik=None,
                         hit=[False] * 3, gun=0, sonuc=None)
                kayit.append(r)
                continue
            e = sb + 1
            entry = float(o[e])
            if not (stop < entry < Tg[0]):
                continue
            hit = [False] * 3
            stopped = False
            stop_fiyat = stop
            sonbar = min(e + hk.MAXD - 1, N - 1)
            gun = 0
            for j in range(e, sonbar + 1):
                gun = j - e + 1
                if j > e and o[j] <= stop:
                    stopped = True
                    stop_fiyat = float(o[j])   # boşlukla açıldıysa açılıştan çık
                    break
                if l[j] <= stop:
                    stopped = True
                    stop_fiyat = stop
                    break
                for i in range(3):
                    if h[j] >= Tg[i]:
                        hit[i] = True
                if hit[2]:
                    break
            dolu = (e + hk.MAXD - 1) <= N - 1
            if hit[2]:
                durum, cik = "T3 ✔ tamam", Tg[2]
            elif stopped:
                durum, cik = "STOP", stop_fiyat
            elif dolu:
                durum, cik = "süre doldu", c[sonbar]
            else:
                durum, cik = "açık", c[-1]
            r.update(durum=durum, giris=entry, cik=float(cik), hit=hit, gun=int(gun),
                     sonuc=float((cik / entry - 1) * 100))
            kayit.append(r)
    kayit.sort(key=lambda r: r["sb"])
    return kayit[:20]


def pc(x):
    return f"{x:+.1f}".replace(".", ",") + "%"


def renkli(x):
    renk = "#3fb950" if x >= 0 else "#f85149"
    return f"<span style='color:{renk}'>{pc(x)}</span>"


def tarih_key(x):
    try:
        return dt.datetime.strptime(x["tarih"], "%d.%m.%y")
    except Exception:
        return dt.datetime(2000, 1, 1)


def detay(x, kapanan):
    son = x["son"]
    vt = x.get("vt", "")
    etiket = f" · {vt} kapanışı" if vt else ""
    s = ["<div style='padding:4px 0 2px 12px;font-size:12px'>"]
    if x.get("giris") is not None:
        fark = (son / x["giris"] - 1) * 100
        s.append(f"Giriş {hk.fp(x['giris'])} · {x['gun']}. gün<br>")
        if kapanan and x.get("cik") is not None:
            s.append(f"Çıkış {hk.fp(x['cik'])} ({renkli(x['sonuc'])}) · {x['durum']}<br>")
        s.append(f"Şimdi {hk.fp(son)} ({renkli(fark)}){etiket}<br>")
    else:
        s.append("Giriş: sonraki işlem günü açılışı<br>")
        s.append(f"Referans: {hk.fp(son)}{etiket}<br>")
    s.append(f"Stop {hk.fp(x['stop'])}<br>")
    for i, t in enumerate(x["T"]):
        tik = " ✔" if x["hit"][i] else ""
        s.append(f"T{i + 1} {hk.fp(t)}{tik}<br>")
    if x.get("hv") is not None:
        dus = " 🔇 düşük" if x.get("dh") else ""
        s.append(f"Hacim (D→onay 4 gün ort. / 20g ort.): {hk.fp(x['hv'])}x{dus}<br>")
    s.append("</div>")
    return "".join(s)


def ses(x):
    return " 🔇" if x.get("dh") else ""


def aktif_satir(x):
    son = x["son"]
    if x.get("giris") is None:
        ozet = f"⏳ giriş bekliyor · referans {hk.fp(son)}"
    else:
        fark = (son / x["giris"] - 1) * 100
        ozet = f"🔵 açık · şimdi {hk.fp(son)} ({renkli(fark)})"
    return ("<details style='border-top:1px solid #30363d;padding:6px 0'>"
            f"<summary><b>{H.escape(x['hisse'])}</b> {x['ad']}{ses(x)} · {x['tarih']} · {ozet}</summary>"
            + detay(x, False) + "</details>")


def kapanan_satir(x):
    d = x["durum"]
    if d.startswith("T3"):
        et = "✅ T3 tamam"
    elif d == "STOP":
        et = "❌ STOP"
        if x["hit"][0]:
            et += " (T1 görüldü)"
    else:
        et = "⏱ süre doldu"
    ozet = f"{et} ({renkli(x['sonuc'])})"
    return ("<details style='border-top:1px solid #30363d;padding:6px 0;opacity:.9'>"
            f"<summary><b>{H.escape(x['hisse'])}</b> {x['ad']}{ses(x)} · {x['tarih']} · {ozet}</summary>"
            + detay(x, True) + "</details>")


def ozet_satiri(kap):
    n = len(kap)
    if not n:
        return "Henüz kapanan işlem yok."
    t1 = sum(1 for x in kap if x["hit"][0])
    t2 = sum(1 for x in kap if x["hit"][1])
    t3 = sum(1 for x in kap if x["hit"][2])
    st = sum(1 for x in kap if x["durum"] == "STOP")
    sd = sum(1 for x in kap if x["durum"] == "süre doldu")
    poz = sum(1 for x in kap if x["sonuc"] > 0)
    ort = sum(x["sonuc"] for x in kap) / n
    return (f"{n} işlem · T1 {t1} · T2 {t2} · T3 {t3} · ❌ stop {st} · ⏱ süre {sd} · "
            f"kârda kapanan {poz}/{n} · ortalama {renkli(ort)}")


def grup_ozet(kap, ad):
    n = len(kap)
    if not n:
        return f"{ad}: henüz yok"
    t1 = sum(1 for x in kap if x["hit"][0])
    st = sum(1 for x in kap if x["durum"] == "STOP")
    ort = sum(x["sonuc"] for x in kap) / n
    return f"{ad}: {n} işlem · T1 {t1} · stop {st} · ortalama {renkli(ort)}"


def kutu(j, g):
    r = j["r"] if j else []
    aktif = [x for x in r if not kapali(x)]
    kap = sorted(g.values(), key=tarih_key, reverse=True)[:40]
    dusuk = [x for x in kap if x.get("dh") is True]
    diger = [x for x in kap if x.get("dh") is False]
    s = ["<div style='margin:14px 0;padding:12px;border-radius:12px;background:#161b22;"
         "color:#e8eaed;font:13px/1.5 sans-serif'>"]
    s.append("<div style='font-weight:700;font-size:15px'>📐 Harmonik boğa takibi "
             "(Gartley / Cypher)</div>")
    s.append("<div style='opacity:.7;font-size:11px;margin:2px 0 8px'>Giriş: onaydan sonraki "
             "ilk açılış · stop: X'in %0,5 ötesi (boşlukla açılırsa açılıştan çıkış) · "
             "hedefler D→A %38,2 / %61,8 / %100 · en fazla 20 gün · "
             "🔇 = D→onay 4 gün ort. hacim ≤0,62x (testte daha iyi çıktı, canlıda doğrulanıyor) · "
             "henüz canlı doğrulanmadı, sadece takip</div>")
    s.append(f"<div style='font-weight:600;margin-top:6px'>Aktif ({len(aktif)})</div>")
    if not aktif:
        s.append("<div style='opacity:.7'>Şu an aktif sinyal yok.</div>")
    for x in aktif:
        s.append(aktif_satir(x))
    s.append(f"<div style='font-weight:600;margin-top:14px'>Kapanan işlemler ({len(kap)})</div>")
    s.append(f"<div style='opacity:.85;font-size:12px;margin:2px 0 2px'>{ozet_satiri(kap)}</div>")
    s.append(f"<div style='opacity:.85;font-size:12px'>{grup_ozet(dusuk, '🔇 düşük hacim')}</div>")
    s.append(f"<div style='opacity:.85;font-size:12px;margin-bottom:6px'>{grup_ozet(diger, 'diğer')}</div>")
    for x in kap:
        s.append(kapanan_satir(x))
    s.append("<div style='opacity:.5;font-size:10px;margin-top:8px'>Günlük mum verisiyle, "
             "2 saatte bir yenilenir · yüzdeler girişe göre, masrafsız · kapananlarda tüm pozisyon "
             "stopta veya T3'te çıkar, T1/T2 sadece görüldü işareti</div></div>")
    return "".join(s)


def sayfaya_ekle(box):
    if not os.path.exists(SAYFA):
        print("sayfa yok:", SAYFA)
        return
    p = open(SAYFA, encoding="utf-8").read()
    blok = ISARET[0] + box + ISARET[1]
    if ISARET[0] in p and ISARET[1] in p:
        a = p.index(ISARET[0])
        b = p.index(ISARET[1]) + len(ISARET[1])
        p = p[:a] + blok + p[b:]
    elif "</body>" in p:
        i = p.rindex("</body>")
        p = p[:i] + blok + p[i:]
    else:
        p += blok
    open(SAYFA, "w", encoding="utf-8").write(p)


if __name__ == "__main__":
    yenile, j = eski_mi()
    if not os.path.exists(GECMIS):
        yenile = True
    if yenile:
        try:
            r = tara()
        except Exception as e:
            print("hata", e)
            r = None
        if r is not None:
            j = dict(t=simdi().isoformat(), v=SURUM, r=r)
            os.makedirs("docs", exist_ok=True)
            json.dump(j, open(DOSYA, "w", encoding="utf-8"), ensure_ascii=False)
            g = gecmis_yukle()
            for x in r:
                if kapali(x):
                    g[f"{x['hisse']}|{x['ad']}|{x['tarih']}"] = x
            gecmis_kaydet(g)
    g = gecmis_yukle()
    if j or g:
        sayfaya_ekle(kutu(j, g))
        print("harmonik kutusu eklendi:", len(j["r"]) if j else 0, "sinyal,",
              len(g), "kapanan")
