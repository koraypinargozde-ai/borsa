import yfinance as yf, pandas as pd, numpy as np
import re, os, itertools
import html as H

PERIOD = "1y"
src = open("scan.py", encoding="utf-8").read()
T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
tick = [t + ".IS" for t in dict.fromkeys(T)]


def norm(ix):
    return pd.to_datetime(ix).tz_localize(None).normalize()


xuchg = pd.Series(dtype=float)
try:
    xu = yf.download("XU100.IS", period=PERIOD, progress=False, auto_adjust=False)
    if xu.columns.nlevels > 1:
        xu.columns = xu.columns.get_level_values(0)
    xu = xu.dropna()
    xu.index = norm(xu.index)
    xuchg = xu["Close"].pct_change() * 100
except Exception as e:
    print("endeks hata", e)


def ozellik(x):
    c, h, l, v = x["Close"], x["High"], x["Low"], x["Volume"]
    f = pd.DataFrame(index=x.index)
    f["chg"] = c.pct_change() * 100
    av = v.shift(1).rolling(20).mean()
    f["vr"] = v / av
    f["lik"] = (av * c) >= 2_000_000
    f["pos"] = ((c - l) / (h - l).replace(0, np.nan)).fillna(0.5) * 100
    f["ret5"] = (c / c.shift(5) - 1) * 100
    f["ret20"] = (c / c.shift(20) - 1) * 100
    f["yak20"] = (c / h.shift(1).rolling(20).max() - 1) * 100
    tr = (h - l) / c * 100
    f["sik"] = tr.rolling(5).mean() / tr.rolling(20).mean()
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
    f["rs"] = f["chg"] - xuchg.reindex(x.index).fillna(0)
    tv = (f["chg"] >= 9.4) & (c >= h * 0.995)
    f["tv10"] = tv.astype(float).rolling(10).sum()
    f["y"] = tv.astype(float).shift(-1)
    f["g1"] = (c.shift(-1) / c - 1) * 100
    f["z1"] = (h.shift(-1) / c - 1) * 100
    nxt = pd.concat([h.shift(-1), h.shift(-2), h.shift(-3)], axis=1)
    f["z3"] = (nxt.max(axis=1).where(nxt.notna().all(axis=1)) / c - 1) * 100
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
            f = ozellik(x)
            f["h"] = t[:-3]
            frames.append(f)
        except Exception:
            continue

A0 = pd.concat(frames).replace([np.inf, -np.inf], np.nan)
A = A0[A0.lik & A0.y.notna()].dropna(subset=["vr", "cmf", "sik", "yak20", "ret20", "vk"])
D = A[A.chg < 7].copy()  # bugun zaten %7+ yukselenler disarida: amac primlenmemis hisse
br = D.y.mean() * 100

COND = {
    "değ ≤0": D.chg <= 0,
    "değ 0-3": (D.chg > 0) & (D.chg <= 3),
    "değ 3-7": (D.chg > 3) & (D.chg < 7),
    "değ <3": D.chg <= 3,
    "hacim <1x": D.vr < 1,
    "hacim 1-2x": (D.vr >= 1) & (D.vr < 2),
    "hacim 2-4x": (D.vr >= 2) & (D.vr < 4),
    "hacim 4x+": D.vr >= 4,
    "kapanış ≥70": D.pos >= 70,
    "kırılım 20g": D.yak20 > 0,
    "zirveye ≤%3": (D.yak20 <= 0) & (D.yak20 >= -3),
    "sıkışma <0.8": D.sik < 0.8,
    "5g getiri <5": D.ret5 < 5,
    "20g getiri <10": D.ret20 < 10,
    "💰 para girişi": D.pg.astype(bool),
    "CMF>0.15": D.cmf > 0.15,
    "endeksten güçlü": D.rs > 1,
    "son 10g tavan var": D.tv10 >= 1,
    "önceki 2g hacim≥1.2x": D.vk >= 1.2,
}
names = list(COND)
M = {k: v.values for k, v in COND.items()}

