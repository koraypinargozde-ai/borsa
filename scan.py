import yfinance as yf, datetime, os
import numpy as np

T = """AKBNK ARCLK ASELS ASTOR BIMAS BRISA CCOLA CIMSA DOAS DOHOL EKGYO ENJSA ENKAI EREGL FROTO GARAN GUBRF HALKB HEKTS ISCTR KCHOL KONTR KOZAL KRDMD MGROS ODAS OYAKC PETKM PGSUS SAHOL SASA SISE SOKM TAVHL TCELL THYAO TKFEN TOASO TSKB TTKOM TUPRS ULKER VAKBN VESTL YKBNK
A1CAP A1YEN AAGYO ACSEL ADEL ADGYO AEFES AGHOL AGROT AHGAZ AKCNS AKENR AKFGY AKFYE AKGRT AKSA AKSEN ALARK ALBRK ALCAR ALFAS ALGYO ALKIM ALKLC ALTNY ANELE ANGEN ANHYT ANSGR ARASE ARDYZ ARENA ARSAN ARTMS ARZUM ASGYO ASUZU ATAGY ATAKP ATATP ATEKS ATLAS AVGYO AVHOL AVOD AVTUR AYCES AYDEM AYEN AYGAZ AZTEK
BAGFS BAHKM BAKAB BALAT BANVT BARMA BASCM BASGZ BAYRK BEGYO BERA BESLR BEYAZ BFREN BIENY BIGCH BIOEN BIZIM BJKAS BLCYT BMSCH BMSTL BNTAS BOBET BORLS BORSK BOSSA BRKO BRKSN BRKVY BRLSM BRMEN BRSAN BRYAT BSOKE BTCIM BUCIM BURCE BURVA BVSAN BYDNR
CANTE CASA CELHA CEMAS CEMTS CEOEM CLEBI CMBTN CMENT CONSE COSMO CRDFA CRFSA CUSAN CVKMD CWENE DAGI DAPGM DARDL DENGE DERHL DERIM DESA DESPC DEVA DGATE DGGYO DGNMO DIRIT DITAS DMSAS DNISI DOBUR DOCO DOFER DOGUB DOKTA DURDO DYOBY DZGYO
EBEBK ECILC ECZYT EDATA EDIP EFOR EGEEN EGEPO EGGUB EGPRO EGSER EKIZ EKOS EKSUN ELITE EMKEL EMNIS ENERY ENSRI EPLAS ERBOS ERCB ERSU ESCAR ESCOM ESEN ETILR EUHOL EUKYO EUPWR EUREN EUYO EYGYO
FADE FENER FLAP FMIZP FONET FORMT FORTE FRIGO FZLGY GARFA GEDIK GEDZA GENIL GENTS GEREL GESAN GIPTA GLBMD GLCVY GLRYH GLYHO GMTAS GOKNR GOLTS GOODY GOZDE GRNYO GRSEL GRTHO GSDDE GSDHO GSRAY GWIND GZNMI
HATEK HATSN HDFGS HEDEF HKTM HLGYO HTTBT HUBVC HUNER HURGZ ICBCT ICUGS IDGYO IEYHO IHAAS IHEVA IHGZT IHLAS IHLGM IHYAY IMASM INDES INFO INGRM INTEM INVEO INVES ISATR ISBIR ISDMR ISFIN ISGSY ISGYO ISKPL ISMEN ISSEN IZENR IZFAS IZINV IZMDC
JANTS KAPLM KAREL KARSN KARTN KARYE KATMR KAYSE KBORU KCAER KERVN KERVT KFEIN KGYO KIMMR KLGYO KLKIM KLMSN KLNMA KLRHO KLSYN KMPUR KNFRT KONKA KONYA KOPOL KORDS KRDMA KRDMB KRGYO KRONT KRPLS KRSTL KRTEK KRVGD KSTUR KTLEV KTSKR KUTPO KUVVA KUYAS KZBGY KZGYO
LIDER LIDFA LILAK LINK LKMNH LOGO LRSHO LUKSK LYDHO LYDYE MAALT MACKO MAGEN MAKIM MAKTK MANAS MARBL MARKA MARTI MAVI MEDTR MEGAP MEGMT MEKAG MEPET MERCN MERIT MERKO METRO MIATK MIPAZ MMCAS MNDRS MNDTR MOBTL MPARK MRGYO MRSHL MSGYO MTRKS MTRYO MZHLD
NATEN NETAS NIBAS NTGAZ NTHOL NUGYO NUHCM OBASE ODINE OFSYM ONCSM ORCAY ORGE ORMA OSMEN OSTIM OTKAR OYAYO OYLUM OZGYO OZKGY OZRDN OZSUB PAGYO PAMEL PAPIL PARSN PASEU PATEK PCILT PEGYO PEKGY PENGD PENTA PETUN PINSU PKART PKENT PLTUR PNLSN PNSUT POLHO POLTK PRDGS PRKAB PRKME PRZMA PSDTC PSGYO QNBTR QUAGR
RALYH RAYSG REEDR RGYAS RNPOL RODRG ROYAL RTALB RUBNS RYGYO RYSAS SAFKR SAMAT SANEL SANFM SANKO SARKY SAYAS SDTTR SEGYO SEKFK SEKUR SELEC SELGD SELVA SEYKM SILVR SKBNK SKTAS SKYMD SMART SMRTG SNGYO SNICA SNKRN SNPAM SODSN SOKE SONME SRVGY SUMAS SUNTK SURGY SUWEN
TABGD TARKM TATEN TATGD TBORG TDGYO TEKTU TERA TETMT TEZOL TKNSA TLMAN TMPOL TMSN TNZTP TRCAS TRGYO TRILC TSGYO TSPOR TTRAK TUCLK TUKAS TURGG TURSG UFUK ULAS ULUFA ULUSE ULUUN UMPAS UNLU USAK UZERB
VAKFN VAKKO VANGD VBTYZ VERTU VERUS VESBE VKFYO VKGYO VKING VRGYO YAPRK YATAS YAYLA YEOTK YESIL YGGYO YGYO YIGIT YKSLN YONGA YUNSA YYAPI YYLGD ZEDUR ZOREN ZRGYO""".split()

