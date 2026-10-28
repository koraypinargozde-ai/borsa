# ottpoc.py - OTT + POC (hacim profili) kirilim / retest geriye testi (BIST, gunluk)
# Cikti: docs/ottpoc.html
import os, re, sys, datetime as dt
import numpy as np
import pandas as pd
import yfinance as yf

PERIOD = "3y"
COST = 0.3          # % (tek seferlik toplam maliyet)
BINS = 30           # hacim profili fiyat dilimi
COOL = 5            # ayni hissede ayni sinyal arasi min gun
WINS = (60, 100)    # POC penceresi (gun)
OTT_LEN, OTT_PCT = 10, 2.0
OUT = "docs/ottpoc.html"

YEDEK = ["THYAO", "ASELS", "BIMAS", "KCHOL", "SISE", "EREGL", "TUPRS", "AKBNK", "GARAN", "ISCTR",
         "YKBNK", "SASA", "FROTO", "TOASO", "PGSUS", "TAVHL", "KRDMD", "PETKM", "ENKAI", "SAHOL",
         "EKGYO", "HEKTS", "ODAS", "KOZAL", "ARCLK", "VESTL", "ULKER", "MGROS", "TCELL", "TTKOM",
         "ASTOR", "ISMEN", "ALARK", "DOHOL", "GUBRF", "SOKM", "AEFES", "CCOLA", "OYAKC", "CIMSA"]
YASAK = {"GET", "POST", "UTF", "NONE", "TRUE", "FALSE", "NAN", "INF", "USD", "TRY", "EOF", "BIST", "XU"}


def hisseler():
    kod = set()
    try:
        txt = open("scan.py", encoding="utf-8").read()
        for m in re.finditer(r'["\']([A-Z]{3,6})(?:\.IS)?["\']', txt):
            kod.add(m.group(1))
    except Exception as e:
        print("scan.py okunamadi:", e)
    kod = sorted(k for k in kod if k not in YASAK)
    if len(kod) < 50:
        print("scan.py'den az hisse cikti, yedek liste eklendi")
        kod = sorted(set(kod) | set(YEDEK))
    return kod


def indir(kodlar):
    veri = {}
    for i in range(0, len(kodlar), 40):
        parca = [k + ".IS" for k in kodlar[i:i + 40]]
        try:
            d = yf.download(parca, period=PERIOD, interval="1d", group_by="ticker",
                            auto_adjust=True, threads=True, progress=False)
        except Exception as e:
            print("indirme hatasi:", e)
            continue
        for t in parca:
            try:
                if isinstance(d.columns, pd.MultiIndex):
                    df = d[t][["Open", "High", "Low", "Close", "Volume"]].dropna()
                else:
                    df = d[["Open", "High", "Low", "Close", "Volume"]].dropna()
                df = df[df["Close"] > 0]
                if len(df) > 250:
                    veri[t[:-3]] = df
            except Exception:
                pass
    return veri


def ott_hesapla(c, length=OTT_LEN, pct=OTT_PCT):
    c = np.asarray(c, dtype=float)
    n = len(c)
    alpha = 2.0 / (length + 1)
    fark_ = np.diff(c, prepend=c[0])
    up = np.maximum(fark_, 0)
    dn = np.maximum(-fark_, 0)
    ups = pd.Series(up).rolling(9).sum().values
    dns = pd.Series(dn).rolling(9).sum().values
    with np.errstate(divide="ignore", invalid="ignore"):
        cmo = np.abs((ups - dns) / (ups + dns))
    cmo = np.nan_to_num(cmo)
    var = np.zeros(n)
    var[0] = c[0]
    for i in range(1, n):
        a = alpha * cmo[i]
        var[i] = a * c[i] + (1 - a) * var[i - 1]
    fark = var * pct * 0.01
    ls = var - fark
    ss = var + fark
    dr = np.ones(n)
    ot = np.zeros(n)
    for i in range(n):
        if i > 0:
            lsp, ssp = ls[i - 1], ss[i - 1]
            if var[i] > lsp:
                ls[i] = max(ls[i], lsp)
            if var[i] < ssp:
                ss[i] = min(ss[i], ssp)
            d = dr[i - 1]
            if d == -1 and var[i] > ssp:
                d = 1
            elif d == 1 and var[i] < lsp:
                d = -1
            dr[i] = d
        mt = ls[i] if dr[i] == 1 else ss[i]
        ot[i] = mt * (200 + pct) / 200 if var[i] > mt else mt * (200 - pct) / 200
    return var, ot


