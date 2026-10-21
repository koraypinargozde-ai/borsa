# -*- coding: utf-8 -*-
"""
astro.py - Finansal astroloji testi (olay calismasi)

Soru: Merkur retrosu, yeni ay/dolunay, tutulma adaylari ve secili acilar
(Venus-Jupiter kavusum, Venus-Neptun kare) gunlerinde BIST100, altin,
USD/TRY ve Bitcoin rastgele gunlerden FARKLI davraniyor mu?

Yontem:
- Tarihler ephem kutuphanesiyle hesaplanir (gecmis + onumuzdeki 120 gun).
- Her olay icin getiri pencereleri olculur: olay gunu, ertesi gun,
  ileri 5 ve 10 gun, ayrica mutlak getiri (oynaklik).
- Karsilastirma: ayni sayida RASTGELE gun (3000 simulasyon). p-degeri
  iki yonlu.
- Merkur retro donemi icin bloklari bozmayan dairesel kaydirma testi.
- Eski %60 egitim / yeni %40 test ayrimi. "Tutarli" = p<0.05 ve egitim
  ile test ayni yonde.
- Cok sayida test yapildigi icin tesadufen p<0.05 cikmasi BEKLENIR;
  ozet kutusu bunu gosterir.

Cikti: docs/astro.html
Gerekenler: pip install yfinance pandas numpy ephem
"""
import os
import sys
import math
import html
import datetime as dt

import numpy as np
import pandas as pd

START = "2005-01-01"
NSIM = 3000
NSIM_RETRO = 2000
TRAIN_FRAC = 0.6
ECL_LAT = 1.5          # tutulma adayi: yeni/dolunayda Ay enlemi < 1.5 derece
MIN_EVENTS = 8
OUT = "docs/astro.html"
SEED = 7

ASSETS = [
    ("XU100.IS", "BIST 100"),
    ("GC=F", "Altın (ons)"),
    ("USDTRY=X", "USD/TRY"),
    ("BTC-USD", "Bitcoin"),
]

PLANETS = {"Mercury": "Merkur", "Venus": "Venus",
           "Jupiter": "Jupiter", "Neptune": "Neptun"}

# (gezegen1, gezegen2, aci, ad)  aci: 0 kavusum, 90 kare, 120 ucgen, 180 karsit
ASPECTS = [
    ("Venus", "Jupiter", 0, "Venüs kavuşum Jüpiter"),
    ("Venus", "Neptune", 90, "Venüs kare Neptün"),
]

WINS = ["gün0", "ertesi gün", "ileri 5g", "ileri 10g", "|gün0|"]


def wrap180(x):
    return (x + 180.0) % 360.0 - 180.0


