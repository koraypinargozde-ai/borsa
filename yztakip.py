import json
import os
import shutil
from datetime import date, timedelta
import yfinance as yf

D = "docs/"
ARA = 30

KUTU = '<div id="yztakip" style="margin:12px;padding:10px;border:1px solid rgba(128,128,128,.3);border-radius:10px;font-size:13px"></div>'

JS = r'''
(function(){
var B=document.getElementById("yztakip");if(!B)return;
function f(x){return x==null?"-":(x>0?"+":"")+String(x).replace(".",",")+"%"}
function c(x){return x==null?"":(x>0?"color:var(--up)":"color:var(--dn,#e5484d)")}
fetch("yz.json?v="+Date.now()).then(function(r){return r.json()}).then(function(j){
var R=j.rows||[];
var h='<b>▲ Hacim zirvesi takibi ('+R.length+')</b><div style="opacity:.7;font-size:11px;margin:2px 0 6px">Giriş: ▲ ilk göründüğü andaki fiyat. 1 ay / 3 ay: giriş tarihinden sonraki ilk kapanış.</div>';
if(!R.length){B.innerHTML=h+"Henüz kayıt yok";return}
h+='<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12px"><tr style="text-align:right;opacity:.7"><th style="text-align:left">Hisse</th><th>Giriş</th><th>1 ay</th><th>3 ay</th><th>Şimdi</th></tr>';
R.forEach(function(r){
h+='<tr style="text-align:right;border-top:1px solid rgba(128,128,128,.2)"><td style="text-align:left"><b>'+r.s+'</b><br><span style="opacity:.7">'+r.d.slice(8)+'.'+r.d.slice(5,7)+'</span></td><td>'+String(r.p).replace(".",",")+'</td><td style="'+c(r.a)+'">'+f(r.a)+'</td><td style="'+c(r.u)+'">'+f(r.u)+'</td><td style="'+c(r.nc)+'">'+f(r.nc)+'<br><span style="opacity:.7">'+String(r.n).replace(".",",")+'</span></td></tr>';
});
B.innerHTML=h+'</table></div>';
}).catch(function(){});
})();
'''


def oku(p, v):
    try:
        return json.load(open(D + p, encoding="utf-8"))
    except Exception:
        return v


def yz_oku():
    # dosya hiç yoksa: ilk çalışma, boş liste ile başla
    yol = D + "yz.json"
    if not os.path.exists(yol):
        return []
    # dosya var ama okunamıyorsa: DURMA, üzerine yazma
    try:
        j = json.load(open(yol, encoding="utf-8"))
        rows = j["rows"]
        if not isinstance(rows, list):
            raise ValueError("rows liste degil")
        return rows
    except Exception as e:
        raise SystemExit("yz.json okunamadi, uzerine yazilmadi: " + str(e))


def main():
    hac = oku("hacim.json", {})
    yz = [s for s, x in hac.items() if x[1]]
    rows = yz_oku()
    onceki = len(rows)

    # okunan sağlam dosyanın yedeği
    if onceki:
        try:
            shutil.copyfile(D + "yz.json", D + "yz_yedek.json")
        except Exception as e:
            print("yedek alinamadi", e)

    tum = sorted(set(yz) | {r["s"] for r in rows})
    d = None
    if tum:
        try:
            d = yf.download([s + ".IS" for s in tum], period="2y",
                            group_by="ticker", progress=False,
                            threads=True, auto_adjust=False)
        except Exception as e:
            print("hata", e)

    def seri(s):
        try:
            c = d[s + ".IS"]["Close"].dropna()
            return c if len(c) else None
        except Exception:
            return None

    yeni = 0
    for s in yz:
        c = seri(s)
        if c is None:
            continue
        t = c.index[-1].date()
        if any(r["s"] == s and abs((t - date.fromisoformat(r["d"])).days) < ARA
               for r in rows):
            continue
        rows.append({"s": s, "d": t.isoformat(), "p": round(float(c.iloc[-1]), 2)})
        yeni += 1

    for r in rows:
        c = seri(r["s"])
        if c is None:
            continue
        t0 = date.fromisoformat(r["d"])
        son = c.index[-1].date()

        def at(gun):
            h = t0 + timedelta(days=gun)
            if son < h:
                return None
            for i, v in c.items():
                if i.date() >= h:
                    return float(v)
            return None

        p = r["p"]
        for k, g in (("a", 30), ("u", 91)):
            v = at(g)
            r[k] = round((v / p - 1) * 100, 1) if v else None
        n = float(c.iloc[-1])
        r["n"] = round(n, 2)
        r["nc"] = round((n / p - 1) * 100, 1)

    rows.sort(key=lambda r: r["d"], reverse=True)

    # kayıt sayısı azalmışsa yazma
    if len(rows) < onceki:
        raise SystemExit("kayit sayisi azaldi, yazilmadi")

    # önce geçici dosyaya yaz, sonra değiştir
    tmp = D + "yz.json.tmp"
    json.dump({"rows": rows}, open(tmp, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, D + "yz.json")

    h = open(D + "index.html", encoding="utf-8").read()
    if 'id="yztakip"' not in h:
        if "<footer" in h:
            h = h.replace("<footer", KUTU + "<footer", 1)
        else:
            h = h.replace("</body>", KUTU + "</body>", 1)
        h = h.replace("</body>", '<script id="yztakipjs">' + JS + "</script></body>", 1)
        open(D + "index.html", "w", encoding="utf-8").write(h)
    print("yz takip:", len(rows), "kayit,", yeni, "yeni")


main()