tick = [t + ".IS" for t in dict.fromkeys(T)]
rows = []
now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
dk = now.hour * 60 + now.minute

for i in range(0, len(tick), 50):
    grup = tick[i:i + 50]
    try:
        d = yf.download(grup, period="2mo", group_by="ticker",
                        progress=False, threads=True, auto_adjust=False)
    except Exception as e:
        print("hata", e)
        continue
    for t in grup:
        try:
            x = d[t].dropna()
            if len(x) < 22:
                continue
            z, p, pr = x.iloc[-1], x.iloc[-2], x.iloc[-21:-1]
            if (now.date() - x.index[-1].date()).days > 5:
                continue
            av = pr["Volume"].mean()
            if not av or av * z["Close"] < 2_000_000:
                continue
            vr = z["Volume"] / av
            if x.index[-1].date() == now.date() and dk < 1090:
                vr = vr / max(0.15, min(1, max(0, (dk - 600) / 480) ** 0.5))
            pos = (z["Close"] - z["Low"]) / (z["High"] - z["Low"]) if z["High"] > z["Low"] else 0.5
            chg = (z["Close"] / p["Close"] - 1) * 100
            if np.busday_count(x.index[-2].date(), x.index[-1].date()) > 1:
                chg = (z["Close"] / yf.Ticker(t).fast_info["previousClose"] - 1) * 100
            brk = z["Close"] > pr["High"].max()

            # Para girisi: CMF (20 gun) + onceki 2 gunun hacim teyidi
            h = x.iloc[-20:]
            rg = (h["High"] - h["Low"]).replace(0, float("nan"))
            mf = (((h["Close"] - h["Low"]) - (h["High"] - h["Close"])) / rg).fillna(0)
            cmf = float((mf * h["Volume"]).sum() / h["Volume"].sum())
            vk = float(x["Volume"].iloc[-3:-1].mean() / av)
            pg = bool(cmf > 0.15 and vk >= 1.2)

            sc = min(vr, 4) / 4 * 40 + pos * 25 + max(0, min(chg, 10)) / 10 * 20 + (15 if brk else 0)
            if pg:
                sc += 10
            if chg <= 0:
                sc *= 0.3
            rows.append((t[:-3], z["Close"], chg, vr, pos * 100, brk, sc,
                         x.index[-1].strftime("%d.%m.%Y"), pg))
        except Exception:
            continue

