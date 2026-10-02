import yfinance as yf, pandas as pd, numpy as np
import re, os, warnings
import html as H

warnings.filterwarnings("ignore")
COST = 0.3
src = open("scan.py", encoding="utf-8").read()
T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
tick = [t + ".IS" for t in dict.fromkeys(T)]


def isle(x):
    ix = x.index
    if ix.tz is None:
        ix = ix.tz_localize("UTC")
    ix = ix.tz_convert("Europe/Istanbul")
    x = x[["Open", "High", "Low", "Close", "Volume"]].copy()
    x.index = ix
    x = x.dropna()
    x = x[x["Volume"] >= 0]
    if len(x) < 300:
        return None, None
    x["d"] = x.index.tz_localize(None).normalize()
    x["k"] = x.groupby("d").cumcount() + 1
    x["cv"] = x.groupby("d")["Volume"].cumsum()
    x["e"] = x.groupby("d")["Open"].shift(-1)
    dd = x.groupby("d").agg(open=("Open", "first"), high=("High", "max"),
                            close=("Close", "last"), vol=("Volume", "sum"),
                            n=("Close", "count"))
    dd = dd[dd["n"] >= 7].copy()
    if len(dd) < 60:
        return None, None
    dd["pc"] = dd["close"].shift(1)
    dd["chg"] = (dd["close"] / dd["pc"] - 1) * 100
    dd["vmax"] = dd["vol"].shift(1).rolling(20).max()
    dd["vmed"] = dd["vol"].shift(1).rolling(20).median()
    dd["lik"] = (dd["vmed"] * dd["close"]) >= 2_000_000
    dd["tv"] = ((dd["chg"] >= 9.4) & (dd["close"] >= dd["high"] * 0.995)).astype(float)
    dd["nopen"] = dd["open"].shift(-1)
    dd["nclose"] = dd["close"].shift(-1)
    dd["ntv"] = dd["tv"].shift(-1)
    dd["hzd"] = dd["vol"] / dd["vmax"]
    dd["art"] = (dd["vol"] > dd["vol"].shift(1)) & (dd["vol"].shift(1) > dd["vol"].shift(2))
    hf = []
    for K in (1, 2, 3):
        s = x[x["k"] == K].join(dd[["pc", "vmax", "vmed", "lik", "tv", "close", "nopen"]],
                                on="d", how="inner")
        o = pd.DataFrame({
            "d": s["d"].values, "K": K,
            "chgk": ((s["Close"] / s["pc"] - 1) * 100).values,
            "hz": (s["cv"] / s["vmax"]).values,
            "hm": (s["cv"] / s["vmed"]).values,
            "lik": s["lik"].values.astype(bool),
            "y": s["tv"].values,
            "rc": ((s["close"] / s["e"] - 1) * 100 - COST).values,
            "rn": ((s["nopen"] / s["e"] - 1) * 100 - COST).values})
        hf.append(o)
    dday = pd.DataFrame({
        "d": dd.index.values, "chg": dd["chg"].values, "hzd": dd["hzd"].values,
        "art": dd["art"].values.astype(bool), "lik": dd["lik"].values.astype(bool),
        "y": dd["ntv"].values,
        "rn": ((dd["nclose"] / dd["nopen"] - 1) * 100 - COST).values})
    return pd.concat(hf, ignore_index=True), dday


HF, DF = [], []
for i in range(0, len(tick), 50):
    grup = tick[i:i + 50]
    try:
        d = yf.download(grup, period="729d", interval="1h", group_by="ticker",
                        progress=False, threads=True, auto_adjust=False)
    except Exception as e:
        print("hata", e)
        continue
    for t in grup:
        try:
            x = d if len(grup) == 1 else d[t]
            if x.columns.nlevels > 1:
                x.columns = x.columns.get_level_values(0)
            a, b = isle(x.dropna(how="all"))
            if a is None:
                continue
            a["h"] = t[:-3]
            b["h"] = t[:-3]
            HF.append(a)
            DF.append(b)
        except Exception as e:
            print("hisse hata", t, e)
            continue

HH = pd.concat(HF, ignore_index=True)
HH = HH[HH["lik"] & HH["hz"].notna() & HH["rc"].notna() & (HH["chgk"] >= 0.5) & (HH["chgk"] <= 6)]
DD = pd.concat(DF, ignore_index=True)
DD = DD[DD["lik"] & DD["y"].notna() & DD["rn"].notna() & DD["hzd"].notna() & (DD["chg"] < 7)]
dates = np.sort(HH["d"].unique())
cut = pd.Timestamp(dates[int(len(dates) * 0.6)])


def mean(a, m):
    z = a[m]
    z = z[np.isfinite(z)]
    return z.mean() if len(z) else np.nan


def ozet(y, rc, rn, tr, m):
    a, b = m & tr, m & ~tr
    n = int(m.sum())
    return dict(
        n=n, ty=y[m].mean() * 100 if n else np.nan,
        ta=y[a].mean() * 100 if a.any() else np.nan,
        tb=y[b].mean() * 100 if b.any() else np.nan,
        ea=int(y[a].sum()), eb=int(y[b].sum()),
        cov=y[m].sum() / max(y.sum(), 1) * 100,
        rc=mean(rc, m), rca=mean(rc, a), rcb=mean(rc, b),
        rn=mean(rn, m), rna=mean(rn, a), rnb=mean(rn, b))


