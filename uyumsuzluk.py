import yfinance as yf, pandas as pd, numpy as np
import re, os
import html as H

PERIOD = "3y"
K = 3          # dip/tepe onayı için sağ-sol mum sayısı
COST = 0.3     # işlem maliyeti %
src = open("scan.py", encoding="utf-8").read()
T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
tick = [t + ".IS" for t in dict.fromkeys(T)]


def norm(ix):
    return pd.to_datetime(ix).tz_localize(None).normalize()


def pivotlar(x, rsi):
    lo, hi, r = x["Low"].values, x["High"].values, rsi.values
    n = len(x)
    bull = np.zeros(n, bool)
    bear = np.zeros(n, bool)
    rp_b = np.full(n, np.nan)
    rd_b = np.full(n, np.nan)
    rp_s = np.full(n, np.nan)
    rd_s = np.full(n, np.nan)
    pl, ph = [], []
    for i in range(K, n - K):
        if np.isnan(r[i]):
            continue
        # dip: solundaki K mumdan kesin düşük, sağındakilerden düşük/eşit
        if lo[i] <= lo[i - K:i + K + 1].min() and (lo[i - K:i] > lo[i]).all():
            if pl:
                j = pl[-1]
                if 5 <= i - j <= 60 and lo[i] < lo[j] and r[i] > r[j]:
                    s = i + K  # sinyal, dip ancak K mum sonra onaylanır
                    bull[s] = True
                    rp_b[s] = r[i]
                    rd_b[s] = r[i] - r[j]
            pl.append(i)
        # tepe
        if hi[i] >= hi[i - K:i + K + 1].max() and (hi[i - K:i] < hi[i]).all():
            if ph:
                j = ph[-1]
                if 5 <= i - j <= 60 and hi[i] > hi[j] and r[i] < r[j]:
                    s = i + K
                    bear[s] = True
                    rp_s[s] = r[i]
                    rd_s[s] = r[i] - r[j]
            ph.append(i)
    return bull, bear, rp_b, rd_b, rp_s, rd_s


def ozellik(x):
    c, o, h, l, v = x["Close"], x["Open"], x["High"], x["Low"], x["Volume"]
    f = pd.DataFrame(index=x.index)
    f["chg"] = c.pct_change() * 100
    av = v.shift(1).rolling(20).mean()
    f["vr"] = v / av
    f["vm3"] = f["vr"].rolling(3).max()
    f["lik"] = (av * c) >= 2_000_000
    f["yesil"] = c > o
    f["tv"] = (f["chg"] >= 9.4) & (c >= h * 0.995)
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    f["rsi"] = rsi
    b, s, rpb, rdb, rps, rds = pivotlar(x, rsi)
    f["bull"], f["bear"] = b, s
    f["rp_b"], f["rd_b"], f["rp_s"], f["rd_s"] = rpb, rdb, rps, rds
    f["r1"] = (c.shift(-1) / o.shift(-1) - 1) * 100 - COST
    f["r3"] = (c.shift(-3) / o.shift(-1) - 1) * 100 - COST
    f["hi1"] = (h.shift(-1) / o.shift(-1) - 1) * 100
    f["n_tv"] = f["tv"].astype(float).shift(-1)
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
            if len(x) < 80:
                continue
            x.index = norm(x.index)
            f = ozellik(x)
            f["h"] = t[:-3]
            frames.append(f)
        except Exception:
            continue

A = pd.concat(frames).replace([np.inf, -np.inf], np.nan)
for col in ("bull", "bear", "lik", "yesil"):
    A[col] = A[col].astype(bool)
D = A[A.lik].dropna(subset=["r1", "r3", "vm3", "n_tv"]).copy()
cut = D.index.unique().sort_values()[int(len(D.index.unique()) * 0.6)]
D["te"] = D.index >= cut


def fm(v, d=2):
    return "-" if v is None or pd.isna(v) else f"{v:.{d}f}"