rows.sort(key=lambda r: -r[6])
veri_tarihi = rows[0][7] if rows else "-"

satirlar = ""
for r in rows[:40]:
    notlar = ("Tavana yakın " if r[2] >= 7 else "") + ("Kırılım " if r[5] else "") + ("💰Para girişi" if r[8] else "")
    satirlar += (f"<tr><td>{r[0]}</td><td class=s>{r[6]:.0f}</td><td>{r[1]:.2f}</td>"
                 f"<td>{r[2]:.1f}</td><td>{r[3]:.1f}x</td><td>{r[4]:.0f}</td><td>{notlar}</td></tr>")

html = """<!DOCTYPE html><html lang=tr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>BIST Tarayıcı</title><style>
:root{--bg:#f6f7f9;--c:#fff;--t:#14171c;--m:#6b7280;--a:#0a7d4b;--b:#e3e6ea}
@media(prefers-color-scheme:dark){:root{--bg:#0e1116;--c:#171b22;--t:#e8eaed;--m:#9aa3af;--a:#34d399;--b:#262c36}}
body{margin:0;background:var(--bg);color:var(--t);font-family:system-ui,sans-serif}
main{max-width:720px;margin:auto;padding:16px}h1{font-size:1.2rem;margin:0}
p{color:var(--m);font-size:.8rem}.w{overflow-x:auto;background:var(--c);border:1px solid var(--b);border-radius:12px;padding:8px}
table{border-collapse:collapse;width:100%;font-size:.85rem}
th,td{padding:7px 6px;text-align:right;border-bottom:1px solid var(--b);white-space:nowrap}
th:first-child,td:first-child{text-align:left;font-weight:600}th{color:var(--m);font-weight:500}.s{color:var(--a);font-weight:700}
</style></head><body><main><h1>BIST Tavan Adayı Tarayıcı</h1>
<p>Veri tarihi: __VT__ · Güncelleme: __GT__ · Veri gecikmelidir (Yahoo Finance)</p>
<div class=w><table><tr><th>Hisse</th><th>Puan</th><th>Fiyat</th><th>Değ.%</th><th>Hacim</th><th>Kapanış%</th><th>Not</th></tr>__S__</table></div>
<p>Filtre amaçlıdır, yatırım tavsiyesi değildir. Puan: hacim patlaması, güçlü kapanış, yükseliş, 20 günlük direnç kırılımı ve para girişi teyidinden hesaplanır.</p>
</main></body></html>"""

html = html.replace("__VT__", veri_tarihi).replace("__GT__", now.strftime("%d.%m.%Y %H:%M")).replace("__S__", satirlar)
os.makedirs("docs", exist_ok=True)
open("docs/index.html", "w", encoding="utf-8").write(html)
print(len(rows), "hisse listelendi", sum(1 for r in rows[:40] if r[8]), "adet para girişi")
try:
    fi = yf.Ticker("XU100.IS").fast_info
    xu = round((fi["lastPrice"] / fi["previousClose"] - 1) * 100, 2)
    open("docs/xu.json", "w").write('{"c":%s}' % xu)
except Exception as e:
    print("endeks hata", e)