def hacim_profili(h, l, v, W):
    # t gunu icin POC/VAL/VAH: t-W .. t-1 mumlari (t gunu dahil degil)
    n = len(h)
    poc = np.full(n, np.nan)
    val = np.full(n, np.nan)
    vah = np.full(n, np.nan)
    for t in range(W, n):
        hh = h[t - W:t]
        ll = l[t - W:t]
        vv = v[t - W:t]
        lo, hi = ll.min(), hh.max()
        if not hi > lo:
            continue
        hh = np.maximum(hh, ll + (hi - lo) / BINS * 0.01)
        edges = np.linspace(lo, hi, BINS + 1)
        blo = edges[:-1][None, :]
        bhi = edges[1:][None, :]
        ov = np.clip(np.minimum(hh[:, None], bhi) - np.maximum(ll[:, None], blo), 0, None)
        prof = (ov / (hh - ll)[:, None] * vv[:, None]).sum(0)
        tot = prof.sum()
        if tot <= 0:
            continue
        i = int(prof.argmax())
        a, b = i, i
        acc = prof[i]
        while acc < 0.7 * tot and (a > 0 or b < BINS - 1):
            u = prof[b + 1] if b < BINS - 1 else -1
            d = prof[a - 1] if a > 0 else -1
            if u >= d:
                b += 1
                acc += prof[b]
            else:
                a -= 1
                acc += prof[a]
        poc[t] = (edges[i] + edges[i + 1]) / 2
        val[t] = edges[a]
        vah[t] = edges[b + 1]
    return poc, val, vah


def roll_any(x, k):
    return pd.Series(x.astype(float)).rolling(k, min_periods=1).max().values > 0


def retest_maske(c, o, l, poc, ottpos, pocK, look=10):
    n = len(c)
    m = np.zeros(n, bool)
    for t in range(1, n):
        for k in range(t - 1, max(t - look, 0) - 1, -1):
            if pocK[k]:
                L = poc[k]
                if not np.isfinite(L):
                    break
                seg_c = c[k:t]
                seg_l = l[k + 1:t]
                if ((seg_c >= L * 0.98).all() and (len(seg_l) == 0 or (seg_l > L * 1.015).all())
                        and l[t] <= L * 1.015 and c[t] > L and c[t] > o[t] and ottpos[t]):
                    m[t] = True
                break
    return m


def cooldown(idx, gap):
    out, last = [], -10 ** 9
    for i in idx:
        if i - last >= gap:
            out.append(i)
            last = i
    return np.array(out, dtype=int)


def kaydet(store, key, mask, start, d, R, cool=True):
    m = np.array(mask, dtype=bool).copy()
    m[:start] = False
    m &= ~np.isnan(R[:, 0])
    idx = np.where(m)[0]
    if cool:
        idx = cooldown(idx, COOL)
    if len(idx):
        store.setdefault(key, []).append(np.column_stack([d[idx], R[idx]]))


