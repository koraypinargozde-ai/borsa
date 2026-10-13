import yfinance as yf, pandas as pd, numpy as np
import re, os, json
import html as HT
from datetime import datetime
from zoneinfo import ZoneInfo

np.seterr(all="ignore")

# TradingView ayarların (BIST Patlama Öncesi AL - Kaliteli)
RSI_LEN = 24
RSI_TOL = 0.682
PRICE_BARS = 31
PRICE_TOL = 0.01543
VOL_MULT = 1000.0
MIN_REL = 4.4
VOL_LEN = 31
VSPIKE = 2.6
BUFFER = 1.002
COOLDOWN = 15
BREAK_VOL = 4.4
DMI_LEN = 20
DMI_SM = 20
ADX_MIN = 19.0
MIN_CS = 0.3
RES_PROX = 0.98
ROB_BAND = 2
ROB_MIN = 0.5
PERIOD = os.environ.get("OBV_PERIOD", "5d")
COST = 0.3
KEEP_DAYS = 180

AYAR = {"hacim": MIN_REL, "aralik": round(PRICE_TOL * 100, 3), "rsit": RSI_TOL,
        "bar": PRICE_BARS, "vp": VSPIKE, "adx": ADX_MIN, "cs": MIN_CS,
        "dir": RES_PROX, "rb": ROB_MIN, "rsi": RSI_LEN}

src = open("scan.py", encoding="utf-8").read()
T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
tick = [t + ".IS" for t in dict.fromkeys(T)]


def rma(s, n):
    return s.ewm(alpha=1 / n, adjust=False).mean()


def yv(z, d=2):
    if z is None or pd.isna(z):
        return None
    return round(float(z), d)


