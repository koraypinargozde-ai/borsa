import json, re, html as HT

D = "docs/"
HEDEF = '<details class="b" id="perf"></details>'
TOG = """var n=this.nextElementSibling;n.style.display=(n.style.display=='none'?'table-row':'none')"""

KUTULAR = [
    {"dosya": "obv.json", "id": "obv", "m": "OBV",
     "baslik": "İndikatör sinyali (Dip OBV, 5 dk)",
     "not": "TradingView'deki Dip OBV indikatörünün 5 dakikalık AL sinyali (hacim 8,9x, aralık %2,2, "
            "OBV 98, RSI 3, volatilite 1, net akış 41)."},
    {"dosya": "obv2.json", "id": "obv2", "m": "OBV2",
     "baslik": "İndikatör sinyali 2 (Dip OBV v2.0 Sade, 5 dk)",
     "not": "Dip OBV v2.0 Sade indikatörünün 5 dakikalık AL sinyali (hacim 12,7x, aralık %1, OBV 111 "
            "robustluk ±6 / 0,92, RSI 3, dip arama 40 / %6, alt fitil 1, kırılım hacmi 12,7x). "
            "Şartları çok sıkı olduğu için sinyal çok seyrek çıkar."},
]


def n(v, d=2):
    if v is None:
        return "-"
    return (("%." + str(d) + "f") % v).replace(".", ",")


def f2(v):
    return ("%+.2f" % v).replace(".", ",") + "%"


def hucre(v):
    if v is None:
        return "<td>-</td>"
    renk = "up" if v >= 0 else "dn"
    return "<td class=" + renk + ">" + f2(v) + "</td>"


def ozet(s, k):
    a = [x[k] - 0.3 for x in s if x.get(k) is not None]
    if not a:
        return "-"
    ort = sum(a) / len(a)
    isabet = round(100 * sum(1 for v in a if v > 0) / len(a))
    return "n %d · ort %s · isabet %%%d" % (len(a), f2(ort), isabet)


def detay(x, ayar):
    giris = x["g"] if x.get("g") is not None else x.get("p")
    t = ("<b>Sinyal fiyatı:</b> " + n(x.get("p")) + " · <b>Giriş:</b> " + n(giris)
         + "<br><b>Volatilite çarpanı (gerçek):</b> " + n(x.get("vm"))
         + " · <b>RSI:</b> " + n(x.get("rsi"), 1)
         + " · <b>CMF:</b> " + n(x.get("cmf"), 3)
         + "<br><b>Puan:</b> " + n(x.get("sc"), 0)
         + " · <b>Aralık:</b> %" + n(x.get("rg"))
         + " · <b>Net akış:</b> %" + n(x.get("nm"))
         + " · <b>Hacim:</b> " + n(x.get("rv")) + "x"
         + "<br><b>Zirve (gün içi):</b> " + (f2(x["rh"]) if x.get("rh") is not None else "-")
         + " · <b>Son fiyat:</b> " + n(x.get("son")))
    if ayar:
        t += ("<br><small style='color:var(--mute)'>Ayarlar: RSI uzunluğu " + str(ayar.get("rsi"))
              + " · hacim min " + n(ayar.get("hacim"), 1) + "x · aralık max %" + n(ayar.get("aralik"), 1)
              + " · OBV " + str(ayar.get("obv")) + " · volatilite çarpanı min " + n(ayar.get("vol"), 1)
              + " · net akış " + str(ayar.get("akis")) + " · min puan " + str(ayar.get("puan")) + "</small>")
    return ("<tr style='display:none'><td colspan=5 style='text-align:left;white-space:normal;"
            "line-height:1.6;padding:8px 6px'>" + t + "</td></tr>")


def kutu(c):
    try:
        j = json.load(open(D + c["dosya"], encoding="utf-8"))
    except Exception:
        return ""
    s = j.get("s", [])
    ayar = j.get("a")
    satir = ""
    for x in s[:25]:
        z = x["z"]
        zaman = z[8:10] + "." + z[5:7] + " " + z[11:]
        giris = x["g"] if x.get("g") is not None else x["p"]
        satir += ("<tr style='cursor:pointer' onclick=\"" + TOG + "\"><td>" + HT.escape(x["t"])
                  + "<br><small style='color:var(--mute)'>"
                  + zaman + " · " + str(x["rv"]).replace(".", ",") + "x hacim</small></td><td>"
                  + str(giris).replace(".", ",") + "</td>"
                  + hucre(x.get("r1")) + hucre(x.get("rd")) + hucre(x.get("r5")) + "</tr>")
        satir += detay(x, ayar)
    if not satir:
        satir = "<tr><td colspan=5>Henüz sinyal yok</td></tr>"
    a, b = "<!--" + c["m"] + "-->", "<!--/" + c["m"] + "-->"
    return (a + '<details class="b" id="' + c["id"] + '"><summary>' + c["baslik"] + '</summary>'
            + "<p>Güncelleme: <b>" + str(j.get("g")) + "</b> · toplam sinyal: <b>" + str(len(s)) + "</b></p>"
            + "<p>1 saat sonra (net): " + ozet(s, "r1") + "<br>Gün sonu (net): " + ozet(s, "rd")
            + "<br>5. gün kapanış (net): " + ozet(s, "r5") + "</p>"
            + "<table class=st><tr><th>Hisse</th><th>Giriş</th><th>1 sa</th><th>Gün sonu</th><th>5. gün</th></tr>"
            + satir + "</table>"
            + "<p>" + c["not"] + " Giriş: sinyalden sonraki mumun açılışı. "
            + "5. gün = girişten sinyalden sonraki 5. işlem gününün kapanışına değişim. "
            + "Detay için hisseye dokun. "
            + "Tablodaki yüzdeler komisyonsuz, üstteki özet %0,3 komisyon düşülmüş net değerdir. "
            + "Son 25 sinyal gösterilir. Veri gecikmelidir; örnek sayısı azken yanıltıcı olabilir.</p>"
            + "</details>" + b)


def main():
    h = open(D + "index.html", encoding="utf-8").read()
    for c in KUTULAR:
        a, b = "<!--" + c["m"] + "-->", "<!--/" + c["m"] + "-->"
        h = re.sub(re.escape(a) + ".*?" + re.escape(b), "", h, flags=re.S)
    if HEDEF not in h:
        print("hedef yer bulunamadi")
        return
    kutular = "".join(kutu(c) for c in KUTULAR)
    h = h.replace(HEDEF, HEDEF + kutular, 1)
    open(D + "index.html", "w", encoding="utf-8").write(h)
    print("indikator kutulari eklendi")


main()
