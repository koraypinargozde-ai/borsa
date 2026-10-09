# forward.py - ileriye dönük takip: her akşam yeni sinyalleri kaydeder, 15 gün gün gün kâr/zarar hesaplar
import os, json, datetime as dt
import numpy as np
import pandas as pd
import swing  # swing.py ile aynı klasörde olmalı (v2: sade kırılım)

LOG = "docs/forward.json"
HTML = "docs/forward.html"


def replay(tr, F, A):
    """Bir işlemi fiyat verisiyle baştan hesaplar (swing.py ile aynı kurallar). Kapalı işleme dokunmaz."""
    if tr["durum"] in ("kapali", "gecersiz"):
        return tr
    dates = F.index
    i = dates.get_loc(pd.Timestamp(tr["sinyal"]))
    n = len(dates)
    if i + 1 >= n:
        tr["durum"] = "bekliyor"
        return tr
    e = float(A["O"][i + 1])
    stop = float(tr["stop"])
    if (not np.isfinite(e)) or e <= stop or (e - stop) / e * 100 > 15:
        tr["durum"] = "gecersiz"
        tr["giris"] = round(e, 2) if np.isfinite(e) else None
        tr["giris_tarihi"] = str(dates[i + 1].date())
        return tr
    risk = e - stop
    tgt = e + swing.TARGET_R * risk
    tr["giris"] = round(e, 2)
    tr["giris_tarihi"] = str(dates[i + 1].date())
    tr["hedef"] = round(tgt, 2)
    tr["risk_pct"] = round(risk / e * 100, 1)
    last = min(i + swing.MAXH, n - 1)
    gunler = []
    x, why = None, None
    for j in range(i + 1, last + 1):
        o, h, l, c = float(A["O"][j]), float(A["H"][j]), float(A["L"][j]), float(A["C"][j])
        if j > i + 1:
            if o <= stop:
                x, why = o, "stop"
            elif o >= tgt:
                x, why = o, "hedef"
        if x is None:
            if l <= stop:
                x, why = stop, "stop"
            elif h >= tgt:
                x, why = tgt, "hedef"
            elif c < float(A["sma50"][j]):
                x, why = c, "trend"
            elif j - i == swing.MAXH:
                x, why = c, "süre"
        px = x if x is not None else c
        gunler.append(dict(d=str(dates[j].date()), c=round(px, 2), pl=round((px / e - 1) * 100, 2)))
        if x is not None:
            tr["durum"] = "kapali"
            tr["cikis_tarihi"] = str(dates[j].date())
            tr["cikis"] = round(x, 2)
            tr["neden"] = why
            tr["net"] = round((x / e - 1) * 100 - swing.COST, 2)
            tr["R"] = round((x - e) / risk, 2)
            break
    else:
        tr["durum"] = "acik"
    tr["gunler"] = gunler
    return tr


def add_signals(store, log, idx_dates):
    masks = {t: swing.mask(F) for t, (F, A) in store.items()}
    son = log["son_sinyal_tarihi"]
    if son is None:
        todo = [idx_dates[-1]]
    else:
        todo = [d for d in idx_dates if d > pd.Timestamp(son)]
    lastsig = {}
    for tr in log["islemler"]:
        lastsig[tr["t"]] = max(lastsig.get(tr["t"], ""), tr["sinyal"])
    added = 0
    for D in todo:
        cands = []
        for t, (F, A) in store.items():
            if D not in F.index:
                continue
            i = F.index.get_loc(D)
            if not masks[t][i]:
                continue
            ls = lastsig.get(t)
            if ls is not None and pd.Timestamp(ls) in F.index:
                j = F.index.get_loc(pd.Timestamp(ls))
                if i - j < swing.COOL:
                    continue
            rs = float(F["rsr"].iloc[i]) if np.isfinite(F["rsr"].iloc[i]) else 0.0
            cands.append((rs, t, i))
        cands.sort(key=lambda x: -x[0])
        for rs, t, i in cands[:swing.CAP]:
            F = store[t][0]
            log["islemler"].append(dict(
                id=f"{t.replace('.IS', '')}-{D.date()}", t=t, sinyal=str(D.date()),
                kapanis=round(float(F["C"].iloc[i]), 2), direnc=round(float(F["hh20"].iloc[i]), 2),
                stop=round(float(F["stop"].iloc[i]), 2), rs=round(rs * 100), durum="bekliyor", gunler=[]))
            lastsig[t] = str(D.date())
            added += 1
        log["son_sinyal_tarihi"] = str(D.date())
    return added


