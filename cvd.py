import re, json, datetime
from collections import Counter
import numpy as np
import yfinance as yf

D = "docs/"
RV_ESIK = 1.5      # goreceli hacim (son 20 gunun ayni saate kadarki ortalamasina gore) en az
CR_ESIK = 0.10     # CVD orani en az (net alim / toplam hacim)
DEG_ALT = -3.0     # bugunku degisim alt siniri (%)
DEG_UST = 2.0      # bugunku degisim ust siniri (%)
G5_MAX = 3.0       # son 5 gunde mutlak getiri en fazla (%)
AR_MAX = 12.0      # son 10 gun (bugun haric) en yuksek-en dusuk araligi, ortalama fiyata gore (%)


def tickers():
    h = open(D + "index.html", encoding="utf-8").read()
    return list(dict.fromkeys(re.findall(r"<tr><td>(.*?)</td><td class=s>", h)))


def hesapla(df):
    # df: 15 dakikalik mumlar (High, Low, Close, Volume)
    if len(df) < 60:
        return None
    gun = df.index.strftime("%Y-%m-%d")
    gunler = list(dict.fromkeys(gun))
    if len(gunler) < 12:
        return None
    bugun = gunler[-1]
    hs = df[gun == bugun]
    n = len(hs)
    if n < 2:
        return None
    vol = hs["Volume"].values.astype(float)
    toplam = float(vol.sum())
    if toplam <= 0:
        return None
    # son 20 gunun ayni muma kadarki toplam hacmi
    onc = []
    for g in gunler[:-1][-20:]:
        dd = df[gun == g]
        if len(dd) >= n:
            onc.append(float(dd["Volume"].values[:n].sum()))
    if len(onc) < 10:
        return None
    ort = sum(onc) / len(onc)
    if ort <= 0:
        return None
    rv = toplam / ort
    hi = hs["High"].values.astype(float)
    lo = hs["Low"].values.astype(float)
    cl = hs["Close"].values.astype(float)
    rng = hi - lo
    guv = np.where(rng > 0, rng, 1.0)
    delta = np.where(rng > 0, vol * ((cl - lo) - (hi - cl)) / guv, 0.0)
    cr = float(delta.sum()) / toplam
    v4 = float(vol[-4:].sum())
    c4 = float(delta[-4:].sum()) / v4 if v4 > 0 else 0.0
    p = 1 if (rv >= RV_ESIK and cr >= CR_ESIK and c4 > 0) else 0

    # yataylik: gunluk kapanislar ve son 10 gunluk aralik
    kap = df["Close"].groupby(gun).last().values.astype(float)
    if len(kap) < 11 or kap[-2] <= 0 or kap[-6] <= 0:
        return None
    deg = (kap[-1] / kap[-2] - 1) * 100
    g5 = (kap[-1] / kap[-6] - 1) * 100
    d10 = df[gun.isin(gunler[-11:-1])]
    ortf = float(np.mean(kap[-11:-1]))
    if len(d10) == 0 or ortf <= 0:
        return None
    ar = (float(d10["High"].max()) - float(d10["Low"].min())) / ortf * 100
    y = 1 if (DEG_ALT <= deg <= DEG_UST and abs(g5) <= G5_MAX and ar <= AR_MAX) else 0
    return bugun, [round(rv, 2), round(cr, 3), round(c4, 3), p, y,
                   round(g5, 1), round(ar, 1), round(deg, 1)]


def main():
    tk = tickers()
    if not tk:
        print("liste yok, cvd.json degismedi")
        return
    syms = [t + ".IS" for t in tk]
    out, tarih = {}, []
    for i in range(0, len(syms), 40):
        grup = syms[i:i + 40]
        try:
            v = yf.download(grup, period="60d", interval="15m", group_by="ticker",
                            progress=False, threads=True, auto_adjust=False)
        except Exception as e:
            print("hata", e)
            continue
        for t in grup:
            try:
                df = v[t][["High", "Low", "Close", "Volume"]].dropna()
                r = hesapla(df)
                if r:
                    tarih.append(r[0])
                    out[t[:-3]] = r[1]
            except Exception:
                pass
    if not out:
        print("veri alinamadi, cvd.json degismedi")
        return
    d = Counter(tarih).most_common(1)[0][0]
    simdi = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    json.dump({"d": d, "t": simdi.strftime("%H:%M"), "x": out},
              open(D + "cvd.json", "w"), separators=(",", ":"))
    print("cvd.json yazildi:", len(out), "hisse,",
          sum(x[3] for x in out.values()), "adet para girisi,",
          sum(1 for x in out.values() if x[3] and x[4]), "adet para girisi + yatay")


main()
