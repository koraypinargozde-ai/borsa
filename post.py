import re, json, os, datetime, zlib, struct, urllib.request, urllib.parse
import yfinance as yf

ESIK = 70  # bu puan ve ustu hisseler Telegram'a bildirilir
SITE = "https://koraypinargozde-ai.github.io/borsa/"
D = "docs/"


def oku():
    h = open(D + "index.html", encoding="utf-8").read()
    m = re.search(r"Veri tarihi: (\S+) · Güncelleme: (\d\d\.\d\d\.\d{4} \d\d:\d\d)", h)
    if not m:
        return None
    rows = []
    for r in re.findall(r"<tr><td>(.*?)</td><td class=s>(\d+)</td><td>([\d.]+)</td><td>(-?[\d.]+)</td><td>([\d.]+)x</td><td>(\d+)</td><td>(.*?)</td></tr>", h):
        n = []
        if "Tavana" in r[6]:
            n.append("Tavana yakın")
        if "Kırılım" in r[6]:
            n.append("20 günlük kırılım")
        if "Para" in r[6]:
            n.append("Para girişi")
        rows.append([r[0], int(r[1]), float(r[2]), float(r[3]), float(r[4]), int(r[5]), " · ".join(n)])
    return m.group(1), m.group(2), rows


def eksik(x, s10):
    # sonucu henuz tamamlanmamis kayit mi?
    if x["r1"] is None or x["r3"] is None:
        return True
    return x["d"] >= s10 and ("mx" in x) and (x["mx"] is None or x["xr3"] is None)


def sonuclari_bul(hist, kes):
    s10 = (datetime.datetime.strptime(kes, "%Y-%m-%d") - datetime.timedelta(days=10)).strftime("%Y-%m-%d")
    bek = sorted({x["t"] for x in hist if eksik(x, s10)})
    if not bek:
        return
    tk = list(dict.fromkeys([t + ".IS" for t in bek] + ["XU100.IS", "THYAO.IS", "GARAN.IS"]))
    fiyat = {}
    for i in range(0, len(tk), 50):
        try:
            v = yf.download(tk[i:i + 50], period="3mo", group_by="ticker",
                            progress=False, threads=True, auto_adjust=False)
        except Exception as e:
            print("hata", e)
            continue
        for t in tk[i:i + 50]:
            try:
                s = v[t][["Close", "High"]].dropna()
                s = s[[k.strftime("%Y-%m-%d") <= kes for k in s.index]]
                fiyat[t[:-3]] = ([k.strftime("%Y-%m-%d") for k in s.index],
                                 list(s["Close"].values), list(s["High"].values))
            except Exception:
                pass
    xs = fiyat.get("XU100")
    for x in hist:
        if x["t"] not in fiyat:
            continue
        g, f, hh = fiyat[x["t"]]
        if x["d"] not in g:
            continue
        p = g.index(x["d"])
        # ilk gorulme kaydi (ps) varsa getiri o anki fiyattan, yoksa gunun kapanisindan olculur
        taban = x["px"] if x.get("ps") else f[p]
        if x["r1"] is None and p + 1 < len(g):
            x["r1"] = round(float(f[p + 1] / taban - 1) * 100, 2)
        if x["r3"] is None and p + 3 < len(g):
            x["r3"] = round(float(f[p + 3] / taban - 1) * 100, 2)
        if "mx" in x:
            # sonraki 3 islem gunundeki en yuksek fiyat
            if x["mx"] is None and p + 3 < len(g):
                x["mx"] = round(float(max(hh[p + 1:p + 4]) / taban - 1) * 100, 2)
            # BIST 100 getirisi: sinyal anindaki endeks seviyesinden (onceki kapanis x (1 + degisim))
            if xs and x["d"] in xs[0]:
                xm = dict(zip(xs[0], xs[1]))
                q = xs[0].index(x["d"])
                xc = x.get("xc")
                xb = xs[1][q - 1] * (1 + xc / 100) if (xc is not None and q >= 1) else xs[1][q]
                for n, key in ((1, "xr1"), (3, "xr3")):
                    if x[key] is None and p + n < len(g) and g[p + n] in xm:
                        x[key] = round(float(xm[g[p + n]] / xb - 1) * 100, 2)


