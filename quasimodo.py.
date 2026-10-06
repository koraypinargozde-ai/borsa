import yfinance as yf, pandas as pd, numpy as np
import re, os
import html as H
from bisect import bisect_left, bisect_right

PERIOD = "3y"
K = 3        # swing onayı için sağ/sol mum sayısı
IMP = 3.0    # OB için BOS kapanışına minimum yükseliş %
WIN = 20     # QM bölgesine geri dönüş için bekleme (gün)
COST = 0.3   # işlem maliyeti %
TMAX = 10    # hedef/stop testinde maksimum bekleme (gün)
MAXAGE = 30  # head dibi ile BOS arası en çok gün
FIB = [0.382, 0.5, 0.618, 0.705, 0.786]

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


def runT(t, E, S, tg, o, h, l, c):
    n = len(c)
    end = t + TMAX
    if end >= n:
        return np.nan
    sret = (S / E - 1) * 100
    if l[t] <= S:
        return sret - COST
    res = (c[end] / E - 1) * 100 - COST
    for k in range(t + 1, end + 1):
        if o[k] <= S:
            return (o[k] / E - 1) * 100 - COST
        if l[k] <= S:
            return sret - COST
        if o[k] >= tg:
            return (o[k] / E - 1) * 100 - COST
        if h[k] >= tg:
            return (tg / E - 1) * 100 - COST
    return res


def sim(t, E, S, o, h, l, c, Top=None):
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

    out["g3"], _ = hold(3)
    out["g5"], st = hold(5)
    out["st5"] = st
    out["r2"] = runT(t, E, S, E * (1 + 2 * R / 100), o, h, l, c)
    for key, x in (("f1", 1.0), ("f2", 1.272), ("f3", 1.618)):
        if Top is None:
            out[key] = np.nan
            continue
        tg = S + x * (Top - S)
        out[key] = runT(t, E, S, tg, o, h, l, c) if tg > E * 1.003 else np.nan
    return out


def qmler(name, idx, o, h, l, c, v, av, reg):
    n = len(c)
    pl, ph = [], []
    for p in range(K, n - K):
        if l[p] < l[p - K:p].min() and l[p] <= l[p + 1:p + K + 1].min():
            pl.append(p)
        if h[p] > h[p - K:p].max() and h[p] >= h[p + 1:p + K + 1].max():
            ph.append(p)
    res = []
    for j in range(30, n - 1):
        a = bisect_right(pl, j - K) - 1
        if a < 1:
            continue
        p2 = pl[a]
        if j - p2 > MAXAGE:
            continue
        i1 = bisect_left(ph, p2) - 1
        if i1 < 0:
            continue
        h1 = ph[i1]
        q = bisect_left(pl, h1) - 1
        if q < 0:
            continue
        L1 = pl[q]
        i0 = bisect_left(ph, L1) - 1
        if i0 < 0:
            continue
        h0 = ph[i0]
        # aşağı trend yapısı: H0 > H1, L1 > L2 (head = daha düşük dip)
        if not (h[h0] > h[h1] and l[p2] < l[L1]):
            continue
        if h[h1] < h[L1:p2 + 1].max():
            continue
        # head dibinden sonra yeni dip yok, BOS ilk kırılım
        if p2 + 1 <= j and l[p2 + 1:j + 1].min() <= l[p2]:
            continue
        if p2 + 1 < j and c[p2 + 1:j].max() > h[h1]:
            continue
        if not (c[j] > h[h1] and c[j - 1] <= h[h1] and c[j] > o[j]):
            continue
        ztop = max(o[L1], c[L1])
        S = l[p2]
        if c[j] <= ztop or ztop <= S:
            continue
        # OB: BOS dalgasından önceki son kırmızı mum
        k = j - 1
        while k >= j - 6 and k >= 0 and c[k] >= o[k]:
            k -= 1
        ob = False
        fvg = False
        imp = np.nan
        if k >= j - 6 and k >= 0 and c[k] < o[k]:
            imp = (c[j] / c[k] - 1) * 100
            ob = imp >= IMP
            if ob:
                fvg = any(l[z + 1] > h[z - 1] for z in range(k + 1, j))
        vr = v[j] / av[j] if av[j] and not np.isnan(av[j]) else np.nan
        lik = (av[j] * c[j] >= 2_000_000) if not np.isnan(av[j]) else False
        for t in range(j + 1, min(j + 1 + WIN, n)):
            if l[t] <= S:
                break
            if l[t] <= ztop:
                E = min(o[t], ztop)
                R = (E - S) / E * 100
                if R < 0.5 or R > 15:
                    break
                Top = h[p2 + 1:t].max()
                ratio = (Top - E) / (Top - S) if Top > S else np.nan
                s = sim(t, E, S, o, h, l, c, Top)
                s.update({"h": name, "date": idx[t], "ob": ob, "fvg": fvg,
                          "vr": vr, "imp": imp, "lik": lik, "wait": t - j,
                          "reg": reg[j], "ratio": ratio})
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
            recs += qmler(t[:-3], x.index, o, h, l, c, v, av, reg)
        except Exception as e:
            continue

