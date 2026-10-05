import yfinance as yf, pandas as pd, numpy as np
import re, os
import html as H

PERIOD = "3y"
K = 3        # swing tepe onayı için sağ/sol mum sayısı
IMP = 3.0    # OB'den BOS kapanışına minimum yükseliş %
WIN = 20     # OB'ye geri dönüş için bekleme (gün)
COST = 0.3   # işlem maliyeti %
TMAX = 10    # hedef/stop testinde maksimum bekleme (gün)

src = open("scan.py", encoding="utf-8").read()
T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
tick = [t + ".IS" for t in dict.fromkeys(T)]


def norm(ix):
    return pd.to_datetime(ix).tz_localize(None).normalize()


xureg = pd.Series(dtype=float)
try:
    xu = yf.download("XU100.IS", period=PERIOD, progress=False, auto_adjust=False)
    if xu.columns.nlevels > 1:
        xu.columns = xu.columns.get_level_values(0)
    xu = xu.dropna()
    xu.index = norm(xu.index)
    sma = xu["Close"].rolling(50).mean()
    xureg = (xu["Close"] > sma).astype(float).where(sma.notna())
except Exception as e:
    print("endeks hata", e)


def sim(t, E, S, o, h, l, c):
    n = len(c)
    R = (E - S) / E * 100
    out = {"R": R}
    sbar = l[t] <= S
    sret = (S / E - 1) * 100

    def hold(N):
        last = t + N - 1
        if last >= n:
            return np.nan, np.nan
        if sbar:
            return sret - COST, 1
        for k in range(t + 1, last + 1):
            if o[k] <= S:
                return (o[k] / E - 1) * 100 - COST, 1
            if l[k] <= S:
                return sret - COST, 1
        return (c[last] / E - 1) * 100 - COST, 0

    for N in (1, 3, 5):
        out["g%d" % N], st = hold(N)
        if N == 5:
            out["st5"] = st
    end = t + TMAX
    for m in (1, 2, 3):
        key = "r%d" % m
        if end >= n:
            out[key] = np.nan
            continue
        if sbar:
            out[key] = sret - COST
            continue
        tg = E * (1 + m * R / 100)
        res = (c[end] / E - 1) * 100 - COST
        for k in range(t + 1, end + 1):
            if o[k] <= S:
                res = (o[k] / E - 1) * 100 - COST
                break
            if l[k] <= S:
                res = sret - COST
                break
            if o[k] >= tg:
                res = (o[k] / E - 1) * 100 - COST
                break
            if h[k] >= tg:
                res = m * R - COST
                break
        out[key] = res
    return out


def obler(name, idx, o, h, l, c, v, av, reg):
    n = len(c)
    piv = np.full(n, np.nan)
    for p in range(K, n - K):
        if h[p] > h[p - K:p].max() and h[p] >= h[p + 1:p + K + 1].max():
            piv[p] = h[p]
    res = []
    lastSH = np.nan
    for j in range(25, n - 1):
        pp = j - 1 - K
        if pp >= 0 and not np.isnan(piv[pp]):
            lastSH = piv[pp]
        if np.isnan(lastSH):
            continue
        if not (c[j] > lastSH and c[j - 1] <= lastSH and c[j] > o[j]):
            continue
        k = j - 1
        while k >= j - 6 and k >= 0 and c[k] >= o[k]:
            k -= 1
        if k < j - 6 or k < 0 or c[k] >= o[k]:
            continue
        b = k
        imp = (c[j] / c[b] - 1) * 100
        if imp < IMP:
            continue
        top, bot = o[b], l[b]
        fvg = any(l[q + 1] > h[q - 1] for q in range(b + 1, j))
        vr = v[j] / av[j] if av[j] and not np.isnan(av[j]) else np.nan
        lik = (av[j] * c[j] >= 2_000_000) if not np.isnan(av[j]) else False
        for t in range(j + 1, min(j + 1 + WIN, n)):
            if l[t] <= top:
                if o[t] <= bot:
                    break
                E = min(o[t], top)
                S = bot
                R = (E - S) / E * 100
                if R < 0.5 or R > 15:
                    break
                s = sim(t, E, S, o, h, l, c)
                s.update({"h": name, "date": idx[t], "fvg": fvg, "vr": vr,
                          "imp": imp, "lik": lik, "wait": t - j, "reg": reg[j]})
                res.append(s)
                break
    return res


store = {}
recs = []
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
            o, h, l, c, v = (x[q].values.astype(float) for q in ["Open", "High", "Low", "Close", "Volume"])
            av = pd.Series(v).shift(1).rolling(20).mean().values
            reg = xureg.reindex(x.index).values
            store[t[:-3]] = (x.index, o, h, l, c, av)
            recs += obler(t[:-3], x.index, o, h, l, c, v, av, reg)
        except Exception as e:
            continue

