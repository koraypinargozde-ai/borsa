import json
from datetime import date, datetime, timedelta
import re
import numpy as np, pandas as pd, yfinance as yf

D = "docs/"
ARA = 30        # aynı hisse en az 30 gün sonra tekrar eklenir
TOP = 15        # günde en çok yeni sinyal (RS63'e göre en güçlüler)
LIQ = 2_000_000
MAXG = 20       # gün gün takip (işlem günü)
SAKLA = 90      # kayıtlar kaç takvim günü tutulur

KUTU = '<div id="guclutakip" style="margin:12px;padding:10px;border:1px solid rgba(128,128,128,.3);border-radius:10px;font-size:13px"></div>'

JS = r'''
(function(){
var B=document.getElementById("guclutakip");if(!B)return;
function f(x){return x==null?"-":(x>0?"+":"")+String(x).replace(".",",")+"%"}
function c(x){return x==null?"":(x>0?"color:var(--up)":"color:var(--dn,#e5484d)")}
function dm(s){return s?s.slice(8)+"."+s.slice(5,7):""}
function p(x){return x==null?"-":String(x).replace(".",",")}
fetch("guclu.json?v="+Date.now()).then(function(r){return r.json()}).then(function(j){
var R=j.rows||[];
var h='<b>💪 Göreceli güç takibi ('+R.length+')</b><div style="opacity:.7;font-size:11px;margin:2px 0 6px">Kural: 3 ayda BIST 100den güçlü (ilk %20) + 120 günlük zirveye %10 içinde. Giriş: sinyalin ertesi günü açılış. Gün sütunları kapanış getirisi (maliyet hariç). Satıra dokun: 20 güne kadar gün gün.</div>';
if(!R.length){B.innerHTML=h+"Henüz kayıt yok";return}
var ok=R.filter(function(r){return r.nc!=null});
if(ok.length){
var t1=0,t2=0,k2=0,up=0;
ok.forEach(function(r){t1+=r.nc;if(r.nc>0)up++;if(r.bx!=null){t2+=r.bx;k2++}});
h+='<div style="margin-bottom:6px">Ortalama şimdi: <b style="'+c(t1)+'">'+f(Math.round(t1/ok.length*10)/10)+'</b> · artıda: <b>'+up+'/'+ok.length+'</b>'+(k2?' · BIST farkı ort: <b style="'+c(t2)+'">'+f(Math.round(t2/k2*10)/10)+'</b>':'')+'</div>';
}
h+='<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><tr style="text-align:right;opacity:.7"><th style="text-align:left">Hisse</th><th>Giriş</th><th>1.g</th><th>2.g</th><th>3.g</th><th>5.g</th><th>10.g</th><th>Şimdi</th></tr>';
R.forEach(function(r){
var g=r.g||[];
function G(i){return g.length>i?g[i]:null}
var gir=r.e!=null?p(r.e):'<span style="opacity:.7">bekliyor</span>';
h+='<tr class="gr" style="text-align:right;border-top:1px solid rgba(128,128,128,.2);cursor:pointer"><td style="text-align:left"><b>'+r.s+'</b><br><span style="opacity:.7">'+dm(r.d)+'</span></td><td>'+gir+'</td>';
[0,1,2,4,9].forEach(function(i){h+='<td style="'+c(G(i))+'">'+f(G(i))+'</td>'});
h+='<td style="'+c(r.nc)+'">'+f(r.nc)+'<br><span style="opacity:.7">'+p(r.n)+'</span></td></tr>';
var d='';
g.forEach(function(v,i){d+='<span style="display:inline-block;margin:2px 10px 2px 0;'+c(v)+'">'+(i+1)+'.g '+f(v)+'</span>'});
if(!g.length)d='<span style="opacity:.7">Henüz kapanmış gün yok</span>';
h+='<tr style="display:none"><td colspan="8" style="text-align:left;padding:4px 0 8px;font-size:11px"><div style="opacity:.7;margin-bottom:3px">Sinyal '+dm(r.d)+' kapanış '+p(r.sc)+' · RS63 '+f(r.rs)+(r.ek?' · giriş '+dm(r.ek)+' açılış':'')+(r.bx!=null?' · BIST farkı '+f(r.bx):'')+'</div>'+d+'</td></tr>';
});
B.innerHTML=h+'</table></div>';
B.querySelectorAll("tr.gr").forEach(function(t){
t.addEventListener("click",function(){var n=t.nextElementSibling;n.style.display=(n.style.display==="none")?"table-row":"none"});
});
}).catch(function(){});
})();
'''

now = datetime.utcnow() + timedelta(hours=3)   # TR saati
TODAY = now.date()
ACIK_SONRA = (now.hour * 60 + now.minute) >= 18 * 60 + 20


def oku(p, v):
    try:
        return json.load(open(D + p, encoding="utf-8"))
    except Exception:
        return v


def norm(ix):
    return pd.to_datetime(ix).tz_localize(None).normalize()


