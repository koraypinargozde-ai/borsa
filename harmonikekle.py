import os, re, json
import datetime as dt
import html as H
import harmonik as hk

DOSYA = "docs/harmonik.json"
SAYFA = "docs/index.html"
ISARET = ("<!--HARM-->", "<!--/HARM-->")
GRUPLAR = ("Gartley", "Cypher")
SON_BAR = 25      # son 25 işlem günündeki sinyaller
YENILE_DK = 120   # taramayı en fazla 2 saatte bir yap


def simdi():
    return dt.datetime.now(dt.timezone.utc)


def eski_mi():
    try:
        j = json.load(open(DOSYA, encoding="utf-8"))
        t = dt.datetime.fromisoformat(j["t"])
        return (simdi() - t).total_seconds() / 60 >= YENILE_DK, j
    except Exception:
        return True, None


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
        N = len(o)
        if N < 80:
            continue
        for (sb, yon, nm, X, A, D) in hk.detect(h, l):
            if yon != 1 or nm not in GRUPLAR:
                continue
            if N - 1 - sb > SON_BAR:
                continue
            stop, Tg = hk.seviyeler(yon, X, A, D)
            r = dict(hisse=hisse, ad=nm, tarih=x.index[sb].strftime("%d.%m.%y"),
                     sb=int(N - 1 - sb), stop=float(stop), T=[float(t) for t in Tg],
                     son=float(c[-1]), vt=x.index[-1].strftime("%d.%m.%y"))
            if sb + 1 >= N:
                if not (stop < c[-1] < Tg[0]):
                    continue
                r.update(durum="giriş bekliyor", giris=None, hit=[False] * 3, gun=0, sonuc=None)
                kayit.append(r)
                continue
            e = sb + 1
            entry = float(o[e])
            if not (stop < entry < Tg[0]):
                continue
            hit = [False] * 3
            stopped = False
            sonbar = min(e + hk.MAXD - 1, N - 1)
            gun = 0
            for j in range(e, sonbar + 1):
                gun = j - e + 1
                if (j > e and o[j] <= stop) or l[j] <= stop:
                    stopped = True
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
                durum, cik = "STOP", stop
            elif dolu:
                durum, cik = "süre doldu", c[sonbar]
            else:
                durum, cik = "açık", c[-1]
            r.update(durum=durum, giris=entry, hit=hit, gun=int(gun),
                     sonuc=float((cik / entry - 1) * 100))
            kayit.append(r)
    kayit.sort(key=lambda r: r["sb"])
    return kayit[:20]


def pc(x):
    return f"{x:+.1f}".replace(".", ",") + "%"


def kutu(j):
    r = j["r"]
    s = ["<div style='margin:14px 0;padding:12px;border-radius:12px;background:#161b22;"
         "color:#e8eaed;font:13px/1.5 sans-serif'>"]
    s.append(f"<div style='font-weight:700;font-size:15px'>📐 Harmonik boğa takibi "
             f"(Gartley / Cypher) ({len(r)})</div>")
    s.append("<div style='opacity:.7;font-size:11px;margin:2px 0 8px'>Giriş: onaydan sonraki "
             "ilk açılış · stop: X'in %0,5 ötesi · hedefler D→A %38,2 / %61,8 / %100 · "
             "en fazla 20 gün · henüz canlı doğrulanmadı, sadece takip</div>")
    if not r:
        s.append("<div style='opacity:.7'>Şu an aktif sinyal yok.</div>")
    for x in r:
        son = x["son"]
        if x["giris"] is None:
            ozet = f"giriş bekliyor · şimdi {hk.fp(son)}"
        else:
            renk = "#3fb950" if x["sonuc"] >= 0 else "#f85149"
            ozet = (f"{x['durum']} · <span style='color:{renk}'>{pc(x['sonuc'])}</span>"
                    f" · şimdi {hk.fp(son)}")
        s.append("<details style='border-top:1px solid #30363d;padding:6px 0'>"
                 f"<summary><b>{H.escape(x['hisse'])}</b> {x['ad']} · {x['tarih']} · {ozet}</summary>"
                 "<div style='padding:4px 0 2px 12px;font-size:12px'>")
        vt = x.get("vt", "")
        etiket = f" ({vt} kapanışı)" if vt else ""
        if x["giris"] is not None:
            fark = (son / x["giris"] - 1) * 100
            s.append(f"Giriş {hk.fp(x['giris'])} · {x['gun']}. gün<br>")
            s.append(f"Şimdi {hk.fp(son)}{etiket} · girişe göre {pc(fark)}<br>")
        else:
            s.append(f"Şimdi {hk.fp(son)}{etiket}<br>")
        s.append(f"Stop {hk.fp(x['stop'])}<br>")
        for i, t in enumerate(x["T"]):
            tik = " ✔" if x["hit"][i] else ""
            s.append(f"T{i + 1} {hk.fp(t)}{tik}<br>")
        s.append("</div></details>")
    s.append(f"<div style='opacity:.5;font-size:10px;margin-top:6px'>Günlük mum verisiyle, "
             f"2 saatte bir yenilenir</div></div>")
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
    if yenile:
        try:
            r = tara()
        except Exception as e:
            print("hata", e)
            r = None
        if r is not None:
            j = dict(t=simdi().isoformat(), r=r)
            os.makedirs("docs", exist_ok=True)
            json.dump(j, open(DOSYA, "w", encoding="utf-8"), ensure_ascii=False)
    if j:
        sayfaya_ekle(kutu(j))
        print("harmonik kutusu eklendi:", len(j["r"]), "sinyal")
