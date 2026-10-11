import re, os, warnings
import numpy as np, pandas as pd, yfinance as yf
from itertools import combinations
warnings.filterwarnings("ignore")
H = 63
ESIK = 1.0
STEP = 5
MINTR, MINTE = 120, 50

BAD = {"TRY","USD","EUR","NONE","TRUE","FALSE","XU100","XU030","UTF","BIST","JSON",
       "HTML","HTTP","HTTPS","CSV","UTC","ATR","EMA","SMA","RSI","OBV","CMF","VWAP",
       "CVD","CSS","NAN","INF","YES","NOT","AND","FOR","DEF","TL","IS","PERIOD",
       "OPEN","HIGH","LOW","CLOSE","VOLUME","DATE","INDEX","TIME","UTF8"}

def clean(s):
    return sorted(x for x in s if x not in BAD and not x.isdigit())

def tickers():
    src = open("scan.py", encoding="utf-8").read()
    t1 = clean(set(re.findall(r'\b([A-Z][A-Z0-9]{2,5})\.IS\b', src)))
    if len(t1) >= 100:
        return t1
    t2 = clean(set(re.findall(r'["\']([A-Z][A-Z0-9]{2,5})(?:\.IS)?["\']', src)))
    if len(t2) >= 100:
        return t2
    return clean(set(re.findall(r'\b([A-Z][A-Z0-9]{2,5})\b', src)))

def load(tks):
    out = {}
    for i in range(0, len(tks), 80):
        part = tks[i:i+80]
        try:
            d = yf.download([t+".IS" for t in part], period="3y", interval="1d",
                            auto_adjust=True, actions=True, group_by="ticker",
                            progress=False, threads=True)
        except Exception as e:
            print("batch hata", e); continue
        for t in part:
            try:
                x = d[t+".IS"].dropna(subset=["Close"])
                if len(x) > 320:
                    x = x.copy()
                    x.index = pd.DatetimeIndex(x.index).tz_localize(None)
                    out[t] = x
            except Exception:
                pass
    return out

tks = tickers()
print("ticker sayisi", len(tks))
if len(tks) < 100:
    raise SystemExit("ticker okunamadi")
data = load(tks)
print("veri gelen hisse", len(data))
xu = yf.download("XU100.IS", period="3y", interval="1d", progress=False, auto_adjust=True)["Close"]
xu = xu.squeeze()
xu.index = pd.DatetimeIndex(xu.index).tz_localize(None)

def feat(x, i, ret, sp):
    c = x["Close"].values; v = x["Volume"].values
    w = c[i-120:i+1]; y = c[i-250:i+1]; w20 = c[i-19:i+1]
    pv = v[i-139:i-19].mean()
    d = x.index[i]
    try:
        ex = float(xu.asof(d) / xu.asof(d - pd.Timedelta(days=91)) - 1)
        e3 = float(xu.asof(d) / xu.asof(d - pd.Timedelta(days=90)) - 1)
    except Exception:
        ex = np.nan; e3 = np.nan
    return dict(
        date=d, r20=c[i]/c[i-20]-1, r60=c[i]/c[i-60]-1, r120=c[i]/c[i-120]-1,
        rng=w.max()/w.min()-1, rng20=w20.max()/w20.min()-1,
        dip=c[i]/y.min()-1, hi=c[i]/y.max(),
        vr=(v[i-19:i+1].mean()/pv) if pv > 0 else np.nan,
        vol60=ret[i-59:i+1].std(),
        tav10=int((ret[i-9:i+1] >= 0.095).any()), tav20=int((ret[i-19:i+1] >= 0.095).sum()),
        bed=int(sp[i-60:i+1].sum() > 0), endeks=e3,
        rs=(c[i]/c[i-63]-1) - ex, tl=float((c[i-19:i+1]*v[i-19:i+1]).mean()),
        s50=int(c[i] > c[i-49:i+1].mean()), s200=int(c[i] > c[i-199:i+1].mean()))

rows, live = [], []
for t, x in data.items():
    c = x["Close"].values; o = x["Open"].values
    n = len(c)
    ret = np.zeros(n); ret[1:] = c[1:]/c[:-1]-1
    sp = x["Stock Splits"].values if "Stock Splits" in x else np.zeros(n)
    for i in range(250, n-H, STEP):
        entry = o[i+1]
        if not (entry > 0):
            continue
        fut = c[i+1:i+H+1]
        f = feat(x, i, ret, sp)
        f.update(hisse=t, mx=fut.max()/entry-1, e63=c[i+H]/entry-1)
        rows.append(f)
    try:
        f = feat(x, n-1, ret, sp); f.update(hisse=t, mx=np.nan, e63=np.nan)
        live.append(f)
    except Exception:
        pass

df = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan)
lv = pd.DataFrame(live).replace([np.inf, -np.inf], np.nan)
df = df.dropna(subset=["mx", "e63"]).reset_index(drop=True)
cut = df["date"].quantile(0.6)
trm = (df["date"] <= cut - pd.Timedelta(days=90)).values
tem = (df["date"] > cut).values
Y = (df["mx"] >= ESIK).astype(int).values
E63 = df["e63"].values
btr = Y[trm].mean()*100; bte = Y[tem].mean()*100
bm_te = np.median(E63[tem])*100
TLMED = df["tl"].median()
print("ornek", len(df), "egitim", trm.sum(), "test", tem.sum(), "taban egitim %", round(btr, 2), "test %", round(bte, 2))

