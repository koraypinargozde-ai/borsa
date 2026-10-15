import yfinance as yf, pandas as pd, numpy as np
import re, os
import html as H

PERIOD = "3y"
COST = 0.3
STEP = 5
LIQ = 2_000_000
W = 40        # ~2 ay (işlem günü)
TGT = 30.0    # hedef %
TGT2 = 40.0
STOP = 15.0   # stop %

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
            av60 = v.shift(1).rolling(60).mean()
            rs63 = ((c / c.shift(63) - 1) - (xc / xc.shift(63) - 1)) * 100
            rs21 = ((c / c.shift(21) - 1) - (xc / xc.shift(21) - 1)) * 100
            vr = av / av60
            near = c / c.rolling(120).max()
            band60 = (c.rolling(60).max() / c.rolling(60).min() - 1) * 100
            rg = (h - l).replace(0, np.nan)
            mf = (((c - l) - (h - c)) / rg).fillna(0)
            cmf = (mf * v).rolling(20).sum() / v.rolling(20).sum()
            obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
            obvup = (obv > obv.shift(20)).astype(int)
            f = pd.DataFrame({"date": x.index, "h": t[:-3], "rs63": rs63.values,
                              "rs21": rs21.values, "vr": vr.values,
                              "near": near.values, "band60": band60.values,
                              "cmf": cmf.values, "obvup": obvup.values})
            ok = (x.index.isin(sample) & ((av * c) >= LIQ).values &
                  rs63.notna().values & rs21.notna().values & vr.notna().values &
                  near.notna().values & band60.notna().values & cmf.notna().values)
            oa, ha, la, ca = o.values, h.values, l.values, c.values
            n = len(x)
            pos = [j for j in np.where(ok)[0] if j + W < n and oa[j + 1] > 0]
            if not pos:
                continue
            w30, w40, st, rk, mx, mn = [], [], [], [], [], []
            for j in pos:
                e = oa[j + 1]
                up = ha[j + 1:j + W + 1] / e * 100 - 100
                dn = la[j + 1:j + W + 1] / e * 100 - 100
                a1 = np.where(up >= TGT)[0]
                a2 = np.where(up >= TGT2)[0]
                b = np.where(dn <= -STOP)[0]
                t1 = a1[0] if len(a1) else 999
                t2 = a2[0] if len(a2) else 999
                ts = b[0] if len(b) else 999
                win = t1 < ts
                w30.append(1.0 if win else 0.0)
                w40.append(1.0 if t2 < ts else 0.0)
                stp = (ts <= t1) and ts < 999
                st.append(1.0 if stp else 0.0)
                if win:
                    r = TGT - COST
                elif stp:
                    r = -STOP - COST
                else:
                    r = ca[j + W] / e * 100 - 100 - COST
                rk.append(r)
                mx.append(up.max())
                mn.append(dn.min())
            g = f.iloc[pos].copy()
            g["w30"], g["w40"], g["st"] = w30, w40, st
            g["rk"], g["mx"], g["mn"] = rk, mx, mn
            rows.append(g)
        except Exception as e:
            continue

D = pd.concat(rows, ignore_index=True)
D["p63"] = D.groupby("date")["rs63"].rank(pct=True)
D["p21"] = D.groupby("date")["rs21"].rank(pct=True)

dates = sorted(D.date.unique())
cut = dates[int(len(dates) * 0.7)]
tr = D.date < cut
base30 = D.w30.mean() * 100

cmfobv = (D.cmf > 0.05) & (D.obvup == 1)
baz = D.band60 <= 30
G = {
    "TÜM (taban)": pd.Series(True, index=D.index),
    "RS63 üst %10": D.p63 >= 0.9,
    "RS63 üst %20": D.p63 >= 0.8,
    "RS63 %20 + hacim↑ + zirve": (D.p63 >= 0.8) & (D.vr > 1.2) & (D.near >= 0.9),
    "RS63 %10 + hacim↑ + zirve": (D.p63 >= 0.9) & (D.vr > 1.2) & (D.near >= 0.9),
    "yatay baz (60g ≤%30)": baz,
    "baz + hacim↑": baz & (D.vr > 1.2),
    "baz + RS63 üst yarı": baz & (D.p63 >= 0.5),
    "baz + CMF>0.05 + OBV↑": baz & cmfobv,
    "CMF>0.05 + OBV↑": cmfobv,
    "RS63 %20 + CMF + OBV↑": (D.p63 >= 0.8) & cmfobv,
    "RS63 alt %10 (ters)": D.p63 <= 0.1,
}

out = []
P = out.append
P("BIST 2 AYDA +%30 HEDEF TESTİ")
P(f"Dönem: {min(dates):%d.%m.%Y} - {max(dates):%d.%m.%Y} · hisse: {D.h.nunique()} · "
  f"örnek tarih: {len(dates)} (her {STEP} işlem günü) · satır: {len(D)}")
P(f"Giriş: ertesi gün açılış. Pencere: {W} işlem günü (~2 ay). Hedef +%{TGT:.0f} (ek: +%{TGT2:.0f}), stop -%{STOP:.0f}.")
P("+30% / +40% = stop'tan ÖNCE hedefe değenlerin oranı. Aynı gün ikisi de değerse stop sayıldı.")
P("stop = hedeften önce -%15'e inenler. ort = kurala göre ortalama net getiri (hedefte çık,")
P(f"stopta çık, yoksa {W}. gün kapanış; %{COST} maliyet). maxY = pencerede ort. en yüksek fiyat %.")
P("kat = +30% oranı / taban oranı. Gap'ler (stopu aşağıdan geçen açılış) hesaba katılmadı.")
P("Örnekler üst üste biner, güncel hisse listesi (hayatta kalma yanlılığı).")
P("")
P(f"{'grup':<26}{'n':>6}{'+30%':>6}{'kat':>5}{'+40%':>6}{'stop':>6}{'ort':>7}{'maxY':>6}")


def line(label, s):
    if len(s) < 50:
        return
    r30 = s.w30.mean() * 100
    P(f"{label:<26}{len(s):>6}{r30:>5.1f}%{r30 / base30:>4.1f}x{s.w40.mean() * 100:>5.1f}%"
      f"{s.st.mean() * 100:>5.0f}%{s.rk.mean():>+7.2f}{s.mx.mean():>6.0f}")


for k, msk in G.items():
    line(k, D[msk])

P("")
P(f"=== EĞİTİM ({min(dates):%d.%m.%Y}-{cut:%d.%m.%Y}) / TEST (sonrası) ===")
P(f"{'grup':<26}{'n_eğ':>6}{'+30%':>6}{'ort':>7}{'n_te':>6}{'+30%':>6}{'ort':>7}")
for k, msk in G.items():
    a, b = D[msk & tr], D[msk & ~tr]
    if len(a) < 50 or len(b) < 30:
        continue
    P(f"{k:<26}{len(a):>6}{a.w30.mean() * 100:>5.1f}%{a.rk.mean():>+7.2f}"
      f"{len(b):>6}{b.w30.mean() * 100:>5.1f}%{b.rk.mean():>+7.2f}")

P("")
P("Not: eğitimde ve testte birlikte +30% oranı tabanın üstünde ve ort > 0 olan satır yoksa kenar yok.")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Momentum2 test</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/momentum2.html", "w", encoding="utf-8").write(page)
