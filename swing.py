# swing.py - gevşek kurallı swing testi (price action + destek/direnç + trend + hacim + volatilite + piyasa yönü + pozisyon kuralı)
import os, re, ast, json, time, datetime as dt
import numpy as np
import pandas as pd

COST = 0.3        # gidiş-dönüş maliyet %
MAXH = 15         # en fazla tutma (işlem günü)
COOL = 10         # aynı hissede sinyaller arası bekleme
PERIOD = "3y"
TARGET_R = 2.0    # hedef = 2R
MIN_TL = 500000   # günlük ort. işlem hacmi alt sınırı (TL)
OUT = "docs/swing.html"


def get_tickers():
    best = []
    for f in ["scan.py"]:
        if not os.path.exists(f):
            continue
        try:
            tree = ast.parse(open(f, encoding="utf-8").read())
        except Exception as e:
            print("scan.py okunamadi:", e)
            continue
        for node in ast.walk(tree):
            cand = []
            if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
                vals = [n.value for n in node.elts if isinstance(n, ast.Constant) and isinstance(n.value, str)]
                if len(vals) == len(node.elts):
                    cand = vals
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 400:
                cand = [t for t in re.split(r"[\s,;]+", node.value.strip()) if t]
            if len(cand) >= 100 and all(re.fullmatch(r"[A-Za-z0-9]{2,7}(\.IS)?", t) for t in cand):
                if len(cand) > len(best):
                    best = cand
    out = []
    for t in best:
        t = t.strip().upper()
        if not t.endswith(".IS"):
            t += ".IS"
        out.append(t)
    return sorted(set(out))


def clean(d):
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    d = d[["Open", "High", "Low", "Close", "Volume"]].copy()
    d.index = pd.to_datetime(d.index).tz_localize(None).normalize()
    d = d[~d.index.duplicated(keep="last")]
    d = d.dropna(subset=["Open", "High", "Low", "Close"])
    d["Volume"] = d["Volume"].fillna(0)
    return d


def load(tickers):
    import yfinance as yf
    data = {}
    for k in range(0, len(tickers), 80):
        chunk = tickers[k:k + 80]
        df = None
        for _ in range(2):
            try:
                df = yf.download(chunk, period=PERIOD, interval="1d", auto_adjust=True,
                                 group_by="ticker", threads=True, progress=False)
                break
            except Exception as e:
                print("indirme hatasi:", e)
                time.sleep(3)
        if df is None or df.empty:
            continue
        for t in chunk:
            try:
                d = clean(df[t])
                if len(d) >= 150:
                    data[t] = d
            except Exception:
                pass
        print("indirildi", min(k + 80, len(tickers)), "/", len(tickers), "gecerli:", len(data))
    idx = None
    for sym in ["XU100.IS", "^XU100"]:
        try:
            x = yf.download(sym, period=PERIOD, interval="1d", auto_adjust=True, progress=False)
            if x is not None and not x.empty:
                idx = clean(x)
                break
        except Exception as e:
            print("endeks hatasi:", e)
    return data, idx


