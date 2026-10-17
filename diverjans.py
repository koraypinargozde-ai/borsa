import yfinance as yf, pandas as pd, numpy as np
import re, os
import html as H

PERIOD = "3y"
COST = 0.3
src = open("scan.py", encoding="utf-8").read()
T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
tick = [t + ".IS" for t in dict.fromkeys(T)]


def norm(ix):
    return pd.to_datetime(ix).tz_localize(None).normalize()


def lowlow(p, ind, w=10):
    # fiyat onceki 10 gune gore daha dusuk dip, gosterge daha yuksek dip
    pn = p.rolling(w).min()
    pp = p.shift(w).rolling(w).min()
    inn = ind.rolling(w).min()
    ip = ind.shift(w).rolling(w).min()
    return (pn < pp * 0.99) & (inn > ip) & (p <= pn * 1.03)


def ozellik(x):
    o, c, h, l, v = x["Open"], x["Close"], x["High"], x["Low"], x["Volume"]
    f = pd.DataFrame(index=x.index)
    f["chg"] = c.pct_change() * 100
    av = v.shift(1).rolling(20).mean()
    f["vr"] = v / av
    f["lik"] = (av * c) >= 2_000_000
    f["yesil"] = (c > o) & (c > c.shift(1))

    dif = c.diff()
    obv = (np.sign(dif).fillna(0) * v).cumsum()
    rg = (h - l).replace(0, np.nan)
    mfm = (((c - l) - (h - c)) / rg).fillna(0)
    ad = (mfm * v).cumsum()
    cmf = (mfm * v).rolling(20).sum() / v.rolling(20).sum()
    tp = (h + l + c) / 3
    rmf = tp * v
    pos = rmf.where(tp > tp.shift(1), 0).rolling(14).sum()
    neg = rmf.where(tp < tp.shift(1), 0).rolling(14).sum()
    mfi = 100 - 100 / (1 + pos / neg.replace(0, np.nan))
    ml = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    mh = ml - ml.ewm(span=9, adjust=False).mean()

    f["d_obv"] = lowlow(c, obv)
    f["d_cmf"] = lowlow(c, cmf)
    f["d_mfi"] = lowlow(c, mfi)
    f["d_ad"] = lowlow(c, ad)
    f["d_macd"] = lowlow(c, mh)

    rng = (c.rolling(20).max() - c.rolling(20).min()) / c.rolling(20).min() * 100
    obvs = (obv - obv.shift(20)) / v.rolling(20).sum()
    f["yatay_obv"] = (rng <= 10) & (obvs > 0.15)

    r10 = (c / c.shift(10) - 1) * 100
    vd = v.rolling(5).mean() / v.shift(5).rolling(5).mean()
    f["kuruma"] = (r10 < -5) & (vd < 0.7)

    e = o.shift(-1)
    for k in (1, 3, 5, 10):
        f[f"n{k}"] = (c.shift(-k) / e - 1) * 100 - COST
    tv = (f["chg"] >= 9.4) & (c >= h * 0.995)
    f["y"] = tv.astype(float).shift(-1)
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
            if len(x) < 80:
                continue
            x.index = norm(x.index)
            f = ozellik(x)
            f["h"] = t[:-3]
            frames.append(f)
        except Exception:
            continue

A0 = pd.concat(frames).replace([np.inf, -np.inf], np.nan)
A = A0[A0.lik & A0.n1.notna() & A0.y.notna()].copy()

five = ["d_obv", "d_cmf", "d_mfi", "d_ad", "d_macd"]
for k in five + ["yatay_obv", "kuruma", "yesil"]:
    A[k] = A[k].fillna(False).astype(bool)
cnt = sum(A[k].astype(int) for k in five)
hac = (A.vr >= 1.5).values
yes = A.yesil.values

dates = sorted(A.index.unique())
cut = dates[int(len(dates) * 0.6)]
trm = np.asarray(A.index < cut)

NAMES = {
    "d_obv": "OBV diverjansı",
    "d_cmf": "CMF diverjansı",
    "d_mfi": "MFI diverjansı",
    "d_ad": "A/D diverjansı",
    "d_macd": "MACD hist diverjansı",
    "yatay_obv": "yatay fiyat + OBV↑",
    "kuruma": "düşüşte hacim kuruması",
}
G = {"TÜM GÜNLER (taban)": np.ones(len(A), bool)}
for k, ad in NAMES.items():
    m = A[k].values
    G[ad] = m
    G[ad + " +yeşil mum"] = m & yes
    G[ad + " +hacim1.5x"] = m & hac
G["diverjans sayısı ≥2"] = (cnt >= 2).values
G["diverjans sayısı ≥2 +yeşil"] = (cnt >= 2).values & yes
G["diverjans sayısı ≥3"] = (cnt >= 3).values
G["OBV + CMF birlikte"] = A.d_obv.values & A.d_cmf.values
G["OBV + MFI birlikte"] = A.d_obv.values & A.d_mfi.values

HZ = ["n1", "n3", "n5", "n10"]
out = []
P = out.append
P("BIST DİVERJANS TESTİ (pozitif / boğa)")
P(f"Dönem: {A.index.min():%d.%m.%Y} - {A.index.max():%d.%m.%Y} · hisse: {A.h.nunique()} · "
  f"örnek: {len(A)} · eğitim/test kesimi: {cut:%d.%m.%Y}")
P("Giriş ertesi gün açılış, %0,3 maliyet düşülmüş net getiri. n1/n3/n5/n10 = 1/3/5/10 gün sonra kapanış.")
P("tavan = ertesi gün tavan olma oranı. Diverjans: fiyat son 10g dibi öncekinden %1+ düşük,")
P("gösterge dibi öncekinden yüksek, fiyat hâlâ dibe %3 yakın. Örnekler üst üste biner,")
P("güncel listeye bağlı hayatta kalma yanlılığı var, stop yok.")
P("")
P(f"{'grup':<32}{'dönem':<8}{'n':>6}{'tavan':>7}{'n1':>7}{'n3':>7}{'n5':>7}{'n10':>7}")

R = {}
for ad, m in G.items():
    for tag, mm in (("eğitim", m & trm), ("test", m & ~trm)):
        s = A[mm]
        if len(s) < 5:
            P(f"{ad:<32}{tag:<8}{len(s):>6}   az örnek")
            continue
        ms = [s[k].mean() for k in HZ]
        R[(ad, tag)] = (len(s), ms)
        P(f"{ad:<32}{tag:<8}{len(s):>6}{s.y.mean() * 100:>6.1f}%"
          + "".join(f"{v:>+7.2f}" for v in ms))
    P("")

P("=== EĞİTİM + TEST BİRLİKTE POZİTİF (her ikisinde n≥60) ===")
bul = 0
for ad in G:
    if ad.startswith("TÜM"):
        continue
    a, b = R.get((ad, "eğitim")), R.get((ad, "test"))
    if not a or not b or a[0] < 60 or b[0] < 60:
        continue
    ok = [HZ[j] for j in range(4) if a[1][j] > 0 and b[1][j] > 0]
    if ok:
        bul += 1
        P(f"{ad}: {', '.join(ok)} (eğitim n={a[0]}, test n={b[0]})")
if not bul:
    P("Yok → hiçbir grup eğitim ve testte birlikte kârlı değil, kenar yok.")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Diverjans testi</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/diverjans.html", "w", encoding="utf-8").write(page)
