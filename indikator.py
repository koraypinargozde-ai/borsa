import yfinance as yf, pandas as pd, numpy as np
import re, os, itertools, warnings
import html as H

warnings.filterwarnings("ignore")
PERIOD = "3y"
COST = 0.3
src = open("scan.py", encoding="utf-8").read()
T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
tick = [t + ".IS" for t in dict.fromkeys(T)]


def norm(ix):
    return pd.to_datetime(ix).tz_localize(None).normalize()


def B(s, n):
    return s.shift(n, fill_value=False)


def cross_up(a, b):
    return (a > b) & (a.shift(1) <= b.shift(1))


def cross_lvl(a, lvl):
    return (a > lvl) & (a.shift(1) <= lvl)


def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def ozellik(x):
    c, o, h, l, v = x["Close"], x["Open"], x["High"], x["Low"], x["Volume"]
    f = pd.DataFrame(index=x.index)
    f["chg"] = c.pct_change() * 100
    av = v.shift(1).rolling(20).mean()
    vr = v / av
    f["lik"] = (av * c) >= 2_000_000
    tv = (f["chg"] >= 9.4) & (c >= h * 0.995)
    f["y"] = tv.astype(float).shift(-1)
    f["r1"] = (c.shift(-1) / o.shift(-1) - 1) * 100 - COST
    f["r3"] = (c.shift(-3) / o.shift(-1) - 1) * 100 - COST

    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    green, red = c > o, c < o
    upper = h - np.maximum(c, o)
    lower = np.minimum(c, o) - l
    sma20, sma50, sma200 = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(200).mean()
    down = (c < sma20) & (c.pct_change(5) < -0.03)
    h20 = h.shift(1).rolling(20).max()
    S = {}

    # --- İndikatörler ---
    r = rsi(c)
    S["RSI<30"] = r < 30
    S["RSI 30'u yukarı kesti"] = cross_lvl(r, 30)
    S["RSI 50'yi yukarı kesti"] = cross_lvl(r, 50)
    S["RSI>70"] = r > 70
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9, adjust=False).mean()
    hist = macd - sig
    S["MACD sinyali yukarı kesti"] = cross_up(macd, sig)
    S["MACD sıfırın üstüne çıktı"] = cross_lvl(macd, 0)
    S["MACD hist 3 gün artıyor (negatifte)"] = ((hist > hist.shift(1)) & (hist.shift(1) > hist.shift(2))
                                              & (hist.shift(2) > hist.shift(3)) & (hist < 0))
    sd = c.rolling(20).std()
    ub, lb = sma20 + 2 * sd, sma20 - 2 * sd
    bw = (ub - lb) / sma20
    sq = bw <= bw.rolling(120).quantile(0.2)
    S["Bollinger üst bant kırıldı"] = c > ub
    S["Bollinger alt bant altı"] = c < lb
    S["Bollinger sıkışma"] = sq
    S["Sıkışma + üst bant kırılımı"] = B(sq, 1) & (c > ub)
    ll, hh = l.rolling(14).min(), h.rolling(14).max()
    k = (c - ll) / (hh - ll).replace(0, np.nan) * 100
    dd = k.rolling(3).mean()
    S["Stokastik dipte yukarı kesti"] = cross_up(k, dd) & (k.shift(1) < 25)
    S["Stokastik >80"] = k > 80
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    upm, dnm = h.diff(), -l.diff()
    pdm = upm.where((upm > dnm) & (upm > 0), 0.0)
    mdm = dnm.where((dnm > upm) & (dnm > 0), 0.0)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False).mean() / atr
    mdi = 100 * mdm.ewm(alpha=1 / 14, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / 14, adjust=False).mean()
    S["ADX>25 ve +DI>-DI"] = (adx > 25) & (pdi > mdi)
    S["+DI -DI'yi yukarı kesti"] = cross_up(pdi, mdi)
    S["ADX 20'yi yukarı kesti"] = cross_lvl(adx, 20)
    S["Kapanış SMA20 üstüne çıktı"] = cross_up(c, sma20)
    S["Kapanış SMA50 üstüne çıktı"] = cross_up(c, sma50)
    S["SMA20 SMA50'yi yukarı kesti"] = cross_up(sma20, sma50)
    S["SMA200 üstünde"] = c > sma200
    S["SMA20'den %10+ uzak"] = (c / sma20 - 1) > 0.10
    S["SMA20'nin %10+ altında"] = (c / sma20 - 1) < -0.10
    ten = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kij = (h.rolling(26).max() + l.rolling(26).min()) / 2
    sa = ((ten + kij) / 2).shift(26)
    sb = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    top = np.maximum(sa, sb)
    S["Ichimoku bulut üstüne çıktı"] = (c > top) & (c.shift(1) <= top.shift(1))
    S["Ichimoku Tenkan Kijun'u kesti"] = cross_up(ten, kij)

    # --- Fibonacci ---
    W = 60
    hi, lo = h.rolling(W).max(), l.rolling(W).min()
    ih = h.rolling(W).apply(np.argmax, raw=True)
    il = l.rolling(W).apply(np.argmin, raw=True)
    up_tr = (ih > il) & ((hi / lo - 1) > 0.25)
    retr = (hi - c) / (hi - lo).replace(0, np.nan)
    for lvl, nm in ((0.236, "%23,6"), (0.382, "%38,2"), (0.5, "%50"), (0.618, "%61,8"), (0.786, "%78,6")):
        S[f"Fibo {nm} geri çekilme + yeşil"] = up_tr & ((retr - lvl).abs() <= 0.03) & green
    S["Fibo %38-%62 arası + yeşil"] = up_tr & (retr >= 0.35) & (retr <= 0.65) & green
    S["Yeni 60g zirve"] = c > h.shift(1).rolling(60).max()

    # --- Hacim ---
    S["Hacim 3x + değişim +1..+6"] = (vr >= 3) & (f["chg"] >= 1) & (f["chg"] <= 6)
    S["Hacim 2x + yeşil"] = (vr >= 2) & green
    S["Hacim kuruması + dipte"] = (vr < 0.5) & (c <= l.rolling(20).min() * 1.05)

    # --- Mum formasyonları ---
    S["Çekiç (düşüş sonrası)"] = down & (lower >= 2 * body) & (upper <= body) & (body > 0)
    S["Kayan yıldız"] = (c.pct_change(5) > 0.03) & (upper >= 2 * body) & (lower <= body) & (body > 0)
    S["Yutan boğa"] = B(red, 1) & green & (o <= c.shift(1)) & (c >= o.shift(1))
    S["Yutan ayı"] = B(green, 1) & red & (o >= c.shift(1)) & (c <= o.shift(1))
    S["Delici çizgi"] = (B(red, 1) & green & (o < c.shift(1)) & (c > (o.shift(1) + c.shift(1)) / 2)
                         & (c < o.shift(1)))
    S["Harami boğa"] = (B(red, 1) & green & (body.shift(1) >= 0.6 * rng.shift(1)) & (o > c.shift(1))
                        & (c < o.shift(1)))
    S["Sabah yıldızı"] = (B(red, 2) & (body.shift(2) >= 0.6 * rng.shift(2))
                          & (body.shift(1) <= 0.3 * rng.shift(1)) & green & (c > (o.shift(2) + c.shift(2)) / 2))
    S["Akşam yıldızı"] = (B(green, 2) & (body.shift(2) >= 0.6 * rng.shift(2))
                          & (body.shift(1) <= 0.3 * rng.shift(1)) & red & (c < (o.shift(2) + c.shift(2)) / 2))
    S["Üç beyaz asker"] = (green & B(green, 1) & B(green, 2) & (c > c.shift(1)) & (c.shift(1) > c.shift(2))
                           & (o > o.shift(1)) & (o <= c.shift(1)) & (o.shift(1) > o.shift(2))
                           & (o.shift(1) <= c.shift(2)))
    S["Doji (düşüş sonrası)"] = down & (body <= 0.1 * rng)
    S["Yeşil marubozu"] = green & (body >= 0.9 * rng) & (f["chg"] >= 3)
    S["İç bar (inside bar)"] = (h < h.shift(1)) & (l > l.shift(1))
    nr7 = rng == rng.rolling(7).min()
    S["NR7 dar aralık"] = nr7
    S["NR7 + zirveye yakın"] = nr7 & (c >= h.rolling(20).max() * 0.95)
    S["Gap yukarı ≥2% + yeşil"] = ((o / c.shift(1) - 1) * 100 >= 2) & green
    S["4 gün kırmızı sonrası yeşil"] = (B(red, 1) & B(red, 2) & B(red, 3) & B(red, 4) & green)

    # --- Grafik formasyonları ---
    ret10p = c.shift(5) / c.shift(15) - 1
    cons = (h.rolling(5).max() - l.rolling(5).min()) / c
    S["Boğa bayrağı (sıçrama+sıkışma)"] = (ret10p >= 0.15) & (cons <= 0.08) & (c >= h.rolling(15).max() * 0.9)
    S["20g kırılım + hacim≥1.5x"] = (c > h20) & (vr >= 1.5)
    S["60g kırılım"] = c > h.shift(1).rolling(60).max()
    S["Volatilite sıkışma + zirveye yakın"] = ((rng.rolling(5).mean() / rng.rolling(20).mean() < 0.6)
                                               & (c >= h20 * 0.97))
    L1, L2 = l.shift(20).rolling(20).min(), l.rolling(20).min()
    S["İkili dip kırılımı (yaklaşık)"] = (((L2 / L1 - 1).abs() <= 0.03)
                                          & (h.rolling(40).max() / np.minimum(L1, L2) - 1 >= 0.08)
                                          & (c >= h.shift(1).rolling(40).max() * 0.99))
    m1, m2, m3 = l.rolling(5).min(), l.shift(5).rolling(5).min(), l.shift(10).rolling(5).min()
    S["Yükselen dipler + zirveye yakın"] = (m1 > m2) & (m2 > m3) & (c >= h20 * 0.95)
    S["Dipten sert dönüş (+5%, hacim≥1.5x)"] = ((c / l.rolling(10).min() - 1 >= 0.05) & (vr >= 1.5)
                                                 & (c < sma20))

    sg = pd.DataFrame({"s_" + n: s.fillna(False).astype(bool) for n, s in S.items()}, index=x.index)
    return pd.concat([f, sg], axis=1)


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
            if len(x) < 250:
                continue
            x.index = norm(x.index)
            f = ozellik(x)
            f["h"] = t[:-3]
            frames.append(f)
        except Exception as e:
            print("hisse hata", t, e)
            continue

