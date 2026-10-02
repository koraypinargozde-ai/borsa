import yfinance as yf, pandas as pd, numpy as np
import re, os
import html as HT

np.seterr(all="ignore")
PERIOD = "1y"
COST = 0.3  # alış+satış toplam komisyon/kayma payı, yüzde
KS = (1, 2)
src = open("scan.py", encoding="utf-8").read()
T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
tick = [t + ".IS" for t in dict.fromkeys(T)]


def hazir(x):
    x = x.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    if x.index.tz is not None:
        x.index = x.index.tz_convert("Europe/Istanbul").tz_localize(None)
    dt = x.index.normalize()
    x = x.assign(dt=dt, n=x.groupby(dt).cumcount().values + 1)
    return x[x.n <= 10]


def pivotla(x, col):
    return x.pivot(index="dt", columns="n", values=col).reindex(columns=range(1, 11))


def stok(x):
    if len(x.dropna(subset=["Close"])) < 200:
        return None
    x = hazir(x)
    O, H, L, C, V = [pivotla(x, c) for c in ("Open", "High", "Low", "Close", "Volume")]
    nb = C.notna().sum(axis=1)
    ok = nb >= 6
    dc = C.ffill(axis=1).iloc[:, -1]
    pc = dc.shift(1)
    dv = V.sum(axis=1)
    av = dv.shift(1).rolling(20).mean()
    lik = (av * dc) >= 2_000_000
    cv = V.fillna(0).cumsum(axis=1)
    dh = H.max(axis=1)
    tavan = ((dc / pc - 1) * 100 >= 9.4) & (dc >= dh * 0.995)
    rows = []
    for k in KS:
        avk = cv[k].shift(1).rolling(20).mean()
        vr = cv[k] / avk
        ck = C[k]
        chg = (ck / pc - 1) * 100
        hk = H[list(range(1, k + 1))].max(axis=1)
        ent = O[k + 1]
        entv = ent.values
        dcv = dc.values
        sp = entv * 0.98
        tg = entv * 1.03
        o_k = (dcv / entv - 1) * 100
        o_i = o_k.copy()
        r_kap = o_k.copy()
        d1 = np.zeros(len(entv), bool)
        d2 = np.zeros(len(entv), bool)
        for j in range(k + 1, 11):
            lo = L[j].values
            hi = H[j].values
            m = ~d1 & (lo <= sp)
            o_k[m] = -2
            d1 |= m
            m = ~d1 & (hi >= tg)
            o_k[m] = 3
            d1 |= m
            m = ~d2 & (hi >= tg)
            o_i[m] = 3
            d2 |= m
            m = ~d2 & (lo <= sp)
            o_i[m] = -2
            d2 |= m
        f = pd.DataFrame({"k": k, "vr": vr, "chg": chg, "yak": ck / hk,
                          "ech": (ent / pc - 1) * 100, "tavan": tavan.astype(float),
                          "r_kap": r_kap - COST, "r_32": o_k - COST,
                          "r_32i": o_i - COST}, index=C.index)
        f = f[ok & lik].replace([np.inf, -np.inf], np.nan).dropna()
        rows.append(f)
    return pd.concat(rows)


def endeks():
    xi = yf.download("XU100.IS", period=PERIOD, interval="1h",
                     progress=False, auto_adjust=False)
    if xi.columns.nlevels > 1:
        xi.columns = xi.columns.get_level_values(0)
    xi = hazir(xi)
    C = pivotla(xi, "Close")
    dc = C.ffill(axis=1).iloc[:, -1]
    pc = dc.shift(1)
    sma = dc.rolling(20).mean()
    R = pd.DataFrame({"trend": np.sign(dc.shift(1) - sma.shift(1))})
    for k in KS:
        R[f"i{k}"] = (C[k] / pc - 1) * 100
    print("endeks günlük mum sayısı ort:", round(xi.groupby("dt").size().mean(), 1))
    return R


