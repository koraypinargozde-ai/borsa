import yfinance as yf, pandas as pd, numpy as np
import re, os
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
    c, o, h, l, v = x["Close"], x["Open"], x["High"], x["Low"], x["Volume"]
    f = pd.DataFrame(index=x.index)
    f["chg"] = c.pct_change() * 100
    av = v.shift(1).rolling(20).mean()
    f["vr"] = v / av
    f["lik"] = (av * c) >= 2_000_000
    f["pos"] = ((c - l) / (h - l).replace(0, np.nan)).fillna(0.5) * 100
    f["ret5"] = (c / c.shift(5) - 1) * 100
    f["yak20"] = (c / h.shift(1).rolling(20).max() - 1) * 100
    f["rs"] = f["chg"] - xuchg.reindex(x.index).fillna(0)
    f["gap"] = (o / c.shift(1) - 1) * 100
    f["oh"] = (h / o - 1) * 100
    tv = (f["chg"] >= 9.4) & (c >= h * 0.995)
    f["tv"] = tv
    f["tv10"] = tv.astype(float).shift(1).rolling(10).sum()
    s = tv.astype(int)
    grp = (s != s.shift()).cumsum()
    f["run"] = s.groupby(grp).cumsum() * s
    f["len"] = s.groupby(grp).transform("sum") * s
    for k in (1, 2, 3):
        for col in ("chg", "vr", "pos", "ret5", "yak20", "rs"):
            f[f"{col}{k}"] = f[col].shift(k)
    f["n_gap"] = (o.shift(-1) / c - 1) * 100
    f["n_oc"] = (c.shift(-1) / o.shift(-1) - 1) * 100
    f["n_chg"] = (c.shift(-1) / c - 1) * 100
    f["n_hi"] = (h.shift(-1) / c - 1) * 100
    f["n_tv"] = tv.astype(float).shift(-1)
    f["g3"] = (c.shift(-3) / c - 1) * 100
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
A0["tv"] = A0["tv"].astype(bool)
E = A0[A0.tv & A0.lik & (A0.run == 1)].dropna(subset=["chg1", "vr1"])
N = A0[A0.lik & ~A0.tv].dropna(subset=["chg", "vr"])


def fm(v, d=1):
    return "-" if v is None or pd.isna(v) else f"{v:.{d}f}"


def med(s):
    s = s.dropna()
    return s.median() if len(s) else np.nan


def pay(s, cond):
    s = s.dropna()
    return cond(s).mean() * 100 if len(s) else np.nan


out = []
P = out.append
P("BIST TAVAN ANALİZİ")
P(f"Dönem: {A0.index.min():%d.%m.%Y} - {A0.index.max():%d.%m.%Y} · hisse: {A0.h.nunique()}")
P(f"İlk tavan olayı (serinin ilk günü): {len(E)} · normal gün-hisse: {len(N)}")
P("Tavan = gün değişimi ≥%9.4 ve kapanış günün zirvesinde. Likit hisseler (günlük işlem ≥2 milyon TL).")

P("")
P("=== BÖLÜM 1: TAVAN ÖNCESİ (medyan) ===")
P("t-1 = tavandan 1 gün önce, t-2 = 2 gün önce, t-3 = 3 gün önce")
P(f"{'özellik':<18}{'t-3':>8}{'t-2':>8}{'t-1':>8}{'normal':>8}")
for ad, col in [("değişim %", "chg"), ("hacim x", "vr"), ("kapanış gücü", "pos"),
                ("5g getiri %", "ret5"), ("20g zirveye %", "yak20"), ("endeksten fark", "rs")]:
    v3, v2, v1 = (med(E[f"{col}{k}"]) for k in (3, 2, 1))
    P(f"{ad:<18}{fm(v3):>8}{fm(v2):>8}{fm(v1):>8}{fm(med(N[col])):>8}")