def build(data, idx):
    ic = idx["Close"]
    idx_ret63 = ic / ic.shift(63) - 1
    idx_ok = (ic >= ic.rolling(50).mean() * 0.98)
    store = {}
    rs_cols = {}
    feats = {}
    for t, d in data.items():
        o, h, l, c, v = d["Open"], d["High"], d["Low"], d["Close"], d["Volume"]
        pc = c.shift(1)
        tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
        F = pd.DataFrame(index=d.index)
        F["O"], F["H"], F["L"], F["C"] = o, h, l, c
        F["atr"] = tr.rolling(14).mean()
        F["sma20"] = c.rolling(20).mean()
        F["sma50"] = c.rolling(50).mean()
        v20 = v.rolling(20).mean().shift(1)
        F["rv"] = v / v20.replace(0, np.nan)
        F["tl"] = v20 * c
        F["hh20"] = h.rolling(20).max().shift(1)
        F["ll10"] = l.rolling(10).min()
        F["llp"] = l.shift(10).rolling(20).min()
        ret63 = c / c.shift(63) - 1
        F["rs_raw"] = ret63 - idx_ret63.reindex(F.index).ffill()
        F["piyasa"] = idx_ok.reindex(F.index).ffill().fillna(False).astype(bool)
        feats[t] = F
        rs_cols[t] = F["rs_raw"]
    rank = pd.DataFrame(rs_cols).rank(axis=1, pct=True)
    for t, F in feats.items():
        F["rsr"] = rank[t].reindex(F.index)
        F["atrp"] = F["atr"] / F["C"] * 100
        F["stop"] = np.maximum(F["ll10"] * 0.995, F["C"] - 3 * F["atr"])
        F["riskp"] = (F["C"] - F["stop"]) / F["C"] * 100
        # giriş türleri (gevşek)
        F["kirb"] = (F["C"] > F["hh20"]) & (F["C"] <= F["hh20"] * 1.08)                       # direnç kırılımı
        F["gerib"] = (F["C"] > F["sma50"]) & (F["L"] <= F["sma20"] + 0.5 * F["atr"]) & \
                     (F["C"] >= F["sma20"] * 0.99) & (F["C"] > F["O"])                          # destek dönüşü
        F["volk"] = F["rv"] >= 1.2
        F["volg"] = F["rv"] >= 0.8
        F["trend"] = (F["C"] > F["sma50"]) & (F["ll10"] >= F["llp"] * 0.97)                     # yükselen dip (gevşek)
        F["rs"] = F["rsr"] >= 0.6                                                                # üst %40
        F["volat"] = (F["atrp"] >= 1) & (F["atrp"] <= 8) & (F["riskp"] >= 0.8) & (F["riskp"] <= 12)
        F["liq"] = F["tl"] >= MIN_TL
        A = {k: F[k].to_numpy(dtype=float) for k in ["O", "H", "L", "C", "sma50", "stop"]}
        store[t] = (F, A)
    return store, bool(idx_ok.iloc[-1]), idx.index[-1]


def mask(F, market=True, rs=True, trend=True, vol=True, volat=True, kind="both", mkt_invert=False):
    kir = F["kirb"] & (F["volk"] if vol else True)
    ger = F["gerib"] & (F["volg"] if vol else True)
    e = kir if kind == "kir" else ger if kind == "ger" else (kir | ger)
    m = e & F["liq"]
    if market:
        m = m & F["piyasa"]
    if mkt_invert:
        m = m & (~F["piyasa"])
    if rs:
        m = m & F["rs"]
    if trend:
        m = m & F["trend"]
    if volat:
        m = m & F["volat"]
    return m.to_numpy(dtype=bool)


def pick(m):
    out, last = [], -10 ** 9
    for i in np.flatnonzero(m):
        if i - last >= COOL:
            out.append(int(i))
            last = i
    return out


def sim(A, i):
    n = len(A["C"])
    if i + 1 >= n:
        return None
    e = A["O"][i + 1]
    stop = A["stop"][i]
    if not (np.isfinite(e) and np.isfinite(stop)) or e <= stop:
        return None
    risk = e - stop
    if risk / e * 100 > 15:
        return None
    tgt = e + TARGET_R * risk
    last = min(i + MAXH, n - 1)
    x, why, j = e, "süre", i + 1
    for j in range(i + 1, last + 1):
        o, h, l, c = A["O"][j], A["H"][j], A["L"][j], A["C"][j]
        if j > i + 1:
            if o <= stop:
                x, why = o, "stop"
                break
            if o >= tgt:
                x, why = o, "hedef"
                break
        if l <= stop:
            x, why = stop, "stop"
            break
        if h >= tgt:
            x, why = tgt, "hedef"
            break
        if c < A["sma50"][j]:
            x, why = c, "trend"
            break
        if j == last:
            x, why = c, "süre"
            break
    g10 = np.nan
    if i + 10 < n:
        g10 = (A["C"][i + 10] / e - 1) * 100 - COST
    return dict(ret=(x / e - 1) * 100 - COST, R=(x - e) / risk, why=why, hold=j - i, g10=g10)


def run_group(store, fn, rnd=False):
    rows = []
    rng = np.random.default_rng(7)
    for t, (F, A) in store.items():
        if rnd:
            ok = (F["liq"] & F["stop"].notna() & F["atr"].notna() & F["sma50"].notna()).to_numpy(dtype=bool)
            ids = np.flatnonzero(ok & (rng.random(len(F)) < 0.04))
            ids = [int(i) for i in ids]
        else:
            ids = pick(fn(F))
        for i in ids:
            r = sim(A, i)
            if r:
                r["date"] = F.index[i]
                r["t"] = t
                rows.append(r)
    return pd.DataFrame(rows)


