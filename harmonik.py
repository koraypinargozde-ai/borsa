import yfinance as yf, pandas as pd, numpy as np
import re, os
import html as H

PERIOD = "3y"
HEDEFLER = [0.382, 0.618, 1.0]   # AD mesafesinin yuzdesi (D'den A'ya dogru)
STOP_TAMPON = 0.005              # X'in %0,5 otesi
MASRAF = 0.003                   # alis+satis maliyeti
PIVOT_N = 3                      # pivot 3 mum sonra onaylanir
TOL = 0.05                       # oran toleransi
MIN_XA = 0.06                    # XA bacagi en az %6 olsun
MAXD = 20                        # en fazla 20 gun tut


def pivots(h, l, n=PIVOT_N):
    out = []
    N = len(h)
    for i in range(n, N - n):
        if h[i] == max(h[i - n:i + n + 1]) and h[i] > max(h[i - n:i]):
            out.append((i, h[i], 'H', i + n))
        elif l[i] == min(l[i - n:i + n + 1]) and l[i] < min(l[i - n:i]):
            out.append((i, l[i], 'L', i + n))
    z = []
    for p in out:
        if z and z[-1][2] == p[2]:
            if (p[2] == 'H' and p[1] > z[-1][1]) or (p[2] == 'L' and p[1] < z[-1][1]):
                z[-1] = p
        else:
            z.append(p)
    return z


def near(x, lo, hi=None):
    if hi is None:
        hi = lo
    return lo - TOL <= x <= hi + TOL


def classify(X, A, B, C, D):
    XA = A - X
    if XA <= 0:
        return None
    AB = A - B
    BC = C - B
    if AB <= 0 or BC <= 0:
        return None
    ab = AB / XA
    bc = BC / AB
    ad = (A - D) / XA
    xc = (C - X) / XA
    if xc > 1.0:
        if near(ab, .382, .618) and near(xc, 1.13, 1.414) and D < C:
            if near((C - D) / (C - X), .786):
                return 'Cypher'
        return None
    if C >= A or not near(bc, .382, .886):
        return None
    if near(ab, .618) and near(ad, .786):
        return 'Gartley'
    if near(ab, .382, .5) and near(ad, .886):
        return 'Bat'
    if near(ab, .786) and near(ad, 1.27, 1.618):
        return 'Butterfly'
    if near(ab, .382, .618) and near(ad, 1.618):
        return 'Crab'
    return None


def detect(h, l):
    """(onay_bari, yon, ad, X, A, D) - fiyatlar gercek fiyat"""
    z = pivots(h, l)
    sig = []
    for k in range(4, len(z)):
        P = z[k - 4:k + 1]
        tips = ''.join(p[2] for p in P)
        if tips == 'LHLHL':
            v = [p[1] for p in P]
            nm = classify(*v)
            yon = 1
        elif tips == 'HLHLH':
            v = [p[1] for p in P]
            nm = classify(*[-x for x in v])
            yon = -1
        else:
            continue
        if not nm:
            continue
        X, A, B, C, D = v
        if abs(A - X) / abs(X) < MIN_XA:
            continue
        sig.append((P[4][3], yon, nm, X, A, D))
    return sig


def seviyeler(yon, X, A, D):
    stop = X * (1 - yon * STOP_TAMPON)
    ad = abs(A - D)
    T = [D + yon * f * ad for f in HEDEFLER]
    return stop, T


def sim(o, h, l, c, e, yon, stop, T):
    """Her hedef icin ayri cikis: hedef / stop (stop once sayilir) / zaman. Net getiri (%) doner."""
    N = len(o)
    entry = o[e]
    son = min(e + MAXD - 1, N - 1)
    rets, kinds = [], []
    for t in T:
        r = None
        for j in range(e, son + 1):
            if yon == 1:
                if j > e and o[j] <= stop:
                    r, k = o[j], 'S'
                    break
                if l[j] <= stop:
                    r, k = stop, 'S'
                    break
                if h[j] >= t:
                    r, k = (max(t, o[j]) if j > e else t), 'T'
                    break
            else:
                if j > e and o[j] >= stop:
                    r, k = o[j], 'S'
                    break
                if h[j] >= stop:
                    r, k = stop, 'S'
                    break
                if l[j] <= t:
                    r, k = (min(t, o[j]) if j > e else t), 'T'
                    break
        if r is None:
            r, k = c[son], 'Z'
        rets.append((yon * (r / entry - 1) - MASRAF) * 100)
        kinds.append(k)
    return rets, kinds