def bant(hist, ad, lo, hi):
    a = [x for x in hist if lo <= x["sc"] < hi and x["r1"] is not None]
    b = [x for x in a if x["r3"] is not None]

    def ort(l, k):
        return round(sum(x[k] for x in l) / len(l), 2) if l else None
    poz = round(100 * sum(x["r1"] > 0 for x in a) / len(a)) if a else None
    return [ad, len(a), ort(a, "r1"), poz, ort(b, "r3")]


def sgrup(sig, kod, ad):
    # rozet grubu ozeti: adet, bekleyen, 1 gun, 3 gun, en iyi, BIST'e gore 1g, 3g
    l = [x for x in sig if x["k"] == kod]
    a = [x for x in l if x["r1"] is not None]
    b = [x for x in l if x["r3"] is not None]
    m = [x for x in l if x.get("mx") is not None]
    f1 = [x["r1"] - x["xr1"] for x in a if x.get("xr1") is not None]
    f3 = [x["r3"] - x["xr3"] for x in b if x.get("xr3") is not None]

    def ort(v):
        return round(sum(v) / len(v), 2) if v else None
    return [ad, len(a), len(l) - len(a), ort([x["r1"] for x in a]), ort([x["r3"] for x in b]),
            ort([x["mx"] for x in m]), ort(f1), ort(f3)]


def xu_c():
    # BIST 100 bugunku degisim yuzdesi (scan.py yazar)
    try:
        return json.load(open(D + "xu.json"))["c"]
    except Exception:
        return None


def bayrak(r, xc):
    # P = para girisi, G = GUCLU, E = ERKEN (sayfadaki rozet kurallariyla ayni)
    t = r[6]
    para = "Para" in t
    ustun = xc is None or r[3] > xc
    k = []
    if para:
        k.append("P")
    if r[1] >= 70 and r[4] >= 3 and 3 <= r[3] <= 8 and para and ustun:
        k.append("G")
    elif r[1] >= 60 and 0.5 <= r[3] <= 5 and r[4] >= 2 and r[5] >= 60 and para and "Tavana" not in t and ustun:
        k.append("E")
    return k


def ilk_gor(rows, d, simdi, xc):
    # Her hissenin o gun listede ILK gorundugu saat ve fiyat (docs/ilk.json),
    # ayrica her rozetin (P/G/E) ilk ciktigi an. Veri tarihi bugun degilse yeni kayit yazilmaz.
    F = D + "ilk.json"
    try:
        st = json.load(open(F)) if os.path.exists(F) else {}
    except Exception:
        st = {}
    if st.get("d") != d:
        st = {"d": d, "h": {}, "f": {}}
    st.setdefault("f", {})
    if d != simdi.strftime("%Y-%m-%d"):
        return st["h"], st["f"]
    saat = simdi.strftime("%H:%M")
    for r in rows:
        if r[0] not in st["h"]:
            st["h"][r[0]] = {"p": r[2], "s": saat, "c": r[3]}
        for k in bayrak(r, xc):
            gk = st["f"].setdefault(k, {})
            if r[0] not in gk:
                gk[r[0]] = {"p": r[2], "s": saat, "c": r[3], "x": xc, "sc": r[1]}
    json.dump(st, open(F, "w"), separators=(",", ":"))
    return st["h"], st["f"]


def telegram(rows, d, gt):
    tok, chat = os.environ.get("TG_TOKEN"), os.environ.get("TG_CHAT")
    if not tok or not chat:
        return
    S = D + "durum.json"
    st = json.load(open(S)) if os.path.exists(S) else {}
    if st.get("d") != d:
        st = {"d": d, "g": []}
    yeni = [r for r in rows if r[1] >= ESIK and r[0] not in st["g"]]
    if yeni:
        msg = "BIST tarayıcı (" + gt + ")\n" + "\n".join(
            f"{r[0]}  puan {r[1]}  %{r[3]:+.1f}  hacim {r[4]:.1f}x" for r in yeni) + "\n" + SITE
        try:
            urllib.request.urlopen(urllib.request.Request(
                "https://api.telegram.org/bot" + tok + "/sendMessage",
                urllib.parse.urlencode({"chat_id": chat, "text": msg}).encode()), timeout=20)
            st["g"] += [r[0] for r in yeni]
        except Exception as e:
            print("telegram hata", e)
    json.dump(st, open(S, "w"))