out = []
P = out.append
P("RSI UYUMSUZLUK + HACİM TESTİ")
P(f"Dönem: {D.index.min():%d.%m.%Y} - {D.index.max():%d.%m.%Y} · hisse: {D.h.nunique()}")
P(f"Eğitim: {D.index.min():%d.%m.%Y} - {cut:%d.%m.%Y} · Test: sonrası")
P("Likit hisseler (günlük işlem ≥2 milyon TL), RSI(14).")
P(f"Dip/tepe {K} mum sonra onaylanır, sinyal o gün kapanışta verilir (geleceği görmez).")
P("Pozitif uyumsuzluk: fiyat daha düşük dip, RSI daha yüksek dip.")
P("Negatif uyumsuzluk: fiyat daha yüksek tepe, RSI daha düşük tepe.")
P("Hacim = sinyal gününün ve önceki 2 günün en yüksek hacim oranı (20g ort.na göre).")
P(f"Giriş: sinyalden sonraki gün açılış. Maliyet %{COST}. Getiriler net.")
P("1g = o gün açılıştan kapanışa · 3g = açılıştan 3. gün kapanışa")
P("eğ/test = eğitim ve test dönemi ortalaması · ok = 1g ve 3g eğitim+test hepsi pozitif")
P("")
P(f"{'grup':<26}{'n':>6}{'tavan%':>7}{'1g':>7}{'eğ1':>7}{'test1':>7}{'3g':>7}{'eğ3':>7}{'test3':>7}{'ok':>4}")


def satir(ad, m):
    s = D[m]
    if len(s) < 15:
        P(f"{ad:<26}{len(s):>6}  (az örnek)")
        return
    tr, te = s[~s.te], s[s.te]
    e1, t1, e3, t3 = tr.r1.mean(), te.r1.mean(), tr.r3.mean(), te.r3.mean()
    ok = "+" if (e1 > 0 and t1 > 0 and e3 > 0 and t3 > 0) else ""
    P(f"{ad:<26}{len(s):>6}{fm(s.n_tv.mean() * 100, 1):>7}{fm(s.r1.mean()):>7}"
      f"{fm(e1):>7}{fm(t1):>7}{fm(s.r3.mean()):>7}{fm(e3):>7}{fm(t3):>7}{ok:>4}")


P("--- TABAN ---")
satir("tüm günler (rastgele)", D.vm3.notna())
satir("hacim ≥2x (uyumsuzluksuz)", (D.vm3 >= 2) & ~D.bull & ~D.bear)
satir("hacim ≥3x (uyumsuzluksuz)", (D.vm3 >= 3) & ~D.bull & ~D.bear)

P("")
P("--- POZİTİF UYUMSUZLUK (alım adayı) ---")
b = D.bull
satir("uyumsuzluk (hepsi)", b)
satir("+ hacim ≥1.5x", b & (D.vm3 >= 1.5))
satir("+ hacim ≥2x", b & (D.vm3 >= 2))
satir("+ hacim ≥3x", b & (D.vm3 >= 3))
satir("+ RSI dip <35", b & (D.rp_b < 35))
satir("+ RSI dip <35 + hacim ≥2x", b & (D.rp_b < 35) & (D.vm3 >= 2))
satir("+ RSI farkı ≥5", b & (D.rd_b >= 5))
satir("+ RSI farkı ≥5 + hacim ≥2x", b & (D.rd_b >= 5) & (D.vm3 >= 2))
satir("+ sinyal günü yeşil", b & D.yesil)
satir("+ yeşil + hacim ≥2x", b & D.yesil & (D.vm3 >= 2))
satir("+ yeşil + hacim ≥2x + RSI<35", b & D.yesil & (D.vm3 >= 2) & (D.rp_b < 35))

P("")
P("--- NEGATİF UYUMSUZLUK (sat/kaçın) ---")
s_ = D.bear
satir("uyumsuzluk (hepsi)", s_)
satir("+ hacim ≥2x", s_ & (D.vm3 >= 2))
satir("+ hacim ≥3x", s_ & (D.vm3 >= 3))
satir("+ RSI tepe >65", s_ & (D.rp_s > 65))
satir("+ RSI tepe >65 + hacim ≥2x", s_ & (D.rp_s > 65) & (D.vm3 >= 2))
satir("+ sinyal günü kırmızı", s_ & ~D.yesil)
satir("+ kırmızı + hacim ≥2x", s_ & ~D.yesil & (D.vm3 >= 2))

P("")
P("Okuma: pozitif uyumsuzlukta net 1g/3g taban satırından belirgin yüksek ve")
P("ok sütununda + varsa umut var. Aksi halde kenar yok demektir.")
P("Negatif uyumsuzlukta getiri tabandan belirgin düşükse 'kaçın' sinyali işe yarıyor demektir.")

text = "\n".join(out)
print(text)
os.makedirs("docs", exist_ok=True)
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Uyumsuzluk testi</title>"
        "<style>body{font:11px/1.45 monospace;padding:12px;background:#0e1116;color:#e8eaed}"
        "pre{overflow-x:auto}</style></head><body><pre>" + H.escape(text) + "</pre></body></html>")
open("docs/uyumsuzluk.html", "w", encoding="utf-8").write(page)