def isle(kod, df, store, bugun, sira):
    idx_ = df.index
    if getattr(idx_, "tz", None) is not None:
        idx_ = idx_.tz_localize(None)
    d = idx_.values.astype("datetime64[D]").astype(np.int64)
    o = df["Open"].values.astype(float)
    h = df["High"].values.astype(float)
    l = df["Low"].values.astype(float)
    c = df["Close"].values.astype(float)
    v = df["Volume"].values.astype(float)
    n = len(c)

    def ileri(k):
        r = np.full(n, np.nan)
        if n > k + 1:
            r[:n - k] = (c[k:] / o[1:n - k + 1] - 1) * 100 - COST
        return r

    tv = np.full(n, np.nan)
    tv[:n - 1] = ((c[1:] / c[:-1] - 1) >= 0.095).astype(float)
    R = np.column_stack([ileri(1), ileri(3), ileri(5), ileri(10), tv])

    var, ot = ott_hesapla(c)
    nn = lambda x, k: np.concatenate([np.full(k, np.nan), x[:-k]])
    cp, otp, varp = nn(c, 1), nn(ot, 1), nn(var, 1)
    ot2, ot2p = nn(ot, 2), nn(ot, 3)
    with np.errstate(invalid="ignore"):
        ottpos = c > ot
        ottA = (c > ot) & (cp <= otp)
        ottV = (var > ot2) & (varp <= ot2p)
    vma = pd.Series(v).rolling(20).mean().shift(1).values
    with np.errstate(invalid="ignore"):
        hv2 = v >= 2 * vma
        hv12 = v >= 1.2 * vma

    kaydet(store, (0, "TABAN: tüm günler"), np.ones(n, bool), 30, d, R, cool=False)
    kaydet(store, (0, "OTT: fiyat OTT'yi yukarı kesti"), ottA, 30, d, R)
    kaydet(store, (0, "OTT: Support(VAR) OTT'yi yukarı kesti"), ottV, 30, d, R)
    kaydet(store, (0, "OTT fiyat kesişimi + hacim 2x"), ottA & hv2, 30, d, R)
    bugun.setdefault((0, "OTT: fiyat OTT'yi yukarı kesti"), []).append((kod, d[-1], bool(ottA[-1])))
    bugun.setdefault((0, "OTT: Support(VAR) OTT'yi yukarı kesti"), []).append((kod, d[-1], bool(ottV[-1])))

    for W in WINS:
        if n < W + 60:
            continue
        poc, val, vah = hacim_profili(h, l, v, W)
        with np.errstate(invalid="ignore"):
            pocK = (cp <= poc) & (c > poc)
            vahK = (cp <= vah) & (c > vah)
            c_vah = c > vah
        pocK3, ottA3, pocK5 = roll_any(pocK, 3), roll_any(ottA, 3), roll_any(pocK, 5)
        rt = retest_maske(c, o, l, poc, ottpos, pocK)
        rt_siz = retest_maske(c, o, l, poc, np.ones(n, bool), pocK)
        G = [
            ("POC yukarı kırılım", pocK),
            ("VAH yukarı kırılım", vahK),
            ("POC kırılım + OTT pozitif (fiyat>OTT)", pocK & ottpos),
            ("POC kırılım + OTT pozitif + hacim 2x", pocK & ottpos & hv2),
            ("POC + OTT kesişimi (3 gün içinde ikisi de)", (pocK | ottA) & pocK3 & ottA3 & ottpos),
            ("  …aynı + hacim 2x", (pocK | ottA) & pocK3 & ottA3 & ottpos & hv2),
            ("VAH kırılım + 5g içinde POC kırılım + OTT pozitif", vahK & pocK5 & ottpos),
            ("RETEST (ilk geri test, OTT şartsız)", rt_siz),
            ("RETEST (ilk geri test, OTT pozitif)", rt),
            ("RETEST + hacim ≥1,2x", rt & hv12),
        ]
        start = max(W, 30)
        for ad, mask in G:
            kaydet(store, (W, ad), mask, start, d, R)
            bugun.setdefault((W, ad), []).append((kod, d[-1], bool(mask[-1])))


def ort(x):
    x = x[~np.isnan(x)]
    return float(x.mean()) if len(x) else float("nan")


def istat(a, cut):
    tr = a[a[:, 0] <= cut]
    te = a[a[:, 0] > cut]
    return {
        "n": len(a), "nt": len(te),
        "tv": ort(a[:, 5]) * 100,
        "m1": ort(a[:, 1]), "m3": ort(a[:, 2]), "m5": ort(a[:, 3]), "m10": ort(a[:, 4]),
        "e5": ort(tr[:, 3]), "t5": ort(te[:, 3]),
        "e10": ort(tr[:, 4]), "t10": ort(te[:, 4]),
    }


def f(x, dec=2, sign=True):
    if x is None or not np.isfinite(x):
        return "-"
    s = f"{x:+.{dec}f}" if sign else f"{x:.{dec}f}"
    return s.replace(".", ",")


def renk(x):
    if x is None or not np.isfinite(x):
        return ""
    return "pos" if x > 0 else ("neg" if x < 0 else "")


def isaret(s, tb):
    if s["nt"] < 30:
        return ""
    sonuc = ""
    for h in ("5", "10"):
        e, t = s["e" + h], s["t" + h]
        if np.isfinite(e) and np.isfinite(t) and e > 0 and t > 0:
            sonuc = "✓"
            if e > tb["e" + h] and t > tb["t" + h]:
                sonuc = "✓✓"
    return sonuc


def tablo(satirlar, tb):
    h = ("<div class='w'><table><tr><th>Sinyal</th><th>n (test)</th><th>T+1 tavan %</th>"
         "<th>1g</th><th>3g</th><th>5g</th><th>5g eğ</th><th>5g test</th>"
         "<th>10g</th><th>10g eğ</th><th>10g test</th><th></th></tr>")
    for ad, s in satirlar:
        h += (f"<tr><td class='ad'>{ad}</td><td>{s['n']} ({s['nt']})</td><td>{f(s['tv'], 1, False)}</td>"
              + "".join(f"<td class='{renk(s[k])}'>{f(s[k])}</td>" for k in ("m1", "m3", "m5", "e5", "t5", "m10", "e10", "t10"))
              + f"<td>{'' if ad.startswith('TABAN') else isaret(s, tb)}</td></tr>")
    return h + "</table></div>"