def summ(df, cut):
    if df.empty:
        return None
    tr, te = df[df["date"] < cut], df[df["date"] >= cut]
    m = lambda x: float(x["ret"].mean()) if len(x) else float("nan")
    return dict(n=len(df), ort=float(df["ret"].mean()), med=float(df["ret"].median()),
                win=float((df["ret"] > 0).mean() * 100), R=float(df["R"].mean()),
                stop=float((df["why"] == "stop").mean() * 100), hed=float((df["why"] == "hedef").mean() * 100),
                hold=float(df["hold"].mean()), g10=float(df["g10"].mean()),
                ntr=len(tr), tr=m(tr), nte=len(te), te=m(te))


def cell(x, d=2, sign=True, color=True):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "<td>-</td>"
    s = f"{x:+.{d}f}" if sign else f"{x:.{d}f}"
    c = ""
    if color:
        c = ' class="g"' if x > 0 else ' class="r"' if x < 0 else ""
    return f"<td{c}>{s}</td>"


def main():
    tk = get_tickers()
    print("hisse listesi:", len(tk))
    if len(tk) < 100:
        raise SystemExit("HATA: scan.py icinde hisse listesi bulunamadi. geriye.py'nin ilk 40 satirini yapistir.")
    data, idx = load(tk)
    if idx is None or len(data) < 100:
        raise SystemExit("HATA: veri yetersiz (hisse: %d, endeks: %s)" % (len(data), idx is not None))
    store, mkt_now, last_date = build(data, idx)
    dates = sorted(idx.index)
    cut = dates[int(len(dates) * 0.6)]
    print("hisse:", len(store), "kesim tarihi:", cut.date())

    groups = [
        ("TÜMÜ (gevşek kurallar)", lambda F: mask(F)),
        ("Piyasa filtresi kapalı", lambda F: mask(F, market=False)),
        ("Piyasa düşüşte (BIST100 < SMA50)", lambda F: mask(F, market=False, mkt_invert=True)),
        ("RS (göreceli güç) kapalı", lambda F: mask(F, rs=False)),
        ("Trend yapısı kapalı", lambda F: mask(F, trend=False)),
        ("Hacim şartı kapalı", lambda F: mask(F, vol=False)),
        ("Volatilite filtresi kapalı", lambda F: mask(F, volat=False)),
        ("Sadece direnç kırılımı", lambda F: mask(F, kind="kir")),
        ("Sadece destek dönüşü", lambda F: mask(F, kind="ger")),
    ]
    res = []
    for name, fn in groups:
        df = run_group(store, fn)
        s = summ(df, cut)
        print(name, "->", None if s is None else (s["n"], round(s["ort"], 2), round(s["tr"], 2), round(s["te"], 2)))
        res.append((name, s))
    base = summ(run_group(store, None, rnd=True), cut)
    res.append(("Rastgele giriş (kural yok, aynı çıkış)", base))
    print("baz:", None if base is None else (base["n"], round(base["ort"], 2)))

    rows = ""
    for name, s in res:
        if s is None:
            rows += f"<tr><td class='l'>{name}</td><td colspan='12'>sinyal yok</td></tr>"
            continue
        flag = " ✅" if (s["tr"] > 0 and s["te"] > 0 and s["n"] >= 30) else ""
        rows += (f"<tr><td class='l'>{name}{flag}</td><td>{s['n']}</td>" + cell(s["ort"]) + cell(s["med"]) +
                 cell(s["win"], 0, False, False) + cell(s["R"]) + cell(s["stop"], 0, False, False) +
                 cell(s["hed"], 0, False, False) + cell(s["hold"], 1, False, False) + cell(s["g10"]) +
                 cell(s["tr"]) + f"<td>{s['ntr']}</td>" + cell(s["te"]) + f"<td>{s['nte']}</td></tr>")

    # güncel adaylar (son bar, tüm filtreler açık; giriş ertesi gün açılış)
    cands = []
    for t, (F, A) in store.items():
        if F.index[-1] != last_date:
            continue
        if not mask(F)[-1]:
            continue
        r = F.iloc[-1]
        kir = bool(r["kirb"] and r["volk"])
        stp = float(r["stop"])
        c = float(r["C"])
        cands.append(dict(t=t.replace(".IS", ""), tip="Kırılım" if kir else "Destek dönüşü", c=c, stop=stp,
                          hedef=c + TARGET_R * (c - stp), risk=float(r["riskp"]), rs=float(r["rsr"]),
                          rv=float(r["rv"]), atr=float(r["atrp"])))
    cands.sort(key=lambda x: -x["rs"])
    crow = ""
    for x in cands[:30]:
        crow += (f"<tr><td class='l'>{x['t']}</td><td>{x['tip']}</td><td>{x['c']:.2f}</td><td>{x['stop']:.2f}</td>"
                 f"<td>{x['hedef']:.2f}</td><td>{x['risk']:.1f}</td><td>{x['rs']*100:.0f}</td><td>{x['rv']:.1f}x</td></tr>")
    if not crow:
        crow = "<tr><td colspan='8'>Şu an tüm kuralları sağlayan aday yok</td></tr>"
    mk = "AÇIK (BIST 100 ortalamasının üstünde)" if mkt_now else "KAPALI (BIST 100 SMA50 altında, alım sinyali verilmez)"

    html = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Swing testi</title>
