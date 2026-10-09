import json, re, warnings
from datetime import datetime, timedelta
import numpy as np, pandas as pd, yfinance as yf

warnings.filterwarnings("ignore")
D = "docs/"
COST = 0.003
HOR = [1, 3, 5, 10]
LIQ = 2_000_000
AYAR = [(0.005, 0.05), (0.01, 0.1), (0.02, 0.2)]
NN = [8, 10, 12]
TOLS = [0.02, 0.03, 0.04]
CANLI = (0.005, 0.05, 10, 0.03)
GERI = 45       # kutuya eklenecek geçmiş (takvim günü)
GTOP = 15       # günde en çok sinyal
ARA = 30
MAXROW = 60


def norm(ix):
    return pd.to_datetime(ix).tz_localize(None).normalize()


def dl(tk, period):
    out = {}
    for i in range(0, len(tk), 50):
        grup = tk[i:i + 50]
        try:
            d = yf.download([t + ".IS" for t in grup], period=period,
                            group_by="ticker", progress=False,
                            threads=True, auto_adjust=True)
        except Exception as e:
            print("hata", e)
            continue
        for t in grup:
            try:
                x = d[t + ".IS"][["Open", "High", "Low", "Close", "Volume"]].dropna()
                if len(x):
                    x.index = norm(x.index)
                    out[t] = x[~x.index.duplicated()]
            except Exception:
                pass
    return out