def png(n):
    def blok(t, b):
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xffffffff)
    ham = bytearray()
    for y in range(n):
        v = y / n
        ham.append(0)
        for x in range(n):
            u = x / n
            k = (16, 24, 32)
            for a, ust in ((0.26, 0.58), (0.44, 0.46), (0.62, 0.30)):
                if a <= u < a + 0.12 and ust <= v < 0.74:
                    k = (77, 179, 214)
            ham += bytes(k)
    return (b"\x89PNG\r\n\x1a\n" + blok(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0))
            + blok(b"IDAT", zlib.compress(bytes(ham), 9)) + blok(b"IEND", b""))


def uygulama_dosyalari():
    for n in (192, 512):
        if not os.path.exists(D + f"icon-{n}.png"):
            open(D + f"icon-{n}.png", "wb").write(png(n))
    json.dump({"name": "BIST Tavan Adayı Tarayıcı", "short_name": "BIST Tarayıcı",
               "start_url": "./", "scope": "./", "display": "standalone",
               "background_color": "#101820", "theme_color": "#101820",
               "icons": [{"src": f"icon-{n}.png", "sizes": f"{n}x{n}", "type": "image/png",
                          "purpose": "any maskable"} for n in (192, 512)]},
              open(D + "manifest.json", "w"), ensure_ascii=False)


