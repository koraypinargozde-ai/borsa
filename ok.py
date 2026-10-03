import yfinance as yf, pandas as pd, numpy as np
import re, os
import html as H

PERIOD = "2y"
MALIYET = 0.3
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
    f["rs"] = f["chg"] - xuchg.reindex(x.index).fillna(0)
    tv = (f["chg"] >= 9.4) & (c >= h * 0.995)
    f["tv"] = tv
    f["tv10"] = tv.astype(float).shift(1).rolling(10).sum()
    s = tv.astype(int)
    grp = (s != s.shift()).cumsum()
    f["run"] = s.groupby(grp).cumsum() * s
    # ▲ = bugunku hacim son 20 gunun en yuksegi
    up = v >= v.shift(1).rolling(19).max()
    f["up"] = up
    f["up1"] = up.shift(1)
    f["up2"] = up.shift(2)
    f["n_gap"] = (o.shift(-1) / c - 1) * 100
    f["n_oc"] = (c.shift(-1) / o.shift(-1) - 1) * 100
    f["n_oh"] = (h.shift(-1) / o.shift(-1) - 1) * 100
    f["n_tv"] = tv.astype(float).shift(-1)
    f["g3o"] = (c.shift(-3) / o.shift(-1) - 1) * 100
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
for k in ("tv", "up", "up1", "up2"):
    A0[k] = A0[k].fillna(False).astype(bool)

gunler = A0.index.unique().sort_values()
CUT = gunler[int(len(gunler) * 0.6)]

L = A0[A0.lik].dropna(subset=["chg", "vr", "n_oc", "n_tv"])
N = L[~L.tv]
U = L[L.up]
B = L[L.up & ~L.tv]


def fm(v, d=2):
    return "-" if v is None or pd.isna(v) else f"{v:.{d}f}"


out = []
P = out.append
P("BIST ▲ TESTİ (20 günün en yüksek hacmi)")
P(f"Dönem: {A0.index.min():%d.%m.%Y} - {A0.index.max():%d.%m.%Y} · hisse: {A0.h.nunique()}")
P(f"Eğitim: {A0.index.min():%d.%m.%Y} - {CUT:%d.%m.%Y} · Test: sonrası")
P(f"Likit gün-hisse: {len(L)} · ▲ olan: {len(U)} (%{fm(len(U) / len(L) * 100, 1)})")
P("▲ = günün hacmi son 20 günün en yükseği. Tavan = değişim ≥%9.4 ve kapanış zirvede.")
P(f"Giriş ertesi açılış, çıkış ertesi kapanış (a→k) veya 3 gün sonra kapanış (3g). Maliyet %{MALIYET} düşüldü (net).")

P("")
P("=== BÖLÜM 1: ▲ ve TAVAN ===")
P(f"Normal gün tavan oranı: %{fm(L.tv.mean() * 100)}")
P(f"▲ günü aynı gün tavan oranı: %{fm(U.tv.mean() * 100)}  (n={len(U)})")
P(f"▲ olup bugün tavan olmayanın ERTESİ gün tavan oranı: %{fm(B.n_tv.mean() * 100)}  (n={len(B)})")
P(f"Normal gün (tavan olmayan) ertesi gün tavan oranı: %{fm(N.n_tv.mean() * 100)}")

E = A0[A0.tv & A0.lik & (A0.run == 1)].dropna(subset=["up", "up1"])
P("")
P(f"İlk tavan olayı: {len(E)}")
P(f"  tavan günü ▲ vardı: %{fm(E.up.mean() * 100, 1)}")
P(f"  tavandan 1 gün önce ▲ vardı: %{fm(E.up1.mean() * 100, 1)}  (normal gün: %{fm(L.up.mean() * 100, 1)})")
P(f"  tavandan 2 gün önce ▲ vardı: %{fm(E.up2.mean() * 100, 1)}")
P(f"  t-1 veya t-2 ▲ vardı: %{fm((E.up1 | E.up2).mean() * 100, 1)}")

P("")
P("=== BÖLÜM 2: ▲ SONRASI GETİRİ (tavan olmayan ▲ günleri) ===")
P("tv = ertesi gün tavan % · a→k = ertesi açılıştan kapanışa net %")
P("zirve = ertesi açılıştan zirveye % · 3g = ertesi açılıştan 3 gün sonra kapanışa net %")
P("eğ / test = a→k net, eğitim ve test döneminde")
P(f"{'grup':<22}{'n':>6}{'tv%':>6}{'a→k':>7}{'zirve':>7}{'3g':>7}{'eğ':>7}{'test':>7}")


def satir(ad, df, m=None):
    s = df if m is None else df[m]
    if len(s) < 15:
        return
    tr = s[s.index <= CUT]
    te = s[s.index > CUT]
    P(f"{ad:<22}{len(s):>6}{fm(s.n_tv.mean() * 100, 1):>6}"
      f"{fm(s.n_oc.mean() - MALIYET):>7}{fm(s.n_oh.mean()):>7}"
      f"{fm(s.g3o.mean() - MALIYET):>7}"
      f"{fm(tr.n_oc.mean() - MALIYET):>7}{fm(te.n_oc.mean() - MALIYET):>7}")


satir("normal gün (taban)", N)
satir("▲ tümü", B)
satir("▲ değ <0", B, B.chg < 0)
satir("▲ değ 0-3%", B, (B.chg >= 0) & (B.chg < 3))
satir("▲ değ 3-7%", B, (B.chg >= 3) & (B.chg < 7))
satir("▲ değ 7%+", B, B.chg >= 7)
satir("▲ kapanış güç ≥70", B, B.pos >= 70)
satir("▲ kapanış güç <40", B, B.pos < 40)
satir("▲ hacim ≥3x", B, B.vr >= 3)
satir("▲ hacim ≥5x", B, B.vr >= 5)
satir("▲ hacim ≥10x", B, B.vr >= 10)
satir("▲ son10g tavan var", B, B.tv10 >= 1)
satir("▲ son10g tavan yok", B, B.tv10 == 0)
satir("▲ endeksten güçlü", B, B.rs > 1)
satir("▲ endeksten zayıf", B, B.rs < -1)
satir("▲ 0-7% + güç≥70", B, (B.chg >= 0) & (B.chg < 7) & (B.pos >= 70))
satir("▲ 0-7% güç≥70 3x+", B, (B.chg >= 0) & (B.chg < 7) & (B.pos >= 70) & (B.vr >= 3))
satir("▲ 3-7% güç≥70 3x+", B, (B.chg >= 3) & (B.chg < 7) & (B.pos >= 70) & (B.vr >= 3))

P("")
P("=== BÖLÜM 3: ▲ SERİSİ ===")
P("Art arda ▲ gelen hisse (dün de ▲ vardı) vs ilk ▲")
satir("ilk ▲ (dün yok)", B, ~B.up1)
satir("ardışık ▲ (dün de var)", B, B.up1)

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>▲ testi</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/ok.html", "w", encoding="utf-8").write(page)
