import yfinance as yf, pandas as pd, numpy as np
import re, os, json
import html as HT
from datetime import datetime
from zoneinfo import ZoneInfo

np.seterr(all="ignore")

# TradingView ayarların (Dip OBV Dengeli v2.0 Sade)
REL_VOL = 12.7
NARROW = 1.0
OBV_LB = 111
OBV_BAND = 6
OBV_RATIO = 0.92
RSI_LEN = 3
VOL_MULT = 1.0
DIP_LB = 40
DIP_TOL = 6.0
PIN = 1.0
BRK_VOL = 12.7
MIN_SCORE = 72
PERIOD = os.environ.get("OBV_PERIOD", "5d")
COST = 0.3

src = open("scan.py", encoding="utf-8").read()
T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
tick = [t + ".IS" for t in dict.fromkeys(T)]


def rma(s, n):
    return s.ewm(alpha=1 / n, adjust=False).mean()


def tara(x, ad):
    x = x.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    if len(x) < 200:
        return []
    if x.index.tz is not None:
        x.index = x.index.tz_convert("Europe/Istanbul").tz_localize(None)
    x = x[~x.index.duplicated()]
    o, h, l, c = x.Open, x.High, x.Low, x.Close
    v = x.Volume.fillna(0)
    gun = x.index.normalize()
    gv = v.groupby(gun).sum()
    ort = gv.iloc[:-1].mean() if len(gv) > 1 else gv.mean()
    if ort * c.iloc[-1] < 2_000_000:
        return []

    avg = v.rolling(30).mean()
    relv = v / avg
    rng = (h.rolling(15).max() - l.rolling(15).min()) / l.rolling(15).min() * 100
    narrow = rng < NARROW
    obv = (np.sign(c.diff()) * v).fillna(0).cumsum()
    cnt = pd.Series(0, index=x.index)
    for n in range(max(1, OBV_LB - OBV_BAND), OBV_LB + OBV_BAND + 1):
        cnt = cnt + (obv > obv.shift(n)).astype(int)
    obv_ok = (cnt / (2 * OBV_BAND + 1)) >= OBV_RATIO
    vb = ((v > v.shift(1)).astype(int) + (v.shift(1) > v.shift(2)).astype(int)
          + (v.shift(2) > v.shift(3)).astype(int) + (v.shift(3) > v.shift(4)).astype(int)) >= 2
    d = c.diff()
    rs = rma(d.clip(lower=0), RSI_LEN) / rma(-d.clip(upper=0), RSI_LEN)
    rsi = 100 - 100 / (1 + rs)
    rsi_ok = rsi.between(46, 63)
    hl = h - l
    mfm = ((c - l) - (h - c)).div(hl.where(hl != 0)).fillna(0)
    mfv = mfm * v
    cmf = mfv.rolling(21).mean() / v.rolling(21).mean()
    cmf_ok = (cmf > 0) & (cmf > cmf.shift(1))
    pcl = c.shift(1)
    tr = pd.concat([hl, (h - pcl).abs(), (l - pcl).abs()], axis=1).max(axis=1)
    atr = rma(tr, 14)
    vol_ok = atr > atr.rolling(20).mean() * VOL_MULT
    rv_ok = (avg > 0) & (relv >= REL_VOL)

    rl = l.rolling(DIP_LB).min()
    near = ((c - rl) / rl * 100) <= DIP_TOL
    body = (c - o).abs()
    wick = np.minimum(o, c) - l
    upper = c >= (l + hl * 0.5)
    rev = (body > 0) & (wick >= body * PIN) & upper
    brk = v > avg * BRK_VOL

    sig = (narrow & obv_ok & vb & rsi_ok & cmf_ok & rv_ok & vol_ok & near & rev & brk)

    pos = pd.Series(np.arange(len(x)), index=x.index)
    ld = pos.groupby(gun).transform("max").values
    son_gun = gun[-1]
    cv, hv, ov = c.values, h.values, o.values
    out = []
    for i in np.where(sig.values)[0]:
        e = ld[i]
        g = ov[i + 1] if i + 1 <= e else None
        j = i + 12
        if j <= e:
            k = cv[j]
        elif gun[i] < son_gun:
            k = cv[e]
        else:
            k = None
        r1 = (k / g - 1) * 100 if (g is not None and k is not None) else None
        rd = (cv[e] / g - 1) * 100 if g is not None else None
        rh = (hv[i + 1:e + 1].max() / g - 1) * 100 if g is not None else None
        rd2 = lambda z: None if z is None else round(float(z), 2)
        out.append({
            "t": ad, "z": x.index[i].strftime("%Y-%m-%d %H:%M"),
            "p": rd2(cv[i]), "g": rd2(g), "r1": rd2(r1), "rd": rd2(rd),
            "rh": rd2(rh), "rv": rd2(relv.iloc[i]), "son": rd2(cv[-1]),
        })
    return out