A0 = pd.concat(frames)
A = A0[A0.lik & A0.y.notna() & A0.r1.notna() & (A0.chg < 7)].copy()
names = [c[2:] for c in A.columns if c.startswith("s_")]
M = {n: A["s_" + n].values for n in names}
y = A.y.values
r1 = A.r1.values
r3 = A.r3.values
dates = np.sort(A.index.unique())
cut = dates[int(len(dates) * 0.6)]
trm = np.asarray(A.index < cut)


def mean(arr, m):
    z = arr[m]
    z = z[np.isfinite(z)]
    return z.mean() if len(z) else np.nan


def ozet(m):
    a, b = m & trm, m & ~trm
    n = int(m.sum())
    return dict(
        n=n, na=int(a.sum()), nb=int(b.sum()),
        ty=y[m].mean() * 100 if n else np.nan,
        ta=y[a].mean() * 100 if a.any() else np.nan,
        tb=y[b].mean() * 100 if b.any() else np.nan,
        ea=int(y[a].sum()), eb=int(y[b].sum()),
        r1=mean(r1, m), r1a=mean(r1, a), r1b=mean(r1, b),
        r3=mean(r3, m), r3a=mean(r3, a), r3b=mean(r3, b))


def fm(v, d=1, s=False):
    if v is None or pd.isna(v):
        return "-"
    return f"{v:+.{d}f}" if s else f"{v:.{d}f}"