<style>body{{font-family:system-ui,sans-serif;background:#0f1419;color:#e6e6e6;margin:0;padding:12px}}
h1{{font-size:18px}}h2{{font-size:15px;margin-top:22px}}.w{{overflow-x:auto}}
table{{border-collapse:collapse;font-size:12px;white-space:nowrap}}th,td{{padding:5px 7px;border-bottom:1px solid #2a323c;text-align:right}}
th{{background:#1a222c;position:sticky;top:0}}td.l,th.l{{text-align:left}}.g{{color:#4ade80}}.r{{color:#f87171}}
.n{{font-size:12px;color:#9aa5b1;line-height:1.5}}</style></head><body>
<h1>Swing testi (gevşek kurallar)</h1>
<p class="n">Hisse: {len(store)} · Dönem: {PERIOD} · Eğitim/test kesimi: {cut.date()} (%60/%40) · Giriş: sinyalden sonraki gün açılış · Maliyet %{COST} ·
Çıkış: stop (swing dip / 3 ATR), hedef {TARGET_R:g}R, SMA50 altı kapanış (trend bozuldu) veya {MAXH} gün · Stop önce sayılır · Aynı hissede {COOL} gün bekleme.<br>
Kurallar: direnç kırılımı (20g zirve + hacim 1,2x) VEYA SMA20 desteğine dönüş (yeşil mum, hacim 0,8x) · yükselen dip + SMA50 üstü · RS üst %40 · BIST 100 SMA50'nin %2 yakınında/üstünde · ATR %1-8.
✅ = eğitim ve testte birlikte pozitif (n≥30).</p>
<div class="w"><table><tr><th class="l">Grup</th><th>n</th><th>Ort net %</th><th>Medyan</th><th>Kazanç %</th><th>Ort R</th><th>Stop %</th><th>Hedef %</th><th>Gün</th><th>10g net</th><th>Eğitim</th><th>n</th><th>Test</th><th>n</th></tr>
{rows}</table></div>
<h2>Güncel adaylar ({last_date.date()} kapanışı)</h2>
<p class="n">Piyasa filtresi: {mk}. Giriş ertesi gün açılış; stop/hedef kapanışa göre yaklaşıktır. Test sonucu pozitif çıkmadan işlem sinyali değildir.</p>
<div class="w"><table><tr><th class="l">Hisse</th><th>Tür</th><th>Kapanış</th><th>Stop</th><th>Hedef</th><th>Risk %</th><th>RS</th><th>Hacim</th></tr>
{crow}</table></div>
<p class="n">Oluşturma: {dt.datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC · Uyarı: güncel hisse listesi (hayatta kalma yanlılığı), örnekler üst üste binebilir.</p>
</body></html>"""
    os.makedirs("docs", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    with open("docs/swing.json", "w", encoding="utf-8") as f:
        json.dump(dict(tarih=str(last_date.date()), piyasa=mkt_now, adaylar=cands[:30]), f, ensure_ascii=False)
    print("yazildi:", OUT)


if __name__ == "__main__":
    main()
