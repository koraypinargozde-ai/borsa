import yfinance as yf, pandas as pd, numpy as np
import re, os
import html as H

PERIOD = "1y"
COST = 0.3  # alış+satış toplam komisyon/kayma payı, yüzde
src = open("scan.py", encoding="utf-8").read()
T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
tick = [t + ".IS" for t in dict.fromkeys(T)]


def norm(ix):
    return pd.to_datetime(ix).tz_localize(None).normalize()


def ozellik(x):
    o, c, h, l, v = x["Open"], x["Close"], x["High"], x["Low"], x["Volume"]
    f = pd.DataFrame(index=x.index)
    f["chg"] = c.pct_change() * 100
    av = v.shift(1).rolling(20).mean()
    f["vr"] = v / av
    f["lik"] = (av * c) >= 2_000_000
    f["pos"] = ((c - l) / (h - l).replace(0, np.nan)).fillna(0.5) * 100
    f["yak20"] = (c / h.shift(1).rolling(20).max() - 1) * 100
    rg = (h - l).replace(0, np.nan)
    mf = (((c - l) - (h - c)) / rg).fillna(0)
    f["cmf"] = (mf * v).rolling(20).sum() / v.rolling(20).sum()
    tp = (h + l + c) / 3
    vwap = (tp * v).rolling(20).sum() / v.rolling(20).sum()
    dif = c.diff()
    up = v.where(dif > 0, 0).rolling(20).sum()
    dn = v.where(dif < 0, 0).rolling(20).sum()
    udr = (up / dn.replace(0, np.nan)).fillna(3.0)
    obv = (np.sign(dif).fillna(0) * v).cumsum()
    ek = (c > vwap).astype(int) + (udr >= 1.2).astype(int) + (obv > obv.shift(10)).astype(int)
    f["vk"] = v.shift(1).rolling(2).mean() / av
    f["pg"] = ((f["cmf"] > 0.15) & (f["vk"] >= 1.2) & (f["chg"] > 0)
               & (f["pos"] >= 50) & (ek >= 2))
    tv = (f["chg"] >= 9.4) & (c >= h * 0.995)
    f["tv10"] = tv.astype(float).rolling(10).sum()
    f["c0"] = c
    for k in (1, 2, 3):
        f[f"o{k}"] = o.shift(-k)
        f[f"h{k}"] = h.shift(-k)
        f[f"l{k}"] = l.shift(-k)
        f[f"c{k}"] = c.shift(-k)
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
            if len(x) < 60:
                continue
            x.index = norm(x.index)
            frames.append(ozellik(x))
        except Exception:
            continue

A0 = pd.concat(frames).replace([np.inf, -np.inf], np.nan)
need = ["vr", "cmf", "yak20", "vk", "c0"] + [f"{a}{k}" for k in (1, 2, 3) for a in "ohlc"]
A = A0[A0["lik"].astype(bool)].dropna(subset=need)
D0 = A[A.chg < 7].copy()
gap = (D0.o1 >= D0.c0 * 1.095).values

dates = sorted(D0.index.unique())
cut = dates[int(len(dates) * 0.7)]
trm = np.asarray(D0.index < cut)


def gun(S, X, Y, days):
    n = len(S)
    res = np.full(n, np.nan)
    done = np.zeros(n, bool)
    o1 = S.o1.values
    sp = o1 * (1 - Y / 100)
    tg = o1 * (1 + X / 100)
    for k in range(1, days + 1):
        ok = S[f"o{k}"].values
        lo = S[f"l{k}"].values
        hi = S[f"h{k}"].values
        if k >= 2:
            m = ~done & (ok <= sp)
            res[m] = (ok[m] / o1[m] - 1) * 100
            done |= m
            m = ~done & (ok >= tg)
            res[m] = (ok[m] / o1[m] - 1) * 100
            done |= m
        m = ~done & (lo <= sp)
        res[m] = -Y
        done |= m
        m = ~done & (hi >= tg)
        res[m] = X
        done |= m
    cl = S[f"c{days}"].values
    res[~done] = ((cl / o1 - 1) * 100)[~done]
    return res - COST


STR = [
    ("kapanış 1g", 1e9, 1e9, 1),
    ("+3/-2 1g", 3, 2, 1),
    ("+4/-3 1g", 4, 3, 1),
    ("+5/-3 1g", 5, 3, 1),
    ("+6/-4 1g", 6, 4, 1),
    ("+6/-4 3g", 6, 4, 3),
    ("+8/-4 3g", 8, 4, 3),
    ("kapanış 3g", 1e9, 1e9, 3),
]

vr = D0.vr.values
tv10 = D0.tv10.values
cmf = D0.cmf.values
yk = D0.yak20.values
pg = D0.pg.astype(bool).values
SIG = [
    ("TÜMÜ (rastgele alış)", np.ones(len(D0), bool)),
    ("hacim 4x+", vr >= 4),
    ("hacim 4x+ & son10g tavan", (vr >= 4) & (tv10 >= 1)),
    ("hacim 4x+ & CMF>0.15", (vr >= 4) & (cmf > 0.15)),
    ("hacim 4x+ & kırılım20g", (vr >= 4) & (yk > 0)),
    ("hacim 2x+ & son10g tavan", (vr >= 2) & (tv10 >= 1)),
    ("💰 para girişi", pg),
]

out = []
P = out.append
P("BIST ÇIKIŞ TESTİ (gerçekçi giriş)")
P(f"Dönem: {dates[0]:%d.%m.%Y} - {dates[-1]:%d.%m.%Y}")
P("Giriş: sinyalden ertesi gün AÇILIŞ fiyatı.")
P("Tavan açan (alınamayan) günler hariç.")
P("Hedef ve stop aynı gün gelirse STOP sayıldı.")
P(f"Komisyon+kayma: %{COST} düşüldü.")
P("isab = kârlı işlem oranı, ort = net getiri % (ortalama)")
P("eğit/test = ilk %70 / son %30 dönem ortalaması")
P("1g = aynı gün, 3g = en çok 3 gün tut")

for ad, m in SIG:
    sel = m & ~gap
    S = D0[sel]
    tr = trm[sel]
    P("")
    P(f"=== {ad} ===")
    P(f"sinyal {int(m.sum())} · tavan açıp alınamayan {int((m & gap).sum())}")
    if len(S) < 30:
        P("yeterli örnek yok")
        continue
    P(f"{'strateji':<11}{'n':>6}{'isab':>7}{'ort':>7}{'eğit':>7}{'test':>7}")
    for sn, X, Y, dy in STR:
        r = gun(S, X, Y, dy)
        a, b = r[tr], r[~tr]
        ea = a.mean() if len(a) else float("nan")
        eb = b.mean() if len(b) else float("nan")
        P(f"{sn:<11}{len(r):>6}{(r > 0).mean() * 100:>6.0f}%{r.mean():>+7.2f}{ea:>+7.2f}{eb:>+7.2f}")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Çıkış testi</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{white-space:pre-wrap}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/cikis.html", "w", encoding="utf-8").write(page)