SABLON = r'''<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#101820">
<link rel="manifest" href="manifest.json">
<link rel="apple-touch-icon" href="icon-192.png">
<title>BIST Tarayıcı</title>
<style>
:root{--bg:#eef2f5;--card:#fff;--ink:#16212b;--mute:#66768a;--line:#dbe3ea;--bar:#1b6f8f;--barbg:#e3ebf1;--up:#0e8a4f;--dn:#c0392b;--warn:#b4570a;--warnbg:#fdeed9;--chip:#16212b;--chipink:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#101820;--card:#18232e;--ink:#e6edf3;--mute:#8a9bb0;--line:#26343f;--bar:#4db3d6;--barbg:#26343f;--up:#3ecf8e;--dn:#ff7b6b;--warn:#f0a35a;--warnbg:#3a2a18;--chip:#e6edf3;--chipink:#101820}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-variant-numeric:tabular-nums;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
main{max-width:640px;margin:0 auto;padding:16px 12px 32px}
h1{font-size:20px;margin:0 0 2px}
.meta{color:var(--mute);font-size:13px;margin:0 0 14px}
.top{display:flex;gap:8px;margin-bottom:10px}
.top div{flex:1;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 10px}
.top b{display:block;font-size:20px}.top span{font-size:12px;color:var(--mute)}
details.b{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-bottom:8px}
summary{font-weight:600;cursor:pointer}
.b p{margin:6px 0 0;font-size:13px;color:var(--mute)}.b p b{color:var(--ink)}
table.st{width:100%;font-size:13px;border-collapse:collapse;margin-top:8px}
.st th,.st td{text-align:right;padding:4px 2px}.st th:first-child,.st td:first-child{text-align:left}.st th{color:var(--mute);font-weight:500}
input{width:100%;font:inherit;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--ink);margin:2px 0 8px}
.chips{display:flex;gap:6px;overflow-x:auto;margin-bottom:10px}
.chips button{font:inherit;font-size:13px;white-space:nowrap;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:6px 12px}
.chips button[aria-pressed="true"]{background:var(--chip);color:var(--chipink);border-color:var(--chip)}
.list{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.row{display:grid;grid-template-columns:64px 1fr 62px 54px;gap:8px;align-items:center;padding:10px 12px;width:100%;background:none;border:0;color:inherit;font:inherit;text-align:left;cursor:pointer}
.head{font-size:12px;color:var(--mute);border-bottom:1px solid var(--line);cursor:default}
.head button{font:inherit;color:inherit;background:none;border:0;padding:0;text-align:left}
.r{text-align:right}.head button.r{text-align:right}
.head button[aria-sort]{color:var(--ink);font-weight:600}
.item{border-bottom:1px solid var(--line)}.item:last-child{border:0}
.sym{font-weight:600}
.sc{display:flex;align-items:center;gap:8px}
.bar{flex:1;height:8px;background:var(--barbg);border-radius:4px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--bar)}
.sc em{font-style:normal;width:24px;text-align:right;font-weight:600}
.up{color:var(--up)}.dn{color:var(--dn)}
.det{display:none;padding:0 12px 12px;font-size:13px}
.item.open .det{display:block}
.det dl{display:grid;grid-template-columns:auto 1fr;gap:2px 12px;margin:0 0 8px}
.det dt{color:var(--mute)}.det dd{margin:0}
.tag{display:inline-block;font-size:11px;background:var(--warnbg);color:var(--warn);border-radius:4px;padding:1px 6px;margin-right:4px}
.det a{color:var(--bar)}
.empty{padding:24px;text-align:center;color:var(--mute)}
footer{color:var(--mute);font-size:12px;margin-top:14px}
button:focus-visible,input:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid var(--bar);outline-offset:2px}
</style></head><body><main>
<h1>BIST Tavan Adayı Tarayıcı</h1>
<p class="meta" id="meta"></p>
<div class="top" id="top"></div>
<details class="b" id="fark"></details>
<details class="b" id="sonuc"></details>
<details class="b" id="perf"></details>
<input id="q" type="search" placeholder="Hisse ara (örn. ETILR)" autocomplete="off" aria-label="Hisse ara">
<div class="chips" id="chips"></div>
<div class="list"><div class="row head" id="head"></div><div id="rows"></div></div>
<footer>Filtre amaçlıdır, yatırım tavsiyesi değildir. Puan; hacim patlaması, güçlü kapanış, yükseliş ve 20 günlük direnç kırılımından hesaplanır. Satıra dokununca ayrıntı açılır.</footer>
</main>
<script>
var V=__VERI__;
var D=V.rows;
var F=[["all","Hepsi"],["near","Tavana yakın"],["vol","Hacim 2x+"],["hi","Puan 50+"]];
var COLS=[["sym","Hisse"],["score","Puan"],["chg","Değ.%"],["vol","Hacim"]];
var IX={sym:0,score:1,chg:3,vol:4};
var S={sort:"score",dir:-1,f:"all",q:"",open:null};
function fmt(n){return n.toLocaleString("tr-TR",{minimumFractionDigits:2,maximumFractionDigits:2})}
function f1(n){return n.toLocaleString("tr-TR",{minimumFractionDigits:1,maximumFractionDigits:1})}
function sg(n){return (n>0?"+":"")+f1(n)}
function pass(r){
  if(S.q&&r[0].indexOf(S.q)<0)return false;
  if(S.f==="near")return r[6].indexOf("Tavana")>=0;
  if(S.f==="vol")return r[4]>=2;
  if(S.f==="hi")return r[1]>=50;
  return true;
}
function fark(){
  var h="<summary>Dünden fark"+(V.onceki?" ("+V.onceki+")":"")+"</summary>";
  if(!V.onceki)return h+"<p>Karşılaştırma bir sonraki iş gününden itibaren görünür.</p>";
  h+="<p><b>Yeni girenler:</b> "+(V.yeni.length?V.yeni.join(", "):"yok")+"</p>";
  h+="<p><b>Puanı sıçrayanlar:</b> "+(V.sic.length?V.sic.map(function(x){return x[0]+" "+x[1]+"→"+x[2]}).join(", "):"yok")+"</p>";
  h+="<p><b>Listeden düşenler:</b> "+(V.dusen.length?V.dusen.join(", "):"yok")+"</p>";
  return h;
}
function rt(v){return v==null?"<span style='color:var(--mute)'>-</span>":"<span class='"+(v>=0?"up":"dn")+"'>"+sg(v)+"%</span>"}
function sonuc(){
  var h="<summary>Sinyal sonrası ne oldu?</summary>";
  var say=V.stats.reduce(function(a,b){return a+b[1]},0);
  if(!say){
    h+="<p>Henüz sonuç yok. Bir hisse listeye girdikten sonraki ilk iş gününün kapanışında burada birikmeye başlar.</p>";
  }else{
    h+="<table class=st><tr><th>Puan</th><th>Adet</th><th>Ertesi gün</th><th>Yükselen</th><th>3 gün</th></tr>";
    V.stats.forEach(function(b){h+="<tr><td>"+b[0]+"</td><td>"+b[1]+"</td><td>"+(b[2]==null?"-":sg(b[2])+"%")+"</td><td>"+(b[3]==null?"-":"%"+b[3])+"</td><td>"+(b[4]==null?"-":sg(b[4])+"%")+"</td></tr>"});
    h+="</table>";
  }
  if(V.son&&V.son.length){
    h+="<p><b>Son sinyaller (puan 70+)</b></p><table class=st><tr><th>Hisse</th><th>İlk fiyat</th><th>Ertesi gün</th><th>3 gün</th></tr>";
    V.son.forEach(function(x){
      h+="<tr><td>"+x[0]+"<br><small style='color:var(--mute)'>"+x[1]+" "+(x[2]||"kapanış")+" · "+x[6]+" puan</small></td><td>"+fmt(x[3])+"</td><td>"+rt(x[4])+"</td><td>"+rt(x[5])+"</td></tr>";
    });
    h+="</table>";
  }
  return h+"<p>Getiriler, hissenin o gün listede ilk göründüğü fiyata göre (eski kayıtlarda günün kapanışına göre). Bugünkü sinyallerin sonucu sonraki günlerde dolar. Örnek sayısı azken yanıltıcı olabilir.</p>";
}
function perf(){
  var h="<summary>Sinyal grupları performansı</summary>";
  var P=V.perf||[];
  h+="<table class=st><tr><th>Grup</th><th>Adet</th><th>1 gün</th><th>3 gün</th><th>En iyi</th><th>BIST farkı</th></tr>";
  P.forEach(function(g){
    h+="<tr><td>"+g[0]+"</td><td>"+g[1]+(g[2]?" <small style='color:var(--mute)'>(+"+g[2]+")</small>":"")+"</td><td>"+rt(g[3])+"</td><td>"+rt(g[4])+"</td><td>"+rt(g[5])+"</td><td>"+rt(g[6])+"<br>"+rt(g[7])+"</td></tr>";
  });
  h+="</table>";
  var E=V.esig||[];
  h+="<p><b>🌱 Erken aday sinyalleri (son "+E.length+")</b></p>";
  if(!E.length){
    h+="<p>Henüz kayıt yok. Erken aday rozeti çıktıkça burada birikir.</p>";
  }else{
    h+="<table class=st><tr><th>Hisse</th><th>İlk fiyat</th><th>1 gün</th><th>3 gün</th><th>En iyi</th></tr>";
    E.forEach(function(x){
      h+="<tr><td>"+x[0]+"<br><small style='color:var(--mute)'>"+x[1]+" "+x[2]+" · "+x[6]+" puan</small></td><td>"+fmt(x[3])+"</td><td>"+rt(x[4])+"</td><td>"+rt(x[5])+"</td><td>"+rt(x[7])+"</td></tr>";
    });
    h+="</table>";
  }
  return h+"<p>Her sinyal, rozetin o gün ilk çıktığı andaki fiyata göre ölçülür. Adet yanındaki (+n) sonucu henüz belli olmayanlardır. En iyi: sonraki 3 işgünündeki en yüksek fiyatın ilk fiyata göre artışı. BIST farkı: hissenin getirisi eksi BIST 100 getirisi (üstte 1 gün, altta 3 gün). 💰 grubu ★ ve 🌱 sinyallerini de kapsar; bir hisse gün içinde birden fazla gruba girebilir. Kayıtlar bu özelliğin açıldığı günden itibaren birikir. Örnek sayısı azken yanıltıcı olabilir.</p>";
}
function draw(){
  document.getElementById("meta").textContent="Veri tarihi "+V.vt+" · Güncelleme "+V.gt+" · Veri gecikmelidir (Yahoo Finance)";
  document.getElementById("top").innerHTML=
    "<div><b>"+D.length+"</b><span>hisse listelendi</span></div>"+
    "<div><b>"+D.filter(function(r){return r[6].indexOf("Tavana")>=0}).length+"</b><span>tavana yakın</span></div>"+
    "<div><b>"+D.filter(function(r){return r[1]>=50}).length+"</b><span>puan 50 üstü</span></div>";
  document.getElementById("chips").innerHTML=F.map(function(f){return '<button data-f="'+f[0]+'" aria-pressed="'+(S.f===f[0])+'">'+f[1]+'</button>'}).join("");
  document.getElementById("head").innerHTML=COLS.map(function(c,i){
    var on=S.sort===c[0];
    return '<button data-s="'+c[0]+'" class="'+(i?"r":"")+'"'+(on?' aria-sort="'+(S.dir<0?"descending":"ascending")+'"':"")+'>'+c[1]+(on?(S.dir<0?" ↓":" ↑"):"")+'</button>'}).join("");
  var k=IX[S.sort],rows=D.filter(pass).sort(function(a,b){var x=a[k],y=b[k];return (x>y?1:x<y?-1:0)*S.dir});
  var el=document.getElementById("rows");
  if(!rows.length){el.innerHTML='<div class="empty">Bu filtreye uyan hisse yok.</div>';return}
  el.innerHTML=rows.map(function(r){
    var o=S.open===r[0];
    var dl=r[7]==="y"?"Listeye yeni girdi":(r[7]==null?"-":sg(r[7])+" puan");
    var il=r[8]?r[8][0]+" · "+fmt(r[8][1])+" TL"+(r[8][2]==null?"":" (%"+sg(r[8][2])+")"):"-";
    return '<div class="item'+(o?" open":"")+'"><button class="row" data-o="'+r[0]+'" aria-expanded="'+o+'">'+
      '<span class="sym">'+r[0]+'</span>'+
      '<span class="sc"><span class="bar"><i style="width:'+r[1]+'%"></i></span><em>'+r[1]+'</em></span>'+
      '<span class="r '+(r[3]>=0?"up":"dn")+'">'+sg(r[3])+'</span>'+
      '<span class="r">'+f1(r[4])+'x</span></button>'+
      '<div class="det"><dl><dt>Fiyat</dt><dd>'+fmt(r[2])+' TL</dd><dt>Kapanış gücü</dt><dd>%'+r[5]+'</dd>'+
      '<dt>Dünden</dt><dd>'+dl+'</dd>'+
      '<dt>İlk görüldü</dt><dd>'+il+'</dd>'+
      '<dt>Sinyal</dt><dd>'+(r[6]?r[6].split(" · ").map(function(t){return '<span class="tag">'+t+'</span>'}).join(""):"Belirgin sinyal yok")+'</dd></dl>'+
      '<a href="https://finance.yahoo.com/quote/'+r[0]+'.IS" target="_blank" rel="noopener">Yahoo Finance ile aç</a></div></div>'}).join("");
}
document.addEventListener("click",function(e){
  var b=e.target.closest("button");if(!b)return;
  if(b.dataset.f){S.f=b.dataset.f}
  else if(b.dataset.s){if(S.sort===b.dataset.s)S.dir*=-1;else{S.sort=b.dataset.s;S.dir=b.dataset.s==="sym"?1:-1}}
  else if(b.dataset.o){S.open=S.open===b.dataset.o?null:b.dataset.o}
  else return;
  draw();
});
document.getElementById("q").addEventListener("input",function(e){S.q=e.target.value.trim().toUpperCase();draw()});
document.getElementById("fark").innerHTML=fark();
document.getElementById("sonuc").innerHTML=sonuc();
document.getElementById("perf").innerHTML=perf();
var XU=null;
function guclu(r){return r[1]>=70&&r[4]>=3&&r[3]>=3&&r[3]<=8&&(r[6]+"").indexOf("Para")>=0&&(XU==null||r[3]>XU)}
var draw0=draw;
draw=function(){draw0();document.querySelectorAll("#rows .item").forEach(function(it){var s=it.querySelector(".sym");if(!s)return;var k=s.textContent.replace(/[^A-Z0-9]/g,"");var r=D.filter(function(z){return z[0]===k})[0];if(!r||!guclu(r))return;s.insertAdjacentHTML("beforeend"," <b class='up'>★</b>");var dd=it.querySelectorAll(".det dd");if(dd.length)dd[dd.length-1].insertAdjacentHTML("afterbegin","<span class='tag'>GÜÇLÜ</span>")})};
fetch("xu.json?v="+Date.now()).then(function(r){return r.json()}).then(function(j){XU=j.c;draw()}).catch(function(){});
draw();
function baskin(j){var s=0,n=[];if(j.a!=null&&j.d!=null&&j.a+j.d>0){var o=j.a/(j.a+j.d);s+=o>=0.55?1:(o<=0.45?-1:0);n.push("yükselen "+j.a+" / düşen "+j.d)}if(j.v!=null){s+=j.v>0?1:(j.v<0?-1:0);n.push(j.v>0?"VWAP üstünde":(j.v<0?"VWAP altında":"VWAP civarında"))}if(!n.length)return null;return [s>=1?"Alıcı baskın":(s<=-1?"Satıcı baskın":"Dengeli"),s,n.join(" · ")]}
fetch("xu.json?v="+Date.now()).then(function(r){return r.json()}).then(function(j){var b=baskin(j);var d=document.createElement("div");d.className="top";d.innerHTML="<div><b class='"+(j.c>=0?"up":"dn")+"'>"+(j.c>0?"+":"")+f1(j.c)+"%</b><span>BIST 100 bugün"+(b?" · <strong class='"+(b[1]>=1?"up":(b[1]<=-1?"dn":"x"))+"'>"+b[0]+"</strong>":"")+"</span>"+(b?"<span style='display:block'>"+b[2]+"</span>":"")+"</div>";document.getElementById("top").before(d)}).catch(function(){});
function erken(r){var t=r[6]+"";return r[1]>=60&&r[3]>=0.5&&r[3]<=5&&r[4]>=2&&r[5]>=60&&t.indexOf("Para")>=0&&t.indexOf("Tavana")<0&&(XU==null||r[3]>XU)}
F.push(["early","Erken aday"]);
var pass0=pass;
pass=function(r){if(S.f==="early")return (!S.q||r[0].indexOf(S.q)>=0)&&erken(r);return pass0(r)};
var draw1=draw;
draw=function(){draw1();document.querySelectorAll("#rows .item").forEach(function(it){var s=it.querySelector(".sym");if(!s)return;var k=s.textContent.replace(/[^A-Z0-9]/g,"");var r=D.filter(function(z){return z[0]===k})[0];if(!r||guclu(r)||!erken(r))return;s.insertAdjacentHTML("beforeend"," <b class='up'>🌱</b>");var dt=it.querySelectorAll(".det dt");for(var i=0;i<dt.length;i++){if(dt[i].textContent==="Sinyal"&&dt[i].nextElementSibling){dt[i].nextElementSibling.insertAdjacentHTML("afterbegin","<span class='tag'>ERKEN</span>")}}})};
draw();
</script></body></html>'''


