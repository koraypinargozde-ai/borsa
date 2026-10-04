import re, os
import numpy as np
import pandas as pd
import html as H
import harmonik as hk

FEATS = (
    ("D günü hacmi / 20g ort", "vD1"),
    ("D→onay 4 gün ort hacim / 20g ort", "vD4"),
    ("Onay günü hacmi / 20g ort", "vO"),
)


def ozellik(v, sb, d):
    if d < 21 or sb < 21:
        return None
    a_d = v[d - 20:d].mean()
    a_o = v[sb - 20:sb].mean()
    if a_d <= 0 or a_o <= 0:
        return None
    return v[d] / a_d, v[d:sb + 1].mean() / a_d, v[sb] / a_o


def topla(veri):
    rng = np.random.default_rng(7)
    rows = []
    for hisse, x in veri.items():
        o, h, l, c, v = (x[k].values.astype(float)
                         for k in ("Open", "High", "Low", "Close", "Volume"))
        N = len(o)
        if N < 80:
            continue
        for (sb, yon, nm, X, A, D) in hk.detect(h, l):
            if yon != 1 or sb + 1 >= N:
                continue
            f = ozellik(v, sb, sb - hk.PIVOT_N)
            if f is None:
                continue
            stop, T = hk.seviyeler(yon, X, A, D)
            e = sb + 1
            entry = o[e]
            if not (stop < entry < T[0]):
                continue
            rets, kinds = hk.sim(o, h, l, c, e, yon, stop, T)
            sp = yon * (entry - stop) / entry
            tp = [abs(t - entry) / entry for t in T]
            base = np.nan
            if N - hk.MAXD - 40 > 5:
                e2 = int(rng.integers(30, N - hk.MAXD - 1))
                en2 = o[e2]
                st2 = en2 * (1 - yon * abs(sp))
                T2 = [en2 * (1 + yon * q) for q in tp]
                b, _ = hk.sim(o, h, l, c, e2, yon, st2, T2)
                base = float(np.mean(b))
            rows.append(dict(tarih=x.index[sb], hisse=hisse, ad=nm,
                             vD1=f[0], vD4=f[1], vO=f[2],
                             k1=kinds[0], K=float(np.mean(rets)), base=base))
    return rows


HDR = f"{'grup':<10}{'n':>4} {'T1':>4} {'stp':>4} {'K':>6} {'taban':>6} {'eğ':>6}{'test':>6} nTest"


def satir(ad, s):
    if len(s) < 5:
        return None
    tr, te = s[s.tr], s[~s.tr]
    a = f"{ad:<10}{len(s):>4} {(s.k1 == 'T').mean() * 100:>3.0f}% {(s.k1 == 'S').mean() * 100:>3.0f}% "
    a += f"{s.K.mean():>+6.2f} {s.base.mean():>+6.2f} "
    a += (f"{tr.K.mean():>+6.2f}" if len(tr) else "     -")
    a += (f"{te.K.mean():>+6.2f}" if len(te) else "     -")
    a += f" n{len(te)}"
    return a


def bolum(R, baslik, P):
    P(f"=== {baslik} ===")
    P(f"sinyal: {len(R)}")
    if len(R) < 15:
        P("Çok az sinyal, bölme yapılmadı.")
        P("")
        return
    P(HDR)
    r = satir("TÜMÜ", R)
    if r:
        P(r)
    for etiket, f in FEATS:
        q1, q2 = R[f].quantile([1 / 3, 2 / 3])
        P(f"-- {etiket} (kesim {q1:.2f}x / {q2:.2f}x)")
        for ad, s in (("düşük", R[R[f] <= q1]),
                      ("orta", R[(R[f] > q1) & (R[f] <= q2)]),
                      ("yüksek", R[R[f] > q2])):
            P(satir(ad, s) or f"{ad:<10} n<5")
    P("")


def rapor(rows):
    out = []
    P = out.append
    P("BIST HARMONİK + HACİM TESTİ (boğa formasyonları)")
    if not rows:
        P("Hiç sinyal çıkmadı.")
        return "\n".join(out)
    R = pd.DataFrame(rows)
    d0, d1 = R.tarih.min(), R.tarih.max()
    cut = R.tarih.sort_values().iloc[int(len(R) * 0.6)]
    R["tr"] = R.tarih < cut
    P(f"Dönem: {d0:%d.%m.%Y} - {d1:%d.%m.%Y} · hisse: {R.hisse.nunique()} · sinyal: {len(R)}")
    P(f"Eğitim: {d0:%d.%m.%Y}-{cut:%d.%m.%Y}, test: sonrası (%60/%40)")
    P("Giriş: onaydan sonraki ilk açılış · stop: X'in %0,5 ötesi · hedefler D→A %38,2/%61,8/%100")
    P("T1 = T1'e ulaşma %, stp = T1'den önce stop %, K = kademeli net getiri (%), taban = rastgele gün")
    P("Hacim grupları sinyallerin üçte biri olacak şekilde bölünür (düşük/orta/yüksek).")
    P("Kenar kriteri: yüksek grupta K taban üstünde VE eğ ile test ikisi de pozitif, n yeterli.")
    P("Test sütunundaki n küçükse (n<30) rakama güvenme.")
    P("")
    bolum(R, "TÜM BOĞA FORMASYONLARI", P)
    bolum(R[R.ad.isin(["Gartley", "Cypher"])], "SADECE GARTLEY + CYPHER", P)
    for nm in ("Gartley", "Cypher"):
        bolum(R[R.ad == nm], nm.upper(), P)
    return "\n".join(out)


if __name__ == "__main__":
    src = open("scan.py", encoding="utf-8").read()
    T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
    tick = [t + ".IS" for t in dict.fromkeys(T)]
    text = rapor(topla(hk.indir(tick)))
    print(text)
    os.makedirs("docs", exist_ok=True)
    page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Harmonik hacim testi</title>"
            "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
            "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
    open("docs/harmonikhacim.html", "w", encoding="utf-8").write(page)