D = pd.DataFrame(recs)
if len(D) == 0:
    print("hiç QM bulunamadı")
    raise SystemExit
D = D[D.lik].copy()
D["ob"] = D.ob.astype(bool)
Rm = float(D.R.median())

base = []
for name, (idx, o, h, l, c, av) in store.items():
    n = len(c)
    for dd in range(60, n - 1, 3):
        if np.isnan(av[dd]) or av[dd] * o[dd] < 2_000_000:
            continue
        E = o[dd]
        base.append(sim(dd, E, E * (1 - Rm / 100), o, h, l, c))
B = pd.DataFrame(base)

cols = ["g3", "g5", "r2", "f1", "f2", "f3"]
dates = sorted(D.date.unique())
cut = dates[int(len(dates) * 0.7)]
tr = D.date < cut

r = D.ratio
fz = (r >= 0.58) & (r <= 0.83)
G = {"TÜM boğa QM": D.R.notna()}
G["OB var"] = D.ob
G["OB yok"] = ~D.ob
for f in FIB:
    G["Fibo %s (±0.05)" % f] = (r - f).abs() <= 0.05
G["Fibo 0.618-0.786 bölge"] = fz
G["Fibo sığ (<0.33)"] = r < 0.33
G["Fibo derin (>0.83)"] = r > 0.83
G["QM + OB"] = D.ob
G["QM + Fibo bölge"] = fz
G["QM + OB + Fibo bölge"] = D.ob & fz
G["QM+OB+Fibo+endeks↑"] = D.ob & fz & (D.reg == 1)
G["QM+OB+Fibo+hacim 2x+"] = D.ob & fz & (D.vr >= 2)
G["endeks↑"] = D.reg == 1
G["endeks↓"] = D.reg == 0

out = []
P = out.append
P("BIST BOĞA QUASIMODO + ORDER BLOCK + FIBONACCI GERİYE TEST")
P(f"Dönem: {D.date.min():%d.%m.%Y} - {D.date.max():%d.%m.%Y} · hisse: {D.h.nunique()} · "
  f"işlem: {len(D)} · medyan risk %{Rm:.1f}")
P("Boğa QM: H0>H1 ve L1>L2 (aşağı trend), L2 sonrası H1 kırılımı (BOS, ilk kırılım).")
P("Giriş: fiyatın sol omuz bölgesine (L1 dibi - L1 mum gövde üstü) ilk dönüşü, en çok "
  f"{WIN} gün. Stop: head dibi (L2).")
P("OB: BOS dalgasından önceki son kırmızı mum + en az %3 yükseliş.")
P("Fibo oranı: giriş fiyatının L2->zirve bacağındaki geri çekilme oranı.")
P("Hedef f1/f2/f3: L2 + 1.0 / 1.272 / 1.618 x (zirve - L2). r2: riskin 2 katı.")
P(f"Net getiri %{COST} maliyet dahil. Aynı barda stop+hedef = stop. En çok {TMAX} gün.")
P("n<20 olan satırlar gösterilmez.")
P("")
P(f"{'grup':<26}{'n':>5}{'st5%':>5}" + "".join(f"{k:>7}" for k in cols))


def line(label, s):
    if len(s) < 20:
        return
    m = [np.nanmean(s[k]) if s[k].notna().any() else np.nan for k in cols]
    st = np.nanmean(s.st5) * 100 if s.st5.notna().any() else np.nan
    P(f"{label:<26}{len(s):>5}{st:>5.0f}" + "".join(f"{x:>+7.2f}" for x in m))


line("RASTGELE giriş (taban)", B)
for k, msk in G.items():
    line(k, D[msk])

P("")
P(f"=== EĞİTİM ({dates[0]:%d.%m.%Y}-{cut:%d.%m.%Y}) / TEST (sonrası): net g3, 2R, f2 ===")
P(f"{'grup':<26}{'n_eğ':>5}{'g3':>7}{'2R':>7}{'f2':>7}{'n_te':>6}{'g3':>7}{'2R':>7}{'f2':>7}")
for k, msk in G.items():
    a, b = D[msk & tr], D[msk & ~tr]
    if len(a) < 20 or len(b) < 10:
        continue
    P(f"{k:<26}{len(a):>5}{np.nanmean(a.g3):>+7.2f}{np.nanmean(a.r2):>+7.2f}"
      f"{np.nanmean(a.f2) if a.f2.notna().any() else np.nan:>+7.2f}"
      f"{len(b):>6}{np.nanmean(b.g3):>+7.2f}{np.nanmean(b.r2):>+7.2f}"
      f"{np.nanmean(b.f2) if b.f2.notna().any() else np.nan:>+7.2f}")

P("")
P("Not: QM/OB kural bazlı yorum; elle çizenler farklı seçer. Eğitim ve testte")
P("birlikte rastgele girişin üstünde çıkan satır yoksa kenar yok demektir.")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>QM test</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/quasimodo.html", "w", encoding="utf-8").write(page)
