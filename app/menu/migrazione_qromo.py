"""Sincronizzazione del catalogo dal menu digitale Qromo (la piattaforma con
cui il locale gestisce davvero il menu: https://<sottodominio>.qromo.it).

Qromo non offre un'API pubblica documentata: la home del menu incorpora
l'intero catalogo (categorie, sottocategorie, prodotti, prezzi, allergeni,
immagini) come costanti JavaScript nel primo ``<script>`` della pagina — gli
stessi dati che il sito manda a qualunque visitatore per disegnare il menu,
letti qui invece che nel browser. Nessun login, nessuno scraping dell'HTML
visibile.

Fonte autorevole: il proprietario gestisce il menu reale su Qromo. Le
sottocategorie ``BANCO - *`` sono un listino interno di cassa con prezzi
diversi dallo stesso prodotto pubblicato al cliente e vengono escluse
("Espresso Decaffeinato" a listino cliente costa piu' del duplicato BANCO);
la categoria "Comunicazioni" non contiene prodotti reali. Restano solo i
menu pubblicati (``available=1``) con almeno un prodotto attivo. Le immagini
vengono scaricate nell'archivio binari a contenuto (deduplicate per hash);
i 39 tag allergene/dietetici di Qromo (comprese le sottospecie di frutta a
guscio/cereali e diciture non alimentari come vegano/piccante/bio) sono
ridotti ai 14 allergeni UE gia' gestiti dal modulo (``MAPPA_ALLERGENI_QROMO``);
le diciture non alimentari non hanno un allergene corrispondente e vengono
scartate.

Idempotente: ogni esecuzione sostituisce per intero categorie, sottocategorie
e prodotti con lo stato attuale di Qromo (stesso pattern delle altre
migrazioni del modulo) — una modifica fatta SOLO da Gestione menu e non anche
su Qromo va persa alla sincronizzazione successiva, e questo e' l'uso
previsto: Qromo resta l'unico punto in cui si modifica il catalogo. Non
tocca sale, ordini, configurazione QR o gli allergeni (gia' seedati a parte).

Uso: ``POST /api/menu/admin/migrazione-qromo`` (solo admin) oppure da riga
di comando con le env del gestionale:

    python -m app.menu.migrazione_qromo
    python -m app.menu.migrazione_qromo --dry-run
    python -m app.menu.migrazione_qromo --sottodominio altronome
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from app.menu import storage as st

logger = logging.getLogger(__name__)

SOTTODOMINIO_DEFAULT = "ceraldicaffe"
PREFISSO_MENU_BANCO = "BANCO - "
_COSTANTE_RE = re.compile(r"const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=")

Progress = Optional[Callable[[str, int], None]]

# Riduzione dei 39 tag Qromo ai 14 allergeni UE gestiti da app/menu/allergeni.py.
# Le sottospecie di frutta a guscio/cereali confluiscono nell'allergene
# generico; le diciture non alimentari (vegano, piccante, bio, alcol, halal,
# kosher, "senza allergeni", surgelato...) non compaiono qui: non sono
# allergeni e vengono scartate.
MAPPA_ALLERGENI_QROMO = {
    "allergens_celery": "celery",
    "allergens_clams": "molluscs",
    "allergens_dioxide": "sulphites",
    "allergens_egg": "eggs",
    "allergens_fish": "fish",
    "allergens_gluten": "gluten",
    "allergens_lupins": "lupin",
    "allergens_milk": "milk",
    "allergens_mustard": "mustard",
    "allergens_peanuts": "peanuts",
    "allergens_sesame": "sesame",
    "allergens_shellfish": "crustaceans",
    "allergens_soia": "soy",
    "allergens_wot": "nuts",
    "allergens_almond": "nuts",
    "allergens_barley": "gluten",
    "allergens_brazil_nuts": "nuts",
    "allergens_cashew": "nuts",
    "allergens_hazelnuts": "nuts",
    "allergens_macadamia": "nuts",
    "allergens_oats": "gluten",
    "allergens_pecan": "nuts",
    "allergens_pistachios": "nuts",
    "allergens_rye": "gluten",
    "allergens_spelt": "gluten",
    "allergens_walnuts": "nuts",
    "allergens_wheat": "gluten",
    "allergens_kamut": "gluten",
}


def _estrai_costanti_javascript(html: str) -> Dict[str, str]:
    """Isola il primo blocco ``<script>...</script>`` e restituisce, per ogni
    ``const NOME = valore;`` di primo livello, il testo grezzo del valore
    (JSON o un letterale JS semplice come ``null``/``true``)."""
    match = re.search(r"<script>(.*?)</script>", html, re.S)
    if not match:
        raise ValueError("Pagina Qromo senza il blocco di configurazione atteso: sottodominio errato?")
    script = match.group(1)
    nomi = _COSTANTE_RE.findall(script)
    posizioni: List[Tuple[str, int]] = [(nome, script.index(f"const {nome} =")) for nome in nomi]
    valori: Dict[str, str] = {}
    for indice, (nome, inizio) in enumerate(posizioni):
        inizio_valore = inizio + len(f"const {nome} =")
        fine = posizioni[indice + 1][1] if indice + 1 < len(posizioni) else len(script)
        grezzo = script[inizio_valore:fine].strip()
        if grezzo.endswith(";"):
            grezzo = grezzo[:-1]
        valori[nome] = grezzo
    return valori


def _costante_json(costanti: Dict[str, str], nome: str, default: Any) -> Any:
    grezzo = costanti.get(nome)
    if not grezzo or grezzo in ("null", "undefined"):
        return default
    try:
        return json.loads(grezzo)
    except json.JSONDecodeError:
        logger.warning("Costante Qromo %s non decodificabile come JSON", nome)
        return default


class SorgenteQromo:
    def __init__(self, sottodominio: str):
        self.url = f"https://{sottodominio}.qromo.it/"
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers={"User-Agent": "GestionaleCloud-sync/1.0"})

    async def chiudi(self) -> None:
        await self.client.aclose()

    async def catalogo(self) -> Dict[str, Any]:
        risposta = await self.client.get(self.url)
        risposta.raise_for_status()
        costanti = _estrai_costanti_javascript(risposta.text)
        return {
            "menus": _costante_json(costanti, "menus", []),
            "menusCategories": _costante_json(costanti, "menusCategories", []),
            "menusItems": _costante_json(costanti, "menusItems", []),
            "menusItemsAllergens": _costante_json(costanti, "menusItemsAllergens", []),
            "allergens": _costante_json(costanti, "allergens", []),
        }

    async def scarica_immagine(self, url: str) -> Optional[Tuple[bytes, str]]:
        try:
            risposta = await self.client.get(url, headers={"Accept": "image/*"})
            risposta.raise_for_status()
            tipo = (risposta.headers.get("content-type") or "").split(";")[0].strip() or "image/jpeg"
            if not tipo.startswith("image/"):
                return None
            return risposta.content, tipo
        except Exception as exc:  # rete, 404, timeout: si conta e si va avanti
            logger.warning("Immagine Qromo non scaricata %s: %s", url, exc)
            return None


def _prezzo(centesimi: Optional[int]) -> str:
    valore = (centesimi or 0) / 100
    testo = f"{valore:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"€ {testo}"


def _pulisci(testo: Optional[str]) -> Optional[str]:
    if not isinstance(testo, str):
        return None
    testo = testo.strip()
    return testo or None


async def _porta_immagine(sorgente: SorgenteQromo, url: Optional[str], con_immagini: bool, cache: Dict[str, Optional[str]], esito: Dict[str, int]) -> Optional[str]:
    if not url or not con_immagini:
        return url
    if url not in cache:
        scaricata = await sorgente.scarica_immagine(url)
        if scaricata is None:
            cache[url] = None
            esito["immagini_non_scaricate"] += 1
        else:
            contenuto, tipo = scaricata
            nome = url.rsplit("/", 1)[-1].split("?", 1)[0] or "immagine"
            salvata = await st.salva_immagine(contenuto, nome, tipo)
            cache[url] = salvata["url"]
            esito["immagini_scaricate"] += 1
    return cache[url]


async def sincronizza(
    *, sottodominio: str = SOTTODOMINIO_DEFAULT, dry_run: bool = False,
    con_immagini: bool = True, progress: Progress = None,
) -> Dict[str, Any]:
    sorgente = SorgenteQromo(sottodominio)
    esito: Dict[str, Any] = {
        "dry_run": dry_run, "sottodominio": sottodominio, "tabelle": {},
        "immagini_scaricate": 0, "immagini_non_scaricate": 0, "coincide": True,
    }
    cache: Dict[str, Optional[str]] = {}
    try:
        dati = await sorgente.catalogo()

        menu_da_includere = {
            m["menu_id"] for m in dati["menus"]
            if m.get("available") == 1 and not str(m.get("name") or "").startswith(PREFISSO_MENU_BANCO)
        }
        categorie_qromo = [m for m in dati["menus"] if m["menu_id"] in menu_da_includere]

        sottocategorie_qromo = [
            c for c in dati["menusCategories"]
            if c.get("menu_id") in menu_da_includere and c.get("active") == 1
        ]
        id_sottocategorie = {c["menu_category_id"] for c in sottocategorie_qromo}

        prodotti_qromo = [
            p for p in dati["menusItems"]
            if p.get("category_id") in id_sottocategorie and p.get("available") == 1
        ]
        id_prodotti = {p["menu_item_id"] for p in prodotti_qromo}

        # Una sottocategoria/categoria senza nemmeno un prodotto pubblicato
        # (es. "Comunicazioni", che su Qromo esiste solo come segnaposto senza
        # prodotti reali) non va replicata: il cliente non la vedrebbe nemmeno
        # sul menu vero.
        sottocategorie_con_prodotti = {p["category_id"] for p in prodotti_qromo}
        sottocategorie_qromo = [c for c in sottocategorie_qromo if c["menu_category_id"] in sottocategorie_con_prodotti]
        sottocat_by_id = {c["menu_category_id"]: c for c in sottocategorie_qromo}
        categorie_con_sottocategorie = {c["menu_id"] for c in sottocategorie_qromo}
        categorie_qromo = [c for c in categorie_qromo if c["menu_id"] in categorie_con_sottocategorie]

        nome_allergene = {a["allergen_id"]: a.get("name_key") for a in dati["allergens"]}
        allergeni_per_prodotto: Dict[int, List[str]] = {}
        for legame in dati["menusItemsAllergens"]:
            if legame.get("menu_item_id") not in id_prodotti:
                continue
            mappato = MAPPA_ALLERGENI_QROMO.get(nome_allergene.get(legame.get("allergen_id")))
            if not mappato:
                continue
            lista = allergeni_per_prodotto.setdefault(legame["menu_item_id"], [])
            if mappato not in lista:
                lista.append(mappato)

        # In prova non si scrive nulla: anche scaricare le immagini sarebbe un
        # effetto collaterale (rete, righe nell'archivio binari) fuori posto
        # in un'anteprima "conta senza scrivere".
        scarica_immagini = con_immagini and not dry_run

        doc_categorie = []
        for c in categorie_qromo:
            nome = _pulisci(c.get("name")) or f"Menu {c['menu_id']}"
            immagine = await _porta_immagine(sorgente, c.get("picture"), scarica_immagini, cache, esito)
            doc_categorie.append({"id": c["menu_id"], "name": nome, "nameIT": nome, "image": immagine})

        doc_sottocategorie = []
        for c in sottocategorie_qromo:
            nome = _pulisci(c.get("name")) or f"Sezione {c['menu_category_id']}"
            immagine = await _porta_immagine(sorgente, c.get("picture"), scarica_immagini, cache, esito)
            doc_sottocategorie.append({
                "id": c["menu_category_id"], "category_id": c["menu_id"],
                "name": nome, "nameIT": nome, "image": immagine,
            })

        doc_prodotti = []
        for p in prodotti_qromo:
            sottocat = sottocat_by_id[p["category_id"]]
            nome = _pulisci(p.get("name")) or f"Prodotto {p['menu_item_id']}"
            descrizione = _pulisci(p.get("ingredients"))
            immagine = await _porta_immagine(sorgente, p.get("picture"), scarica_immagini, cache, esito)
            doc_prodotti.append({
                "id": p["menu_item_id"], "category_id": sottocat["menu_id"], "subcategory_id": p["category_id"],
                "name": nome, "nameIT": nome, "price": _prezzo(p.get("price")),
                "description": descrizione, "descriptionIT": descrizione,
                "allergens": allergeni_per_prodotto.get(p["menu_item_id"], []),
                "image": immagine,
            })

        for tabella, collezione, docs in (
            ("menu", st.COLL_CATEGORIE, doc_categorie),
            ("sottocategorie", st.COLL_SOTTOCATEGORIE, doc_sottocategorie),
            ("prodotti", st.COLL_PRODOTTI, doc_prodotti),
        ):
            if progress:
                progress(tabella, len(docs))
            if not dry_run:
                await st.elimina(collezione, {})
                for doc in docs:
                    await st.inserisci(collezione, doc)
            destinazione = len(docs) if dry_run else await st.db()[collezione].count_documents({})
            esito["tabelle"][tabella] = {"sorgente": len(docs), "destinazione": destinazione, "collezione": collezione}
            if destinazione != len(docs):
                esito["coincide"] = False
    finally:
        await sorgente.chiudi()
    return esito


def _main() -> None:
    import os

    from app.database import Database

    parser = argparse.ArgumentParser(description="Sincronizzazione del menu da Qromo -> GestionaleCloud")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--senza-immagini", action="store_true")
    parser.add_argument("--sottodominio", default=os.environ.get("QROMO_SOTTODOMINIO", SOTTODOMINIO_DEFAULT))
    args = parser.parse_args()

    async def _run():
        await Database.connect_db()
        try:
            esito = await sincronizza(
                sottodominio=args.sottodominio, dry_run=args.dry_run,
                con_immagini=not args.senza_immagini, progress=lambda n, c: print(f"{n}: {c}"),
            )
        finally:
            await Database.close_db()
        print(esito)
        if not esito["coincide"]:
            raise SystemExit(2)

    asyncio.run(_run())


if __name__ == "__main__":
    _main()
