import yfinance as yf, pandas as pd, numpy as np
import re, os, json
import html as HT
from datetime import datetime
from zoneinfo import ZoneInfo

np.seterr(all="ignore")

# TradingView ayarların
REL_VOL = 8.9
NARROW = 2.2
OBV_LB = 98
RSI_LEN = 3
VOL_MULT = 1.1
FLOW_LB = 41
MIN_SCORE = 72
PERIOD = os.environ.get("OBV_PERIOD", "5d")
COST = 0.3

AYAR = {"hacim": REL_VOL, "aralik": NARROW, "obv": OBV_LB, "rsi": RSI_LEN,
        "vol": VOL_MULT, "akis": FLOW_LB, "puan": MIN_SCORE}

src = open("scan.py", encoding="utf-8").read()
T = re.search(r'T = """(.*?)"""', src, re.S).group(1).split()
tick = [t + ".IS" for t in dict.fromkeys(T)]


def rma(s, n):
    return s.ewm(alpha=1 / n, adjust=False).mean()


def yv(z, d=2):
    if z is None or pd.isna(z):
        return None
    return round(float(z), d)


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
    obv_up = obv > obv.shift(OBV_LB)
    obd = (obv - obv.shift(OBV_LB)) / v.rolling(OBV_LB).sum() * 100
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
    nmf = mfv.rolling(FLOW_LB).sum()
    nf_ok = (nmf > 0) & (nmf > nmf.shift(FLOW_LB))
    nmfp = nmf / v.rolling(FLOW_LB).sum() * 100
    pcl = c.shift(1)
    tr = pd.concat([hl, (h - pcl).abs(), (l - pcl).abs()], axis=1).max(axis=1)
    atr = rma(tr, 14)
    vm = atr / atr.rolling(20).mean()
    vol_ok = atr > atr.rolling(20).mean() * VOL_MULT
    rv_ok = (avg > 0) & (relv >= REL_VOL)

    dip = narrow & obv_up & vb & rsi_ok & cmf_ok & nf_ok & rv_ok & vol_ok
    score = (narrow * 24 + obv_up * 28 + vb * 16 + rsi_ok * 10 + cmf_ok * 8
             + nf_ok * 14 + rv_ok * 5 + vol_ok * 5).clip(upper=100)
    sig = dip & (score >= MIN_SCORE)

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
        out.append({
            "t": ad, "z": x.index[i].strftime("%Y-%m-%d %H:%M"),
            "p": yv(cv[i]), "g": yv(g), "r1": yv(r1), "rd": yv(rd),
            "rh": yv(rh), "rv": yv(relv.iloc[i]), "son": yv(cv[-1]),
            "vm": yv(vm.iloc[i]), "rsi": yv(rsi.iloc[i], 1),
            "cmf": yv(cmf.iloc[i], 3), "sc": yv(score.iloc[i], 0),
            "rg": yv(rng.iloc[i]), "nm": yv(nmfp.iloc[i]),
            "nf": yv(nmf.iloc[i], 0), "ob": yv(obd.iloc[i]),
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
if os.path.exists("docs/obv.json"):
    try:
        eski = json.load(open("docs/obv.json", encoding="utf-8")).get("s", [])
    except Exception:
        eski = []
sozluk = {(s["t"], s["z"]): s for s in eski}
for s in yeni:
    k = (s["t"], s["z"])
    ek = sozluk.get(k)
    if ek:
        for a in ("gk", "ss", "sg"):
            if a in ek:
                s[a] = ek[a]
    sozluk[k] = s
S = sorted(sozluk.values(), key=lambda s: s["z"], reverse=True)[:500]


def gun_sonuc(S):
    # gk = sinyalden sonraki 1..5. işlem günü kapanışının girişe göre % değişimi
    # ss = en son fiyata göre % değişim, sg = sinyalden bu yana geçen işlem günü
    su = datetime.now(ZoneInfo("Europe/Istanbul"))
    bt = pd.Timestamp(su.date())
    kapandi = (su.hour, su.minute) >= (18, 15)
    sinir = (bt - pd.Timedelta(days=14)).strftime("%Y-%m-%d")
    bek = [s for s in S if s.get("g") and (s["z"][:10] >= sinir or "gk" not in s)]
    tl = sorted({s["t"] for s in bek})
    seri = {}
    for i in range(0, len(tl), 30):
        grup = [t + ".IS" for t in tl[i:i + 30]]
        try:
            d = yf.download(grup, period="3mo", interval="1d", group_by="ticker",
                            progress=False, threads=True, auto_adjust=False)
        except Exception as e:
            print("günlük hata", e)
            continue
        for t in grup:
            try:
                x = d[t] if isinstance(d.columns, pd.MultiIndex) else d
                cs = x["Close"].dropna()
                cs.index = pd.to_datetime(cs.index).tz_localize(None).normalize()
                cs = cs[~cs.index.duplicated()]
                seri[t[:-3]] = cs
            except Exception:
                continue
    for s in bek:
        cs = seri.get(s["t"])
        if cs is None or len(cs) == 0:
            s.setdefault("gk", [])
            continue
        dz = pd.Timestamp(s["z"][:10])
        k = cs.index.searchsorted(dz)
        if k >= len(cs) or cs.index[k] != dz:
            s.setdefault("gk", [])
            continue
        g = s["g"]
        gk = []
        for dd in range(1, 6):
            j = k + dd
            if j >= len(cs):
                break
            dj = cs.index[j]
            if dj > bt or (dj == bt and not kapandi):
                break
            gk.append(yv((float(cs.iloc[j]) / g - 1) * 100))
        last = len(cs) - 1
        s["gk"] = gk
        s["sg"] = last - k
        s["ss"] = yv((float(cs.iloc[last]) / g - 1) * 100)


try:
    gun_sonuc(S)
except Exception as e:
    print("günlük sonuç hesabı hata", e)

simdi = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")
json.dump({"g": simdi, "s": S, "a": AYAR}, open("docs/obv.json", "w", encoding="utf-8"),
          ensure_ascii=False)


def ozet(key):
    a = [s[key] - COST for s in S if s.get(key) is not None]
    if not a:
        return "—"
    return f"n {len(a)} · ort {np.mean(a):+.2f}% · isabet %{np.mean([x > 0 for x in a]) * 100:.0f}"


def ozet_g(i):
    a = [s["gk"][i] - COST for s in S if s.get("gk") and len(s["gk"]) > i]
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
              f"{td(s['r1'])}{td(s['rd'])}{td(s.get('ss'))}<td>{s['rv']}x</td></tr>")
if not satir:
    satir = "<tr><td colspan=8>Henüz sinyal yok</td></tr>"

css = ("body{font:12px/1.45 sans-serif;padding:12px;background:#0e1116;color:#e8eaed}"
       "table{border-collapse:collapse;width:100%}td,th{padding:5px 4px;border-bottom:1px solid #222;"
       "text-align:right;white-space:nowrap}th{color:#9aa0a6;font-weight:600}"
       "td:first-child,th:first-child{text-align:left}.g{color:#3ddc84}.r{color:#ff6b6b}"
       ".box{background:#161b22;border-radius:8px;padding:10px;margin-bottom:10px}"
       ".w{overflow-x:auto}")
page = ("<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Dip OBV sinyali</title>"
        f"<style>{css}</style></head><body>"
        "<h3>Dip OBV · 5 dakikalık AL sinyali</h3>"
        f"<div class=box>Güncelleme: {simdi} · Yahoo verisi ~15 dk gecikmeli<br>"
        f"Ayar: hacim {REL_VOL}x · aralık %{NARROW} · OBV {OBV_LB} · RSI {RSI_LEN} · "
        f"volatilite {VOL_MULT} · net akış {FLOW_LB}<br><br>"
        f"Toplam sinyal: {len(S)}<br>"
        f"1 saat sonra (net %{COST} düşüldü): {ozet('r1')}<br>"
        f"Gün sonu (net): {ozet('rd')}<br>"
        f"1. gün (net): {ozet_g(0)}<br>"
        f"2. gün (net): {ozet_g(1)}<br>"
        f"3. gün (net): {ozet_g(2)}<br>"
        f"5. gün (net): {ozet_g(4)}</div>"
        "<div class=w><table><tr><th>Hisse</th><th>Zaman</th><th>Sinyal</th><th>Giriş</th>"
        "<th>1sa %</th><th>Gün sonu %</th><th>Şimdi %</th><th>Hacim</th></tr>"
        + satir + "</table></div>"
        "<p style='color:#9aa0a6'>Giriş = sinyalden sonraki mumun açılışı. Getiriler girişe göre, "
        "komisyonsuz. Şimdi = girişe göre en son fiyat.</p></body></html>")
open("docs/obv.html", "w", encoding="utf-8").write(page)
