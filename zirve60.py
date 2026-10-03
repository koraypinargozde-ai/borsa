import yfinance as yf, pandas as pd, numpy as np
import re, os
import html as H

PERIOD = "3y"
COST = 0.3
src = open("scan.py", encoding="utf-8").read()
T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
tick = [t + ".IS" for t in dict.fromkeys(T)]


def norm(ix):
    return pd.to_datetime(ix).tz_localize(None).normalize()


def ozellik(x):
    c, o, h, l, v = x["Close"], x["Open"], x["High"], x["Low"], x["Volume"]
    f = pd.DataFrame(index=x.index)
    f["chg"] = c.pct_change() * 100
    av = v.shift(1).rolling(20).mean()
    f["vr"] = v / av
    f["lik"] = (av * c) >= 2_000_000
    f["yesil"] = c > o
    f["pos"] = ((c - l) / (h - l).replace(0, np.nan)).fillna(0.5) * 100
    tv = (f["chg"] >= 9.4) & (c >= h * 0.995)
    f["tv"] = tv
    tvi = tv.astype(int)
    f["ilk_tv"] = tv & (tvi.shift(1).fillna(0) == 0)
    for n in (20, 60, 120):
        m = (v >= v.shift(1).rolling(n).max()) & (v > 0)
        f[f"m{n}"] = m
        mi = m.astype(int)
        f[f"m{n}_1"] = mi.shift(1).fillna(0).astype(bool)
        f[f"m{n}_12"] = (mi.shift(1).fillna(0) + mi.shift(2).fillna(0)) > 0
        f[f"ilk{n}"] = m & (mi.shift(1).rolling(5).sum() == 0)
    f["r1"] = (c.shift(-1) / o.shift(-1) - 1) * 100 - COST
    f["r3"] = (c.shift(-3) / o.shift(-1) - 1) * 100 - COST
    f["n_tv"] = tvi.shift(-1)
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
            if len(x) < 150:
                continue
            x.index = norm(x.index)
            f = ozellik(x)
            f["h"] = t[:-3]
            frames.append(f)
        except Exception:
            continue

A = pd.concat(frames).replace([np.inf, -np.inf], np.nan)
bcols = ["lik", "yesil", "tv", "ilk_tv"] + [f"{p}{n}{s}" for n in (20, 60, 120)
                                              for p in ("m", "ilk") for s in ("",)] + \
        [f"m{n}_1" for n in (20, 60, 120)] + [f"m{n}_12" for n in (20, 60, 120)]
for col in bcols:
    A[col] = A[col].fillna(False).astype(bool)

# ön-tavan payı: ilk tavanların t-1 / t-2 günlerinde zirve hacim var mıydı
E = A[A.ilk_tv & A.lik]
N = A[A.lik & ~A.tv]

D = A[A.lik].dropna(subset=["r1", "r3", "n_tv", "chg", "pos"]).copy()
gunler = D.index.unique().sort_values()
cut = gunler[int(len(gunler) * 0.6)]
D["te"] = D.index >= cut
nt = ~D.tv  # sinyal günü tavan olmayan (tavan öncesi arıyoruz)


def fm(v, d=2):
    return "-" if v is None or pd.isna(v) else f"{v:.{d}f}"