base = ozet(np.ones(len(A), bool))
ba, bb = base["ta"], base["tb"]
R = {n: ozet(M[n]) for n in names}

out = []
P = out.append
P("BIST İNDİKATÖR + FORMASYON TESTİ")
P(f"Dönem: {A.index.min():%d.%m.%Y} - {A.index.max():%d.%m.%Y} · hisse: {A.h.nunique()} · "
  f"örnek: {len(A)} · sinyal: {len(names)}")
P(f"Eğitim: {A.index.min():%d.%m.%Y}-{cut:%d.%m.%Y} · test: sonrası")
P("Sadece o gün %7'den az yükselen, likit hisseler. Sinyal gün sonunda bilinir.")
P("Giriş: ertesi gün açılış. Net getiri %0,3 maliyet düşülmüş.")
P("kat = ertesi gün tavan oranı / taban oran. eğ = eğitim, test = test dönemi")
P("UYARI: ~70 sinyal denendi, tesadüfen iyi görünen çıkar. Eğitim VE testte tutana bak.")
P("")
P(f"TABAN: tavan %{fm(base['ty'], 2)} (eğ %{fm(ba, 2)}, test %{fm(bb, 2)}) · "
  f"net 1g {fm(base['r1'], 2, True)}% (eğ {fm(base['r1a'], 2, True)}, test {fm(base['r1b'], 2, True)}) · "
  f"net 3g {fm(base['r3'], 2, True)}%")


