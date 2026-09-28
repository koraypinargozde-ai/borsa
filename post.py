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
        rows.append([r[0], int(r[1]), float(r[2]), float(r[3]), float(r[4]), int(r[5]), " · ".join(n)])
    return m.group(1), m.group(2), rows


def sonuclari_bul(hist, kes):
    bek = sorted({x["t"] for x in hist if x["r1"] is None or x["r3"] is None})
    if not bek:
        return
    tk = [t + ".IS" for t in bek] + ["THYAO.IS", "GARAN.IS"]
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
                s = v[t]["Close"].dropna()
                s = s[[k.strftime("%Y-%m-%d") <= kes for k in s.index]]
                fiyat[t[:-3]] = ([k.strftime("%Y-%m-%d") for k in s.index], list(s.values))
            except Exception:
                pass
    for x in hist:
        if x["t"] not in fiyat:
            continue
        g, f = fiyat[x["t"]]
        if x["d"] not in g:
            continue
        p = g.index(x["d"])
        if x["r1"] is None and p + 1 < len(g):
            x["r1"] = round(float(f[p + 1] / f[p] - 1) * 100, 2)
        if x["r3"] is None and p + 3 < len(g):
            x["r3"] = round(float(f[p + 3] / f[p] - 1) * 100, 2)


def bant(hist, ad, lo, hi):
    a = [x for x in hist if lo <= x["sc"] < hi and x["r1"] is not None]
    b = [x for x in a if x["r3"] is not None]

    def ort(l, k):
        return round(sum(x[k] for x in l) / len(l), 2) if l else None
    poz = round(100 * sum(x["r1"] > 0 for x in a) / len(a)) if a else None
    return [ad, len(a), ort(a, "r1"), poz, ort(b, "r3")]


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
function sonuc(){
  var h="<summary>Sinyal sonrası ne oldu?</summary>";
  var say=V.stats.reduce(function(a,b){return a+b[1]},0);
  if(!say)return h+"<p>Henüz sonuç yok. Bir hisse listeye girdikten sonraki ilk iş gününün kapanışında burada birikmeye başlar.</p>";
  h+="<table class=st><tr><th>Puan</th><th>Adet</th><th>Ertesi gün</th><th>Yükselen</th><th>3 gün</th></tr>";
  V.stats.forEach(function(b){h+="<tr><td>"+b[0]+"</td><td>"+b[1]+"</td><td>"+(b[2]==null?"-":sg(b[2])+"%")+"</td><td>"+(b[3]==null?"-":"%"+b[3])+"</td><td>"+(b[4]==null?"-":sg(b[4])+"%")+"</td></tr>"});
  return h+"</table><p>Getiriler, hissenin listeye girdiği günün kapanışına göre. Örnek sayısı azken yanıltıcı olabilir.</p>";
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
    return '<div class="item'+(o?" open":"")+'"><button class="row" data-o="'+r[0]+'" aria-expanded="'+o+'">'+
      '<span class="sym">'+r[0]+'</span>'+
      '<span class="sc"><span class="bar"><i style="width:'+r[1]+'%"></i></span><em>'+r[1]+'</em></span>'+
      '<span class="r '+(r[3]>=0?"up":"dn")+'">'+sg(r[3])+'</span>'+
      '<span class="r">'+f1(r[4])+'x</span></button>'+
      '<div class="det"><dl><dt>Fiyat</dt><dd>'+fmt(r[2])+' TL</dd><dt>Kapanış gücü</dt><dd>%'+r[5]+'</dd>'+
      '<dt>Dünden</dt><dd>'+dl+'</dd>'+
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
    kapanis = simdi.hour * 60 + simdi.minute >= 18 * 60 + 15
    kes = simdi.strftime("%Y-%m-%d") if kapanis else (simdi - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    G = D + "gecmis.json"
    hist = json.load(open(G)) if os.path.exists(G) else []
    gunler = sorted({x["d"] for x in hist if x["d"] < d})
    onc_gun = gunler[-1] if gunler else None
    onc = {x["t"]: x["sc"] for x in hist if x["d"] == onc_gun}

    if kapanis:
        hist = [x for x in hist if x["d"] != d] + [
            {"d": d, "t": r[0], "sc": r[1], "px": r[2], "r1": None, "r3": None} for r in rows]
    sinir = (simdi - datetime.timedelta(days=120)).strftime("%Y-%m-%d")
    hist = [x for x in hist if x["d"] >= sinir]
    sonuclari_bul(hist, kes)
    json.dump(hist, open(G, "w"), separators=(",", ":"))

    for r in rows:
        r.append(None if not onc else ("y" if r[0] not in onc else r[1] - onc[r[0]]))
    bugun = {r[0] for r in rows}
    veri = {
        "vt": vt, "gt": gt, "rows": rows,
        "onceki": ".".join(reversed(onc_gun.split("-"))) if onc_gun else None,
        "yeni": [r[0] for r in rows if onc and r[0] not in onc],
        "dusen": [t for t in onc if t not in bugun],
        "sic": [[r[0], onc[r[0]], r[1]] for r in rows if r[0] in onc and r[1] - onc[r[0]] >= 15],
        "stats": [bant(hist, "70+", 70, 101), bant(hist, "50-69", 50, 70), bant(hist, "0-49", 0, 50)],
    }
    telegram(rows, d, gt)
    uygulama_dosyalari()
    open(D + "index.html", "w", encoding="utf-8").write(
        SABLON.replace("__VERI__", json.dumps(veri, ensure_ascii=False)))
    print("sayfa yenilendi:", len(rows), "hisse")


main()
