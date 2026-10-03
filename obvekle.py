import json, re, html as HT

D = "docs/"
A, B = "<!--OBV-->", "<!--/OBV-->"
HEDEF = '<details class="b" id="perf"></details>'


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


def main():
    try:
        j = json.load(open(D + "obv.json", encoding="utf-8"))
    except Exception:
        print("obv.json yok")
        return
    s = j.get("s", [])
    h = open(D + "index.html", encoding="utf-8").read()
    h = re.sub(re.escape(A) + ".*?" + re.escape(B), "", h, flags=re.S)
    if HEDEF not in h:
        print("hedef yer bulunamadi")
        return
    satir = ""
    for x in s[:25]:
        z = x["z"]
        zaman = z[8:10] + "." + z[5:7] + " " + z[11:]
        giris = x["g"] if x.get("g") is not None else x["p"]
        satir += ("<tr><td>" + HT.escape(x["t"]) + "<br><small style='color:var(--mute)'>"
                  + zaman + " · " + str(x["rv"]).replace(".", ",") + "x hacim</small></td><td>"
                  + str(giris).replace(".", ",") + "</td>"
                  + hucre(x.get("r1")) + hucre(x.get("rd")) + hucre(x.get("rh")) + "</tr>")
    if not satir:
        satir = "<tr><td colspan=5>Henüz sinyal yok</td></tr>"
    kutu = (A + '<details class="b" id="obv"><summary>İndikatör sinyali (Dip OBV, 5 dk)</summary>'
            + "<p>Güncelleme: <b>" + str(j.get("g")) + "</b> · toplam sinyal: <b>" + str(len(s)) + "</b></p>"
            + "<p>1 saat sonra (net): " + ozet(s, "r1") + "<br>Gün sonu (net): " + ozet(s, "rd") + "</p>"
            + "<table class=st><tr><th>Hisse</th><th>Giriş</th><th>1 sa</th><th>Gün sonu</th><th>Zirve</th></tr>"
            + satir + "</table>"
            + "<p>TradingView'deki Dip OBV indikatörünün 5 dakikalık AL sinyali (hacim 8,9x, aralık %2,2, "
            + "OBV 98, RSI 3, volatilite 1, net akış 41). Giriş: sinyalden sonraki mumun açılışı. "
            + "Tablodaki yüzdeler komisyonsuz, üstteki özet %0,3 komisyon düşülmüş net değerdir. "
            + "Son 25 sinyal gösterilir. Veri gecikmelidir; örnek sayısı azken yanıltıcı olabilir.</p>"
            + "</details>" + B)
    h = h.replace(HEDEF, HEDEF + kutu, 1)
    open(D + "index.html", "w", encoding="utf-8").write(h)
    print("indikator kutusu eklendi:", len(s), "sinyal")


main()