conds = {
 "yatay120 (aralık<%60)": lambda d: d.rng < 0.6,
 "geniş120 (aralık>%120)": lambda d: d.rng > 1.2,
 "r120<%20": lambda d: d.r120 < 0.2,
 "r120>%50": lambda d: d.r120 > 0.5,
 "r20>%10": lambda d: d.r20 > 0.1,
 "r60>%30": lambda d: d.r60 > 0.3,
 "dipten<%40": lambda d: d.dip < 0.4,
 "dipten>%100": lambda d: d.dip > 1.0,
 "zirveye>=%90": lambda d: d.hi >= 0.9,
 "zirve<%60": lambda d: d.hi < 0.6,
 "hacim>=1,5x": lambda d: d.vr >= 1.5,
 "hacim>=2,5x": lambda d: d.vr >= 2.5,
 "RS63>%15": lambda d: d.rs > 0.15,
 "RS63<0": lambda d: d.rs < 0,
 "tavan 10g var": lambda d: d.tav10 == 1,
 "tavan 20g>=2": lambda d: d.tav20 >= 2,
 "oynaklık>%4": lambda d: d.vol60 > 0.04,
 "oynaklık<%2,5": lambda d: d.vol60 < 0.025,
 "likidite düşük": lambda d: d.tl < TLMED,
 "likidite yüksek": lambda d: d.tl >= TLMED,
 "bedelsiz 60g": lambda d: d.bed == 1,
 "BIST100 3ay>0": lambda d: d.endeks > 0,
 "sıkışma20 (<%12)": lambda d: d.rng20 < 0.12,
 "SMA50 üstü": lambda d: d.s50 == 1,
 "SMA200 üstü": lambda d: d.s200 == 1,
}
names = list(conds)
M = np.column_stack([conds[k](df).fillna(False).values.astype(bool) for k in names])

def ev(mask):
    a = mask & trm; b = mask & tem
    na, nb = int(a.sum()), int(b.sum())
    if na < MINTR or nb < MINTE:
        return None
    ra = Y[a].mean()*100; rb = Y[b].mean()*100
    return [na, round(ra, 1), round(ra/btr, 2) if btr else np.nan,
            nb, round(rb, 1), round(rb/bte, 2) if bte else np.nan,
            round(np.median(E63[b])*100, 1), round(np.mean(E63[b])*100, 1)]

res = []
for k in (1, 2, 3):
    for cb in combinations(range(len(names)), k):
        m = M[:, cb[0]].copy()
        for j in cb[1:]:
            m &= M[:, j]
        r = ev(m)
        if r:
            res.append((k, cb, r))

cols = ["Koşul", "n eğ", "Olay% eğ", "Kat eğ", "n test", "Olay% test", "Kat test", "Medyan63g test %", "Ort63g test %"]
def table(k, top=25):
    sel = [(cb, r) for kk, cb, r in res if kk == k]
    sel.sort(key=lambda z: -min(z[1][2], z[1][5]))
    out = [[" + ".join(names[j] for j in cb)] + r for cb, r in sel[:top]]
    return pd.DataFrame(out, columns=cols), sel[:top]

t1, s1 = table(1, 30); t2, s2 = table(2); t3, s3 = table(3)

live_html = ""
best = [(cb, r) for cb, r in (s3[:3] + s2[:2]) if min(r[2], r[5]) > 1]
for cb, r in best:
    m = np.ones(len(lv), dtype=bool)
    for j in cb:
        m &= conds[names[j]](lv).fillna(False).values.astype(bool)
    lst = ", ".join(sorted(lv.loc[m, "hisse"].tolist())) or "yok"
    live_html += "<p><b>" + " + ".join(names[j] for j in cb) + "</b> (kat eğ " + str(r[2]) + ", test " + str(r[5]) + "): " + lst + "</p>"

os.makedirs("docs", exist_ok=True)
css = "<style>body{font-family:sans-serif;margin:8px;font-size:13px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:3px 6px;text-align:right}td:first-child{text-align:left}th{background:#eee}div{overflow-x:auto}</style>"
html = ("<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>" + css + "</head><body>"
        "<h3>Devasa yükseliş ihtimali: koşul kombinasyonları</h3>"
        f"<p>Olay = giriş ertesi açılış, sonraki 63 günde kapanış zirvesi +%100. {len(data)} hisse, {len(df)} örnek (5 günde bir), eğitim/test ayrımı tarihe göre (arada 90 gün boşluk). "
        f"Taban olay oranı: eğitim %{btr:.2f}, test %{bte:.2f}. Test dönemi medyan 63g getiri (hepsi): %{bm_te:.1f}. Kat = koşullu olay oranı / taban.</p>"
        "<p>Uyarı: güncel hisse listesi (hayatta kalma yanlılığı), örnekler üst üste biner, çok kombinasyon denendi (şans eseri iyi görünenler olabilir). "
        "Sıralama = eğitim ve testte kat değerlerinin küçüğü. Gerçek kâr için son iki sütuna (63g sonu getiri) bak, olay oranı tek başına yetmez.</p>"
        "<h4>Bugün uyan hisseler (en iyi kombinasyonlar)</h4>" + (live_html or "<p>yok</p>") +
        "<h4>Tekli koşullar</h4><div>" + t1.to_html(index=False) + "</div>"
        "<h4>İkili kombinasyonlar</h4><div>" + t2.to_html(index=False) + "</div>"
        "<h4>Üçlü kombinasyonlar</h4><div>" + t3.to_html(index=False) + "</div></body></html>")
open("docs/devasa2.html", "w", encoding="utf-8").write(html)
print("docs/devasa2.html yazildi")
