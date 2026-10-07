import yfinance as yf, pandas as pd, numpy as np
import re, os, itertools
import html as H

PERIOD = "3y"
COST = 0.3
src = open("scan.py", encoding="utf-8").read()
T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
tick = [t + ".IS" for t in dict.fromkeys(T)]


def norm(ix):
    return pd.to_datetime(ix).tz_localize(None).normalize()


def ozellik(x):
    c, h, l, v, o = x["Close"], x["High"], x["Low"], x["Volume"], x["Open"]
    f = pd.DataFrame(index=x.index)
    f["chg"] = c.pct_change() * 100
    av = v.shift(1).rolling(20).mean()
    f["lik"] = (av * c) >= 2_000_000
    f["pos"] = ((c - l) / (h - l).replace(0, np.nan)).fillna(0.5) * 100
    tv = ((f["chg"] >= 9.4) & (c >= h * 0.995)).astype(float)
    f["tv20"] = tv.rolling(20).sum()
    rg = (h - l).replace(0, np.nan)
    mf = (((c - l) - (h - c)) / rg).fillna(0)
    dif = c.diff()
    obv = (np.sign(dif).fillna(0) * v).cumsum()
    for W in (10, 20):
        f[f"vr{W}"] = v.rolling(W).mean() / v.shift(W).rolling(60).mean()
        f[f"ret{W}"] = (c / c.shift(W) - 1) * 100
        f[f"rng{W}"] = (h.rolling(W).max() - l.rolling(W).min()) / c * 100
        f[f"cmf{W}"] = (mf * v).rolling(W).sum() / v.rolling(W).sum()
        up = v.where(dif > 0, 0).rolling(W).sum()
        dn = v.where(dif < 0, 0).rolling(W).sum()
        f[f"udr{W}"] = (up / dn.replace(0, np.nan)).fillna(3.0)
        f[f"obv{W}"] = (obv > obv.shift(W)).astype(float)
    f["y1"] = tv.shift(-1)
    a10 = pd.concat([tv.shift(-k) for k in range(1, 11)], axis=1)
    f["y10"] = a10.max(axis=1).where(a10.notna().all(axis=1))
    a20 = pd.concat([tv.shift(-k) for k in range(1, 21)], axis=1)
    f["y20"] = a20.max(axis=1).where(a20.notna().all(axis=1))
    o1 = o.shift(-1)
    f["ag"] = (o1 / c - 1) * 100
    f["n10"] = (c.shift(-10) / o1 - 1) * 100 - COST
    f["n20"] = (c.shift(-20) / o1 - 1) * 100 - COST
    hs = h.shift(-1)
    f["z10"] = (hs.iloc[::-1].rolling(10).max().iloc[::-1] / o1 - 1) * 100
    return f


frames = []
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
            if len(x) < 120:
                continue
            x.index = norm(x.index)
            f = ozellik(x)
            f["h"] = t[:-3]
            frames.append(f)
        except Exception:
            continue

A0 = pd.concat(frames).replace([np.inf, -np.inf], np.nan)
need = ["vr10", "vr20", "cmf10", "cmf20", "y10", "y20", "n10", "n20", "z10", "ag", "tv20"]
A = A0[A0.lik].dropna(subset=need)
# bugun %7+ yukselmemis, son 20g tavan yok (hacim tavan gununden gelmesin), ertesi acilis tavan degil (alinabilir)
D = A[(A.chg < 7) & (A.tv20 == 0) & (A.ag < 9)].copy()

dates = sorted(D.index.unique())
cut = dates[int(len(dates) * 0.7)]
trm = np.asarray(D.index < cut)


def kos(W):
    ret, rng, vr = D[f"ret{W}"], D[f"rng{W}"], D[f"vr{W}"]
    C = {
        f"{W}g sakin": (ret.abs() <= 5) & (rng <= 15),
        f"{W}g sıkı sakin": (ret.abs() <= 3) & (rng <= 10),
        f"{W}g hacim ≥1.5x": vr >= 1.5,
        f"{W}g hacim ≥2x": vr >= 2,
        f"{W}g hacim ≥3x": vr >= 3,
        f"{W}g CMF>0.1": D[f"cmf{W}"] > 0.1,
        f"{W}g OBV↑": D[f"obv{W}"] > 0,
        f"{W}g alım baskın": D[f"udr{W}"] >= 1.3,
    }
    ana = (C[f"{W}g sakin"] & (vr >= 2) & (D[f"cmf{W}"] > 0.1) & (D[f"obv{W}"] > 0))
    sk = (C[f"{W}g sıkı sakin"] & (vr >= 3) & (D[f"cmf{W}"] > 0.1) & (D[f"obv{W}"] > 0))
    return C, ana, sk


SH = {
    "bugün 0-5%": (D.chg > 0) & (D.chg < 5),
    "kapanış ≥60": D.pos >= 60,
}

b10 = D.y10.mean() * 100
b20 = D.y20.mean() * 100
bn10 = D.n10.mean()
bn20 = D.n20.mean()

