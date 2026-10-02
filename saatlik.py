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


def stok(x):
    x = x.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    if len(x) < 200:
        return None
    if x.index.tz is not None:
        x.index = x.index.tz_convert("Europe/Istanbul").tz_localize(None)
    dt = x.index.normalize()
    x = x.assign(dt=dt, n=x.groupby(dt).cumcount().values + 1)
    x = x[x.n <= 10]

    def pv(col):
        return x.pivot(index="dt", columns="n", values=col).reindex(columns=range(1, 11))

    O, H, L, C, V = pv("Open"), pv("High"), pv("Low"), pv("Close"), pv("Volume")
    nb = C.notna().sum(axis=1)
    ok = nb >= 6
    dc = C.ffill(axis=1).iloc[:, -1]
    pc = dc.shift(1)
    dv = V.sum(axis=1)
    av = dv.shift(1).rolling(20).mean()
    lik = (av * dc) >= 2_000_000
    cv = V.fillna(0).cumsum(axis=1)
    nd = dc.shift(-1)
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
        res = {}
        res["r_kap"] = (dcv / entv - 1) * 100
        for nm, X, Y in (("r_32", 3, 2), ("r_53", 5, 3)):
            sp = entv * (1 - Y / 100)
            tg = entv * (1 + X / 100)
            out = (dcv / entv - 1) * 100
            done = np.zeros(len(entv), bool)
            for j in range(k + 1, 11):
                lo = L[j].values
                hi = H[j].values
                m = ~done & (lo <= sp)
                out[m] = -Y
                done |= m
                m = ~done & (hi >= tg)
                out[m] = X
                done |= m
            res[nm] = out
        f = pd.DataFrame({"k": k, "vr": vr, "chg": chg, "yak": ck / hk,
                          "ech": (ent / pc - 1) * 100, "tavan": tavan.astype(float),
                          "r_kap": res["r_kap"] - COST,
                          "r_32": res["r_32"] - COST,
                          "r_53": res["r_53"] - COST,
                          "r_ert": (nd / ent - 1) * 100 - COST}, index=C.index)
        f = f[ok & lik].replace([np.inf, -np.inf], np.nan).dropna()
        rows.append(f)
    return pd.concat(rows)


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
dates = sorted(U.index.unique())
cut = dates[int(len(dates) * 0.7)]

SIG = [
    ("TÜMÜ (rastgele alış)", lambda d: d.vr >= 0),
    ("hacim 3x+ & +1..+6%", lambda d: (d.vr >= 3) & d.chg.between(1, 6)),
    ("hacim 5x+ & +1..+6%", lambda d: (d.vr >= 5) & d.chg.between(1, 6)),
    ("hacim 3x+ & +1..+6% & zirvede",
     lambda d: (d.vr >= 3) & d.chg.between(1, 6) & (d.yak >= 0.995)),
    ("hacim 3x+ & 0..+3% (erken)", lambda d: (d.vr >= 3) & d.chg.between(0, 3)),
]
EXITS = [("kapanış", "r_kap"), ("+3/-2", "r_32"), ("+5/-3", "r_53"), ("ertesi gün", "r_ert")]

out = []
P = out.append
P("BIST GÜN İÇİ GİRİŞ TESTİ (saatlik mum)")
P(f"Dönem: {dates[0]:%d.%m.%Y} - {dates[-1]:%d.%m.%Y}")
P("Sinyal: ilk 1 ya da 2 saatlik mum bitince.")
P("Giriş: bir sonraki mumun AÇILIŞ fiyatı.")
P("hacim 3x = o ana kadarki hacim, son 20 günün")
P("aynı saatine göre 3 kat.")
P("Çıkış: gün sonu kapanış / hedef-stop /")
P("ertesi gün kapanış. Hedef ve stop aynı mumda")
P("gelirse STOP sayıldı.")
P("Zaten tavana yakın (%9+) olanlar hariç.")
P(f"Komisyon+kayma %{COST} düşüldü. ort = net getiri %")
P("eğit/test = ilk %70 / son %30 dönem ortalaması")

for ad, fn in SIG:
    for k in KS:
        d = U[U.k == k]
        S = d[fn(d)]
        P("")
        P(f"=== {ad} · ilk {k} saatlik mum ===")
        if len(S) < 30:
            P(f"örnek az ({len(S)})")
            continue
        P(f"n {len(S)} · gün sonu tavan %{S.tavan.mean() * 100:.1f} (taban %{d.tavan.mean() * 100:.1f})")
        P(f"{'strateji':<11}{'isab':>6}{'ort':>7}{'eğit':>7}{'test':>7}")
        tr = np.asarray(S.index < cut)
        for en, col in EXITS:
            r = S[col].values
            a, b = r[tr], r[~tr]
            ea = a.mean() if len(a) else float("nan")
            eb = b.mean() if len(b) else float("nan")
            P(f"{en:<11}{(r > 0).mean() * 100:>5.0f}%{r.mean():>+7.2f}{ea:>+7.2f}{eb:>+7.2f}")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Saatlik test</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{white-space:pre-wrap}</style></head><body><pre>" + HT.escape(text) + "</pre></body></html>")
open("docs/saatlik.html", "w", encoding="utf-8").write(page)