D = pd.DataFrame(recs)
D = D[D.lik].copy()
Rm = float(D.R.median())

base = []
for name, (idx, o, h, l, c, av) in store.items():
    n = len(c)
    for dd in range(60, n - 1, 3):
        if np.isnan(av[dd]) or av[dd] * o[dd] < 2_000_000:
            continue
        E = o[dd]
        s = sim(dd, E, E * (1 - Rm / 100), o, h, l, c)
        base.append(s)
B = pd.DataFrame(base)

cols = ["g1", "g3", "g5", "r1", "r2", "r3"]
dates = sorted(D.date.unique())
cut = dates[int(len(dates) * 0.7)]
tr = D.date < cut

G = {
    "TÜM boğa OB": D.R.notna(),
    "FVG var": D.fvg,
    "FVG yok": ~D.fvg,
    "impuls hacmi ≥2x": D.vr >= 2,
    "impuls hacmi <2x": D.vr < 2,
    "impuls ≥%6": D.imp >= 6,
    "impuls %3-6": D.imp < 6,
    "hızlı dönüş ≤3 gün": D.wait <= 3,
    "geç dönüş 4+ gün": D.wait > 3,
    "endeks↑ (SMA50 üstü)": D.reg == 1,
    "endeks↓": D.reg == 0,
    "risk ≤%3": D.R <= 3,
    "risk >%3": D.R > 3,
    "FVG + hacim 2x+": D.fvg & (D.vr >= 2),
    "FVG + hacim 2x+ + endeks↑": D.fvg & (D.vr >= 2) & (D.reg == 1),
}

out = []
P = out.append
P("BIST BOĞA ORDER BLOCK GERİYE TEST")
P(f"Dönem: {D.date.min():%d.%m.%Y} - {D.date.max():%d.%m.%Y} · hisse: {D.h.nunique()} · "
  f"işlem: {len(D)} · medyan risk (giriş-stop) %{Rm:.1f}")
P(f"Kural: BOS (swing tepe kırılımı, K={K}) + en az %{IMP:.0f} yükseliş, OB = son kırmızı mum "
  f"(alt fitil - açılış). Giriş: ilk geri dönüş (en çok {WIN} gün). Stop: OB alt fitili.")
P(f"Net getiri, %{COST} maliyet dahil. Aynı barda stop+hedef = stop. Rastgele giriş: aynı stop mesafesi.")
P("gs = giriş günü kapanışı · g3/g5 = 3./5. gün kapanışı (stoplu) · st5 = 5 günde stop %")
P("1R/2R/3R = hedef riskin 1/2/3 katı, stop altta, en çok 10 gün")
P("")
P(f"{'grup':<28}{'n':>6}{'st5%':>6}{'gs':>7}{'g3':>7}{'g5':>7}{'1R':>7}{'2R':>7}{'3R':>7}")


def line(label, s):
    if len(s) < 30:
        return
    m = [np.nanmean(s[k]) if s[k].notna().any() else np.nan for k in cols]
    st = np.nanmean(s.st5) * 100 if s.st5.notna().any() else np.nan
    P(f"{label:<28}{len(s):>6}{st:>6.0f}" + "".join(f"{x:>+7.2f}" for x in m))


line("RASTGELE giriş (taban)", B)
for k, msk in G.items():
    line(k, D[msk])

P("")
P(f"=== EĞİTİM ({dates[0]:%d.%m.%Y}-{cut:%d.%m.%Y}) / TEST (sonrası): net g3 ve 2R ===")
P(f"{'grup':<28}{'n_eğ':>6}{'g3':>7}{'2R':>7}{'n_test':>8}{'g3':>7}{'2R':>7}")
for k, msk in G.items():
    a, b = D[msk & tr], D[msk & ~tr]
    if len(a) < 30 or len(b) < 15:
        continue
    P(f"{k:<28}{len(a):>6}{np.nanmean(a.g3):>+7.2f}{np.nanmean(a.r2):>+7.2f}"
      f"{len(b):>8}{np.nanmean(b.g3):>+7.2f}{np.nanmean(b.r2):>+7.2f}")

P("")
P("Not: OB tanımı kural bazlı bir yorum; elle çizenler farklı seçer. Eğitim ve testte")
P("birlikte rastgele girişin üstünde çıkan satır yoksa kenar yok demektir.")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>OB test</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/obtest.html", "w", encoding="utf-8").write(page)