out = []
P = out.append
P("SON 3 AY (60 GÜN) EN YÜKSEK HACİM TESTİ")
P(f"Dönem: {D.index.min():%d.%m.%Y} - {D.index.max():%d.%m.%Y} · hisse: {D.h.nunique()}")
P(f"Eğitim: {D.index.min():%d.%m.%Y} - {cut:%d.%m.%Y} · Test: sonrası")
P("Likit hisseler (günlük işlem ≥2 milyon TL).")
P("m20/m60/m120 = o günün hacmi son 20/60/120 günün en yüksek hacmi")
P("Sinyal günü kapanışta verilir, giriş ertesi gün açılış, maliyet %0.3, getiriler net.")
P("Sinyal günü tavan olan satırlar hariç (tavan öncesi aranıyor), 'tavan günü' satırı hariç.")
P("1g = o gün açılıştan kapanışa · 3g = açılıştan 3. gün kapanışa")
P("ok = eğitim ve test, 1g ve 3g hepsi pozitif")
P("")
P("=== BÖLÜM 1: İLK TAVANLARDAN ÖNCE ZİRVE HACİM VAR MIYDI? ===")
P(f"İlk tavan sayısı: {len(E)} · normal gün-hisse: {len(N)}")
P(f"{'durum':<26}{'tavan öncesi':>13}{'normal':>9}")
for ad, col in [("m20 t-1", "m20_1"), ("m60 t-1", "m60_1"), ("m120 t-1", "m120_1"),
                ("m20 t-1 veya t-2", "m20_12"), ("m60 t-1 veya t-2", "m60_12"),
                ("m120 t-1 veya t-2", "m120_12"), ("m60 tavan günü", "m60")]:
    P(f"{ad:<26}{fm(E[col].mean() * 100, 1):>12}%{fm(N[col].mean() * 100, 1):>8}%")

P("")
P("=== BÖLÜM 2: SİNYALDEN SONRA NE OLUYOR ===")
P(f"{'grup':<30}{'n':>6}{'tavan%':>7}{'1g':>7}{'eğ1':>7}{'test1':>7}{'3g':>7}{'eğ3':>7}{'test3':>7}{'ok':>4}")


def satir(ad, m):
    s = D[m]
    if len(s) < 15:
        P(f"{ad:<30}{len(s):>6}  (az örnek)")
        return
    tr, te = s[~s.te], s[s.te]
    e1, t1, e3, t3 = tr.r1.mean(), te.r1.mean(), tr.r3.mean(), te.r3.mean()
    ok = "+" if (e1 > 0 and t1 > 0 and e3 > 0 and t3 > 0) else ""
    P(f"{ad:<30}{len(s):>6}{fm(s.n_tv.mean() * 100, 1):>7}{fm(s.r1.mean()):>7}"
      f"{fm(e1):>7}{fm(t1):>7}{fm(s.r3.mean()):>7}{fm(e3):>7}{fm(t3):>7}{ok:>4}")


satir("tüm günler (rastgele)", nt)
satir("m20", nt & D.m20)
satir("m60", nt & D.m60)
satir("m120", nt & D.m120)
P("")
satir("m60 ilk (son 5g yok)", nt & D.ilk60)
satir("m60 + değ <3%", nt & D.m60 & (D.chg < 3))
satir("m60 + değ 0-7%", nt & D.m60 & (D.chg >= 0) & (D.chg < 7))
satir("m60 + değ 0-7% + güç≥70", nt & D.m60 & (D.chg >= 0) & (D.chg < 7) & (D.pos >= 70))
satir("m60 + yeşil + güç≥70", nt & D.m60 & D.yesil & (D.pos >= 70))
satir("m60 + hacim ≥3x", nt & D.m60 & (D.vr >= 3))
satir("m60 + hacim ≥5x", nt & D.m60 & (D.vr >= 5))
satir("m60 + hacim ≥5x + değ 0-7%", nt & D.m60 & (D.vr >= 5) & (D.chg >= 0) & (D.chg < 7))
satir("m60 ilk + değ 0-7% + güç≥70", nt & D.ilk60 & (D.chg >= 0) & (D.chg < 7) & (D.pos >= 70))
P("")
satir("m120 + değ 0-7% + güç≥70", nt & D.m120 & (D.chg >= 0) & (D.chg < 7) & (D.pos >= 70))
satir("m120 ilk (son 5g yok)", nt & D.ilk120)
P("")
P("Bilgi: sinyal günü tavan olan zirve hacimler (devam var mı?)")
satir("m60 tavan günü", D.tv & D.m60)
satir("m60 tavan günü + ilk tavan", D.ilk_tv & D.m60)
P("")
P("Okuma: Bölüm 1'de tavan öncesi payı normalden belirgin yüksekse zirve hacim erken işaret.")
P("Bölüm 2'de net getiri tabandan yüksek ve ok sütununda + varsa kenar var, yoksa yok.")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Zirve60 testi</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/zirve60.html", "w", encoding="utf-8").write(page)