def main():
    s = oku()
    if not s or not s[2]:
        print("veri yok, sayfa degismedi")
        return
    vt, gt, rows = s
    d = "-".join(reversed(vt.split(".")))
    simdi = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    bugun_str = simdi.strftime("%Y-%m-%d")
    kapanis = simdi.hour * 60 + simdi.minute >= 18 * 60 + 15
    kes = bugun_str if kapanis else (simdi - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    xc = xu_c()
    ilk, fl = ilk_gor(rows, d, simdi, xc)

    G = D + "gecmis.json"
    hist = json.load(open(G)) if os.path.exists(G) else []
    gunler = sorted({x["d"] for x in hist if x["d"] < d})
    onc_gun = gunler[-1] if gunler else None
    onc = {x["t"]: x["sc"] for x in hist if x["d"] == onc_gun}

    if kapanis:
        kayit = []
        for r in rows:
            k = {"d": d, "t": r[0], "sc": r[1], "px": r[2], "r1": None, "r3": None}
            if r[0] in ilk:
                k["px"] = ilk[r[0]]["p"]
                k["ps"] = ilk[r[0]]["s"]
                if ilk[r[0]].get("c") is not None:
                    k["c0"] = ilk[r[0]]["c"]
            kayit.append(k)
        hist = [x for x in hist if x["d"] != d] + kayit
    sinir = (simdi - datetime.timedelta(days=120)).strftime("%Y-%m-%d")
    hist = [x for x in hist if x["d"] >= sinir]

    # Rozet sinyalleri (P = para girisi, G = GUCLU, E = ERKEN): docs/sinyal.json
    SG = D + "sinyal.json"
    try:
        sig = json.load(open(SG)) if os.path.exists(SG) else []
    except Exception:
        sig = []
    if d == bugun_str:
        eski = {(x["t"], x["k"]): x for x in sig if x["d"] == d}
        sig = [x for x in sig if x["d"] != d]
        for kod, dk in fl.items():
            for t, v in dk.items():
                e = eski.get((t, kod))
                sig.append(e if e else {
                    "d": d, "t": t, "k": kod, "px": v["p"], "ps": v["s"], "sc": v["sc"],
                    "c0": v["c"], "xc": v.get("x"),
                    "r1": None, "r3": None, "mx": None, "xr1": None, "xr3": None})
    sig = [x for x in sig if x["d"] >= sinir]

    sonuclari_bul(hist + sig, kes)
    json.dump(hist, open(G, "w"), separators=(",", ":"))
    json.dump(sig, open(SG, "w"), separators=(",", ":"))

    for r in rows:
        r.append(None if not onc else ("y" if r[0] not in onc else r[1] - onc[r[0]]))
        r.append([ilk[r[0]]["s"], ilk[r[0]]["p"], ilk[r[0]].get("c")] if r[0] in ilk else None)
    bugun = {r[0] for r in rows}

    # Son sinyaller (puan 70+): bugunku satirlar + gecmis kayitlar, hisse adi ve ilk gorulme fiyatiyla
    def gm(t):
        return t[8:10] + "." + t[5:7]
    bugun_son = [[r[0], gm(d), ilk[r[0]]["s"] if r[0] in ilk else None,
                  ilk[r[0]]["p"] if r[0] in ilk else r[2], None, None, r[1]]
                 for r in rows if r[1] >= 70][:8]
    gecmis_son = [[x["t"], gm(x["d"]), x.get("ps"), x["px"], x["r1"], x["r3"], x["sc"]]
                  for x in sorted((x for x in hist if x["sc"] >= 70 and x["d"] != d),
                                  key=lambda x: (x["d"], x["sc"]), reverse=True)]
    son = (bugun_son + gecmis_son)[:20]

    # Erken aday listesi: tarih, saat, ilk fiyat, 1 gun, 3 gun, puan, en iyi
    esig = [[x["t"], gm(x["d"]), x.get("ps"), x["px"], x["r1"], x["r3"], x["sc"], x.get("mx")]
            for x in sorted((x for x in sig if x["k"] == "E"),
                            key=lambda x: (x["d"], x.get("ps") or ""), reverse=True)][:20]
    perf = [sgrup(sig, "E", "🌱 Erken aday"), sgrup(sig, "G", "★ GÜÇLÜ"), sgrup(sig, "P", "💰 Para girişi")]

    veri = {
        "vt": vt, "gt": gt, "rows": rows,
        "onceki": ".".join(reversed(onc_gun.split("-"))) if onc_gun else None,
        "yeni": [r[0] for r in rows if onc and r[0] not in onc],
        "dusen": [t for t in onc if t not in bugun],
        "sic": [[r[0], onc[r[0]], r[1]] for r in rows if r[0] in onc and r[1] - onc[r[0]] >= 15],
        "stats": [bant(hist, "70+", 70, 101), bant(hist, "50-69", 50, 70), bant(hist, "0-49", 0, 50)],
        "son": son,
        "perf": perf,
        "esig": esig,
    }
    telegram(rows, d, gt)
    uygulama_dosyalari()
    open(D + "index.html", "w", encoding="utf-8").write(
        SABLON.replace("__VERI__", json.dumps(veri, ensure_ascii=False)))
    print("sayfa yenilendi:", len(rows), "hisse")


main()