def jdef(o):
    if hasattr(o, "item"):
        return o.item()
    return str(o)


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

    d = c.diff()
    rs = rma(d.clip(lower=0), RSI_LEN) / rma(-d.clip(upper=0), RSI_LEN)
    rsi = 100 - 100 / (1 + rs)
    rdl = (rsi - rsi.shift(1)).abs()
    rsi_flat = rdl <= RSI_TOL

    hh = h.rolling(PRICE_BARS).max()
    ll = l.rolling(PRICE_BARS).min()
    rg = (hh - ll) / ll * 100
    price_flat = (hh - ll) / ll < PRICE_TOL
    pre_break = c <= hh * BUFFER
    near_res = c >= hh * RES_PROX

    avgv = v.rolling(VOL_LEN).mean()
    relv = v / avgv.where(avgv > 0)
    high_vol = v > avgv * VOL_MULT
    rel_ok = relv >= MIN_REL
    brk_ok = v > avgv * BREAK_VOL

    hl = h - l
    avgr = hl.rolling(VOL_LEN).mean()
    vp = hl / avgr.where(avgr > 0)
    vspike = hl > avgr * VSPIKE

    up = h.diff()
    dn = -l.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=x.index)
    mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=x.index)
    pcl = c.shift(1)
    tr = pd.concat([hl, (h - pcl).abs(), (l - pcl).abs()], axis=1).max(axis=1)
    trr = rma(tr, DMI_LEN)
    dip = 100 * rma(pdm, DMI_LEN) / trr
    dim = 100 * rma(mdm, DMI_LEN) / trr
    toplam = (dip + dim).where((dip + dim) != 0)
    dx = (dip - dim).abs() / toplam * 100
    adx = rma(dx.fillna(0), DMI_SM)
    trend_up = (dip > dim) & (adx >= ADX_MIN)

    cs = ((c - l) / hl.where(hl != 0)).fillna(0)
    bull = cs >= MIN_CS

    core = (rsi_flat & price_flat).astype(float)
    rob = core.rolling(ROB_BAND).mean()
    rob_ok = rob >= ROB_MIN

    pre = (rsi_flat & price_flat & pre_break & (high_vol | vspike) & rel_ok
           & brk_ok & trend_up & bull & near_res & rob_ok)

    idx = []
    last = None
    for i in np.where(pre.values)[0]:
        if last is None or i - last > COOLDOWN:
            idx.append(i)
            last = i

    pos = pd.Series(np.arange(len(x)), index=x.index)
    ld = pos.groupby(gun).transform("max").values
    son_gun = gun[-1]
    cv, hv, ov = c.values, h.values, o.values
    out = []
    for i in idx:
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
        out.append({
            "t": ad, "z": x.index[i].strftime("%Y-%m-%d %H:%M"),
            "p": yv(cv[i]), "g": yv(g), "r1": yv(r1), "rd": yv(rd),
            "rh": yv(rh), "rv": yv(relv.iloc[i]), "son": yv(cv[-1]),
            "rsi": yv(rsi.iloc[i], 1), "rdl": yv(rdl.iloc[i], 3),
            "rg": yv(rg.iloc[i]), "vp": yv(vp.iloc[i]),
            "adx": yv(adx.iloc[i], 1), "dp": yv(dip.iloc[i], 1),
            "dm": yv(dim.iloc[i], 1), "cs": yv(cs.iloc[i]),
            "dy": yv((cv[i] / hh.iloc[i] - 1) * 100), "rb": yv(rob.iloc[i]),
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
if os.path.exists("docs/obv3.json"):
    try:
        eski = json.load(open("docs/obv3.json", encoding="utf-8")).get("s", [])
    except Exception:
        eski = []
sozluk = {(s["t"], s["z"]): s for s in eski}
for s in yeni:
    k = (s["t"], s["z"])
    ek = sozluk.get(k)
    if ek:
        for a in ("gk", "ss", "sg", "bd"):
            if a in ek:
                s[a] = ek[a]
    sozluk[k] = s
bugun_ts = pd.Timestamp(datetime.now(ZoneInfo("Europe/Istanbul")).date())
kes = (bugun_ts - pd.Timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
S = sorted([s for s in sozluk.values() if s["z"][:10] >= kes],
           key=lambda s: s["z"], reverse=True)
print("saklanan sinyal:", len(S), "(son", KEEP_DAYS, "gün)")


def gun_sonuc(S):
    su = datetime.now(ZoneInfo("Europe/Istanbul"))
    bt = pd.Timestamp(su.date())
    kapandi = (su.hour, su.minute) >= (18, 15)
    bek = [s for s in S if s.get("g")]
    tl = sorted({s["t"] for s in bek})
    seri = {}
    for i in range(0, len(tl), 30):
        grup = [t + ".IS" for t in tl[i:i + 30]]
        try:
            d = yf.download(grup, period="1y", interval="1d", group_by="ticker",
                            progress=False, threads=True, auto_adjust=False)
        except Exception as e:
            print("günlük hata", e)
            continue
        for t in grup:
            try:
                x = d[t] if isinstance(d.columns, pd.MultiIndex) else d
                cs_ = x["Close"].dropna()
                cs_.index = pd.to_datetime(cs_.index).tz_localize(None).normalize()
                cs_ = cs_[~cs_.index.duplicated()]
                seri[t[:-3]] = cs_
            except Exception:
                continue
    for s in bek:
        cs_ = seri.get(s["t"])
        if cs_ is None or len(cs_) == 0:
            s.setdefault("gk", [])
            continue
        dz = pd.Timestamp(s["z"][:10])
        k = int(cs_.index.searchsorted(dz))
        if k >= len(cs_) or cs_.index[k] != dz:
            s.setdefault("gk", [])
            continue
        g = s["g"]
        f = 1.0
        p = s.get("p")
        ck = float(cs_.iloc[k])
        if p and ck > 0:
            r = p / ck
            if r > 1.4 or r < 0.7:
                f = r
        if f != 1.0:
            g = g / f
            s["bd"] = round(f, 3)
        else:
            s.pop("bd", None)
        gk = []
        for dd in range(1, 6):
            j = k + dd
            if j >= len(cs_):
                break
            dj = cs_.index[j]
            if dj > bt or (dj == bt and not kapandi):
                break
            gk.append(yv((float(cs_.iloc[j]) / g - 1) * 100))
        last = len(cs_) - 1
        s["gk"] = gk
        s["sg"] = int(last - k)
        s["ss"] = yv((float(cs_.iloc[last]) / g - 1) * 100)


try:
    gun_sonuc(S)
except Exception as e:
    print("günlük sonuç hesabı hata", e)

simdi = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")
json.dump({"g": simdi, "s": S, "a": AYAR}, open("docs/obv3.json", "w", encoding="utf-8"),
          ensure_ascii=False, default=jdef)


def td(v):
    if v is None:
        return "<td>—</td>"
    return f"<td class={'g' if v > 0 else 'r' if v < 0 else ''}>{v:+.2f}</td>"


satir = ""
for s in S[:600]:
    z = datetime.strptime(s["z"], "%Y-%m-%d %H:%M").strftime("%d.%m %H:%M")
    satir += (f"<tr><td><b>{HT.escape(s['t'])}</b></td><td>{z}</td><td>{s['p']}</td>"
              f"<td>{'—' if s['g'] is None else s['g']}</td>"
              f"{td(s['r1'])}{td(s['rd'])}{td(s.get('ss'))}<td>{s['rv']}x</td></tr>")
if not satir:
    satir = "<tr><td colspan=8>Henüz sinyal yok</td></tr>"

css = ("body{font:12px/1.45 sans-serif;padding:12px;background:#0e1116;color:#e8eaed}"
       "table{border-collapse:collapse;width:100%}td,th{padding:5px 4px;border-bottom:1px solid #222;"
       "text-align:right;white-space:nowrap}th{color:#9aa0a6;font-weight:600}"
       "td:first-child,th:first-child{text-align:left}.g{color:#3ddc84}.r{color:#ff6b6b}"
       ".w{overflow-x:auto}")
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Patlama Öncesi AL</title>"
        f"<style>{css}</style></head><body>"
        "<h3>BIST Patlama Öncesi AL (Kaliteli) · 5 dk</h3>"
        f"<p>Güncelleme: {simdi} · toplam sinyal: {len(S)}</p>"
        "<div class=w><table><tr><th>Hisse</th><th>Zaman</th><th>Sinyal</th><th>Giriş</th>"
        "<th>1sa %</th><th>Gün sonu %</th><th>Şimdi %</th><th>Hacim</th></tr>"
        + satir + "</table></div></body></html>")
open("docs/obv3.html", "w", encoding="utf-8").write(page)