# ----------------------------------------------------------------------
# 1) ASTRO TARIHLERI
# ----------------------------------------------------------------------
def compute_astro(end_date):
    import ephem

    start = pd.Timestamp(START) - pd.Timedelta(days=40)
    days = pd.date_range(start, end_date, freq="D")

    bodies = {k: getattr(ephem, k)() for k in PLANETS}
    lon = {k: np.zeros(len(days)) for k in bodies}
    for i, d in enumerate(days):
        ed = ephem.Date(d.to_pydatetime().replace(hour=12))
        for k, b in bodies.items():
            b.compute(ed)
            lon[k][i] = math.degrees(float(ephem.Ecliptic(b).lon)) % 360.0

    events = {}

    # Merkur retro
    dm = wrap180(np.diff(lon["Mercury"], prepend=lon["Mercury"][0]))
    retro = dm < 0
    retro[0] = False
    r_start = list(days[1:][retro[1:] & ~retro[:-1]])
    r_end = list(days[1:][~retro[1:] & retro[:-1]])
    events["Merkür retro başlangıcı"] = r_start
    events["Merkür retro bitişi"] = r_end
    retro_series = pd.Series(retro, index=days)

    # Acilar
    for a, b, ang, name in ASPECTS:
        targets = [0.0] if ang in (0, 180) else [float(ang), -float(ang)]
        found = []
        for t in targets:
            f = wrap180(lon[a] - lon[b] - t)
            cross = (f[:-1] * f[1:] < 0) & (np.abs(f[:-1]) < 20) & (np.abs(f[1:]) < 20)
            found += list(days[1:][cross])
        events[name] = sorted(found)

    # Ay evreleri
    end_e = ephem.Date(pd.Timestamp(end_date).to_pydatetime())

    def collect(fn):
        out = []
        x = ephem.Date(start.to_pydatetime())
        while x < end_e:
            nm = fn(x)
            out.append(nm)
            x = ephem.Date(nm + 1)
        return out

    new_moons = collect(ephem.next_new_moon)
    full_moons = collect(ephem.next_full_moon)

    moon = ephem.Moon()

    def moon_info(dd):
        moon.compute(dd)
        e = ephem.Ecliptic(moon)
        lat = abs(math.degrees(float(e.lat)))
        l = math.degrees(float(e.lon))
        ts = pd.Timestamp(dd.datetime())
        yrs = ts.year + (ts.dayofyear - 1) / 365.25 - 2000.0
        l = (l + 0.013969 * yrs) % 360.0          # J2000 -> tarih (presesyon)
        return lat, l

    def ts(dd):
        return pd.Timestamp(dd.datetime()).normalize()

    ev_new, ev_full = [], []
    ev_sol, ev_lun, ev_taurus = [], [], []
    for nm in new_moons:
        t = ts(nm)
        ev_new.append(t)
        lat, _ = moon_info(nm)
        if lat < ECL_LAT:
            ev_sol.append(t)
    for fm in full_moons:
        t = ts(fm)
        ev_full.append(t)
        lat, l = moon_info(fm)
        if lat < ECL_LAT:
            ev_lun.append(t)
        if 30.0 <= l < 60.0:
            ev_taurus.append(t)

    events["Yeni ay"] = ev_new
    events["Dolunay"] = ev_full
    events["Güneş tutulması adayı (yeni ay)"] = ev_sol
    events["Ay tutulması adayı (dolunay)"] = ev_lun
    events["Tutulma adayı (hepsi)"] = sorted(ev_sol + ev_lun)
    events["Dolunay, Ay Boğa burcunda"] = ev_taurus

    return events, retro_series, r_start, r_end


# ----------------------------------------------------------------------
# 2) VERI
# ----------------------------------------------------------------------
def get_close(tkr):
    import yfinance as yf
    df = yf.download(tkr, start=START, auto_adjust=True, progress=False)
    if df is None or len(df) == 0:
        return None
    c = df["Close"]
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    c = c.dropna().astype(float)
    c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
    c = c[~c.index.duplicated(keep="last")].sort_index()
    return c


# ----------------------------------------------------------------------
# 3) ANALIZ
# ----------------------------------------------------------------------
def window_arrays(c):
    n = len(c)
    ret = np.full(n, np.nan)
    ret[1:] = c[1:] / c[:-1] - 1.0

    def fwd(k):
        o = np.full(n, np.nan)
        if n > k:
            o[:n - k] = c[k:] / c[:n - k] - 1.0
        return o

    nxt = np.full(n, np.nan)
    nxt[:-1] = ret[1:]
    return {"gün0": ret, "ertesi gün": nxt, "ileri 5g": fwd(5),
            "ileri 10g": fwd(10), "|gün0|": np.abs(ret)}


def event_idx(dates, evs):
    out = set()
    for e in evs:
        if e < dates[0] or e > dates[-1]:
            continue
        i = int(dates.searchsorted(e))
        if i >= len(dates):
            continue
        if (dates[i] - e).days > 4:
            continue
        out.add(i)
    return sorted(out)


def nm(a):
    a = np.asarray(a, dtype=float)
    a = a[~np.isnan(a)]
    return float(a.mean()) if len(a) else float("nan")


def analyze_events(name, arrs, idx, cut_i, rng):
    rows = []
    for w in WINS:
        a = arrs[w]
        ev = [i for i in idx if not np.isnan(a[i])]
        if len(ev) < MIN_EVENTS:
            continue
        pool = np.where(~np.isnan(a))[0]
        obs = float(a[ev].mean())
        base = nm(a)
        sims = a[rng.choice(pool, size=(NSIM, len(ev)))].mean(axis=1)
        mu = float(sims.mean())
        p = (1 + int(np.sum(np.abs(sims - mu) >= abs(obs - mu)))) / (NSIM + 1)
        tr = [i for i in ev if i < cut_i]
        te = [i for i in ev if i >= cut_i]
        d_tr = (float(a[tr].mean()) - nm(a[:cut_i])) if len(tr) >= 3 else float("nan")
        d_te = (float(a[te].mean()) - nm(a[cut_i:])) if len(te) >= 3 else float("nan")
        rows.append(make_row(name, w, len(ev), obs, base, p, d_tr, d_te, len(tr), len(te)))
    return rows


