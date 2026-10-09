# swingekle.py - ana sayfaya (docs/index.html) "Swing takip" açılır kutusunu ekler / yeniler
import re, json, html as H

IDX = "docs/index.html"
LOG = "docs/forward.json"
A, B = "<!--swing-->", "<!--/swing-->"
GREEN, RED = "#34d399", "#f87171"


def kisa(d):
    try:
        return f"{d[8:10]}.{d[5:7]}"
    except Exception:
        return str(d)


def renk(v):
    return GREEN if v > 0 else RED if v < 0 else "inherit"


def build():
    try:
        log = json.load(open(LOG, encoding="utf-8"))
    except Exception:
        log = None
    pend, opn, cls = [], [], []
    if log:
        for x in log.get("islemler", []):
            d = x.get("durum")
            if d == "bekliyor":
                pend.append(x)
            elif d == "acik":
                opn.append(x)
            elif d == "kapali":
                cls.append(x)
    parts = []
    if cls:
        nets = [x["net"] for x in cls]
        win = sum(1 for v in nets if v > 0) / len(nets) * 100
        parts.append(f"<div>Kapanan: <b>{len(cls)}</b> · Ort net: <b style='color:{renk(sum(nets)/len(nets))}'>"
                     f"{sum(nets)/len(nets):+.2f}%</b> · Kazanç oranı: <b>{win:.0f}%</b></div>")
    else:
        parts.append("<div style='opacity:.7'>Henüz kapanan işlem yok (ilk sonuçlar 15 işlem günü sonra).</div>")

    parts.append("<div style='margin-top:8px;font-weight:600'>Yeni sinyaller (giriş: yarın açılış)</div>")
    if pend:
        for x in sorted(pend, key=lambda z: -z.get("rs", 0))[:10]:
            parts.append(f"<div>{H.escape(x['t'].replace('.IS', ''))} · kapanış {x['kapanis']:.2f} · "
                         f"stop {x['stop']:.2f} · RS {x.get('rs', 0)}</div>")
    else:
        parts.append("<div style='opacity:.7'>Yok</div>")

    parts.append("<div style='margin-top:8px;font-weight:600'>Açık işlemler (gün gün kâr/zarar %)</div>")
    if opn:
        for x in sorted(opn, key=lambda z: z.get("giris_tarihi", ""), reverse=True)[:20]:
            g = x.get("gunler", [])
            now = g[-1]["pl"] if g else 0
            chips = " ".join(f"<span style='color:{renk(k['pl'])}'>{k['pl']:+.1f}</span>" for k in g)
            parts.append(f"<div style='margin-top:4px'><b>{H.escape(x['t'].replace('.IS', ''))}</b> · giriş "
                         f"{x['giris']:.2f} ({kisa(x['giris_tarihi'])}) · gün {len(g)}/15 · "
                         f"<b style='color:{renk(now)}'>{now:+.2f}%</b><br>"
                         f"<span style='font-size:.78rem'>{chips}</span></div>")
    else:
        parts.append("<div style='opacity:.7'>Yok</div>")

    parts.append("<div style='margin-top:10px'><a href='forward.html' style='color:var(--a,#34d399)'>Tüm detay ve kapananlar →</a></div>")
    baslik = f"📈 Swing takip ({len(pend)} yeni · {len(opn)} açık)"
    return (f"{A}<details id='swingtakip' style='background:var(--c,#171b22);border:1px solid var(--b,#262c36);"
            f"border-radius:12px;padding:12px 14px;margin:10px 0'>"
            f"<summary style='font-weight:700;cursor:pointer'>{baslik}</summary>"
            f"<div style='font-size:.85rem;line-height:1.6;margin-top:8px'>{''.join(parts)}</div></details>{B}")


def main():
    s = open(IDX, encoding="utf-8").read()
    s = re.sub(re.escape(A) + ".*?" + re.escape(B), "", s, flags=re.S)
    block = build()
    m = re.search(r"<details", s)
    if m:
        pos = m.start()
    else:
        m = re.search(r"<div class=w>", s)
        pos = m.start() if m else (s.rfind("</main>") if s.rfind("</main>") >= 0 else len(s))
    s = s[:pos] + block + s[pos:]
    open(IDX, "w", encoding="utf-8").write(s)
    print("swing kutusu eklendi")


if __name__ == "__main__":
    main()
