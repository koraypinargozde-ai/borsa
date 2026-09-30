import re, json, os, datetime
import yfinance as yf

D = "docs/"


def fiyatlar():
    src = open("scan.py", encoding="utf-8").read()
    T = list(dict.fromkeys(re.search(r'T = """(.*?)"""', src, re.S).group(1).split()))
    tk = [t + ".IS" for t in T]
    p = {}
    for i in range(0, len(tk), 50):
        grup = tk[i:i + 50]
        try:
            d = yf.download(grup, period="5d", group_by="ticker", progress=False,
                            threads=True, auto_adjust=False)
        except Exception as e:
            print("hata", e)
            continue
        for t in grup:
            try:
                s = d[t]["Close"].dropna()
                if len(s):
                    p[t[:-3]] = round(float(s.iloc[-1]), 2)
            except Exception:
                pass
    return T, p


CSS = r'''
.dfg{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:8px 0}
.dfg input,.dfg select{margin:0;padding:8px 10px;font-size:14px}
.dfg select{font:inherit;font-size:14px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--ink)}
.dp{border-top:1px solid var(--line);padding:8px 0;font-size:13px;display:grid;gap:2px}
#defter button{font:inherit;font-size:13px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:5px 10px}
#defter .go{background:var(--chip);color:var(--chipink);border-color:var(--chip);grid-column:1/-1;padding:9px}
.dekle{font:inherit;font-size:13px;border:1px solid var(--line);background:none;color:var(--bar);border-radius:8px;padding:4px 10px;margin-top:6px}
.dn2{background:rgba(192,57,43,.15);color:var(--dn)}
.up2{background:rgba(14,138,79,.15);color:var(--up)}
'''

