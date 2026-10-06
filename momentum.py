import yfinance as yf, pandas as pd, numpy as np
import re, os
import html as H

PERIOD = "3y"
COST = 0.3          # işlem maliyeti %
HOLDS = (5, 10, 20) # tutma süresi (gün)
STEP = 5            # her 5 işlem gününde bir örnek tarih
LIQ = 2_000_000     # günlük ort. işlem hacmi alt sınırı (TL)

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
            o, c, v = x["Open"], x["Close"], x["Volume"]
            xc = xc_all.reindex(x.index, method="ffill")
            av = v.shift(1).rolling(20).mean()
            av60 = v.shift(1).rolling(60).mean()
            rs63 = ((c / c.shift(63) - 1) - (xc / xc.shift(63) - 1)) * 100
            rs21 = ((c / c.shift(21) - 1) - (xc / xc.shift(21) - 1)) * 100
            vr = av / av60
            near = c / c.rolling(120).max()
            entry = o.shift(-1)
            f = pd.DataFrame({"date": x.index, "h": t[:-3], "rs63": rs63.values,
                              "rs21": rs21.values, "vr": vr.values,
                              "near": near.values})
            for k in HOLDS:
                f["n%d" % k] = ((c.shift(-k) / entry - 1) * 100 - COST).values
            ok = (x.index.isin(sample) & ((av * c) >= LIQ).values &
                  rs63.notna().values & rs21.notna().values &
                  vr.notna().values & near.notna().values & entry.notna().values)
            rows.append(f[ok])
        except Exception as e:
            continue

D = pd.concat(rows, ignore_index=True)
D["p63"] = D.groupby("date")["rs63"].rank(pct=True)
D["p21"] = D.groupby("date")["rs21"].rank(pct=True)
for k in HOLDS:
    D["x%d" % k] = D["n%d" % k] - D.groupby("date")["n%d" % k].transform("mean")

dates = sorted(D.date.unique())
cut = dates[int(len(dates) * 0.7)]
tr = D.date < cut

G = {
    "TÜM (taban)": D.n10.notna() | D.n5.notna(),
    "RS63 üst %10": D.p63 >= 0.9,
    "RS63 üst %20": D.p63 >= 0.8,
    "RS63 alt %10 (ters)": D.p63 <= 0.1,
    "RS21 üst %10": D.p21 >= 0.9,
    "RS63 %20 + RS21 üst yarı": (D.p63 >= 0.8) & (D.p21 >= 0.5),
    "RS63 %20 + hacim↑": (D.p63 >= 0.8) & (D.vr > 1.2),
    "RS63 %20 + zirveye yakın": (D.p63 >= 0.8) & (D.near >= 0.9),
    "RS63 %20 + hacim↑ + zirve": (D.p63 >= 0.8) & (D.vr > 1.2) & (D.near >= 0.9),
    "RS63 %10 + hacim↑ + zirve": (D.p63 >= 0.9) & (D.vr > 1.2) & (D.near >= 0.9),
}

out = []
P = out.append
P("BIST GÖRECELİ GÜÇ (MOMENTUM) GERİYE TEST")
P(f"Dönem: {min(dates):%d.%m.%Y} - {max(dates):%d.%m.%Y} · hisse: {D.h.nunique()} · "
  f"örnek tarih: {len(dates)} (her {STEP} işlem günü) · satır: {len(D)}")
P("RS63 / RS21 = hissenin 63 / 21 günlük getirisi - BIST 100 getirisi. 'üst %10' = o gün")
P("tüm hisseler içinde ilk %10. hacim↑ = 20g ort hacim / 60g ort hacim > 1,2.")
P("zirve = kapanış / 120 günlük en yüksek ≥ 0,90.")
P(f"Giriş: ertesi gün açılış. Çıkış: 5/10/20. gün kapanışı. Net, %{COST} maliyet dahil.")
P("x10 = aynı günün tüm hisse ortalamasına göre fark (taban üstü). gün% = tarihlerin kaçında")
P("grup tabanı geçti. Örnekler üst üste biner (10/20 gün). Hisse listesi güncel liste:")
P("geçmişte listeden çıkan hisseler yok (hayatta kalma yanlılığı).")
P("")
P(f"{'grup':<28}{'n':>6}{'n5':>7}{'n10':>7}{'n20':>7}{'x10':>7}{'kazan%':>7}{'gün%':>6}")


def line(label, s):
    if len(s) < 50:
        return
    g = s.groupby("date")["x10"].mean().dropna()
    gp = (g > 0).mean() * 100 if len(g) else np.nan
    win = (s.n10.dropna() > 0).mean() * 100
    P(f"{label:<28}{len(s):>6}{s.n5.mean():>+7.2f}{s.n10.mean():>+7.2f}"
      f"{s.n20.mean():>+7.2f}{s.x10.mean():>+7.2f}{win:>7.0f}{gp:>6.0f}")


for k, msk in G.items():
    line(k, D[msk])

P("")
P(f"=== EĞİTİM ({min(dates):%d.%m.%Y}-{cut:%d.%m.%Y}) / TEST (sonrası): net n10, x10, n20 ===")
P(f"{'grup':<28}{'n_eğ':>6}{'n10':>7}{'x10':>7}{'n20':>7}{'n_te':>6}{'n10':>7}{'x10':>7}{'n20':>7}")
for k, msk in G.items():
    a, b = D[msk & tr], D[msk & ~tr]
    if len(a) < 50 or len(b) < 30:
        continue
    P(f"{k:<28}{len(a):>6}{a.n10.mean():>+7.2f}{a.x10.mean():>+7.2f}{a.n20.mean():>+7.2f}"
      f"{len(b):>6}{b.n10.mean():>+7.2f}{b.x10.mean():>+7.2f}{b.n20.mean():>+7.2f}")

P("")
P("Not: eğitimde ve testte birlikte x10 > 0 ve net n10 > 0 olan satır yoksa kenar yok.")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Momentum test</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/momentum.html", "w", encoding="utf-8").write(page)