def rapor(store, bugun, nhisse):
    taban_all = np.vstack(store[(0, "TABAN: tüm günler")])
    cut = np.quantile(taban_all[:, 0], 0.6)
    son = int(taban_all[:, 0].max())
    gun = lambda x: str(np.datetime64(int(x), "D"))
    istatlar = {k: istat(np.vstack(v), cut) for k, v in store.items()}
    tb = istatlar[(0, "TABAN: tüm günler")]

    html = ["<!doctype html><html lang='tr'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'><title>OTT + POC testi</title>"
            "<style>body{background:#0f1419;color:#e6e6e6;font:13px/1.45 -apple-system,Segoe UI,sans-serif;margin:10px}"
            "h1{font-size:18px}h2{font-size:15px;margin-top:22px;color:#9ecbff}.w{overflow-x:auto}"
            "table{border-collapse:collapse;margin:6px 0}th,td{border:1px solid #2a3340;padding:4px 7px;text-align:right;white-space:nowrap}"
            "th{background:#18202a}td.ad{text-align:left;white-space:normal;min-width:210px}.pos{color:#4ade80}.neg{color:#f87171}"
            ".n{color:#9aa7b4;font-size:12px}.k{color:#fbbf24}</style></head><body>"]
    html.append("<h1>📊 OTT + POC geriye testi</h1>")
    html.append(f"<p class='n'>{nhisse} hisse · günlük · {PERIOD} · veri sonu {gun(son)} · eğitim/test kesimi {gun(cut)} (%60/%40) · "
                f"giriş ertesi gün açılış · maliyet %{COST:.1f} · getiriler net % · aynı hissede aynı sinyal arası en az {COOL} gün</p>")

    html.append("<h2>1) Taban ve OTT tek başına</h2>")
    ilk = [(k[1], istatlar[k]) for k in store if k[0] == 0]
    html.append(tablo(ilk, tb))

    for W in WINS:
        ks = [k for k in store if k[0] == W]
        if not ks:
            continue
        html.append(f"<h2>2) POC penceresi {W} gün</h2>")
        html.append(tablo([(k[1], istatlar[k]) for k in ks], tb))

    html.append(f"<h2>3) Bugünkü sinyaller (veri tarihi {gun(son)})</h2>")
    for k, lst in bugun.items():
        if k[1].startswith("TABAN"):
            continue
        aktif = sorted(x[0] for x in lst if x[1] == son and x[2])
        if aktif:
            etiket = ("OTT" if k[0] == 0 else f"POC{k[0]}") + " · " + k[1].strip()
            html.append(f"<p><b>{etiket}</b> ({len(aktif)}): {', '.join(aktif[:40])}{' …' if len(aktif) > 40 else ''}</p>")

    html.append("<h2>Nasıl okunur</h2><ul class='n'>"
                "<li>✓ = 5g veya 10g getiri hem eğitimde hem testte pozitif (test n≥30); ✓✓ = ayrıca ikisinde de tabandan iyi.</li>"
                "<li>OTT: Anıl Özekşi formülü (VAR ortalaması, periyot 10, yüzde 2,0). 'Fiyat kesişimi' = kapanış OTT'nin üstüne geçti; 'Support' = VAR çizgisi OTT[2]'yi yukarı kesti.</li>"
                f"<li>POC/VAH: günlük mumların hacmi, mum aralığına eşit dağıtılarak {BINS} fiyat diliminde toplanır (yaklaşık profil, gerçek tick profili değil). "
                "Pencere t gününü içermez, bakış-ileri hatası yok. VAH = hacmin %70'ini kapsayan bölgenin üstü.</li>"
                "<li>RETEST: son 10 günde POC kırılımı oldu, kapanış kırılan seviyenin %2 altına inmedi, bu arada seviyeye hiç temas yok (ilk geri test), "
                "bugün düşük seviyenin %1,5 yakınına indi, kapanış seviyenin üstünde ve yeşil mum.</li>"
                "<li>Stop/hedef yok: sadece ertesi açılıştan N. gün kapanışına tutma getirisi. T+1 tavan: ertesi gün kapanış ≥ +%9,5.</li>"
                "<li>Uyarı: güncel hisse listesi (hayatta kalma yanlılığı), örnekler üst üste binebilir, dönem düşen piyasa olabilir; tabanla karşılaştır.</li></ul>")
    html.append("</body></html>")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("".join(html))
    print("yazildi:", OUT)


def main():
    kodlar = hisseler()
    print(len(kodlar), "kod")
    veri = indir(kodlar)
    print(len(veri), "hisse verisi indi")
    if len(veri) < 20:
        print("yetersiz veri")
        sys.exit(1)
    store, bugun = {}, {}
    for i, (kod, df) in enumerate(veri.items()):
        try:
            isle(kod, df, store, bugun, i)
        except Exception as e:
            print("hata", kod, e)
        if i % 50 == 0:
            print(i, "/", len(veri))
    rapor(store, bugun, len(veri))


if __name__ == "__main__":
    main()