yeni = []
islenen = 0
for i in range(0, len(tick), 30):
    grup = tick[i:i + 30]
    try:
        d = yf.download(grup, period=PERIOD, interval="5m", group_by="ticker",
                        progress=False, threads=True, auto_adjust=False)
    except Exception as e:
        print("hata", e)
        continue
    for t in grup:
        try:
            r = tara(d[t].copy(), t.replace(".IS", ""))
            islenen += 1
            yeni += r
        except Exception:
            continue

print(islenen, "hisse tarandı,", len(yeni), "sinyal (pencere içinde)")
if islenen == 0:
    raise SystemExit("veri yok")

os.makedirs("docs", exist_ok=True)
eski = []
if os.path.exists("docs/obv2.json"):
    try:
        eski = json.load(open("docs/obv2.json", encoding="utf-8")).get("s", [])
    except Exception:
        eski = []
sozluk = {(s["t"], s["z"]): s for s in eski}
for s in yeni:
    sozluk[(s["t"], s["z"])] = s
S = sorted(sozluk.values(), key=lambda s: s["z"], reverse=True)[:500]
simdi = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")
json.dump({"g": simdi, "s": S}, open("docs/obv2.json", "w", encoding="utf-8"),
          ensure_ascii=False)


def ozet(key):
    a = [s[key] - COST for s in S if s[key] is not None]
    if not a:
        return "—"
    return f"n {len(a)} · ort {np.mean(a):+.2f}% · isabet %{np.mean([x > 0 for x in a]) * 100:.0f}"


def td(v):
    if v is None:
        return "<td>—</td>"
    return f"<td class={'g' if v > 0 else 'r' if v < 0 else ''}>{v:+.2f}</td>"


satir = ""
for s in S[:150]:
    z = datetime.strptime(s["z"], "%Y-%m-%d %H:%M").strftime("%d.%m %H:%M")
    satir += (f"<tr><td><b>{HT.escape(s['t'])}</b></td><td>{z}</td><td>{s['p']}</td>"
              f"<td>{'—' if s['g'] is None else s['g']}</td>"
              f"{td(s['r1'])}{td(s['rd'])}{td(s['rh'])}<td>{s['rv']}x</td></tr>")
if not satir:
    satir = "<tr><td colspan=8>Henüz sinyal yok</td></tr>"

css = ("body{font:12px/1.45 sans-serif;padding:12px;background:#0e1116;color:#e8eaed}"
       "table{border-collapse:collapse;width:100%}td,th{padding:5px 4px;border-bottom:1px solid #222;"
       "text-align:right;white-space:nowrap}th{color:#9aa0a6;font-weight:600}"
       "td:first-child,th:first-child{text-align:left}.g{color:#3ddc84}.r{color:#ff6b6b}"
       ".box{background:#161b22;border-radius:8px;padding:10px;margin-bottom:10px}"
       ".w{overflow-x:auto}")
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Dip OBV v2</title>"
        f"<style>{css}</style></head><body>"
        "<h3>Dip OBV v2.0 Sade · 5 dakikalık AL sinyali</h3>"
        f"<div class=box>Güncelleme: {simdi} · Yahoo verisi ~15 dk gecikmeli<br>"
        f"Toplam sinyal: {len(S)}<br>"
        f"1 saat sonra (net %{COST} düşüldü): {ozet('r1')}<br>"
        f"Gün sonu/şu an (net): {ozet('rd')}</div>"
        "<div class=w><table><tr><th>Hisse</th><th>Zaman</th><th>Sinyal</th><th>Giriş</th>"
        "<th>1sa %</th><th>Gün sonu %</th><th>Zirve %</th><th>Hacim</th></tr>"
        + satir + "</table></div>"
        "<p style='color:#9aa0a6'>Giriş = sinyalden sonraki mumun açılışı. Getiriler girişe göre, "
        "komisyonsuz.</p></body></html>")
open("docs/obv2.html", "w", encoding="utf-8").write(page)