def kapali(x):
    if ACIK_SONRA:
        return x
    return x[x.index < pd.Timestamp(TODAY)]


def dl(tk, period):
    out = {}
    for i in range(0, len(tk), 50):
        grup = tk[i:i + 50]
        try:
            d = yf.download([t + ".IS" for t in grup], period=period,
                            group_by="ticker", progress=False,
                            threads=True, auto_adjust=False)
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


def main():
    src = open("scan.py", encoding="utf-8").read()
    T = list(dict.fromkeys(re.search(r'T = """(.*?)"""', src, re.S).group(1).split()))

    veri = oku("guclu.json", {})
    rows = veri.get("rows", [])
    son = veri.get("son")

    try:
        xu = yf.download("XU100.IS", period="1y", progress=False, auto_adjust=False)
        if xu.columns.nlevels > 1:
            xu.columns = xu.columns.get_level_values(0)
        xu = xu.dropna()
        xu.index = norm(xu.index)
    except Exception as e:
        print("endeks hata", e)
        return
    xuk = kapali(xu)
    L = xuk.index[-1].date()

    tum = {}
    taranan = 0
    if son != L.isoformat():
        tum = dl(T, "1y")
        xc = xuk["Close"]
        rs_all, ad = {}, {}
        for s, x in tum.items():
            xk = kapali(x)
            if len(xk) < 130 or xk.index[-1].date() != L:
                continue
            c = xk["Close"]
            av = xk["Volume"].shift(1).rolling(20).mean().iloc[-1]
            if not (av * c.iloc[-1] >= LIQ):
                continue
            xcc = xc.reindex(xk.index, method="ffill")
            r63 = ((c.iloc[-1] / c.iloc[-64] - 1) - (xcc.iloc[-1] / xcc.iloc[-64] - 1)) * 100
            near = c.iloc[-1] / c.iloc[-120:].max()
            if np.isnan(r63) or np.isnan(near):
                continue
            rs_all[s] = float(r63)
            ad[s] = (float(r63), float(near), float(c.iloc[-1]))
        taranan = len(rs_all)
        if taranan > 100:
            pc = pd.Series(rs_all).rank(pct=True)
            cand = [(s, a) for s, a in ad.items() if pc[s] >= 0.8 and a[1] >= 0.9]
            cand.sort(key=lambda z: -z[1][0])
            yeni = 0
            for s, a in cand[:TOP]:
                if any(r["s"] == s and (L - date.fromisoformat(r["d"])).days < ARA
                       for r in rows):
                    continue
                rows.append({"s": s, "d": L.isoformat(), "sc": round(a[2], 2),
                             "rs": round(a[0], 1), "e": None, "ek": None, "g": []})
                yeni += 1
            veri["son"] = L.isoformat()
            print("tarama:", taranan, "hisse,", len(cand), "aday,", yeni, "yeni")
        else:
            print("tarama yetersiz veri:", taranan)

    rows = [r for r in rows if (L - date.fromisoformat(r["d"])).days <= SAKLA]
    eksik = [r["s"] for r in rows if r["s"] not in tum]
    if eksik:
        tum.update(dl(sorted(set(eksik)), "6mo"))

    for r in rows:
        x = tum.get(r["s"])
        if x is None:
            continue
        d0 = pd.Timestamp(r["d"])
        ard = x[x.index > d0]
        n = float(x["Close"].iloc[-1])
        r["n"] = round(n, 2)
        if len(ard) == 0:
            r["nc"] = None
            continue
        if r.get("e") is None:
            r["e"] = round(float(ard["Open"].iloc[0]), 2)
            r["ek"] = ard.index[0].date().isoformat()
        e = r["e"]
        kap = kapali(ard)
        r["g"] = [round((float(v) / e - 1) * 100, 1) for v in kap["Close"].iloc[:MAXG]]
        r["nc"] = round((n / e - 1) * 100, 1)
        ax = xu[xu.index >= pd.Timestamp(r["ek"])]
        if len(ax):
            xe = float(ax["Open"].iloc[0])
            xn = float(xu["Close"].iloc[-1])
            r["bx"] = round(r["nc"] - (xn / xe - 1) * 100, 1)

    rows.sort(key=lambda r: (r["d"], r.get("rs", 0)), reverse=True)
    rows = rows[:80]
    veri["rows"] = rows
    json.dump(veri, open(D + "guclu.json", "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))

    try:
        h = open(D + "index.html", encoding="utf-8").read()
        if 'id="guclutakip"' not in h:
            if "<footer" in h:
                h = h.replace("<footer", KUTU + "<footer", 1)
            else:
                h = h.replace("</body>", KUTU + "</body>", 1)
            h = h.replace("</body>", '<script id="guclutakipjs">' + JS + "</script></body>", 1)
            open(D + "index.html", "w", encoding="utf-8").write(h)
    except Exception as e:
        print("sayfa hata", e)
    print("guclu takip:", len(rows), "kayit")


main()