def blok(n, r):
    P(f"{n}")
    P(f"   n={r['n']} · tavan %{fm(r['ty'])} ({fm(r['ty'] / base['ty'])}x) · "
      f"eğ {fm(r['ta'] / ba)}x · test {fm(r['tb'] / bb)}x")
    P(f"   1g net {fm(r['r1'], 2, True)}% (eğ {fm(r['r1a'], 2, True)} test {fm(r['r1b'], 2, True)})"
      f" · 3g net {fm(r['r3'], 2, True)}%")


P("")
P("=== 1) TAVAN İHTİMALİNİ EN ÇOK ARTIRANLAR (eğitim ve testte ikisinde) ===")
ok = [(n, r) for n, r in R.items() if r["n"] >= 200 and r["ea"] >= 15 and r["eb"] >= 10]
ok.sort(key=lambda t: -min(t[1]["ta"] / ba, t[1]["tb"] / bb))
for n, r in ok[:15]:
    blok(n, r)

P("")
P("=== 2) ERTESİ GÜN NET GETİRİ EN İYİLER (✔ = eğitim ve test ikisi de pozitif) ===")
okn = [(n, r) for n, r in R.items() if r["n"] >= 200 and not pd.isna(r["r1"])]
okn.sort(key=lambda t: -t[1]["r1"])
for n, r in okn[:12]:
    blok(("✔ " if r["r1a"] > 0 and r["r1b"] > 0 else "") + n, r)
poz = sum(1 for n, r in okn if r["r1a"] > 0 and r["r1b"] > 0)
P(f"Eğitim+test ikisi de net pozitif: {poz} / {len(okn)} sinyal (tesadüfle ~{len(okn) // 4} beklenir)")

P("")
P("=== 3) 3 GÜNLÜK NET GETİRİ EN İYİLER ===")
ok3 = [(n, r) for n, r in R.items() if r["n"] >= 200 and not pd.isna(r["r3a"]) and not pd.isna(r["r3b"])]
ok3.sort(key=lambda t: -t[1]["r3"])
for n, r in ok3[:8]:
    blok(("✔ " if r["r3a"] > 0 and r["r3b"] > 0 else "") + n, r)

P("")
P("=== 4) İKİLİ KOMBİNASYONLAR: TAVAN İHTİMALİ ===")
big = [n for n in names if R[n]["n"] >= 200]
pairs = []
for a, b in itertools.combinations(big, 2):
    m = M[a] & M[b]
    if m.sum() < 150:
        continue
    pairs.append((a + " + " + b, ozet(m)))
P(f"Denenen kombinasyon: {len(pairs)}")
pl = [(n, r) for n, r in pairs if r["ea"] >= 12 and r["eb"] >= 8]
pl.sort(key=lambda t: -min(t[1]["ta"] / ba, t[1]["tb"] / bb))
for n, r in pl[:10]:
    blok(n, r)

P("")
P("=== 5) İKİLİ KOMBİNASYONLAR: NET GETİRİ (eğitim+test pozitif) ===")
pp = [(n, r) for n, r in pairs if r["r1a"] > 0 and r["r1b"] > 0]
pp.sort(key=lambda t: -min(t[1]["r1a"], t[1]["r1b"]))
if not pp:
    P("Eğitim ve testte ikisinde de net pozitif kombinasyon çıkmadı.")
for n, r in pp[:10]:
    blok(n, r)
P(f"Pozitif çıkan: {len(pp)} / {len(pairs)} (tesadüfle ~{len(pairs) // 4} beklenir)")

az = [n for n in names if R[n]["n"] < 200]
if az:
    P("")
    P("Yetersiz örnek (n<200), değerlendirilmedi: " + ", ".join(az))

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>İndikatör testi</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto;white-space:pre-wrap}</style></head><body><pre>"
        + H.escape(text) + "</pre></body></html>")
open("docs/indikator.html", "w", encoding="utf-8").write(page)