R = endeks()
frames = []
for i in range(0, len(tick), 30):
    grup = tick[i:i + 30]
    try:
        d = yf.download(grup, period=PERIOD, interval="1h", group_by="ticker",
                        progress=False, threads=True, auto_adjust=False)
    except Exception as e:
        print("hata", e)
        continue
    for t in grup:
        try:
            r = stok(d[t].copy())
            if r is not None and len(r):
                frames.append(r)
        except Exception:
            continue

print(len(frames), "hisse işlendi")
if not frames:
    raise SystemExit("veri yok")

U = pd.concat(frames)
U = U[(U.chg < 9) & (U.ech < 9.3)]
idx = np.full(len(U), np.nan)
for k in KS:
    mk = (U.k == k).values
    idx[mk] = R[f"i{k}"].reindex(U.index[mk]).values
U["idx"] = idx
U["trend"] = R["trend"].reindex(U.index).values
U = U.dropna(subset=["idx", "trend"])
dates = sorted(U.index.unique())
cut = dates[int(len(dates) * 0.7)]

SIG = [
    ("TÜMÜ (rastgele alış)", lambda d: d.vr >= 0),
    ("hacim 3x+ & +1..+6%", lambda d: (d.vr >= 3) & d.chg.between(1, 6)),
    ("hacim 3x+ & +1..+6% & zirvede",
     lambda d: (d.vr >= 3) & d.chg.between(1, 6) & (d.yak >= 0.995)),
    ("hacim 5x+ & +1..+6%", lambda d: (d.vr >= 5) & d.chg.between(1, 6)),
]
REJ = [
    ("hepsi", lambda d: d.vr >= 0),
    ("gün↑", lambda d: d.idx > 0),
    ("gün↓", lambda d: d.idx <= 0),
    ("trend↑", lambda d: d.trend > 0),
    ("trend↓", lambda d: d.trend < 0),
]

out = []
P = out.append
P("BIST REJİM TESTİ (saatlik giriş)")
P(f"Dönem: {dates[0]:%d.%m.%Y} - {dates[-1]:%d.%m.%Y}")
P("Giriş: sinyal mumundan sonraki mumun AÇILIŞI.")
P("gün↑/↓ = sinyal anında BIST100 dünkü kapanışa")
P("göre artıda/ekside. trend↑/↓ = dünkü BIST100")
P("kapanışı 20 günlük ortalamanın üstünde/altında.")
P("kap = gün sonu kapanışta sat, k-test = aynısı")
P("son %30 dönemde. 3/2k = +3/-2 çıkış kötümser")
P("(stop önce), 3/2i = iyimser (hedef önce).")
P("Gerçek sonuç 3/2k ile 3/2i arasındadır.")
P(f"Komisyon+kayma %{COST} düşüldü. Değerler net %.")
P("Küçük örnekli satırlara (n<150) güvenme.")

for ad, fn in SIG:
    for k in KS:
        d = U[U.k == k]
        S0 = d[fn(d)]
        P("")
        P(f"=== {ad} · ilk {k} saat ===")
        if len(S0) < 30:
            P(f"örnek az ({len(S0)})")
            continue
        P(f"n {len(S0)} · tavan %{S0.tavan.mean() * 100:.1f} (taban %{d.tavan.mean() * 100:.1f})")
        P(f"{'rejim':<8}{'n':>6}{'kap':>7}{'k-test':>7}{'3/2k':>7}{'3/2i':>7}")
        for rn, rf in REJ:
            S = S0[rf(S0)]
            if len(S) < 20:
                P(f"{rn:<8}{len(S):>6}  az örnek")
                continue
            te = np.asarray(S.index >= cut)
            kt = S.r_kap.values[te].mean() if te.any() else float("nan")
            P(f"{rn:<8}{len(S):>6}{S.r_kap.mean():>+7.2f}{kt:>+7.2f}{S.r_32.mean():>+7.2f}{S.r_32i.mean():>+7.2f}")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Rejim testi</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{white-space:pre-wrap}</style></head><body><pre>" + HT.escape(text) + "</pre></body></html>")
open("docs/rejim.html", "w", encoding="utf-8").write(page)