out = []
P = out.append
P("BIST TAVAN ÖNCESİ GERİYE TEST")
P(f"Dönem: {D.index.min():%d.%m.%Y} - {D.index.max():%d.%m.%Y} · hisse: {D.h.nunique()} · "
  f"gün-hisse örneği: {len(D)} · ertesi gün tavan: {int(D.y.sum())} (taban oran %{br:.2f})")
P("Sadece o gün %7'den az yükselmiş (primlenmemiş) hisseler sayıldı.")
P("tavan = ertesi gün tavan olma oranı · kat = taban orana göre kaç kat")
P("g1 = ertesi gün kapanış getirisi (ort.) · z1 = ertesi gün en yüksek · z3 = 3 günde en yüksek")
P("")
P("=== TEK KOŞULLAR ===")
P(f"{'koşul':<24}{'n':>7}{'tavan':>8}{'kat':>7}{'g1':>7}{'z1':>7}{'z3':>7}")
for k in names:
    s = D[M[k]]
    if len(s) < 30:
        continue
    r = s.y.mean() * 100
    P(f"{k:<24}{len(s):>7}{r:>7.1f}%{r / br:>6.1f}x{s.g1.mean():>+7.1f}{s.z1.mean():>+7.1f}{s.z3.mean():>+7.1f}")

dates = sorted(D.index.unique())
cut = dates[int(len(dates) * 0.7)]
y = D.y.values
trm = np.asarray(D.index < cut)
res = []
for r in (1, 2, 3):
    for combo in itertools.combinations(names, r):
        m = M[combo[0]].copy()
        for k in combo[1:]:
            m &= M[k]
        a, b = m & trm, m & ~trm
        ea, eb = y[a].sum(), y[b].sum()
        if a.sum() < 100 or ea < 8 or eb < 3:
            continue
        res.append((y[a].mean() * 100, y[b].mean() * 100, int(a.sum()), int(b.sum()),
                    int(ea), int(eb), combo))
res.sort(key=lambda r: -r[0])

P("")
P(f"=== EN İYİ KOMBİNASYONLAR (eğitim: {dates[0]:%d.%m.%Y}-{cut:%d.%m.%Y}, test: sonrası) ===")
P("Test sütunu kuralın görmediği dönemdeki sonucu. İkisi de yüksekse güvenilir.")
for n, (ra, rb, na, nb, ea, eb, combo) in enumerate(res[:12], 1):
    m = M[combo[0]].copy()
    for k in combo[1:]:
        m &= M[k]
    s = D[m]
    P(f"{n}) " + " + ".join(combo))
    P(f"   eğitim: n={na} tavan %{ra:.1f} ({ea} olay) · test: n={nb} tavan %{rb:.1f} ({eb} olay)")
    P(f"   ertesi gün kapanış {s.g1.mean():+.1f}% · ertesi gün en yüksek {s.z1.mean():+.1f}% · 3 günde en yüksek {s.z3.mean():+.1f}%")
if not res:
    P("Yeterli örnekli kombinasyon çıkmadı.")

P("")
P("=== INFO: TAVANDAN BİR GÜN ÖNCEKİ HALİ ===")
ib = A0[(A0.h == "INFO") & (A0.y == 1)]
if len(ib) == 0:
    P("INFO için dönemde tavan olayı bulunamadı.")
for ix, r in ib.iterrows():
    P(f"{ix:%d.%m.%Y}: değ {r.chg:+.1f}% · hacim {r.vr:.1f}x · kapanış {r.pos:.0f} · "
      f"20g zirveye {r.yak20:+.1f}% · sıkışma {r.sik:.2f} · 5g {r.ret5:+.1f}% · "
      f"20g {r.ret20:+.1f}% · 💰 {'evet' if r.pg else 'hayır'} · endeksten fark {r.rs:+.1f}")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Geriye test</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/geriye.html", "w", encoding="utf-8").write(page)
