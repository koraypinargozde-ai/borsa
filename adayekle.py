import json
from datetime import date, datetime, timedelta
import re
import numpy as np, pandas as pd, yfinance as yf

D = "docs/"
ARA = 30        # aynı hisse en az 30 gün sonra tekrar eklenir
TOP = 10        # günde en çok yeni sinyal (RS63'e göre en güçlüler)
LIQ = 2_000_000
MAXG = 63       # gün gün takip (işlem günü, ~3 ay)
HG = 40         # hedef/stop penceresi (~2 ay)
TGT = 40
STOP = 20
SAKLA = 130     # kayıtlar kaç takvim günü tutulur

KUTU = '<div id="adaytakip" style="margin:12px;padding:10px;border:1px solid rgba(128,128,128,.3);border-radius:10px;font-size:13px"></div>'

JS = r'''
(function(){
var B=document.getElementById("adaytakip");if(!B)return;
function f(x){return x==null?"-":(x>0?"+":"")+String(x).replace(".",",")+"%"}
function c(x){return x==null?"":(x>0?"color:var(--up)":"color:var(--dn,#e5484d)")}
function dm(s){return s?s.slice(8)+"."+s.slice(5,7):""}
function p(x){return x==null?"-":String(x).replace(".",",")}
function ort(R,i){var t=0,k=0;R.forEach(function(r){var g=r.g||[];if(g.length>i){t+=g[i];k++}});return k?[Math.round(t/k*10)/10,k]:null}
fetch("aday.json?v="+Date.now()).then(function(r){return r.json()}).then(function(j){
var R=j.rows||[];
var h='<b>🎯 Aday takibi ('+R.length+')</b><div style="opacity:.7;font-size:11px;margin:2px 0 6px">Kural: 3 ayda BIST 100den güçlü (ilk %20) + CMF>0,05 + OBV yükseliyor + likit. Giriş: sinyalin ertesi günü açılış. Gün sütunları kapanış getirisi (maliyet hariç). ✅ = ilk 40 günde +%40a değdi, ❌ = önce -%20ye değdi. Satıra dokun: gün gün.</div>';
if(!R.length){B.innerHTML=h+"Henüz kayıt yok";return}
var H=R.filter(function(r){return r.hs==="H"}).length;
var S=R.filter(function(r){return r.hs==="S"}).length;
var O=R.filter(function(r){return !r.hs&&r.e!=null}).length;
h+='<div style="margin-bottom:6px">Hedef ✅ <b>'+H+'</b> · Stop ❌ <b>'+S+'</b> · açık <b>'+O+'</b></div>';
var lab=[[20,"1 ay (21.g)"],[39,"2 ay (40.g)"],[62,"3 ay (63.g)"]];
var s2="";
lab.forEach(function(L){var o=ort(R,L[0]);if(o)s2+='<span style="margin-right:12px">'+L[1]+': <b style="'+c(o[0])+'">'+f(o[0])+'</b> <span style="opacity:.7">('+o[1]+')</span></span>'});
if(s2)h+='<div style="margin-bottom:6px">Ortalama: '+s2+'</div>';
var ok=R.filter(function(r){return r.nc!=null});
if(ok.length){
var t1=0,up=0;
ok.forEach(function(r){t1+=r.nc;if(r.nc>0)up++});
h+='<div style="margin-bottom:6px">Ortalama şimdi: <b style="'+c(t1)+'">'+f(Math.round(t1/ok.length*10)/10)+'</b> · artıda: <b>'+up+'/'+ok.length+'</b></div>';
}
h+='<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><tr style="text-align:right;opacity:.7"><th style="text-align:left">Hisse</th><th>Giriş</th><th>5.g</th><th>21.g</th><th>40.g</th><th>Şimdi</th></tr>';
R.slice(0,60).forEach(function(r){
var g=r.g||[];
function G(i){return g.length>i?g[i]:null}
var gir=r.e!=null?p(r.e):'<span style="opacity:.7">bekliyor</span>';
var im=r.hs==="H"?" ✅":(r.hs==="S"?" ❌":"");
h+='<tr class="ar" style="text-align:right;border-top:1px solid rgba(128,128,128,.2);cursor:pointer"><td style="text-align:left"><b>'+r.s+'</b>'+im+'<br><span style="opacity:.7">'+dm(r.d)+'</span></td><td>'+gir+'</td>';
[4,20,39].forEach(function(i){h+='<td style="'+c(G(i))+'">'+f(G(i))+'</td>'});
h+='<td style="'+c(r.nc)+'">'+f(r.nc)+'<br><span style="opacity:.7">'+p(r.n)+'</span></td></tr>';
var d='';
g.forEach(function(v,i){d+='<span style="display:inline-block;margin:2px 10px 2px 0;'+c(v)+'">'+(i+1)+'.g '+f(v)+'</span>'});
if(!g.length)d='<span style="opacity:.7">Henüz kapanmış gün yok</span>';
var hd=r.hs==="H"?"Hedef +%40: "+r.hg+". günde":(r.hs==="S"?"Stop -%20: "+r.hg+". günde":"Hedef/stop henüz yok ("+(r.kg||0)+"/40 gün)");
h+='<tr style="display:none"><td colspan="6" style="text-align:left;padding:4px 0 8px;font-size:11px"><div style="opacity:.7;margin-bottom:3px">Sinyal '+dm(r.d)+' kapanış '+p(r.sc)+' · RS63 '+f(r.rs)+' · 63g '+f(r.r)+' · CMF '+p(r.cm)+(r.ek?' · giriş '+dm(r.ek)+' açılış':'')+'<br>'+hd+'</div>'+d+'</td></tr>';
});
B.innerHTML=h+'</table></div>'+(R.length>60?'<div style="opacity:.7;font-size:11px;margin-top:4px">Son 60 kayıt gösteriliyor, özet hepsi için.</div>':'');
B.querySelectorAll("tr.ar").forEach(function(t){
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

    veri = oku("aday.json", {})
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
    if son != L.isoformat():
        tum = dl(T, "1y")
        xc = xuk["Close"]
        rs_all, ad = {}, {}
        for s, x in tum.items():
            xk = kapali(x)
            if len(xk) < 130 or xk.index[-1].date() != L:
                continue
            c, h, l, v = xk["Close"], xk["High"], xk["Low"], xk["Volume"]
            av = v.shift(1).rolling(20).mean().iloc[-1]
            if not (av * c.iloc[-1] >= LIQ):
                continue
            xcc = xc.reindex(xk.index, method="ffill")
            r63 = ((c.iloc[-1] / c.iloc[-64] - 1) - (xcc.iloc[-1] / xcc.iloc[-64] - 1)) * 100
            own = (c.iloc[-1] / c.iloc[-64] - 1) * 100
            rg = (h - l).replace(0, np.nan)
            mf = (((c - l) - (h - c)) / rg).fillna(0)
            cmf = ((mf * v).rolling(20).sum() / v.rolling(20).sum()).iloc[-1]
            obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
            obvup = bool(obv.iloc[-1] > obv.iloc[-21])
            if np.isnan(r63) or np.isnan(cmf):
                continue
            rs_all[s] = float(r63)
            ad[s] = (float(r63), float(cmf), obvup, float(c.iloc[-1]), float(own))
        if len(rs_all) > 100:
            pc = pd.Series(rs_all).rank(pct=True)
            cand = [(s, a) for s, a in ad.items()
                    if pc[s] >= 0.8 and a[1] > 0.05 and a[2]]
            cand.sort(key=lambda z: -z[1][0])
            yeni = 0
            for s, a in cand[:TOP]:
                if any(r["s"] == s and (L - date.fromisoformat(r["d"])).days < ARA
                       for r in rows):
                    continue
                rows.append({"s": s, "d": L.isoformat(), "sc": round(a[3], 2),
                             "rs": round(a[0], 1), "r": round(a[4], 1),
                             "cm": round(a[1], 2), "e": None, "ek": None,
                             "g": [], "hs": None, "hg": None, "kg": 0})
                yeni += 1
            veri["son"] = L.isoformat()
            print("tarama:", len(rs_all), "hisse,", len(cand), "aday,", yeni, "yeni")
        else:
            print("tarama yetersiz veri:", len(rs_all))

    rows = [r for r in rows if (L - date.fromisoformat(r["d"])).days <= SAKLA]
    eksik = [r["s"] for r in rows if r["s"] not in tum]
    if eksik:
        tum.update(dl(sorted(set(eksik)), "1y"))

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
        hs, hg = None, None
        pen = kap.iloc[:HG]
        for i, (hh, ll) in enumerate(zip(pen["High"], pen["Low"])):
            up = (float(hh) / e - 1) * 100
            dn = (float(ll) / e - 1) * 100
            if dn <= -STOP:
                hs, hg = "S", i + 1
                break
            if up >= TGT:
                hs, hg = "H", i + 1
                break
        r["hs"], r["hg"], r["kg"] = hs, hg, len(pen)

    rows.sort(key=lambda r: (r["d"], r.get("rs", 0)), reverse=True)
    rows = rows[:400]
    veri["rows"] = rows
    json.dump(veri, open(D + "aday.json", "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))

    try:
        h = open(D + "index.html", encoding="utf-8").read()
        if 'id="adaytakip"' not in h:
            if "<footer" in h:
                h = h.replace("<footer", KUTU + "<footer", 1)
            else:
                h = h.replace("</body>", KUTU + "</body>", 1)
            h = h.replace("</body>", '<script id="adaytakipjs">' + JS + "</script></body>", 1)
            open(D + "index.html", "w", encoding="utf-8").write(h)
    except Exception as e:
        print("sayfa hata", e)
    print("aday takip:", len(rows), "kayit")


main()
