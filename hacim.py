import re, json
import yfinance as yf

D = "docs/"

CSS = r'''
.sym[data-yz]::after{content:" ▲";color:var(--up);font-size:11px}
'''

JS = r'''
(function(){
var R=document.getElementById("rows");if(!R)return;
var H={};
function ek(){
 R.querySelectorAll(".item").forEach(function(it){
  var s=it.querySelector(".sym");if(!s)return;
  var x=H[s.textContent];if(!x)return;
  if(x[1])s.setAttribute("data-yz","1");
  var dl=it.querySelector(".det dl");
  if(dl&&!dl.querySelector(".hz")){
   dl.insertAdjacentHTML("beforeend",'<dt class="hz">Hacim (medyan)</dt><dd>'+String(x[0]).replace(".",",")+'x</dd>'+(x[1]?'<dt>Hacim</dt><dd>Son 20 günün en yüksek hacmi</dd>':""));
  }
 });
}
new MutationObserver(ek).observe(R,{childList:true});
fetch("hacim.json?v="+Date.now()).then(function(r){return r.json()}).then(function(j){
 H=j;ek();
 var f=document.querySelector("footer");
 if(f)f.insertAdjacentHTML("beforeend"," ▲ işareti: bugünkü hacim son 20 iş gününün en yüksek hacmi.");
}).catch(function(){});
})();
'''


def main():
    h = open(D + "index.html", encoding="utf-8").read()
    m = re.search(r"var V=(\{.*?\});\nvar D=V\.rows;", h, re.S)
    if not m:
        print("sayfa uygun degil")
        return
    syms = [r[0] for r in json.loads(m.group(1))["rows"]]
    tk = [s + ".IS" for s in syms] + ["THYAO.IS", "GARAN.IS"]
    out = {}
    try:
        d = yf.download(tk, period="2mo", group_by="ticker", progress=False,
                        threads=True, auto_adjust=False)
    except Exception as e:
        print("hata", e)
        d = None
    for s in syms:
        try:
            v = d[s + ".IS"]["Volume"].dropna()
            if len(v) < 21:
                continue
            bugun = float(v.iloc[-1])
            onceki = v.iloc[-21:-1]
            med = float(onceki.median())
            if not med:
                continue
            out[s] = [round(bugun / med, 1), bool(bugun > float(onceki.max()))]
        except Exception:
            pass
    json.dump(out, open(D + "hacim.json", "w"), separators=(",", ":"))
    if 'id="hacimjs"' in h:
        print("hacim guncellendi,", len(out), "hisse")
        return
    h = h.replace("</style>", CSS + "</style>", 1)
    h = h.replace("</body>", '<script id="hacimjs">' + JS + "</script></body>", 1)
    open(D + "index.html", "w", encoding="utf-8").write(h)
    print("hacim eklendi,", len(out), "hisse")


main()
