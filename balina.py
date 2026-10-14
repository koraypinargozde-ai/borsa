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


xu10 = pd.Series(dtype=float)
try:
    xu = yf.download("XU100.IS", period=PERIOD, progress=False, auto_adjust=False)
    if xu.columns.nlevels > 1:
        xu.columns = xu.columns.get_level_values(0)
    xu = xu.dropna()
    xu.index = norm(xu.index)
    xu10 = (xu["Close"] / xu["Close"].shift(10) - 1) * 100
except Exception as e:
    print("endeks hata", e)

KN = {
    "k1": "yatay/dar bant (5g aralık ≤%8)",
    "k2": "hacim 2x+ ama değ <%4",
    "k3": "OBV yükseliyor (10g)",
    "k4": "CMF>0.05 ve artıyor",
    "k5": "satış hacmi zayıf + kapanış tutunuyor",
    "k6": "BIST 100'den güçlü (10g)",
}


def ozellik(x):
    o, c, h, l, v = x["Open"], x["Close"], x["High"], x["Low"], x["Volume"]
    f = pd.DataFrame(index=x.index)
    f["chg"] = c.pct_change() * 100
    av = v.shift(1).rolling(20).mean()
    f["vr"] = v / av
    f["lik"] = (av * c) >= 2_000_000
    pos = ((c - l) / (h - l).replace(0, np.nan)).fillna(0.5) * 100
    f["ret10"] = (c / c.shift(10) - 1) * 100
    f["band5"] = (h.rolling(5).max() / l.rolling(5).min() - 1) * 100
    rg = (h - l).replace(0, np.nan)
    mf = (((c - l) - (h - c)) / rg).fillna(0)
    cmf = (mf * v).rolling(20).sum() / v.rolling(20).sum()
    f["cmf"] = cmf
    dif = c.diff()
    obv = (np.sign(dif).fillna(0) * v).cumsum()
    up10 = v.where(dif > 0, 0).rolling(10).sum()
    dn10 = v.where(dif < 0, 0).rolling(10).sum()
    udr = (up10 / dn10.replace(0, np.nan)).fillna(3.0)
    rs10 = f["ret10"] - xu10.reindex(x.index).ffill().fillna(0)
    f["k1"] = (f["band5"] <= 8).astype(int)
    f["k2"] = ((f["vr"] >= 2) & (f["chg"] < 4)).astype(int)
    f["k3"] = (obv > obv.shift(10)).astype(int)
    f["k4"] = ((cmf > 0.05) & (cmf > cmf.shift(5))).astype(int)
    f["k5"] = ((udr >= 1.2) & (pos.rolling(5).mean() >= 50)).astype(int)
    f["k6"] = (rs10 > 0).astype(int)
    f["skor"] = f[["k1", "k2", "k3", "k4", "k5", "k6"]].sum(axis=1)
    tv = (f["chg"] >= 9.4) & (c >= h * 0.995)
    f["y"] = tv.astype(float).shift(-1)
    o1 = o.shift(-1)
    for k in (5, 10, 20):
        f[f"n{k}"] = (c.shift(-k) / o1 - 1) * 100 - COST
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
D = A0[A0.lik & A0.n10.notna() & A0.y.notna() & (A0.chg < 7)].dropna(subset=["vr", "cmf", "band5"]).copy()
dates = sorted(D.index.unique())
cut = dates[int(len(dates) * 0.7)]

out = []
P = out.append
P("🐋 BALİNA 100 GERİYE TEST (6 koşullu skor)")
P(f"Dönem: {D.index.min():%d.%m.%Y} - {D.index.max():%d.%m.%Y} · hisse: {D.h.nunique()} · örnek: {len(D)}")
P(f"Eğitim: {dates[0]:%d.%m.%Y}-{cut:%d.%m.%Y} · test: sonrası · giriş ertesi gün açılış · %{COST} maliyet")
P("Sadece o gün %7'den az yükselmiş, likit hisseler. n5/n10/n20 = sinyal gününden 5/10/20 gün sonra kapanış, net %.")
P("eğ10 / test10 = n10'un eğitim ve test dönemindeki ortalaması. İkisi de taban üstündeyse güvenilir.")
P("Uyarı: örnekler üst üste biner, güncel hisse listesi (hayatta kalma yanlılığı), stop yok.")
P("")
P("KOŞULLAR:")
for k, v in KN.items():
    P(f"  {k} = {v}")
P("")
P(f"{'grup':<20}{'n':>7}{'tavan':>7}{'n5':>7}{'n10':>7}{'n20':>7}{'eğ10':>7}{'test10':>8}")


def satir(ad, s):
    if len(s) < 30:
        return
    tr, te = s[s.index < cut], s[s.index >= cut]
    P(f"{ad:<20}{len(s):>7}{s.y.mean() * 100:>6.1f}%{s.n5.mean():>+7.2f}{s.n10.mean():>+7.2f}"
      f"{s.n20.mean():>+7.2f}{tr.n10.mean():>+7.2f}{te.n10.mean():>+8.2f}")


satir("TABAN (hepsi)", D)
P("")
P("--- TEK KOŞUL ---")
for k in KN:
    satir(k, D[D[k] == 1])
P("")
P("--- SKOR (kaç koşul birlikte) ---")
for sk in range(0, 7):
    satir(f"skor = {sk}", D[D.skor == sk])
P("")
P("--- SKOR ≥ ---")
for sk in (3, 4, 5):
    satir(f"skor ≥ {sk}", D[D.skor >= sk])
P("")
P("--- HANGİ KOŞUL FARK YARATIYOR? (skor ≥4 içinde, koşul varsa / yoksa) ---")
S4 = D[D.skor >= 4]
for k in KN:
    satir(f"{k} VAR", S4[S4[k] == 1])
    satir(f"{k} YOK", S4[S4[k] == 0])

P("")
last = A0.index.max()
P(f"=== BUGÜN SKORU ≥4 OLANLAR ({last:%d.%m.%Y}) ===")
L = A0[(A0.index == last) & A0.lik & (A0.skor >= 4)].sort_values("skor", ascending=False)
if len(L) == 0:
    P("Yok.")
for _, r in L.head(25).iterrows():
    et = "".join(k[1] if r[k] == 1 else "-" for k in KN)
    P(f"{r.h:<8} skor {int(r.skor)} [{et}] değ {r.chg:+.1f}% hacim {r.vr:.1f}x")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Balina test</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/balina.html", "w", encoding="utf-8").write(page)