def make_row(name, w, n, obs, base, p, d_tr, d_te, n_tr, n_te):
    ok = (p < 0.05 and not np.isnan(d_tr) and not np.isnan(d_te)
          and d_tr != 0 and d_te != 0 and (d_tr > 0) == (d_te > 0)
          and (obs - base > 0) == (d_te > 0))
    return {"grup": name, "pencere": w, "n": n, "obs": obs, "base": base,
            "fark": obs - base, "p": p, "d_tr": d_tr, "d_te": d_te,
            "n_tr": n_tr, "n_te": n_te, "tutarli": bool(ok)}


def analyze_retro(arrs, mask, cut_i, rng):
    rows = []
    n = len(mask)
    if mask.sum() < 30 or n < 400:
        return rows
    for w in ["gün0", "|gün0|"]:
        a = arrs[w]
        valid = ~np.isnan(a)
        a0 = np.where(valid, a, 0.0)
        v = valid.astype(float)

        def stat(mm):
            s1 = a0[mm].sum()
            n1 = v[mm].sum()
            s2 = a0[~mm].sum()
            n2 = v[~mm].sum()
            if n1 == 0 or n2 == 0:
                return float("nan")
            return s1 / n1 - s2 / n2

        obs = stat(mask)
        sims = np.empty(NSIM_RETRO)
        offs = rng.integers(60, n - 60, size=NSIM_RETRO)
        for k, o in enumerate(offs):
            sims[k] = stat(np.roll(mask, int(o)))
        mu = float(np.nanmean(sims))
        p = (1 + int(np.sum(np.abs(sims - mu) >= abs(obs - mu)))) / (NSIM_RETRO + 1)
        d_tr = stat_slice(a0, v, mask, 0, cut_i)
        d_te = stat_slice(a0, v, mask, cut_i, n)
        base = nm(a[~mask])
        in_mean = nm(a[mask])
        rows.append(make_row("Merkür retro DÖNEMİ (tüm günler)", w, int(mask.sum()),
                             in_mean, base, p, d_tr, d_te,
                             int(mask[:cut_i].sum()), int(mask[cut_i:].sum())))
    return rows


def stat_slice(a0, v, mask, lo, hi):
    m = mask[lo:hi]
    x = a0[lo:hi]
    vv = v[lo:hi]
    n1, n2 = vv[m].sum(), vv[~m].sum()
    if n1 < 10 or n2 < 10:
        return float("nan")
    return x[m].sum() / n1 - x[~m].sum() / n2


# ----------------------------------------------------------------------
# 4) HTML
# ----------------------------------------------------------------------
def pct(x):
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else "%+.2f" % (x * 100)


def pv(p):
    return "%.3f" % p


def table(rows, show_asset=False):
    h = ["<div class='w'><table><tr>"]
    if show_asset:
        h.append("<th>Varlık</th>")
    h.append("<th>Olay</th><th>Pencere</th><th>n</th><th>Olay ort %</th>"
             "<th>Baz %</th><th>Fark %</th><th>p</th><th>Eğitim</th>"
             "<th>Test</th><th>Tutarlı</th></tr>")
    for r in rows:
        cls = "ok" if r["tutarli"] else ("lo" if r["p"] < 0.05 else "")
        h.append("<tr class='%s'>" % cls)
        if show_asset:
            h.append("<td>%s</td>" % html.escape(r["varlik"]))
        h.append("<td>%s</td><td>%s</td><td>%d</td><td>%s</td><td>%s</td>"
                 "<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                     html.escape(r["grup"]), r["pencere"], r["n"], pct(r["obs"]),
                     pct(r["base"]), pct(r["fark"]), pv(r["p"]),
                     "%s (%d)" % (pct(r["d_tr"]), r["n_tr"]),
                     "%s (%d)" % (pct(r["d_te"]), r["n_te"]),
                     "EVET" if r["tutarli"] else "-"))
    h.append("</table></div>")
    return "".join(h)


