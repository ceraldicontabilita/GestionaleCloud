"""Righe acquisti → Lotti: il titolare sceglie l'articolo di casa per una riga.

Una scelta fa tre cose, con lo stesso gesto:

* scrive la conferma dell'articolo in Lotti (``articoli_fattura.conferma_articolo``,
  l'unico scrittore di ``nome_mapping``): da lì Lotti sa che quella descrizione
  di fattura è quell'articolo e popola magazzino, FIFO e lotti;
* conferma la classificazione della riga (natura, categoria, destinazione dal
  prodotto; conto e centro di costo dalla regola per categoria, se il titolare
  l'ha impostata, altrimenti restano vuoti: mai un valore plausibile);
* estende la stessa conferma alle altre righe dello stesso fornitore con la
  stessa descrizione esatta, che non hanno ancora una decisione umana.

Le regole per categoria (``righe_acquisti_regole_categoria``) partono vuote:
conto e centro di costo li dice il titolare, non il codice.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services import agenti_proposte
from app.services.piano_conti_ufficiale import CONTI_UFFICIALI
from app.utils.id_fattura import filtro_id

logger = logging.getLogger(__name__)

COLL_REGOLE = "righe_acquisti_regole_categoria"
FONTE_TITOLARE = "lotti_titolare"
FONTE_STESSA_DESCRIZIONE = "lotti_stessa_descrizione"
DESTINAZIONE_LOTTI = "magazzino_lotti"
MAX_RIGHE_ESTESE = 500
_ESCLUDI = {"_id": 0, "xml_raw": 0, "xml_content": 0, "fattura_allegata": 0,
            "document_original_ref": 0, "foto": 0}


class SceltaNonValida(ValueError):
    """La scelta del titolare non è applicabile (riga cambiata, dato mancante…)."""


def _adesso() -> str:
    return datetime.now(timezone.utc).isoformat()


def categorie_lotti() -> List[str]:
    from app.lotti.servizi.dizionario_ingredienti import CATEGORIE
    return list(CATEGORIE)


async def elenco_regole(db) -> List[Dict[str, Any]]:
    """Una riga per categoria di Lotti, anche senza regola (conto/centro vuoti)."""
    salvate = {
        str(r.get("categoria")): r
        for r in await db[COLL_REGOLE].find({}, {"_id": 0}).to_list(None)
    }
    return [
        {"categoria": c, "conto": (salvate.get(c) or {}).get("conto"),
         "centro_costo": (salvate.get(c) or {}).get("centro_costo"),
         "aggiornato_il": (salvate.get(c) or {}).get("aggiornato_il")}
        for c in categorie_lotti()
    ]


async def salva_regola(
    db, categoria: str, conto: Optional[str], centro_costo: Optional[str], utente: str,
) -> Dict[str, Any]:
    categoria = str(categoria or "").strip()
    if categoria not in categorie_lotti():
        raise SceltaNonValida("categoria sconosciuta")
    conto = str(conto or "").strip() or None
    centro_costo = str(centro_costo or "").strip() or None
    if conto and conto not in CONTI_UFFICIALI:
        raise SceltaNonValida("conto fuori dal piano dei conti ufficiale")
    if centro_costo:
        trovato = await db["centri_costo"].find_one({"codice": centro_costo}, {"_id": 0, "codice": 1})
        if not trovato:
            raise SceltaNonValida("centro di costo inesistente")
    record = {"id": categoria, "categoria": categoria, "conto": conto, "centro_costo": centro_costo,
              "aggiornato_il": _adesso(), "aggiornato_da": utente}
    await db[COLL_REGOLE].update_one({"id": categoria}, {"$set": record}, upsert=True)
    return record


async def prodotti_lotti(db_lotti, q: str = "", limite: int = 30) -> List[Dict[str, Any]]:
    """Gli articoli di casa già noti a Lotti (nome canonico), per la tendina."""
    ago = (q or "").strip().lower()
    righe = await db_lotti.nome_mapping.find(
        {"alimentare": {"$ne": False}}, {"_id": 0, "nome_canc": 1, "categoria": 1},
    ).to_list(None)
    visti: Dict[str, Dict[str, Any]] = {}
    for r in righe:
        nome = str(r.get("nome_canc") or "").strip()
        if not nome or (ago and ago not in nome.lower()):
            continue
        visti.setdefault(nome.lower(), {"nome_canc": nome, "categoria": r.get("categoria") or None})
    return sorted(visti.values(), key=lambda x: x["nome_canc"].lower())[:limite]


def _chiave(descrizione: Any) -> str:
    from app.lotti.servizi.articoli_fattura import chiave_descrizione
    return chiave_descrizione(descrizione)


async def _riga_corrente(db, riga_id: str) -> Dict[str, Any]:
    from app.routers.righe_acquisti import costruisci_righe

    fattura_id = riga_id.rsplit(":", 1)[0]
    invoice = await db["invoices"].find_one(
        {"$and": [filtro_id(fattura_id), {"status": {"$nin": ["deleted", "archived"]}}]}, _ESCLUDI,
    )
    riga = next((r for r in costruisci_righe([invoice] if invoice else []) if r.get("id") == riga_id), None)
    if not riga:
        raise SceltaNonValida("riga non trovata")
    return riga


def _classificazione(nome: str, categoria: str, alimentare: bool, regola: Dict[str, Any]) -> Dict[str, Any]:
    return agenti_proposte.valida_classificazione_riga({
        "natura": "ingrediente" if alimentare else "altro",
        "categoria": categoria,
        "conto": regola.get("conto"),
        "centro_costo": regola.get("centro_costo"),
        "destinazione_operativa": DESTINAZIONE_LOTTI if alimentare else None,
        "confidenza": 1.0,
        "spiegazione": f"Articolo di Lotti scelto dal titolare: {nome}",
        "regola": "lotti_articolo",
    })


async def _scrivi_conferma(db, riga: Dict[str, Any], classificazione: Dict[str, Any], utente: str,
                           fonte: str, motivazione: str) -> None:
    esistente = await db[agenti_proposte.COLL_RIGHE_ACQUISTI].find_one({"id": riga["id"]}, {"_id": 0}) or {}
    adesso = _adesso()
    prima = {"stato": esistente.get("stato"),
             "classificazione_confermata": esistente.get("classificazione_confermata")}
    record = {
        "id": riga["id"], "fattura_id": riga.get("fattura_id"), "numero_linea": riga.get("numero_linea"),
        "impronta_riga": agenti_proposte.impronta_riga(riga),
        "identita_regola": agenti_proposte.identita_regola_riga(riga),
        "stato": agenti_proposte.STATO_CONFERMATA, "classificazione_confermata": classificazione,
        "fonte": fonte, "deciso_da": utente, "deciso_il": adesso, "motivazione": motivazione[:500],
        "aggiornato_il": adesso,
        "audit_decisione": {"azione": "assegna_prodotto_lotti", "utente": utente, "deciso_il": adesso,
                            "motivazione": motivazione[:500], "prima": prima,
                            "dopo": {"stato": agenti_proposte.STATO_CONFERMATA,
                                     "classificazione_confermata": classificazione}},
    }
    await db[agenti_proposte.COLL_RIGHE_ACQUISTI].update_one({"id": riga["id"]}, {"$set": record}, upsert=True)


async def _righe_stessa_descrizione(db, riga: Dict[str, Any]) -> List[Dict[str, Any]]:
    from app.routers.righe_acquisti import costruisci_righe

    piva = str(riga.get("partita_iva") or "").strip()
    if not piva:
        return []
    invoices = await db["invoices"].find(
        {"$and": [{"status": {"$nin": ["deleted", "archived"]}},
                  {"$or": [{"supplier_vat": piva}, {"fornitore_partita_iva": piva}, {"cedente_piva": piva}]}]}, _ESCLUDI,
    ).to_list(None)
    chiave = _chiave(riga.get("descrizione_originale"))
    return [
        r for r in costruisci_righe(invoices)
        if r.get("id") != riga["id"] and r.get("partita_iva") == piva
        and _chiave(r.get("descrizione_originale")) == chiave
    ][:MAX_RIGHE_ESTESE]


async def assegna_prodotto(
    db, db_lotti, riga_id: str, nome_canc: str, categoria: str, utente: str, *, alimentare: bool = True,
) -> Dict[str, Any]:
    from app.lotti.servizi.articoli_fattura import conferma_articolo

    nome = str(nome_canc or "").strip()
    categoria = str(categoria or "").strip()
    if alimentare and not nome:
        raise SceltaNonValida("scegli l'articolo")
    if alimentare and categoria not in categorie_lotti():
        raise SceltaNonValida("scegli la categoria")
    if not alimentare:
        nome, categoria = "Non alimentare", "Non Alimentare"
    riga = await _riga_corrente(db, riga_id)
    if not riga.get("descrizione_originale"):
        raise SceltaNonValida("riga senza descrizione")

    esito = await conferma_articolo(db_lotti, riga["descrizione_originale"], nome, alimentare=alimentare)
    if not esito.get("chiave"):
        raise SceltaNonValida("descrizione o articolo mancanti")
    regola = next((r for r in await elenco_regole(db) if r["categoria"] == categoria), {})
    classificazione = _classificazione(nome, categoria, alimentare, regola)

    await _scrivi_conferma(db, riga, classificazione, utente, FONTE_TITOLARE,
                           f"Articolo di Lotti: {nome}")
    estese = 0
    for altra in await _righe_stessa_descrizione(db, riga):
        salvata = await db[agenti_proposte.COLL_RIGHE_ACQUISTI].find_one({"id": altra["id"]}, {"_id": 0, "stato": 1})
        if (salvata or {}).get("stato") == agenti_proposte.STATO_CONFERMATA:
            continue  # una decisione umana già presa non si tocca
        await _scrivi_conferma(db, altra, classificazione, utente, FONTE_STESSA_DESCRIZIONE,
                               f"Stessa descrizione e fornitore: articolo di Lotti {nome}")
        estese += 1
    try:
        from app.services.audit_logger import log_evento
        await log_evento(
            modulo="righe_acquisti", azione="assegna_prodotto_lotti", entita_id=riga_id,
            entita_collection=agenti_proposte.COLL_RIGHE_ACQUISTI, db=db,
            nuovo_stato={"nome_canc": nome, "categoria": categoria, "righe_estese": estese},
            fonte="decisione_umana", utente=utente, dettaglio=f"Articolo di Lotti: {nome}",
        )
    except Exception as exc:  # noqa: BLE001 - il record conserva già l'audit della decisione
        logger.error("[RIGHE-LOTTI] audit esterno non scritto per %s: %s: %s", riga_id, type(exc).__name__, exc)
    return {"classificazione": {**classificazione, "stato": "CONFERMATA"}, "nome_canc": nome,
            "categoria": categoria, "righe_estese": estese, "lotti_aggiornati": esito.get("lotti_aggiornati", 0)}
