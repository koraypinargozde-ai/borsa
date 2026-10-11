import re, os, time, warnings
import numpy as np, pandas as pd, yfinance as yf
warnings.filterwarnings("ignore")
H = 63  # ~3 ay
ESIK = 1.0  # +%100

BAD = {"TRY","USD","EUR","NONE","TRUE","FALSE","XU100","XU030","UTF","BIST","JSON",
       "HTML","HTTP","HTTPS","CSV","UTC","ATR","EMA","SMA","RSI","OBV","CMF","VWAP",
       "CVD","CSS","NAN","INF","YES","NOT","AND","FOR","DEF","TL","IS","PERIOD",
       "OPEN","HIGH","LOW","CLOSE","VOLUME","DATE","INDEX","TIME","UTF8"}

def clean(s):
    return sorted(x for x in s if x not in BAD and not x.isdigit())

def tickers():
    src = open("scan.py", encoding="utf-8").read()
    print("scan.py boyut", len(src))
    for l in [l for l in src.splitlines() if "ASELS" in l or "THYAO" in l][:3]:
        print("ornek satir:", l.strip()[:200])
    t1 = clean(set(re.findall(r'\b([A-Z][A-Z0-9]{2,5})\.IS\b', src)))
    print("yontem1 (.IS)", len(t1))
    if len(t1) >= 100:
        return t1
    t2 = clean(set(re.findall(r'["\']([A-Z][A-Z0-9]{2,5})(?:\.IS)?["\']', src)))
    print("yontem2 (tirnakli)", len(t2))
    if len(t2) >= 100:
        return t2
    t3 = clean(set(re.findall(r'\b([A-Z][A-Z0-9]{2,5})\b', src)))
    print("yontem3 (genis)", len(t3))
    return t3

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
                if len(x) > 300:
                    x = x.copy()
                    x.index = pd.DatetimeIndex(x.index).tz_localize(None)
                    out[t] = x
            except Exception:
                pass
    return out

tks = tickers()
print("ticker sayisi", len(tks))
if len(tks) < 100:
    raise SystemExit("scan.py'den yeterli ticker okunamadi")
data = load(tks)
print("veri gelen hisse", len(data))
xu = yf.download("XU100.IS", period="3y", interval="1d", progress=False, auto_adjust=True)["Close"]
xu = xu.squeeze()
xu.index = pd.DatetimeIndex(xu.index).tz_localize(None)
last = xu.index[-1]
cut = last - pd.Timedelta(days=365)

def feats(x, i):
    c = x["Close"].values; v = x["Volume"].values
    w = c[i-120:i+1]; y = c[i-250:i+1]
    pv = v[i-139:i-19].mean()
    sp = 0
    if "Stock Splits" in x:
        sp = x["Stock Splits"].values[max(0, i-60):min(len(c), i+H+1)].sum()
    d = x.index[i]
    try:
        e = float(xu.asof(d) / xu.asof(d - pd.Timedelta(days=90)) - 1)
    except Exception:
        e = np.nan
    return dict(r120=c[i]/c[i-120]-1, rng=w.max()/w.min()-1,
                vr=(v[i-19:i+1].mean()/pv) if pv > 0 else np.nan,
                dip=c[i]/y.min()-1, hi=c[i]/y.max(),
                bed=int(sp > 0), endeks=e)

ev, base = [], []
for t, x in data.items():
    c = x["Close"]; n = len(c)
    fm = c.iloc[::-1].rolling(H, min_periods=15).max().iloc[::-1].shift(-1)
    r = (fm / c - 1).values
    i = 250
    while i < n - 15:
        if x.index[i] >= cut and r[i] >= ESIK:
            f = feats(x, i)
            f.update(hisse=t, tarih=x.index[i].strftime("%d.%m.%Y"),
                     maks=r[i], son=c.iloc[min(i+H, n-1)]/c.iloc[i]-1)
            ev.append(f)
            i += H
        else:
            i += 1
    for i in range(250, n-15, 21):
        if x.index[i] >= cut:
            base.append(feats(x, i))

