"""Righe acquisti → Lotti: il titolare sceglie l'articolo di casa per una riga.

Una scelta fa tre cose, con lo stesso gesto:

* scrive la conferma dell'articolo in Lotti (``articoli_fattura.conferma_articolo``,
  l'unico scrittore di ``nome_mapping``): da lì Lotti sa che quella descrizione
  di fattura è quell'articolo e popola magazzino, FIFO e lotti;
* conferma la classificazione della riga (natura, categoria, destinazione, conto
  e centro di costo: ogni campo lo corregge il titolare; se non lo tocca, conto e
  centro vengono dalla regola per categoria, altrimenti restano vuoti: mai un
  valore plausibile);
* estende la stessa conferma alle altre righe dello stesso fornitore con la
  stessa descrizione esatta, che non hanno ancora una decisione umana.

``proponi`` legge la riga e suggerisce categoria e natura **dal nome** (quello che
Lotti già sa o che il nome dice con certezza): è una proposta, non un dato.

«Non è un cespite» (shopper, buste, materiale di consumo) è un flag della
classificazione confermata: i due punti che creano cespiti da una fattura
(`handlers/cespiti.py` e lo scan manuale) lo leggono con ``chiavi_non_cespite``.

Le regole per categoria (``righe_acquisti_regole_categoria``) partono vuote:
conto e centro di costo li dice il titolare, non il codice.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from app.services import agenti_proposte
from app.services.piano_conti_ufficiale import CONTI_UFFICIALI
from app.utils.id_fattura import filtro_id, varianti_id

logger = logging.getLogger(__name__)

COLL_REGOLE = "righe_acquisti_regole_categoria"
FONTE_TITOLARE = "lotti_titolare"
FONTE_STESSA_DESCRIZIONE = "lotti_stessa_descrizione"
DESTINAZIONE_LOTTI = "magazzino_lotti"
MAX_RIGHE_ESTESE = 500
_ESCLUDI = {"_id": 0, "xml_raw": 0, "xml_content": 0, "fattura_allegata": 0,
            "document_original_ref": 0, "foto": 0}

#: Materiale di consumo che dal nome non è merce alimentare né un bene
#: ammortizzabile. Sono **proposte** (il titolare le conferma): una parola
#: all'inizio di parola, mai dentro una più lunga.
_CONSUMO = [
    ("pulizia", ["detersiv", "sgrassat", "igienizz", "sanific", "candeggin", "detergent"]),
    ("altro", ["shopper", "busta", "buste", "sacchett", "imball", "tovagliol", "cannuc",
               "bicchier", "pellicola", "vaschett", "guant"]),
]
_CONSUMO_RX = [
    (natura, re.compile(r"(?<![a-zà-ÿ])(?:" + "|".join(re.escape(p) for p in parole) + ")", re.IGNORECASE))
    for natura, parole in _CONSUMO
]


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


async def _controlla_conto_e_centro(db, conto: Optional[str], centro_costo: Optional[str]) -> None:
    if conto and conto not in CONTI_UFFICIALI:
        raise SceltaNonValida("conto fuori dal piano dei conti ufficiale")
    if centro_costo:
        trovato = await db["centri_costo"].find_one({"codice": centro_costo}, {"_id": 0, "codice": 1})
        if not trovato:
            raise SceltaNonValida("centro di costo inesistente")


async def salva_regola(
    db, categoria: str, conto: Optional[str], centro_costo: Optional[str], utente: str,
) -> Dict[str, Any]:
    categoria = str(categoria or "").strip()
    if categoria not in categorie_lotti():
        raise SceltaNonValida("categoria sconosciuta")
    conto = str(conto or "").strip() or None
    centro_costo = str(centro_costo or "").strip() or None
    await _controlla_conto_e_centro(db, conto, centro_costo)
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


async def proponi(db, db_lotti, riga_id: str) -> Dict[str, Any]:
    """Cosa dice il nome della riga: articolo, categoria, natura, flag cespite.

    Fonti, in ordine: l'associazione che Lotti ha già per quella descrizione;
    la categoria che il nome dice con certezza (`categoria_da_testo`); il
    materiale di consumo riconosciuto per parola. Senza una fonte i campi
    restano ``None``: la riga si classifica a mano.
    """
    from app.lotti.servizi.dizionario_ingredienti import categoria_da_testo

    riga = await _riga_corrente(db, riga_id)
    descrizione = riga.get("descrizione_originale") or ""
    chiave = _chiave(descrizione)
    esito: Dict[str, Any] = {
        "nome_canc": None, "categoria": None, "natura": None, "alimentare": True,
        "non_cespite": False, "fonte": None, "spiegazione": "Nessuna proposta: classifica la riga a mano.",
    }
    noto = await db_lotti.nome_mapping.find_one({"descrizione_key": chiave}, {"_id": 0}) if chiave else None
    if noto and str(noto.get("nome_canc") or "").strip():
        esito.update({
            "nome_canc": str(noto["nome_canc"]).strip(),
            "alimentare": noto.get("alimentare") is not False,
            "fonte": "lotti_confermato" if noto.get("confermato") else "lotti_proposta",
            "spiegazione": ("Lotti ha già confermato questo articolo." if noto.get("confermato")
                            else "Lotti ha una proposta per questa descrizione, non ancora confermata."),
        })
        if noto.get("categoria") in categorie_lotti():
            esito["categoria"] = noto["categoria"]
    if not esito["categoria"] and esito["alimentare"]:
        categoria = categoria_da_testo(descrizione)
        if categoria:
            esito.update({"categoria": categoria, "fonte": esito["fonte"] or "dal_nome",
                          "spiegazione": f"Il nome dice «{categoria}»."})
    if not esito["nome_canc"] and not esito["categoria"]:
        testo = " ".join(str(descrizione).lower().split())
        for natura, rx in _CONSUMO_RX:
            if rx.search(testo):
                esito.update({
                    "alimentare": False, "natura": natura, "non_cespite": True,
                    "categoria": "Non Alimentare", "nome_canc": "Non alimentare", "fonte": "dal_nome",
                    "spiegazione": "Dal nome sembra materiale di consumo: non è merce di magazzino né un cespite.",
                })
                break
    if esito["alimentare"] and esito["categoria"]:
        esito["natura"] = esito["natura"] or "ingrediente"
    regola = next((r for r in await elenco_regole(db) if r["categoria"] == esito["categoria"]), {})
    esito["conto"], esito["centro_costo"] = regola.get("conto"), regola.get("centro_costo")
    return esito


def _classificazione(nome: str, categoria: str, alimentare: bool, regola: Dict[str, Any],
                     scelta: Dict[str, Any]) -> Dict[str, Any]:
    natura = scelta.get("natura") or ("ingrediente" if alimentare else "altro")
    return agenti_proposte.valida_classificazione_riga({
        "natura": natura,
        "categoria": categoria,
        "conto": scelta.get("conto") or regola.get("conto"),
        "centro_costo": scelta.get("centro_costo") or regola.get("centro_costo"),
        "destinazione_operativa": (scelta.get("destinazione_operativa")
                                   if scelta.get("destinazione_operativa") is not None
                                   else (DESTINAZIONE_LOTTI if alimentare else None)),
        "confidenza": 1.0,
        "spiegazione": f"Articolo di Lotti scelto dal titolare: {nome}",
        "regola": "lotti_articolo",
        "non_cespite": scelta.get("non_cespite") is True,
    }, rigorosa=True)


async def _scrivi_conferma(db, riga: Dict[str, Any], classificazione: Dict[str, Any], utente: str,
                           fonte: str, motivazione: str) -> None:
    esistente = await db[agenti_proposte.COLL_RIGHE_ACQUISTI].find_one({"id": riga["id"]}, {"_id": 0}) or {}
    adesso = _adesso()
    prima = {"stato": esistente.get("stato"),
             "classificazione_confermata": esistente.get("classificazione_confermata")}
    record = {
        "id": riga["id"], "fattura_id": riga.get("fattura_id"), "numero_linea": riga.get("numero_linea"),
        "descrizione_chiave": _chiave(riga.get("descrizione_originale")),
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
                  {"$or": [{"supplier_vat": piva}, {"fornitore_partita_iva": piva}, {"cedente_piva": piva}]}]},
        _ESCLUDI,
    ).to_list(None)
    chiave = _chiave(riga.get("descrizione_originale"))
    return [
        r for r in costruisci_righe(invoices)
        if r.get("id") != riga["id"] and r.get("partita_iva") == piva
        and _chiave(r.get("descrizione_originale")) == chiave
    ][:MAX_RIGHE_ESTESE]


async def chiavi_non_cespite(db) -> Dict[str, Set[str]]:
    """Per ogni fattura, le descrizioni (chiave) che il titolare ha escluso dai cespiti."""
    righe = await db[agenti_proposte.COLL_RIGHE_ACQUISTI].find(
        {"classificazione_confermata.non_cespite": True},
        {"_id": 0, "fattura_id": 1, "descrizione_chiave": 1},
    ).to_list(None)
    esito: Dict[str, Set[str]] = {}
    for r in righe:
        if r.get("fattura_id") and r.get("descrizione_chiave"):
            esito.setdefault(str(r["fattura_id"]), set()).add(r["descrizione_chiave"])
    return esito


def esclusa_dai_cespiti(esclusi: Dict[str, Set[str]], fattura_id: Any, descrizione: Any) -> bool:
    return _chiave(descrizione) in esclusi.get(str(fattura_id), set())


async def assegna_prodotto(
    db, db_lotti, riga_id: str, nome_canc: str, categoria: str, utente: str, *, alimentare: bool = True,
    natura: Optional[str] = None, conto: Optional[str] = None, centro_costo: Optional[str] = None,
    destinazione_operativa: Optional[str] = None, non_cespite: bool = False,
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
    natura = str(natura or "").strip().lower() or None
    if natura and natura not in agenti_proposte.NATURE_RIGA:
        raise SceltaNonValida("natura non ammessa")
    if non_cespite and natura == "cespite":
        raise SceltaNonValida("una riga «non cespite» non può avere natura cespite")
    conto = str(conto or "").strip() or None
    centro_costo = str(centro_costo or "").strip() or None
    await _controlla_conto_e_centro(db, conto, centro_costo)
    riga = await _riga_corrente(db, riga_id)
    if not riga.get("descrizione_originale"):
        raise SceltaNonValida("riga senza descrizione")

    esito = await conferma_articolo(db_lotti, riga["descrizione_originale"], nome, alimentare=alimentare)
    if not esito.get("chiave"):
        raise SceltaNonValida("descrizione o articolo mancanti")
    regola = next((r for r in await elenco_regole(db) if r["categoria"] == categoria), {})
    classificazione = _classificazione(nome, categoria, alimentare, regola, {
        "natura": natura, "conto": conto, "centro_costo": centro_costo,
        "destinazione_operativa": destinazione_operativa, "non_cespite": non_cespite,
    })

    await _scrivi_conferma(db, riga, classificazione, utente, FONTE_TITOLARE,
                           f"Articolo di Lotti: {nome}")
    toccate = [riga]
    for altra in await _righe_stessa_descrizione(db, riga):
        salvata = await db[agenti_proposte.COLL_RIGHE_ACQUISTI].find_one({"id": altra["id"]}, {"_id": 0, "stato": 1})
        if (salvata or {}).get("stato") == agenti_proposte.STATO_CONFERMATA:
            continue  # una decisione umana già presa non si tocca
        await _scrivi_conferma(db, altra, classificazione, utente, FONTE_STESSA_DESCRIZIONE,
                               f"Stessa descrizione e fornitore: articolo di Lotti {nome}")
        toccate.append(altra)
    cespiti_gia_creati = 0
    if non_cespite:
        cespiti_gia_creati = await _cespiti_gia_creati(db, toccate)
    try:
        from app.services.audit_logger import log_evento
        await log_evento(
            modulo="righe_acquisti", azione="assegna_prodotto_lotti", entita_id=riga_id,
            entita_collection=agenti_proposte.COLL_RIGHE_ACQUISTI, db=db,
            nuovo_stato={"nome_canc": nome, "categoria": categoria, "righe_estese": len(toccate) - 1,
                         "non_cespite": non_cespite},
            fonte="decisione_umana", utente=utente, dettaglio=f"Articolo di Lotti: {nome}",
        )
    except Exception as exc:  # noqa: BLE001 - il record conserva già l'audit della decisione
        logger.error("[RIGHE-LOTTI] audit esterno non scritto per %s: %s: %s", riga_id, type(exc).__name__, exc)
    return {"classificazione": {**classificazione, "stato": "CONFERMATA"}, "nome_canc": nome,
            "categoria": categoria, "righe_estese": len(toccate) - 1,
            "lotti_aggiornati": esito.get("lotti_aggiornati", 0),
            "cespiti_gia_creati": cespiti_gia_creati}


async def _cespiti_gia_creati(db, righe: List[Dict[str, Any]]) -> int:
    """Cespiti già nati da queste righe: si contano, non si toccano (niente si cancella)."""
    ids = {str(r.get("fattura_id")) for r in righe if r.get("fattura_id")}
    chiavi = {(str(r.get("fattura_id")), _chiave(r.get("descrizione_originale"))) for r in righe}
    if not ids:
        return 0
    varianti = [v for i in ids for v in varianti_id(i)]
    cespiti = await db["cespiti"].find(
        {"fattura_id": {"$in": varianti}}, {"_id": 0, "fattura_id": 1, "descrizione": 1},
    ).to_list(None)
    return sum(1 for c in cespiti if (str(c.get("fattura_id")), _chiave(c.get("descrizione"))) in chiavi)