def chips(gunler):
    out = ""
    for g in gunler:
        cls = "g" if g["pl"] > 0 else "r" if g["pl"] < 0 else ""
        out += f"<span class='{cls}'>{g['pl']:+.1f}</span> "
    return out


def page(log, last_date, mkt_now):
    tr = log["islemler"]
    pend = [x for x in tr if x["durum"] == "bekliyor"]
    opn = [x for x in tr if x["durum"] == "acik"]
    cls = [x for x in tr if x["durum"] == "kapali"]
    inv = [x for x in tr if x["durum"] == "gecersiz"]
    s = ""
    if cls:
        nets = [x["net"] for x in cls]
        win = sum(1 for v in nets if v > 0) / len(nets) * 100
        rr = np.mean([x["R"] for x in cls])
        neden = {}
        for x in cls:
            neden[x["neden"]] = neden.get(x["neden"], 0) + 1
        nd = " · ".join(f"{k}: {v}" for k, v in neden.items())
        s = (f"Kapanan: <b>{len(cls)}</b> · Ort net: <b>{np.mean(nets):+.2f}%</b> · Kazanç oranı: <b>{win:.0f}%</b> · Ort R: {rr:+.2f}<br>"
             f"Çıkış nedenleri: {nd}")
    else:
        s = "Henüz kapanan işlem yok."
    cur = ""
    if opn:
        cp = [x["gunler"][-1]["pl"] - swing.COST for x in opn if x["gunler"]]
        if cp:
            cur = f"<br>Açık işlemlerin şu anki ortalaması (maliyet düşülmüş): <b>{np.mean(cp):+.2f}%</b>"

    prow = ""
    for x in sorted(pend, key=lambda z: -z["rs"]):
        prow += (f"<tr><td class='l'>{x['t'].replace('.IS', '')}</td><td>{x['sinyal']}</td><td>{x['kapanis']:.2f}</td>"
                 f"<td>{x['direnc']:.2f}</td><td>{x['stop']:.2f}</td><td>{x['rs']}</td></tr>")
    if not prow:
        prow = "<tr><td colspan='6'>Giriş bekleyen sinyal yok</td></tr>"

    orow = ""
    for x in sorted(opn, key=lambda z: z["giris_tarihi"], reverse=True):
        g = x["gunler"]
        now = g[-1]["pl"] if g else 0
        c = "g" if now > 0 else "r" if now < 0 else ""
        orow += (f"<tr><td class='l'>{x['t'].replace('.IS', '')}</td><td>{x['giris_tarihi']}</td><td>{x['giris']:.2f}</td>"
                 f"<td>{x['stop']:.2f}</td><td>{x['hedef']:.2f}</td><td>{len(g)}/{swing.MAXH}</td>"
                 f"<td class='{c}'>{now:+.2f}</td><td class='l ch'>{chips(g)}</td></tr>")
    if not orow:
        orow = "<tr><td colspan='8'>Açık işlem yok</td></tr>"

    crow = ""
    for x in sorted(cls, key=lambda z: z["cikis_tarihi"], reverse=True)[:60]:
        c = "g" if x["net"] > 0 else "r" if x["net"] < 0 else ""
        crow += (f"<tr><td class='l'>{x['t'].replace('.IS', '')}</td><td>{x['giris_tarihi']}</td><td>{x['giris']:.2f}</td>"
                 f"<td>{x['cikis_tarihi']}</td><td>{x['cikis']:.2f}</td><td>{x['neden']}</td>"
                 f"<td class='{c}'>{x['net']:+.2f}</td><td>{x['R']:+.2f}</td><td>{len(x['gunler'])}</td></tr>")
    if not crow:
        crow = "<tr><td colspan='9'>Kapanan işlem yok</td></tr>"
    ninv = f" · Geçersiz (gap sonrası risk büyük): {len(inv)}" if inv else ""
    mk = "BIST 100 SMA50 üstünde" if mkt_now else "BIST 100 SMA50 altında"

    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>İleri test</title>