P("")
P("Pay (%): tavan öncesi t-1 günü vs normal gün")
P(f"{'durum':<22}{'t-1':>8}{'normal':>8}")
for ad, col, fn in [
    ("hacim ≥2x", "vr", lambda s: s >= 2),
    ("hacim ≥4x", "vr", lambda s: s >= 4),
    ("değişim <3%", "chg", lambda s: s < 3),
    ("değişim ≥7%", "chg", lambda s: s >= 7),
    ("kapanış gücü ≥70", "pos", lambda s: s >= 70),
    ("20g zirveyi kırdı", "yak20", lambda s: s > 0),
    ("endeksten güçlü", "rs", lambda s: s > 1),
]:
    P(f"{ad:<22}{fm(pay(E[col + '1'], fn)):>8}{fm(pay(N[col], fn)):>8}")
P(f"{'son 10g tavan var':<22}{fm((E.tv10 >= 1).mean() * 100):>8}{fm((N.tv10 >= 1).mean() * 100):>8}")

P("")
P("Tavan günü açılış (alınabilir mi?)")
P(f"açılışta tavan (gap≥9%): %{fm((E.gap >= 9).mean() * 100)} → alınamaz")
P(f"gap 3-9%: %{fm(((E.gap >= 3) & (E.gap < 9)).mean() * 100)}")
P(f"gap <3% (gün içi tavan): %{fm((E.gap < 3).mean() * 100)}")
P(f"açılıştan zirveye medyan: %{fm(med(E.oh))}")

P("")
P("=== BÖLÜM 2: TAVAN SONRASI ===")
S = E.dropna(subset=["n_chg"])
L = S["len"]
P(f"Seri uzunluğu (ilk tavanlardan): 1 gün %{fm((L == 1).mean() * 100)} · "
  f"2 gün %{fm((L == 2).mean() * 100)} · 3 gün %{fm((L == 3).mean() * 100)} · "
  f"4+ gün %{fm((L >= 4).mean() * 100)}")
P("devam = ertesi gün de tavan · açılış = ertesi gün açılış farkı")
P("a→k = ertesi gün açılıştan kapanışa · kap = tavan kapanışından ertesi kapanışa")
P("zirve = ertesi gün en yüksek · 3g = tavan kapanışından 3 gün sonra")
P(f"{'grup':<18}{'n':>5}{'devam':>7}{'açılış':>7}{'a→k':>6}{'kap':>6}{'zirve':>7}{'3g':>6}")


def satir(ad, m):
    s = S[m]
    if len(s) < 15:
        return
    P(f"{ad:<18}{len(s):>5}{fm(s.n_tv.mean() * 100, 0):>6}%{fm(s.n_gap.mean()):>7}"
      f"{fm(s.n_oc.mean()):>6}{fm(s.n_chg.mean()):>6}{fm(s.n_hi.mean()):>7}{fm(s.g3.mean()):>6}")


satir("tümü", S.n_chg.notna())
satir("açılışta tavan", S.gap >= 9)
satir("gün içi tavan", S.gap < 5)
satir("hacim <2x", S.vr < 2)
satir("hacim 2-5x", (S.vr >= 2) & (S.vr < 5))
satir("hacim 5x+", S.vr >= 5)
satir("t-1 hacim ≥2x", S.vr1 >= 2)
satir("t-1 hacim <2x", S.vr1 < 2)
satir("t-1 değişim <3%", S.chg1 < 3)
satir("son10g tavan var", S.tv10 >= 1)
satir("son10g tavan yok", S.tv10 == 0)

P("")
P("=== INFO: TAVAN ÖNCESİ ===")
ib = A0[(A0.h == "INFO") & A0.tv & (A0.run == 1)]
if len(ib) == 0:
    P("INFO için dönemde tavan olayı bulunamadı.")
for ix, r in ib.iterrows():
    P(f"{ix:%d.%m.%Y} tavan (gap {fm(r.gap)}%, hacim {fm(r.vr)}x)")
    P(f"  t-1: değ {fm(r.chg1)}% hacim {fm(r.vr1)}x kapanış {fm(r.pos1, 0)}")
    P(f"  t-2: değ {fm(r.chg2)}% hacim {fm(r.vr2)}x kapanış {fm(r.pos2, 0)}")
    P(f"  t-3: değ {fm(r.chg3)}% hacim {fm(r.vr3)}x kapanış {fm(r.pos3, 0)}")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Tavan analizi</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/tavan.html", "w", encoding="utf-8").write(page)