ev = pd.DataFrame(ev); base = pd.DataFrame(base)
print("olay", len(ev), "taban", len(base))

mc, ha, pe, pb = {}, {}, {}, {}
for t in ev["hisse"].unique()[:150]:
    try:
        inf = yf.Ticker(t+".IS").info
        mc[t] = (inf.get("marketCap") or np.nan) / 1e9
        fl, so = inf.get("floatShares"), inf.get("sharesOutstanding")
        ha[t] = fl/so*100 if fl and so else np.nan
        pe[t] = inf.get("trailingPE", np.nan)
        pb[t] = inf.get("priceToBook", np.nan)
    except Exception:
        pass
    time.sleep(0.3)
ev["pd_mlr"] = ev["hisse"].map(mc); ev["halka_%"] = ev["hisse"].map(ha)
ev["fk"] = ev["hisse"].map(pe); ev["pddd"] = ev["hisse"].map(pb)

conds = {
 "120g aralık < %60 (yatay)": lambda d: d.rng < 0.6,
 "120g getiri < %20": lambda d: d.r120 < 0.2,
 "1 yıl dibinden < %40": lambda d: d.dip < 0.4,
 "1 yıl zirvesinin < %60'ı": lambda d: d.hi < 0.6,
 "20g hacim >= 1,5x": lambda d: d.vr >= 1.5,
 "bedelsiz var": lambda d: d.bed == 1,
 "BIST100 3 ay > 0": lambda d: d.endeks > 0,
}
rows = []
for k, f in conds.items():
    a = f(ev).mean()*100; b = f(base).mean()*100
    rows.append([k, round(a, 1), round(b, 1), round(a/b, 2) if b else np.nan])
tab = pd.DataFrame(rows, columns=["Koşul", "Olay %", "Normal %", "Kat"])

evs = ev.sort_values("maks", ascending=False).copy()
for c_ in ["r120", "rng", "dip", "maks", "son", "endeks"]:
    evs[c_] = (evs[c_]*100).round(1)
evs["vr"] = evs["vr"].round(2); evs["hi"] = (evs["hi"]*100).round(0)
evs = evs[["hisse", "tarih", "maks", "son", "r120", "rng", "dip", "hi", "vr", "bed", "endeks", "pd_mlr", "halka_%", "fk", "pddd"]]
evs.columns = ["Hisse", "Başlangıç", "Maks %", "63g sonu %", "Önceki120g %", "120g aralık %", "Dipten %", "Zirvenin %", "Hacim20/120", "Bedelsiz", "BIST100 %", "PD mlr TL", "Halka %", "F/K", "PD/DD"]

med = ev[["r120", "rng", "dip", "hi", "vr"]].median().round(2).to_dict()
os.makedirs("docs", exist_ok=True)
css = "<style>body{font-family:sans-serif;margin:8px;font-size:13px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:3px 6px;text-align:right}th{background:#eee}div{overflow-x:auto}</style>"
html = ("<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>" + css + "</head><body>"
        f"<h3>Devasa yükselenler (3 ayda +%100 ve üzeri), son 1 yıl</h3>"
        f"<p>{len(data)} hisse, {len(ev)} olay, {ev['hisse'].nunique()} farklı hisse, taban örnek {len(base)}. Başlangıç = sonraki 63 günde zirvesi +%100 olan ilk gün.</p>"
        f"<p>Olay medyanları: {med}</p>"
        "<p>Uyarı: güncel hisse listesi (hayatta kalma yanlılığı), fon/manipülasyon dönemi, PD/halka açıklık/F-K güncel değerler.</p>"
        "<h4>Ortak izler (olay / normal)</h4><div>" + tab.to_html(index=False) + "</div>"
        "<h4>Olaylar</h4><div>" + evs.to_html(index=False, na_rep="-") + "</div></body></html>")
open("docs/devasa.html", "w", encoding="utf-8").write(html)
print("docs/devasa.html yazildi")