def render(all_rows, per_asset, cover, upcoming, retro_now, retro_next):
    total = len(all_rows)
    sig = sum(1 for r in all_rows if r["p"] < 0.05)
    cons = sum(1 for r in all_rows if r["tutarli"])
    expected = total * 0.05
    bonf = 0.05 / total if total else 0
    top = sorted(all_rows, key=lambda r: r["p"])[:12]

    h = []
    h.append("<!doctype html><html lang='tr'><head><meta charset='utf-8'>"
             "<meta name='viewport' content='width=device-width,initial-scale=1'>"
             "<title>Finansal astroloji testi</title><style>"
             ":root{color-scheme:light dark;--bg:#fff;--fg:#1a1a1a;--mu:#666;--bd:#ddd;"
             "--ok:#d9f2d9;--lo:#fff3cd}"
             "@media(prefers-color-scheme:dark){:root{--bg:#121212;--fg:#eee;--mu:#aaa;"
             "--bd:#333;--ok:#14391a;--lo:#3d3410}}"
             "body{font:14px/1.45 system-ui,sans-serif;margin:12px;background:var(--bg);color:var(--fg)}"
             "h1{font-size:19px}h2{font-size:16px;margin-top:22px}"
             ".w{overflow-x:auto}table{border-collapse:collapse;font-size:12px;white-space:nowrap}"
             "th,td{border:1px solid var(--bd);padding:3px 6px;text-align:right}"
             "th:first-child,td:first-child{text-align:left}"
             "tr.ok{background:var(--ok)}tr.lo{background:var(--lo)}"
             ".mu{color:var(--mu)}.box{border:1px solid var(--bd);border-radius:8px;padding:8px 10px;margin:8px 0}"
             "details{margin:8px 0}summary{cursor:pointer;font-weight:600}"
             "</style></head><body>")
    h.append("<h1>Finansal astroloji testi</h1>")
    h.append("<div class='mu'>Güncelleme: %s UTC. Yöntem: olay günleri vs %d rastgele gün, "
             "eğitim %%%d / test %%%d.</div>" % (
                 dt.datetime.utcnow().strftime("%d.%m.%Y %H:%M"), NSIM,
                 int(TRAIN_FRAC * 100), int(100 - TRAIN_FRAC * 100)))

    h.append("<div class='box'><b>Özet</b><br>Toplam test: %d &middot; p&lt;0.05: <b>%d</b> "
             "(sadece şansla beklenen: ~%.1f) &middot; eğitim+test tutarlı: <b>%d</b><br>"
             "Bonferroni eşiği (çoklu test düzeltmesi): p&lt;%.5f &rarr; geçen: <b>%d</b></div>" % (
                 total, sig, expected, cons, bonf,
                 sum(1 for r in all_rows if r["p"] < bonf)))
    h.append("<div class='box mu'>Okuma: p&lt;0.05 sayısı beklenen şans sayısına yakınsa "
             "sonuçlar tesadüfle uyumludur. Tek tek parlayan satır kanıt değildir; "
             "ancak Bonferroni eşiğini geçen VE eğitim/test tutarlı satırlar ciddiye alınabilir. "
             "Yeşil = tutarlı, sarı = p&lt;0.05 ama tutarsız.</div>")

    h.append("<h2>En düşük p değerli 12 satır</h2>")
    h.append(table(top, show_asset=True))

    h.append("<h2>Yaklaşan astro tarihleri (60 gün)</h2><div class='box'>")
    h.append("<b>Merkür retro:</b> %s" % html.escape(retro_now))
    if retro_next:
        h.append("<br>%s" % html.escape(retro_next))
    h.append("<br>")
    for d, g in upcoming:
        h.append("%s &middot; %s<br>" % (d.strftime("%d.%m.%Y"), html.escape(g)))
    if not upcoming:
        h.append("Yok")
    h.append("</div>")

    h.append("<h2>Varlık bazında tüm sonuçlar</h2>")
    for label, rows in per_asset:
        h.append("<details><summary>%s &middot; %s</summary>%s</details>" % (
            html.escape(label), html.escape(cover.get(label, "")), table(rows)))

    h.append("<h2>Notlar</h2><div class='box mu'>"
             "Gün0 = olay gününün kapanış getirisi; ertesi gün = ondan sonraki gün; "
             "ileri 5g/10g = olay günü kapanışından itibaren; |gün0| = mutlak getiri (oynaklık). "
             "Olay tarihleri UTC'ye göre, ilk işlem gününe eşleniyor. 'Tutulma adayı' yeni/dolunayda "
             "Ay enlemi 1.5 dereceden küçükse işaretlenir (kesin tutulma listesi değildir). "
             "Fark = olay ortalaması - tüm günlerin ortalaması. USD/TRY ve BIST nominal TL "
             "getirileridir; rastgele-gün karşılaştırması bu eğilimi zaten içerir. Altın için "
             "vadeli kontrat (GC=F) kullanılır. Bu bir yatırım tavsiyesi değildir."
             "</div></body></html>")
    return "".join(h)


