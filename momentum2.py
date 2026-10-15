import yfinance as yf, pandas as pd, numpy as np
import re, os
import html as H

PERIOD = "3y"
COST = 0.3
STEP = 5
LIQ = 2_000_000
W = 40
RULES = [(40, 20), (30, 20), (None, None)]


def rname(r):
    tg, sp = r
    a = f"hedef %{tg}" if tg else "hedefsiz"
    b = f"stop %{sp}" if sp else "stopsuz"
    return f"{a} / {b}"


src = open("scan.py", encoding="utf-8").read()
T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
tick = [t + ".IS" for t in dict.fromkeys(T)]


def norm(ix):
    return pd.to_datetime(ix).tz_localize(None).normalize()


def first(a):
    i = int(a.argmax())
    return i if a[i] else 999


xu = yf.download("XU100.IS", period=PERIOD, progress=False, auto_adjust=False)
if xu.columns.nlevels > 1:
    xu.columns = xu.columns.get_level_values(0)
xu = xu.dropna()
xu.index = norm(xu.index)
xc_all = xu["Close"]
sample = set(xu.index[130::STEP])

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
            if len(x) < 200:
                continue
            x.index = norm(x.index)
            x = x[~x.index.duplicated()]
            o, h, l, c, v = x["Open"], x["High"], x["Low"], x["Close"], x["Volume"]
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
            obvup = (obv > obv.shift(20)).astype(int)
            f = pd.DataFrame({"date": x.index, "h": t[:-3], "rs63": rs63.values,
                              "r63": r63.values, "rsi": rsi.values,
                              "cmf": cmf.values, "obvup": obvup.values})
            ok = (x.index.isin(sample) & ((av * c) >= LIQ).values &
                  rs63.notna().values & r63.notna().values & rsi.notna().values &
                  cmf.notna().values)
            oa, ha, la, ca = o.values, h.values, l.values, c.values
            n = len(x)
            pos = [j for j in np.where(ok)[0] if j + W < n and oa[j + 1] > 0]
            if not pos:
                continue
            cols = {f"{p}{k}": [] for k in range(len(RULES)) for p in ("w", "s", "r")}
            for j in pos:
                e = oa[j + 1]
                up = ha[j + 1:j + W + 1] / e * 100 - 100
                dn = la[j + 1:j + W + 1] / e * 100 - 100
                end = ca[j + W] / e * 100 - 100
                for k, (tg, sp) in enumerate(RULES):
                    t1 = first(up >= tg) if tg else 999
                    ts = first(dn <= -sp) if sp else 999
                    win = t1 < ts
                    stp = (ts <= t1) and ts < 999
                    if win:
                        r = tg - COST
                    elif stp:
                        r = -sp - COST
                    else:
                        r = end - COST
                    cols[f"w{k}"].append(1.0 if win else 0.0)
                    cols[f"s{k}"].append(1.0 if stp else 0.0)
                    cols[f"r{k}"].append(r)
            g = f.iloc[pos].copy()
            for kk, vv in cols.items():
                g[kk] = vv
            rows.append(g)
        except Exception as e:
            continue

D = pd.concat(rows, ignore_index=True)
D["p63"] = D.groupby("date")["rs63"].rank(pct=True)
dates = sorted(D.date.unique())
cut = dates[int(len(dates) * 0.7)]
tr = D.date < cut
base = (D.p63 >= 0.8) & (D.cmf > 0.05) & (D.obvup == 1)

ROWS = [
    ("TÜM (taban)", pd.Series(True, index=D.index)),
    ("GRUP: RS63%20+CMF+OBV", base),
    ("  RSI < 60", base & (D.rsi < 60)),
    ("  RSI 60-70", base & (D.rsi >= 60) & (D.rsi < 70)),
    ("  RSI 70+", base & (D.rsi >= 70)),
    ("  63g yükseliş < %40", base & (D.r63 < 40)),
    ("  63g yükseliş %40-80", base & (D.r63 >= 40) & (D.r63 < 80)),
    ("  63g yükseliş %80+", base & (D.r63 >= 80)),
]

out = []
P = out.append
P("BIST ŞİŞME TESTİ: RSI ve 63 GÜN YÜKSELİŞE GÖRE (2 ay)")
P(f"Dönem: {min(dates):%d.%m.%Y} - {max(dates):%d.%m.%Y} · hisse: {D.h.nunique()} · satır: {len(D)}")
P("GRUP = göreceli güç (RS63) üst %20 + CMF>0.05 + OBV↑. RSI = RSI14. 63g yükseliş = hissenin kendi 63 günlük getirisi.")
P(f"Giriş: ertesi gün açılış, pencere {W} işlem günü, net %{COST} maliyet. Aynı gün hedef+stop = stop.")
P("hedef% = stoptan önce hedefe ulaşan · stop% = stoptan çıkan · ort = ort. net getiri %")
P("eğ / test = eğitim (ilk %70 tarih) / test dönemi ort. Gap'ler hesaba katılmadı, hayatta kalma yanlılığı var.")
P("")
P("Grubun ortalamaları: RSI %.0f · 63g yükseliş %%%.0f" % (D[base].rsi.mean(), D[base].r63.mean()))
for k, r in enumerate(RULES):
    P("")
    P(f"--- KURAL: {rname(r)} ---")
    P(f"{'grup':<24}{'n':>6}{'hedef%':>7}{'stop%':>7}{'ort':>7}{'eğ':>7}{'test':>7}")
    for lab, msk in ROWS:
        s = D[msk]
        if len(s) < 50:
            continue
        a, b = D[msk & tr], D[msk & ~tr]
        P(f"{lab:<24}{len(s):>6}{s[f'w{k}'].mean() * 100:>6.1f}%{s[f's{k}'].mean() * 100:>6.0f}%"
          f"{s[f'r{k}'].mean():>+7.2f}{a[f'r{k}'].mean():>+7.2f}{b[f'r{k}'].mean():>+7.2f}")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Momentum2 test</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/momentum2.html", "w", encoding="utf-8").write(page)