out = []
P = out.append
P("BIST SESSİZ EMİLİM TESTİ")
P(f"Dönem: {D.index.min():%d.%m.%Y} - {D.index.max():%d.%m.%Y} · hisse: {D.h.nunique()} · örnek (gün-hisse): {len(D)}")
P("Şartlar: o gün %7'den az yükselmiş, son 20 günde tavan yok, ertesi açılış tavan değil.")
P(f"Giriş: sinyal ertesi AÇILIŞ · maliyet %{COST} · eğitim/test kesimi: {cut:%d.%m.%Y}")
P("sakin = fiyat yatay (W günde değişim ±%5, aralık ≤%15). hacim = son W gün ort. / önceki 60 gün ort.")
P("tavan10/20 = 10/20 işlem günü içinde tavan olma oranı · kat = tabana göre")
P("n10/n20 = 10/20 gün sonra kapanışta net getiri (%) · z10 = 10 günde en yüksek (açılışa göre)")
P("Uyarı: komşu günler üst üste biner, n görünenden daha az bağımsızdır.")
P("")
P(f"{'koşul':<30}{'n':>7}{'tav10':>7}{'kat':>6}{'tav20':>7}{'n10':>7}{'n20':>7}{'z10':>7}")


def satir(ad, m):
    s = D[m]
    if len(s) < 30:
        return
    r10 = s.y10.mean() * 100
    P(f"{ad:<30}{len(s):>7}{r10:>6.1f}%{r10 / b10:>5.1f}x{s.y20.mean() * 100:>6.1f}%"
      f"{s.n10.mean():>+7.2f}{s.n20.mean():>+7.2f}{s.z10.mean():>+7.1f}")


satir("TÜM (taban)", np.ones(len(D), bool))
P("")
P("=== TEK KOŞULLAR ===")
for W in (10, 20):
    C, ana, sk = kos(W)
    for k, v in C.items():
        satir(k, v.values)
    P("")
for k, v in SH.items():
    satir(k, v.values)

P("")
P("=== SESSİZ EMİLİM TANIMLARI (eğitim / test) ===")
P("ana = sakin + hacim ≥2x + CMF>0.1 + OBV↑ · sıkı = sıkı sakin + hacim ≥3x + CMF + OBV")
for W in (10, 20):
    C, ana, sk = kos(W)
    for ad, m in ((f"{W}g ANA", ana), (f"{W}g SIKI", sk)):
        m = m.values
        a, b = m & trm, m & ~trm
        if m.sum() < 30:
            P(f"{ad}: örnek yok/az (n={int(m.sum())})")
            continue
        s = D[m]
        P(f"{ad}: n={int(m.sum())} · tavan10 %{s.y10.mean() * 100:.1f} ({s.y10.mean() * 100 / b10:.1f}x) · "
          f"n10 {s.n10.mean():+.2f} · n20 {s.n20.mean():+.2f} · z10 {s.z10.mean():+.1f}")
        if a.sum() > 0 and b.sum() > 0:
            P(f"   eğitim n={int(a.sum())} tavan10 %{D.y10.values[a].mean() * 100:.1f} n10 {D.n10.values[a].mean():+.2f} · "
              f"test n={int(b.sum())} tavan10 %{D.y10.values[b].mean() * 100:.1f} n10 {D.n10.values[b].mean():+.2f}")
P(f"(taban: tavan10 %{b10:.1f}, tavan20 %{b20:.1f}, n10 {bn10:+.2f}, n20 {bn20:+.2f})")

y10 = D.y10.values
n10 = D.n10.values
for W in (10, 20):
    C, ana, sk = kos(W)
    allc = {**C, **SH}
    names = list(allc)
    M = {k: v.values for k, v in allc.items()}
    res = []
    for r in (1, 2, 3):
        for combo in itertools.combinations(names, r):
            m = M[combo[0]].copy()
            for k in combo[1:]:
                m &= M[k]
            a, b = m & trm, m & ~trm
            if a.sum() < 100 or b.sum() < 40:
                continue
            res.append((n10[a].mean(), n10[b].mean(), int(a.sum()), int(b.sum()),
                        y10[a].mean() * 100, y10[b].mean() * 100, combo))
    res.sort(key=lambda r: -r[0])
    P("")
    P(f"=== EN İYİ KOMBİNASYONLAR ({W} gün penceresi; eğitim net10'a göre sıralı) ===")
    P(f"taban n10: {bn10:+.2f} · çok kombinasyon denendi, tek başına parlak satıra güvenme")
    for n, (ea, tb, na, nb, ya, yb, combo) in enumerate(res[:8], 1):
        P(f"{n}) " + " + ".join(combo))
        P(f"   eğitim n={na} n10 {ea:+.2f} tavan10 %{ya:.1f} · test n={nb} n10 {tb:+.2f} tavan10 %{yb:.1f}")
    pos = [r for r in res if r[0] > 0 and r[1] > 0]
    P(f"Eğitim VE testte n10 pozitif olan kombinasyon: {len(pos)} / {len(res)}")

P("")
P("=== INFO: TAVANDAN BİR GÜN ÖNCEKİ HALİ ===")
ib = A0[(A0.h == "INFO") & (A0.y1 == 1)]
if len(ib) == 0:
    P("INFO için dönemde tavan olayı bulunamadı.")
for ix, r in ib.iterrows():
    fl = []
    for W in (10, 20):
        ok = (abs(r[f"ret{W}"]) <= 5 and r[f"rng{W}"] <= 15 and r[f"vr{W}"] >= 2
              and r[f"cmf{W}"] > 0.1 and r[f"obv{W}"] > 0)
        fl.append(f"{W}g ana {'EVET' if ok else 'hayır'}")
    P(f"{ix:%d.%m.%Y}: 10g hacim {r.vr10:.1f}x · 10g değ {r.ret10:+.1f}% · aralık {r.rng10:.1f}% · "
      f"CMF {r.cmf10:+.2f} · OBV↑ {'evet' if r.obv10 > 0 else 'hayır'} · " + " · ".join(fl))

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Sessiz emilim</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/sessiz.html", "w", encoding="utf-8").write(page)