def psar(h, l, c, st, mx):
    n = len(h)
    sar = np.zeros(n)
    tr = np.zeros(n, dtype=int)
    up = c[1] >= c[0]
    sar[0] = l[0] if up else h[0]
    ep = h[0] if up else l[0]
    af = st
    tr[0] = 1 if up else -1
    for i in range(1, n):
        s = sar[i - 1] + af * (ep - sar[i - 1])
        if up:
            s = min(s, l[i - 1], l[i - 2] if i > 1 else l[i - 1])
            if l[i] < s:
                up = False
                s = ep
                ep = l[i]
                af = st
            elif h[i] > ep:
                ep = h[i]
                af = min(af + st, mx)
        else:
            s = max(s, h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > s:
                up = True
                s = ep
                ep = h[i]
                af = st
            elif l[i] < ep:
                ep = l[i]
                af = min(af + st, mx)
        sar[i] = s
        tr[i] = 1 if up else -1
    return sar, tr


def ozet(dt, hv, R, thr, cut):
    m = hv >= thr
    if m.sum() == 0:
        return None
    r = R[m]
    d = dt[m]
    o = {"n": int(m.sum())}
    for j, k in enumerate(HOR):
        col = r[:, j]
        col = col[np.isfinite(col)]
        o["m%d" % k] = float(col.mean()) * 100 if len(col) else None
    v5 = r[:, 2]
    v5 = v5[np.isfinite(v5)]
    o["hit"] = float((v5 > 0).mean()) * 100 if len(v5) else None
    tr = d <= cut
    for k, j in ((5, 2), (10, 3)):
        for nm, mk in (("e", tr), ("t", ~tr)):
            col = r[mk, j]
            col = col[np.isfinite(col)]
            o[nm + str(k)] = float(col.mean()) * 100 if len(col) else None
            o["n" + nm + str(k)] = int(len(col))
    return o


def fm(x, nd=2):
    if x is None:
        return "-"
    return ("%+." + str(nd) + "f") % x


def satir(ad, o, extra=""):
    if o is None:
        return '<tr><td>%s</td><td colspan="12">sinyal yok</td></tr>' % ad
    ok = all(o.get(k) is not None and o[k] > 0 for k in ("e5", "t5", "e10", "t10"))
    return ('<tr%s><td style="text-align:left">%s</td><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
            '<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>') % (
        ' class="ok"' if ok else "", ad, o["n"], fm(o["m1"]), fm(o["m3"]), fm(o["m5"]), fm(o["m10"]),
        fm(o["hit"], 0) + "%" if o["hit"] is not None else "-",
        fm(o["e5"]) + "<br><small>n%d</small>" % o["ne5"], fm(o["t5"]) + "<br><small>n%d</small>" % o["nt5"],
        fm(o["e10"]), fm(o["t10"]), "✓" if ok else "")


def main():
    src = open("scan.py", encoding="utf-8").read()
    T = list(dict.fromkeys(re.search(r'T = """(.*?)"""', src, re.S).group(1).split()))
    tum = dl(T, "3y")
    now = datetime.utcnow() + timedelta(hours=3)
    today = pd.Timestamp(now.date())
    acik_sonra = (now.hour * 60 + now.minute) >= 18 * 60 + 20

    for s in list(tum):
        x = tum[s]
        if not acik_sonra:
            x = x[x.index < today]
        if len(x) < 80:
            del tum[s]
        else:
            tum[s] = x
    alld = [x.index[0] for x in tum.values()] + [x.index[-1] for x in tum.values()]
    d0, d1 = min(alld), max(alld)
    cut = np.datetime64(d0 + (d1 - d0) * 0.6)

    ev = {}
    bd, bR = [], []
    recent = []
    for s, x in tum.items():
        o = x["Open"].values.astype(float)
        h = x["High"].values.astype(float)
        l = x["Low"].values.astype(float)
        c = x["Close"].values.astype(float)
        v = x["Volume"].values.astype(float)
        n = len(c)
        idx = x.index
        av = pd.Series(v).shift(1).rolling(20).mean().values
        with np.errstate(all="ignore"):
            liq = (av * c >= LIQ)
            hvv = v / av
        R = np.full((n, 4), np.nan)
        for j, k in enumerate(HOR):
            if n > k + 1:
                R[:n - k, j] = c[k:n] / o[1:n - k + 1] - 1 - COST
        mk = liq & np.isfinite(R[:, 0])
        bd.append(idx.values[mk])
        bR.append(R[mk])
        for (st, mx) in AYAR:
            sar, tr = psar(h, l, c, st, mx)
            sar_s = pd.Series(sar)
            dn = pd.Series((tr == -1).astype(float))
            prev_tr = np.roll(tr, 1)
            above = c > np.roll(sar, 1)
            flip = (tr == 1) & (prev_tr == -1)
            for N in NN:
                run = (dn.shift(1).rolling(N).sum() == N).values
                mxs = sar_s.shift(1).rolling(N).max().values
                mns = sar_s.shift(1).rolling(N).min().values
                mean = sar_s.shift(1).rolling(N).mean().values
                with np.errstate(all="ignore"):
                    bant = (mxs - mns) / mean
                for tol in TOLS:
                    with np.errstate(all="ignore"):
                        cond = flip & run & above & liq & (bant <= tol)
                    cond[:N + 2] = False
                    ii = np.where(cond)[0]
                    if not len(ii):
                        continue
                    key = (st, mx, N, tol)
                    okm = np.isfinite(R[ii, 0])
                    jj = ii[okm]
                    e = ev.setdefault(key, {"d": [], "hv": [], "R": []})
                    e["d"].append(idx.values[jj])
                    e["hv"].append(hvv[jj])
                    e["R"].append(R[jj])
                    if key == CANLI:
                        for i in ii:
                            if idx[i] < d1 - pd.Timedelta(days=GERI):
                                continue
                            g = []
                            if i + 1 < n:
                                for k in range(1, 11):
                                    if i + k < n:
                                        g.append(round((c[i + k] / o[i + 1] - 1) * 100, 1))
                            recent.append({
                                "s": s, "d": idx[i].date().isoformat(),
                                "sc": round(float(c[i]), 2), "ip": round(float(sar[i - 1]), 2),
                                "br": round(float((c[i] / sar[i - 1] - 1) * 100), 1),
                                "bant": round(float(bant[i]) * 100, 1),
                                "hv": round(float(hvv[i]), 1),
                                "e": round(float(o[i + 1]), 2) if i + 1 < n else None,
                                "g": g})

    BD = np.concatenate(bd)
    BR = np.concatenate(bR)
    bo = ozet(BD, np.zeros(len(BD)), BR, 0, cut)

    rows_html = [satir("<b>Rastgele giriş (taban)</b>", bo)]
    canli_o = None
    for key in sorted(ev):
        e = ev[key]
        dt = np.concatenate(e["d"])
        hv = np.concatenate(e["hv"])
        R = np.concatenate(e["R"])
        for thr in (0, 2):
            o = ozet(dt, hv, R, thr, cut)
            if o is None:
                continue
            ad = "SAR %s/%s · ip %d · bant %%%d%s" % (
                str(key[0]).replace(".", ","), str(key[1]).replace(".", ","),
                key[2], int(round(key[3] * 100)), " · hacim 2x+" if thr else "")
            if key == CANLI and thr == 0:
                ad = "<b>" + ad + " (kutudaki kural)</b>"
                canli_o = o
            rows_html.append(satir(ad, o))

    recent.sort(key=lambda z: (z["d"], z["hv"]), reverse=True)
    rec_html = []
    for r in recent[:80]:
        g = r["g"]

        def G(i):
            return fm(g[i], 1) if len(g) > i else "-"
        rec_html.append(
            '<tr><td style="text-align:left"><b>%s</b><br><small>%s</small></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                r["s"], r["d"][8:] + "." + r["d"][5:7], str(r["e"]).replace(".", ",") if r["e"] else "bekliyor",
                G(0), G(1), G(2), G(4), G(9), "%sx" % str(r["hv"]).replace(".", ",")))

    html = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SAR ip testi</title><style>
