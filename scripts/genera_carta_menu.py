"""Costruisce frontend_menu/public/carta/ dai sorgenti della replica del menu Qromo.

Uso: python scripts/genera_carta_menu.py <cartella ceraldi-menu decompressa> <all.css>

La pagina statica (index.html, carta.css, carta.js) prende i dati da
``../api/menu/carta`` (app/menu/carta_qromo.py): niente dati incorporati, foto
e icone sono file in carta/img e carta/icone.
"""
import json
import os
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, Comment

ORIGINE = Path(sys.argv[1])
CSS_ORIGINE = Path(sys.argv[2])
DEST = Path(__file__).resolve().parents[1] / "frontend_menu" / "public" / "carta"
RIF = ORIGINE / "riferimenti-qromo"


def zuppa(nome):
    s = BeautifulSoup((RIF / nome).read_text(encoding="utf-8"), "lxml")
    for c in s.find_all(string=lambda x: isinstance(x, Comment)):
        c.extract()
    for t in s(["script", "noscript", "iframe", "canvas"]):
        t.decompose()
    return s


imgmap = json.loads((ORIGINE / "dati" / "imgmap.json").read_text(encoding="utf-8"))


def foto(url):
    u2 = re.sub(r"-full(\.\w+)$", r"\1", url)
    for cand in (url, u2):
        if imgmap.get(cand):
            return imgmap[cand]  # «img/<file>.webp», relativo a carta/
    return ""


def icona(nome, colore):
    return f"icone/{nome}_{colore.upper()}.svg"


home = zuppa("d_home.html")
app = home.select_one("#app")
cover = foto("https://img.qromo.io/businesses/18rw4uzhl2zkjbm-full.jpeg")
logo = foto("https://img.qromo.io/businesses/y5ih1fut8yaxv8v-full.jpg")
for img in app.select(".menu-banner.menuOnly img"):
    img["src"] = cover
app.select_one(".menu-header .logo-container img")["src"] = logo
mc = app.select_one(".menus-container")
TPL_MENU = str(mc.select_one(".menu-container"))
mc.clear()
pagine = app.select(".pagination-content > .page-content")
pagine[1].clear()
foot = app.select_one(".menu-footer")
for sel in [".footer-buttons", ".logo-container", ".cookie-container", ".line"]:
    for x in foot.select(sel):
        x.decompose()
legale = BeautifulSoup(
    '<div class="cc-legale"><a href="../privacy">Privacy</a> · <a href="../cookie">Cookie</a></div>', "lxml"
).select_one(".cc-legale")
foot.append(legale)
inp = app.select_one(".menu-back-container-absolute input")
inp["id"] = "q"
inp["placeholder"] = "Cerca"
inp["aria-label"] = "Cerca"
for x in app.select(".items-counter-container, .container-cookies"):
    x.decompose()

cat = zuppa("d_cat.html")
TPL_CAT = str(cat.select(".page-content.active-page .menu-category")[1])
itm = [i for i in cat.select(".menu-category-item") if "Espressino" in i.text][0]
for x in itm.select(".item-data-delete"):
    x.decompose()
TPL_ITEM = str(itm)

sh = zuppa("sheet_153843.html").select_one("#product-details-bottom-sheet")
sh["class"] = [c for c in sh.get("class", []) if c != "hidden"] + ["hidden"]
TPL_LIST = str(zuppa("sheet_153754.html").select_one(".lists-container").select_one(".item-list-container"))

flt = zuppa("d_filter.html").select_one("#allergens-filter-bottom-sheet")
flt["class"] = [c for c in flt.get("class", []) if c != "hidden"] + ["hidden"]
for img in flt.select("img"):
    m = re.search(r"icon-(\w+)\.php\?c=([0-9A-Fa-f]{6})", img["src"])
    img["src"] = icona(m.group(1), m.group(2))
    img.parent.parent.parent["data-k"] = m.group(1)

rootvars = (RIF / "rootvars.txt").read_text(encoding="utf-8").split("\n")[0]

css = CSS_ORIGINE.read_text(encoding="utf-8")
css = re.sub(r"@font-face\s*\{[^}]*\}", "", css)
css = css.replace('url("https://img.qromo.io/img/icon-satispay-square.svg")', "none")
css = re.sub(r"https?://[a-z.]*qromo\.(?:it|io)/[^\"\\s)]*", "", css)
(DEST / "carta.css").write_text(css, encoding="utf-8")

tpl_js = (ORIGINE / "sorgenti" / "app_template.html").read_text(encoding="utf-8")
inizio = tpl_js.index("(function(){")
fine = tpl_js.rindex("</script>")
js = tpl_js[inizio:fine]
js = js.replace(
    "const TPL=JSON.parse(document.getElementById('tpl').textContent);\n"
    "const D=JSON.parse(document.getElementById('data').textContent);\n"
    "const ICONS=JSON.parse(document.getElementById('icons').textContent);\n"
    "const IMG=JSON.parse(document.getElementById('imgs').textContent);\n",
    "const TPL=JSON.parse(document.getElementById('tpl').textContent);\n"
    "const ICONS=JSON.parse(document.getElementById('icons').textContent);\n"
    "const IMG=new Proxy({},{get:(_,k)=>k}); // le foto sono gia' URL\n",
    1,
)
assert "const D=" not in js and "new Proxy" in js
js = js.replace("(function(){", "fetch('../api/menu/carta',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(r.status);return r.json()}).then(D=>{", 1)
assert js.rstrip().endswith("})();")
js = js.rstrip()[:-len("})();")] + "}).catch(e=>{document.querySelector('.menus-container').textContent='Menu non disponibile, riprova tra poco.';console.error(e)});\n"
(DEST / "carta.js").write_text(js, encoding="utf-8")

icone_piccole = {}
for f in os.listdir(DEST / "icone"):
    if f.endswith("_DBCCA5.svg"):
        icone_piccole[f[: -len("_DBCCA5.svg")]] = "icone/" + f
icons = {"al": icone_piccole, "generic": "icone/generic.svg"}

html = f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Menù Ceraldi Caffé</title>
<meta name="theme-color" content="#303D21">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700&display=swap">
<link rel="stylesheet" href="carta.css">
<style>
:root{{color-scheme:dark}}
html,body{{background:#303D21}}
body{{margin:0;font-family:Montserrat,system-ui,-apple-system,"Segoe UI",sans-serif}}
[hidden]{{display:none!important}}
.menu-category-item.noDeep{{cursor:default}}
.menu-category-item{{cursor:pointer}}
.cc-legale{{text-align:center;padding:14px 0 26px;font-size:12px;opacity:.8}}
.cc-legale a{{color:inherit}}
.cc-empty{{color:var(--theme-txt2-color);text-align:center;padding:24px 12px;font-size:var(--font-size-s)}}
</style>
<script>document.documentElement.setAttribute('style',{json.dumps(rootvars)});</script>
</head><body>
{app}
<div id="popups">{sh}{flt}</div>
<script id="tpl" type="application/json">{json.dumps({"menu": TPL_MENU, "cat": TPL_CAT, "item": TPL_ITEM, "list": TPL_LIST}).replace("</", "<" + chr(92) + "/")}</script>
<script id="icons" type="application/json">{json.dumps(icons)}</script>
<script src="carta.js"></script>
</body></html>
"""
html = re.sub(r"https?://[a-z.]*qromo\.(?:it|io)/[^\"\\s)]*", "", html)
(DEST / "index.html").write_text(html, encoding="utf-8")
print("index.html", len(html), "carta.css", len(css), "carta.js", len(js))
