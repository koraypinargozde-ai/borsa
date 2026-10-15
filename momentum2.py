import yfinance as yf, pandas as pd, numpy as np
import re, os
import html as H

PERIOD = "1y"
LIQ = 2_000_000
TGT = 40
STOP = 20

src = open("scan.py", encoding="utf-8").read()
T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
tick = [t + ".IS" for t in dict.fromkeys(T)]


def norm(ix):
    return pd.to_datetime(ix).tz_localize(None).normalize()


xu = yf.download("XU100.IS", period=PERIOD, progress=False, auto_adjust=False)
if xu.columns.nlevels > 1:
    xu.columns = xu.columns.get_level_values(0)
xu = xu.dropna()
xu.index = norm(xu.index)
xc_all = xu["Close"]
last = xu.index[-1]

rows = []
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
            if len(x) < 130:
                continue
            x.index = norm(x.index)
            x = x[~x.index.duplicated()]
            if x.index[-1] != last:
                continue
            h, l, c, v = x["High"], x["Low"], x["Close"], x["Volume"]
            xc = xc_all.reindex(x.index, method="ffill")
            av = v.shift(1).rolling(20).mean()
            rs63 = ((c / c.shift(63) - 1) - (xc / xc.shift(63) - 1)) * 100
            r63 = (c / c.shift(63) - 1) * 100
            dl = c.diff()
            gn = dl.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
            ls = (-dl.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
            rsi = 100 - 100 / (1 + gn / ls.replace(0, np.nan))
            rg = (h - l).replace(0, np.nan)
            mf = (((c - l) - (h - c)) / rg).fillna(0)
            cmf = (mf * v).rolling(20).sum() / v.rolling(20).sum()
            obv = (np.sign(dl).fillna(0) * v).cumsum()
            obvup = int(obv.iloc[-1] > obv.iloc[-21])
            vals = [rs63.iloc[-1], r63.iloc[-1], rsi.iloc[-1], cmf.iloc[-1]]
            if any(pd.isna(z) for z in vals):
                continue
            rows.append({"h": t[:-3], "c": float(c.iloc[-1]),
                         "rs63": vals[0], "r63": vals[1], "rsi": vals[2],
                         "cmf": vals[3], "obvup": obvup,
                         "liq": bool((av.iloc[-1] * c.iloc[-1]) >= LIQ)})
        except Exception:
            continue

D = pd.DataFrame(rows)
L = D[D.liq].copy()
L["p63"] = L.rs63.rank(pct=True)
C = L[(L.p63 >= 0.8) & (L.cmf > 0.05) & (L.obvup == 1)].sort_values("rs63", ascending=False)

out = []
P = out.append
P(f"BUGÜNÜN ADAYLARI ({last:%d.%m.%Y} kapanışı)")
P("Süzgeç: göreceli güç (63g getiri - BIST 100) üst %20 + CMF>0.05 + OBV↑ (20g) + likit.")
P(f"Geriye testte en iyi kural: hedef +%{TGT} / stop -%{STOP}, 40 işlem günü (~2 ay).")
P("Bu geriye test ortalaması, garanti değil: işlemlerin ~%32'si stopa, ~%20'si hedefe gitti.")
P("⚠ = 63 günde %80+ yükselmiş: hedefe de stopa da daha sık gidiyor (stop ~%44).")
P(f"Likit hisse: {len(L)} · aday: {len(C)}")
P("Fiyatlar bugünün kapanışına göre; gerçek giriş ertesi gün açılışı olur.")
P("")
P(f"{'hisse':<8}{'kapanış':>9}{'RS63':>6}{'63g%':>6}{'RSI':>5}{'CMF':>6}{'stop':>9}{'hedef':>9}")
for _, r in C.iterrows():
    fl = " ⚠" if r.r63 >= 80 else ""
    P(f"{r.h:<8}{r.c:>9.2f}{r.rs63:>+6.0f}{r.r63:>6.0f}{r.rsi:>5.0f}{r.cmf:>6.2f}"
      f"{r.c * (1 - STOP / 100):>9.2f}{r.c * (1 + TGT / 100):>9.2f}{fl}")
if len(C) == 0:
    P("Aday yok.")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Adaylar</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/momentum2.html", "w", encoding="utf-8").write(page)