<style>body{{font-family:system-ui,sans-serif;background:#0f1419;color:#e6e6e6;margin:0;padding:12px}}
h1{{font-size:18px}}h2{{font-size:15px;margin-top:22px}}.w{{overflow-x:auto}}
table{{border-collapse:collapse;font-size:12px;white-space:nowrap}}th,td{{padding:5px 7px;border-bottom:1px solid #2a323c;text-align:right}}
th{{background:#1a222c}}td.l,th.l{{text-align:left}}.g{{color:#4ade80}}.r{{color:#f87171}}.ch span{{margin-right:4px}}
.n{{font-size:12px;color:#9aa5b1;line-height:1.5}}</style></head><body>
<h1>İleriye dönük takip (sade kırılım)</h1>
<p class="n">Başlangıç: {log['baslangic']} · Son veri: {last_date.date()} · Piyasa (sadece bilgi): {mk}<br>
Bu sayfa geçmiş test değil: sinyaller her akşam kaydedilir, giriş ertesi gün açılış fiyatıdır, sonuçlar gerçekleştikçe yazılır.
Çıkış kuralları testle aynı: stop, 2R hedef, SMA50 altı kapanış veya 15 gün. Maliyet %{swing.COST}.<br>
Geriye dönük test referansı: işlem başına net ≈ +%1,1, kazanç oranı ≈ %46.</p>
<p class="n">{s}{cur}<br>Toplam kayıt: {len(tr)} · Giriş bekleyen: {len(pend)} · Açık: {len(opn)} · Kapalı: {len(cls)}{ninv}</p>
<h2>Yeni sinyaller (giriş: sonraki gün açılış)</h2>
<div class="w"><table><tr><th class="l">Hisse</th><th>Sinyal</th><th>Kapanış</th><th>Kırılan direnç</th><th>Stop</th><th>RS</th></tr>{prow}</table></div>
<h2>Açık işlemler (gün gün kâr/zarar %, brüt)</h2>
<div class="w"><table><tr><th class="l">Hisse</th><th>Giriş günü</th><th>Giriş</th><th>Stop</th><th>Hedef</th><th>Gün</th><th>Şimdi %</th><th class="l">Gün gün</th></tr>{orow}</table></div>
<h2>Kapanan işlemler (net, maliyet düşülmüş)</h2>
<div class="w"><table><tr><th class="l">Hisse</th><th>Giriş günü</th><th>Giriş</th><th>Çıkış günü</th><th>Çıkış</th><th>Neden</th><th>Net %</th><th>R</th><th>Gün</th></tr>{crow}</table></div>
<p class="n">Oluşturma: {dt.datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC · Veri Yahoo Finance, gecikme/hata olabilir. Bu bir yatırım tavsiyesi değildir.</p>
</body></html>"""


def main():
    tk = swing.get_tickers()
    print("hisse listesi:", len(tk))
    if len(tk) < 100:
        raise SystemExit("HATA: scan.py icinde hisse listesi bulunamadi.")
    data, idx = swing.load(tk)
    if idx is None or len(data) < 100:
        raise SystemExit("HATA: veri yetersiz")
    now_tr = dt.datetime.utcnow() + dt.timedelta(hours=3)
    lastd = idx.index[-1]
    if lastd.date() == now_tr.date() and (now_tr.hour, now_tr.minute) < (18, 20):
        print("seans acik olabilir: bugunku mum atiliyor")
        data = {t: d[d.index < lastd] for t, d in data.items()}
        idx = idx[idx.index < lastd]
    store, mkt_now, last_date = swing.build(data, idx)
    print("hisse:", len(store), "son veri:", last_date.date())

    if os.path.exists(LOG):
        log = json.load(open(LOG, encoding="utf-8"))
    else:
        log = dict(baslangic=str(last_date.date()), son_sinyal_tarihi=None, islemler=[])
    added = add_signals(store, log, list(idx.index))
    print("yeni sinyal:", added)
    for tr in log["islemler"]:
        if tr["t"] in store:
            F, A = store[tr["t"]]
            try:
                replay(tr, F, A)
            except Exception as e:
                print("replay hata", tr["id"], e)
    os.makedirs("docs", exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False)
    with open(HTML, "w", encoding="utf-8") as f:
        f.write(page(log, last_date, mkt_now))
    print("yazildi:", HTML)


if __name__ == "__main__":
    main()