def fm(v, d=1, s=False):
    if v is None or pd.isna(v):
        return "-"
    return f"{v:+.{d}f}" if s else f"{v:.{d}f}"


out = []
P = out.append
P("BIST HACİM HIZI TESTİ (20 günün en yüksek hacmine gidiş)")
P(f"Saatlik veri: {HH['d'].min():%d.%m.%Y} - {HH['d'].max():%d.%m.%Y} · hisse: {HH['h'].nunique()}")
P(f"Eğitim: başlangıç-{cut:%d.%m.%Y} · test: sonrası")
P("Likit hisseler. Sinyal anında fiyat dünkü kapanışa göre +%0,5..+%6 (tavana gitmemiş).")
P("hacim oranı = o ana kadarki hacim / son 20 günün en yüksek günlük hacmi")
P("Giriş: sinyal saatinin ertesi saat açılışı. %0,3 maliyet düşülmüş.")
P("tavan = aynı gün tavan · kapsam = o saatte aralıkta olan tavanların kaçı sinyalde")
P("net kapanış = girişten gün kapanışına · net ertesi = girişten ertesi gün açılışına")
P("✔ = eğitim VE test ikisi de pozitif. Çok grup denendi, tesadüf mümkün.")

for K, saat in ((1, "11:00"), (2, "12:00"), (3, "13:00")):
    S = HH[HH["K"] == K].reset_index(drop=True)
    y, rc, rn = S["y"].values, S["rc"].values, S["rn"].values
    tr = np.asarray(S["d"] < cut)
    hz, hm, ch = S["hz"].values, S["hm"].values, S["chgk"].values
    gr = [("hepsi (taban)", np.ones(len(S), bool)),
          ("hacim ≥3x medyan", hm >= 3),
          ("hacim oranı ≥%15", hz >= 0.15),
          ("hacim oranı ≥%25", hz >= 0.25),
          ("hacim oranı ≥%40", hz >= 0.40),
          ("hacim oranı ≥%60", hz >= 0.60),
          ("hacim oranı ≥%80", hz >= 0.80),
          ("hacim zirveyi aştı (≥%100)", hz >= 1.0),
          ("hacim oranı ≥%40 + değişim 2-6%", (hz >= 0.40) & (ch >= 2)),
          ("hacim oranı ≥%25 + değişim 0.5-2%", (hz >= 0.25) & (ch < 2))]
    P("")
    P(f"=== SAAT {saat} İTİBARIYLA (giriş sonraki saat açılışı) ===")
    base = ozet(y, rc, rn, tr, gr[0][1])
    for ad, m in gr:
        r = ozet(y, rc, rn, tr, m)
        if r["n"] < 100:
            continue
        tag = ""
        if r["rca"] > 0 and r["rcb"] > 0:
            tag += " ✔kapanış"
        if r["rna"] > 0 and r["rnb"] > 0:
            tag += " ✔ertesi"
        P(ad + tag)
        P(f"   n={r['n']} · tavan %{fm(r['ty'])} ({fm(r['ty'] / base['ty'])}x) · "
          f"eğ {fm(r['ta'] / base['ta'])}x test {fm(r['tb'] / base['tb'])}x · kapsam %{fm(r['cov'])}")
        P(f"   net kapanış {fm(r['rc'], 2, True)}% (eğ {fm(r['rca'], 2, True)} test {fm(r['rcb'], 2, True)})"
          f" · net ertesi {fm(r['rn'], 2, True)}% (eğ {fm(r['rna'], 2, True)} test {fm(r['rnb'], 2, True)})")

S = DD.reset_index(drop=True)
y, rn = S["y"].values, S["rn"].values
tr = np.asarray(S["d"] < cut)
hzd, art = S["hzd"].values, S["art"].values
P("")
P("=== BİR GÜN ÖNCE: gün sonu hacmi / 20g zirve hacim, ertesi gün sonucu ===")
P("Giriş ertesi gün açılış, çıkış ertesi gün kapanış. Bugün %7'den az yükselenler.")
gr = [("hepsi (taban)", np.ones(len(S), bool)),
      ("hacim oranı ≥%50", hzd >= 0.5),
      ("hacim oranı ≥%70", hzd >= 0.7),
      ("hacim zirveyi aştı (≥%100)", hzd >= 1.0),
      ("2 gün üst üste hacim artışı", art),
      ("2 gün artış + oran ≥%50", art & (hzd >= 0.5)),
      ("2 gün artış + zirveyi aştı", art & (hzd >= 1.0))]
base = ozet(y, rn, rn, tr, gr[0][1])
for ad, m in gr:
    r = ozet(y, rn, rn, tr, m)
    if r["n"] < 100:
        continue
    tag = " ✔" if r["rna"] > 0 and r["rnb"] > 0 else ""
    P(ad + tag)
    P(f"   n={r['n']} · ertesi gün tavan %{fm(r['ty'], 2)} ({fm(r['ty'] / base['ty'])}x) · "
      f"eğ {fm(r['ta'] / base['ta'])}x test {fm(r['tb'] / base['tb'])}x · kapsam %{fm(r['cov'])}")
    P(f"   net ertesi gün {fm(r['rn'], 2, True)}% (eğ {fm(r['rna'], 2, True)} test {fm(r['rnb'], 2, True)})")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Hacim hızı testi</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto;white-space:pre-wrap}</style></head><body><pre>"
        + H.escape(text) + "</pre></body></html>")
open("docs/hizli.html", "w", encoding="utf-8").write(page)