# ----------------------------------------------------------------------
# 5) ANA AKIS
# ----------------------------------------------------------------------
def run_asset(label, close, events, retro_series, rng):
    dates = close.index
    arrs = window_arrays(close.values)
    cut_i = int(len(dates) * TRAIN_FRAC)
    rows = []
    for name, evs in events.items():
        idx = event_idx(dates, evs)
        rows += analyze_events(name, arrs, idx, cut_i, rng)
    mask = retro_series.reindex(dates, method="ffill").fillna(False).values.astype(bool)
    rows += analyze_retro(arrs, mask, cut_i, rng)
    for r in rows:
        r["varlik"] = label
    return rows


def main():
    try:
        import ephem  # noqa: F401
    except ImportError:
        print("ephem yok: pip install ephem")
        sys.exit(1)
    try:
        import yfinance  # noqa: F401
    except ImportError:
        print("yfinance yok: pip install yfinance")
        sys.exit(1)

    today = pd.Timestamp.today().normalize()
    print("Astro tarihleri hesaplanıyor...")
    events, retro_series, r_start, r_end = compute_astro(today + pd.Timedelta(days=120))
    for k, v in events.items():
        print("  %-36s %d olay" % (k, len(v)))

    rng = np.random.default_rng(SEED)
    all_rows, per_asset, cover = [], [], {}
    for tkr, label in ASSETS:
        try:
            close = get_close(tkr)
        except Exception as e:
            print("%s indirilemedi: %s" % (tkr, e))
            continue
        if close is None or len(close) < 500:
            print("%s: yeterli veri yok" % tkr)
            continue
        print("%s: %d gün (%s - %s)" % (label, len(close), close.index[0].date(),
                                        close.index[-1].date()))
        rows = run_asset(label, close, events, retro_series, rng)
        all_rows += rows
        per_asset.append((label, rows))
        cover[label] = "%d gün, %s - %s" % (len(close), close.index[0].strftime("%d.%m.%Y"),
                                           close.index[-1].strftime("%d.%m.%Y"))

    if not all_rows:
        print("Sonuç yok")
        sys.exit(1)

    horizon = today + pd.Timedelta(days=60)
    upcoming = []
    for g, evs in events.items():
        if g == "Tutulma adayı (hepsi)":
            continue
        for d in evs:
            if today <= d <= horizon:
                upcoming.append((d, g))
    upcoming.sort()

    now_retro = bool(retro_series.get(today, False))
    nxt_s = [d for d in r_start if d > today]
    nxt_e = [d for d in r_end if d > today]
    retro_now = "şu an retro" if now_retro else "şu an direkt"
    parts = []
    if nxt_s:
        parts.append("sonraki başlangıç %s" % nxt_s[0].strftime("%d.%m.%Y"))
    if nxt_e:
        parts.append("sonraki bitiş %s" % nxt_e[0].strftime("%d.%m.%Y"))
    retro_next = ", ".join(parts)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(all_rows, per_asset, cover, upcoming, retro_now, retro_next))

    total = len(all_rows)
    sig = sum(1 for r in all_rows if r["p"] < 0.05)
    cons = sum(1 for r in all_rows if r["tutarli"])
    print("Toplam test %d, p<0.05: %d (beklenen ~%.1f), tutarli: %d" % (
        total, sig, total * 0.05, cons))
    print("Yazıldı:", OUT)


if __name__ == "__main__":
    main()