:root{color-scheme:light dark}body{font-family:system-ui,sans-serif;margin:10px;font-size:13px}
table{border-collapse:collapse;width:100%%;font-size:12px}td,th{padding:4px 5px;text-align:right;border-top:1px solid rgba(128,128,128,.3)}
th{opacity:.7}tr.ok{background:rgba(60,180,90,.18)}small{opacity:.7}.w{overflow-x:auto}
</style></head><body>
<h3>SAR ip kırılımı testi</h3>
<p>Dönem: %s - %s · %d hisse · giriş ertesi gün açılış · kapanışta çıkış (1/3/5/10 gün) · net %%0,3 maliyet · fiyatlar bedelsiz düzeltmeli · eğitim/test kesimi %s.<br>
Yeşil satır: 5 ve 10 günde hem eğitim hem testte ortalama net getiri pozitif. Sayılar ortalama net getiri %%.</p>
<div class="w"><table><tr><th style="text-align:left">Kural</th><th>n</th><th>1g</th><th>3g</th><th>5g</th><th>10g</th><th>5g artı</th><th>Eğ 5g</th><th>Test 5g</th><th>Eğ 10g</th><th>Test 10g</th><th></th></tr>
%s</table></div>
<h3>Son sinyaller (kutudaki kural)</h3>
<p>Brüt getiri, giriş = sinyalin ertesi günü açılış. Gün sütunları kapanış.</p>
<div class="w"><table><tr><th style="text-align:left">Hisse</th><th>Giriş</th><th>1.g</th><th>2.g</th><th>3.g</th><th>5.g</th><th>10.g</th><th>Hacim</th></tr>
%s</table></div></body></html>""" % (
        d0.date().strftime("%d.%m.%Y"), d1.date().strftime("%d.%m.%Y"), len(tum),
        str(cut)[:10], "\n".join(rows_html), "\n".join(rec_html))
    open(D + "sar.html", "w", encoding="utf-8").write(html)

    # kutuya geçmiş sinyaller
    try:
        veri = json.load(open(D + "sar.json", encoding="utf-8"))
    except Exception:
        veri = {}
    rows = veri.get("rows", [])
    veri["a"] = {"adim": CANLI[0], "maks": CANLI[1], "ip_gun": CANLI[2], "tol": round(CANLI[3] * 100, 1)}
    gun = {}
    for r in recent:
        gun.setdefault(r["d"], []).append(r)
    yeni = []
    for d in sorted(gun, reverse=True):
        for r in sorted(gun[d], key=lambda z: -z["hv"])[:GTOP]:
            yeni.append(r)

    def yakin(s, d):
        for q in rows:
            if q["s"] == s and abs((datetime.fromisoformat(d) - datetime.fromisoformat(q["d"])).days) < ARA:
                return True
        return False
    eklenen = 0
    for r in yeni:
        if eklenen >= MAXROW:
            break
        if yakin(r["s"], r["d"]):
            continue
        rows.append({"s": r["s"], "d": r["d"], "sc": r["sc"], "ip": r["ip"], "br": r["br"],
                     "bant": r["bant"], "hv": r["hv"], "e": None, "ek": None, "g": []})
        eklenen += 1
    veri["rows"] = rows
    json.dump(veri, open(D + "sar.json", "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))

    print("TABAN:", bo)
    print("KUTUDAKI KURAL:", canli_o)
    print("gecmis sinyal:", len(recent), "kutuya eklenen:", eklenen)


main()