def fp(x):
    return f"{x:.2f}".replace('.', ',')


def analiz(veri):
    rng = np.random.default_rng(7)
    rows, canli = [], []
    for hisse, x in veri.items():
        o, h, l, c = (x[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
        N = len(o)
        if N < 80:
            continue
        for (sb, yon, nm, X, A, D) in detect(h, l):
            stop, T = seviyeler(yon, X, A, D)
            if sb + 1 >= N:
                canli.append((x.index[sb], hisse, yon, nm, c[-1], stop, T))
                continue
            e = sb + 1
            entry = o[e]
            if yon == 1 and not (stop < entry < T[0]):
                continue
            if yon == -1 and not (T[0] < entry < stop):
                continue
            rets, kinds = sim(o, h, l, c, e, yon, stop, T)
            # taban: ayni yuzde stop/hedef, ayni hissede rastgele gun
            sp = yon * (entry - stop) / entry
            tp = [abs(t - entry) / entry for t in T]
            base = np.nan
            if N - MAXD - 40 > 5:
                e2 = int(rng.integers(30, N - MAXD - 1))
                en2 = o[e2]
                st2 = en2 * (1 - yon * abs(sp))
                T2 = [en2 * (1 + yon * q) for q in tp]
                b, _ = sim(o, h, l, c, e2, yon, st2, T2)
                base = float(np.mean(b))
            rr = (abs(T[1] - entry)) / abs(entry - stop)
            rows.append(dict(tarih=x.index[sb], giris_t=x.index[e], hisse=hisse, yon=yon, ad=nm,
                             giris=entry, stop=stop, tg=T, r1=rets[0], r2=rets[1], r3=rets[2],
                             k1=kinds[0], k2=kinds[1], k3=kinds[2],
                             K=float(np.mean(rets)), base=base, rr=rr))
    out = []
    P = out.append
    P("BIST HARMONİK FORMASYON TESTİ")
    if not rows:
        P("Hiç sinyal çıkmadı.")
        return "\n".join(out)
    R = pd.DataFrame(rows)
    d0, d1 = R.tarih.min(), R.tarih.max()
    P(f"Dönem: {d0:%d.%m.%Y} - {d1:%d.%m.%Y} · hisse: {R.hisse.nunique()} · sinyal: {len(R)}")
    P("Giriş: onaydan sonraki ilk açılış · stop: X'in %0,5 ötesi (stop önce sayılır)")
    P("Hedefler D'den A'ya: T1 %38,2 · T2 %61,8 · T3 %100 · en fazla 20 gün · masraf %0,3")
    P("Ayı = short simülasyonu (BIST'te açığa satış yok; 'düşüş geldi mi' ölçüsü)")
    P("T1/T2/T3 = hedefe ulaşma % · stop = T1'den önce stop % · RR = T2/stop")
    P("R1/R2/R3 = o hedefte çıkışın net ort. getirisi (%) · K = kademeli (1/3'er)")
    P("taban = aynı stop/hedef yüzdesiyle rastgele gün · eğ/test = %60/%40 tarih ayrımı")
    cut = R.tarih.sort_values().iloc[int(len(R) * 0.6)]
    R["tr"] = R.tarih < cut
    P(f"Eğitim: {d0:%d.%m.%Y}-{cut:%d.%m.%Y}, test: sonrası")
    P("")

    def satir(ad, s):
        if len(s) < 5:
            return None
        tr, te = s[s.tr], s[~s.tr]
        a = f"{ad:<14}{len(s):>5} "
        a += f"{(s.k1 == 'T').mean() * 100:>3.0f}% {(s.k2 == 'T').mean() * 100:>3.0f}% {(s.k3 == 'T').mean() * 100:>3.0f}% "
        a += f"{(s.k1 == 'S').mean() * 100:>3.0f}% {s.rr.mean():>4.1f} "
        a += f"{s.r1.mean():>+6.2f}{s.r2.mean():>+6.2f}{s.r3.mean():>+6.2f}{s.K.mean():>+6.2f} "
        a += f"{s.base.mean():>+6.2f} "
        a += (f"{tr.K.mean():>+6.2f}" if len(tr) else "     -")
        a += (f"{te.K.mean():>+6.2f}" if len(te) else "     -")
        a += f" n{len(te)}"
        return a

    hdr = f"{'grup':<14}{'n':>5} {'T1':>4} {'T2':>4} {'T3':>4} {'stp':>4} {'RR':>4} {'R1':>6}{'R2':>6}{'R3':>6}{'K':>6} {'taban':>6} {'eğ':>6}{'test':>6}"
    for yon, ady in ((1, "BOĞA (yükseliş)"), (-1, "AYI (düşüş)")):
        P(f"=== {ady} ===")
        P(hdr)
        S = R[R.yon == yon]
        for nm in ("Gartley", "Bat", "Butterfly", "Crab", "Cypher"):
            r = satir(nm, S[S.ad == nm])
            if r:
                P(r)
        r = satir("TÜMÜ", S)
        if r:
            P(r)
        P("")
    P("Yorum: K sütunu taban sütunundan belirgin yüksekse VE eğ ile test ikisi de pozitifse kenar var.")
    P("Test sütunundaki n küçükse (n<30) rakama güvenme.")
    P("")
    P("=== SON 12 SİNYAL (fiyatlarla) ===")
    son = R.sort_values("tarih").tail(12)
    for _, r in son.iterrows():
        yy = "BOĞA" if r.yon == 1 else "AYI"
        P(f"{r.tarih:%d.%m.%y} {r.hisse} {yy} {r.ad}")
        P(f"  giriş {fp(r.giris)} · stop {fp(r.stop)} · T1 {fp(r.tg[0])} · T2 {fp(r.tg[1])} · T3 {fp(r.tg[2])}")
        P(f"  sonuç: T1 {r.k1} T2 {r.k2} T3 {r.k3} · kademeli {r.K:+.2f}%")
    P("")
    P("=== ŞU AN OLUŞAN / GİRİŞ BEKLEYEN ===")
    if not canli:
        P("Yok.")
    for (t, hs, yon, nm, px, stop, T) in sorted(canli, key=lambda r: r[0])[-15:]:
        yy = "BOĞA" if yon == 1 else "AYI"
        P(f"{t:%d.%m.%y} {hs} {yy} {nm} · son fiyat {fp(px)}")
        P(f"  stop {fp(stop)} · T1 {fp(T[0])} · T2 {fp(T[1])} · T3 {fp(T[2])}")
    return "\n".join(out)


def indir(tick):
    veri = {}
    for i in range(0, len(tick), 50):
        grup = tick[i:i + 50]
        try:
            d = yf.download(grup, period=PERIOD, group_by="ticker",
                            progress=False, threads=True, auto_adjust=False)
        except Exception as e:
            print("hata", e)
            continue
        for t in grup:
            try:
                x = d[t].dropna()
                if len(x) < 80:
                    continue
                x.index = pd.to_datetime(x.index).tz_localize(None).normalize()
                veri[t[:-3]] = x
            except Exception:
                continue
    return veri


if __name__ == "__main__":
    src = open("scan.py", encoding="utf-8").read()
    T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
    tick = [t + ".IS" for t in dict.fromkeys(T)]
    text = analiz(indir(tick))
    print(text)
    os.makedirs("docs", exist_ok=True)
    page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'><title>Harmonik test</title>"
            "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
            "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
    open("docs/harmonik.html", "w", encoding="utf-8").write(page)