JS = r'''
(function(){
var el=document.getElementById("defter");if(!el)return;
var K="borsa_defter_v1",P={},TK=[],GT="",L=[];
try{L=JSON.parse(localStorage.getItem(K)||"[]")}catch(e){L=[]}
function kaydet(){try{localStorage.setItem(K,JSON.stringify(L))}catch(e){alert("Kayıt yapılamadı, tarayıcı hafızası kapalı olabilir.")}}
function num(s){var n=parseFloat(String(s).replace(",","."));return isFinite(n)&&n>0?n:null}
function f2(n){return n.toLocaleString("tr-TR",{minimumFractionDigits:2,maximumFractionDigits:2})}
function sg(n){return (n>0?"+":"")+f2(n)+"%"}
function g(id){return document.getElementById(id)}
el.innerHTML='<summary>Defterim</summary>'+
 '<datalist id="dtk"></datalist>'+
 '<div class="dfg"><input id="d_t" list="dtk" placeholder="Hisse (ETILR)" autocapitalize="characters" autocomplete="off">'+
 '<input id="d_p" inputmode="decimal" placeholder="Giriş fiyatı">'+
 '<input id="d_a" inputmode="decimal" placeholder="Adet (isteğe bağlı)">'+
 '<select id="d_r"><option value="d">Deneme (kâğıt üstü)</option><option value="g">Gerçek alım</option></select>'+
 '<input id="d_s" inputmode="decimal" placeholder="Stop % (örn. 7)">'+
 '<input id="d_h" inputmode="decimal" placeholder="Hedef % (örn. 10)">'+
 '<button class="go" data-dgo="1">Deftere ekle</button></div>'+
 '<div id="dl"></div><div id="dm"></div>'+
 '<p><button data-dyed="k">Yedeği kopyala</button> <button data-dyed="y">Yedeği yükle</button></p>'+
 '<p>Kayıtlar sadece bu telefonun tarayıcısında durur. Komisyon ve vergi hesaba katılmaz.</p>';
function ciz(){
 var acik=L.filter(function(x){return !x.c}),kap=L.filter(function(x){return x.c}),h="";
 el.querySelector("summary").textContent="Defterim ("+acik.length+" açık)";
 acik.forEach(function(x){
  var cur=P[x.t],kz=cur?(cur/x.px-1)*100:null,dur="";
  if(kz!=null){
   if(x.s&&kz<=-x.s)dur=' <span class="tag dn2">Stop seviyesinde</span>';
   else if(x.s&&kz<=-x.s+2)dur=' <span class="tag">Stopa yakın</span>';
   else if(x.h&&kz>=x.h)dur=' <span class="tag up2">Hedefe ulaştı</span>';
  }
  if(typeof V!=="undefined"&&V.rows){var lr=V.rows.filter(function(z){return z[0]===x.t})[0];if(!lr)dur+=' <span class="tag dn2">ÇIKIŞ: listeden düştü</span>';else if(lr[1]<50)dur+=' <span class="tag dn2">ÇIKIŞ: puan '+lr[1]+'</span>';}
  h+='<div class="dp"><div><b>'+x.t+'</b> <span class="tag">'+(x.r==="g"?"Gerçek":"Deneme")+'</span>'+dur+'</div>'+
   '<div>Giriş '+f2(x.px)+(x.a?" · "+x.a+" adet":"")+(cur?" · Şimdi "+f2(cur):" · fiyat yok")+'</div>'+
   (kz==null?"":'<div class="'+(kz>=0?"up":"dn")+'">'+sg(kz)+(x.a?" ("+f2((cur-x.px)*x.a)+" TL)":"")+'</div>')+
   '<div><button data-dsat="'+x.id+'">Sattım</button> <button data-dsil="'+x.id+'">Sil</button></div></div>';
 });
 if(!acik.length)h="<p>Açık pozisyon yok.</p>";
 g("dl").innerHTML=h;
 var m="";
 ["d","g"].forEach(function(t){
  var a=kap.filter(function(x){return x.r===t});if(!a.length)return;
  var kz=a.map(function(x){return (x.c/x.px-1)*100});
  var w=kz.filter(function(v){return v>0}).length;
  m+="<p><b>"+(t==="g"?"Gerçek":"Deneme")+":</b> "+a.length+" işlem · kazanan %"+Math.round(100*w/a.length)+" · ortalama "+sg(kz.reduce(function(s,v){return s+v},0)/a.length)+"</p>";
 });
 g("dm").innerHTML=(m||"<p>Kapanan işlem yok.</p>")+(GT?"<p>Fiyatlar: "+GT+" (gecikmeli)</p>":"");
}
el.addEventListener("click",function(e){
 var b=e.target.closest("button");if(!b)return;
 if(b.dataset.dgo){
  var t=g("d_t").value.trim().toUpperCase();
  if(!t){alert("Hisse kodunu yaz");return}
  var px=num(g("d_p").value)||P[t]||null;
  if(!px){alert("Giriş fiyatını yaz");return}
  L.push({id:Date.now(),t:t,r:g("d_r").value,px:px,a:num(g("d_a").value),s:num(g("d_s").value),h:num(g("d_h").value),d:new Date().toISOString().slice(0,10),c:null});
  kaydet();
  ["d_t","d_p","d_a"].forEach(function(i){g(i).value=""});
  g("d_p").placeholder="Giriş fiyatı";
  ciz();
 }else if(b.dataset.dsat||b.dataset.dsil){
  var id=+(b.dataset.dsat||b.dataset.dsil),x=L.filter(function(y){return y.id===id})[0];
  if(!x)return;
  if(b.dataset.dsat){
   var v=prompt("Çıkış fiyatı ("+x.t+")",P[x.t]?String(P[x.t]).replace(".",","):""),c=v?num(v):null;
   if(c){x.c=c;kaydet();ciz()}
  }else if(confirm(x.t+" kaydı silinsin mi?")){
   L=L.filter(function(y){return y.id!==id});kaydet();ciz();
  }
 }else if(b.dataset.dyed==="k"){
  var j=JSON.stringify(L);
  if(navigator.clipboard&&navigator.clipboard.writeText){
   navigator.clipboard.writeText(j).then(function(){alert("Yedek kopyalandı")},function(){prompt("Yedeği kopyala",j)});
  }else prompt("Yedeği kopyala",j);
 }else if(b.dataset.dyed==="y"){
  var s=prompt("Yedeği buraya yapıştır");if(!s)return;
  try{
   var a=JSON.parse(s);
   if(!Array.isArray(a)||a.some(function(z){return !z.t||!z.px}))throw 0;
   L=a;kaydet();ciz();
  }catch(err){alert("Yedek okunamadı")}
 }
});
g("d_t").addEventListener("input",function(){
 var t=this.value.trim().toUpperCase();
 g("d_p").placeholder=P[t]?"Şimdi "+f2(P[t]):"Giriş fiyatı";
});
document.addEventListener("click",function(e){
 var b=e.target.closest("button");if(!b||!b.dataset.dekle)return;
 var t=b.dataset.dekle;
 el.open=true;g("d_t").value=t;g("d_p").value=P[t]?String(P[t]).replace(".",","):"";
 el.scrollIntoView({behavior:"smooth"});g("d_a").focus();
});
var R=g("rows");
function ek(){
 R.querySelectorAll(".item").forEach(function(it){
  if(it.querySelector(".dekle"))return;
  var det=it.querySelector(".det"),s=it.querySelector(".sym");if(!det||!s)return;
  var b=document.createElement("button");b.className="dekle";b.dataset.dekle=s.textContent;b.textContent="Deftere ekle";
  det.appendChild(b);
 });
}
if(R){new MutationObserver(ek).observe(R,{childList:true});ek()}
fetch("fiyatlar.json?v="+Date.now()).then(function(r){return r.json()}).then(function(j){
 P=j.p||{};GT=j.gt||"";TK=j.t||[];
 g("dtk").innerHTML=TK.map(function(t){return '<option value="'+t+'">'}).join("");
 ciz();
}).catch(function(){ciz()});
ciz();
})();
'''


def main():
    T, p = fiyatlar()
    eski = {}
    if os.path.exists(D + "fiyatlar.json"):
        try:
            eski = json.load(open(D + "fiyatlar.json", encoding="utf-8")).get("p", {})
        except Exception:
            pass
    p = {**eski, **p}
    gt = (datetime.datetime.utcnow() + datetime.timedelta(hours=3)).strftime("%d.%m.%Y %H:%M")
    json.dump({"gt": gt, "t": T, "p": p}, open(D + "fiyatlar.json", "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    h = open(D + "index.html", encoding="utf-8").read()
    if 'id="sonuc"' not in h or 'id="defter"' in h:
        print("sayfa uygun degil, defter eklenmedi")
        return
    h = h.replace("</style>", CSS + "</style>", 1)
    h = h.replace('<details class="b" id="sonuc"></details>',
                  '<details class="b" id="sonuc"></details>\n<details class="b" id="defter"></details>', 1)
    h = h.replace("</body>", "<script>" + JS + "</script></body>", 1)
    open(D + "index.html", "w", encoding="utf-8").write(h)
    print("defter eklendi,", len(p), "fiyat")


main()
