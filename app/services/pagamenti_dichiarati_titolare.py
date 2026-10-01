"""Pagamenti dichiarati dal titolare nel report «Fatture ricevute».

Il report del portale fiscale (``fatture_report_ae``) arriva dal titolare con
tre colonne sue: il metodo con cui ha davvero pagato ogni fattura (cassa,
banca, assegno, PayPal, SumUp), la spunta «carta di credito» e il numero
dell'assegno. Sono i dati veri del pagamento: qui diventano Prima Nota
passando **solo dai motori che esistono gia'**, nessuna scrittura diretta.

- Cassa → ``conferma_fattura_provvisoria`` con l'approvazione esplicita del
  metodo: la dichiarazione del titolare e' quella conferma.
- Assegno → l'addebito sull'estratto conto con lo stesso numero (le cifre
  finali che il titolare scrive) e l'importo al centesimo della somma delle
  fatture pagate con quell'assegno, univoco; poi
  ``collega_assegno_riconciliato_a_fatture``.
- Banca, carta, PayPal, assegno non ancora trovato → la fattura entra subito
  in Prima Nota Banca con una riga **dichiarata** (``dichiarato_titolare``) ed
  e' pagata; resta ``in_attesa_riscontro_banca`` finche' un motore bancario
  (bonifico, carta Nexi, PayPal, assegno) non trova il movimento: la sua riga
  con la prova sostituisce quella dichiarata (``assorbi_righe_dichiarate``),
  mai due uscite per lo stesso pagamento.
- SumUp → nessun motore sa registrare un fornitore pagato con la carta SumUp:
  resta aperta con il metodo dichiarato scritto, e decide il titolare.
- Non pagata → non si tocca.

La cassa scritta d'ufficio quando il fornitore non aveva un metodo
(``metodo_fornitore_assente_provvisorio``) diventa la riga vera se il titolare
dice cassa, e si **storna** (soft delete, per id) se dice altro.

Il metodo del fornitore si ricava dalle stesse righe: uno solo → quello
(assegno, carta e PayPal sono banca), piu' d'uno → ``misto``, cioe' le fatture
future vanno in Provvisoria e sceglie il titolare.

Idempotente: una fattura gia' pagata si salta, quindi il secondo giro da'
``registrate=0``.
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.services.fatture_report_ae import COLLECTION_REPORT, collega_righe_a_fatture
from app.services.payment_allocation_validator import is_credit_note, to_cents
from app.services.prima_nota_integrity import (
    SOURCES_NON_PAGAMENTO,
    fatture_senza_pagamento_contabile_confermato,
)
from app.utils.id_fattura import filtro_id, filtro_id_in

logger = logging.getLogger(__name__)

ATTORE = "report_pagamenti_titolare"
CHIAVE_JOB = "pagamenti_dichiarati_titolare"

# Esiti dopo i quali il giro automatico non ripassa la riga: o e' fatta, o
# niente puo' cambiarla senza una decisione del titolare.
ESITI_DEFINITIVI = {"registrata", "gia_pagata", "non_pagata", "da_decidere"}

_PROIEZIONE = {"_id": 0, "xml_raw": 0, "xml_content": 0, "linee": 0}


def normalizza_metodo_titolare(metodo: Any, carta: Any = None) -> str:
    """Le parole del titolare nei valori che il gestionale conosce."""
    testo = str(metodo or "").strip().lower()
    if "carta" in str(carta or "").lower():
        return "carta"
    if not testo:
        return ""
    if testo in {"cassa", "contanti", "contante"}:
        return "cassa"
    if "assegn" in testo:
        return "assegno"
    if "paypal" in testo:
        return "paypal"
    if "sumup" in testo:
        return "sumup"
    if "carta" in testo:
        return "carta"
    if testo in {"banca", "bonifico", "rid", "sdd"}:
        return "banca"
    return ""


# Metodi dichiarati che non passano dal conto BPM: la carta SumUp ha il suo
# conto (19.01.05), PayPal e la carta Nexi non hanno un conto di tesoreria
# nel piano. Una riga dichiarata con questi metodi non e' mai BPM.
METODI_DICHIARATI_FUORI_BPM = ("carta", "paypal", "sumup")


def conto_metodo_dichiarato(metodo: Any, testo: Any = "") -> Optional[str]:
    """Il conto di tesoreria del metodo dichiarato dal titolare.

    Banca e assegno escono da BPM (19.01.01), la carta SumUp dalla
    Mastercard (19.01.05). PayPal e la carta Nexi restano senza conto
    (``None``): meglio un conto vuoto che un BPM inventato.
    """
    from app.services import conti_pos

    metodo = str(metodo or "").strip().lower()
    if metodo == "sumup" or (metodo == "carta" and "sumup" in str(testo or "").lower()):
        return conti_pos.CONTO_SUMUP_MASTERCARD
    if metodo in {"banca", "assegno"}:
        return conti_pos.CONTO_BPM
    if metodo == "paypal":
        return conti_pos.conto_accredito(conti_pos.PAYPAL) or None
    return None


def metodo_fornitore(metodi: set) -> str:
    gruppi = {"cassa" if m == "cassa" else "banca" for m in metodi if m}
    if not gruppi:
        return ""
    return gruppi.pop() if len(gruppi) == 1 else "misto"


_EPOCA_EXCEL = datetime(1899, 12, 30)
_DATA_EXCEL = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T]00:00:00)?$")


def numero_da_data_excel(valore: Any) -> str:
    """Excel scambia un numero d'assegno scritto a mano per una data: «860»
    diventa il 09/05/1902 (860 giorni dal 30/12/1899). Una data prima del 1990
    in quella colonna e' sempre un numero, e si riporta al numero."""
    if isinstance(valore, datetime):
        data = valore
    else:
        trovato = _DATA_EXCEL.match(str(valore or "").strip())
        if not trovato:
            return ""
        try:
            data = datetime(*(int(x) for x in trovato.groups()))
        except ValueError:
            return ""
    if data.year >= 1990:
        return ""
    return str((data.replace(tzinfo=None) - _EPOCA_EXCEL).days)


def cifre_assegno(numero: Any) -> str:
    """«334-07» → «334»: il titolare scrive le cifre finali del numero."""
    testo = str(numero or "").strip()
    if isinstance(numero, float) and numero.is_integer():
        testo = str(int(numero))
    testo = numero_da_data_excel(numero) or testo
    parte = re.split(r"[-/\s]", testo)[0]
    cifre = re.sub(r"\D", "", parte)
    return cifre if len(cifre) >= 3 else ""


def _segno(fattura: Dict[str, Any]) -> int:
    return -1 if is_credit_note(fattura) else 1


def _oggi() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _salva_esito(db, riga: Dict[str, Any], stato: str, **dettagli) -> None:
    await db[COLLECTION_REPORT].update_one(
        {"report_key": riga["report_key"]},
        {"$set": {"pagamento_applicato": {"stato": stato, "at": _oggi(), **dettagli}}},
    )


async def _aggiorna_fornitori(db, righe: List[Dict[str, Any]], *, dry_run: bool) -> Dict[str, Any]:
    from app.services import metodi_pagamento_fornitori as metodi

    per_fornitore: Dict[str, Dict[str, Any]] = {}
    for riga in righe:
        metodo = riga.get("metodo_pagamento_titolare")
        piva = riga.get("supplier_vat") or ""
        chiave = piva or metodi.normalizza_nome(riga.get("supplier_name"))
        if not metodo or not chiave:
            continue
        voce = per_fornitore.setdefault(chiave, {
            "nome": riga.get("supplier_name") or "",
            "partita_iva": piva,
            "codice_fiscale": riga.get("supplier_cf") or "",
            "metodi": set(),
        })
        voce["metodi"].add(metodo)

    # Il metodo impostato dal titolare in Fornitori vince sul file: il file
    # dice come sono state pagate le SUE fatture, il metodo del fornitore
    # vale per quelle dopo la data limite (regola del 26/09/2026). Si
    # riempie solo un fornitore che il metodo non ce l'ha ancora.
    from app.constants.metodi_pagamento import metodo_non_configurato
    from app.routers.prima_nota_module.sync import mappa_fornitori_per_piva

    metodi_attuali, _esclusi = await mappa_fornitori_per_piva(db)
    gia_configurati = {
        chiave for chiave, v in per_fornitore.items()
        if v["partita_iva"] and not metodo_non_configurato(metodi_attuali.get(v["partita_iva"], ""))
    }
    per_fornitore = {k: v for k, v in per_fornitore.items() if k not in gia_configurati}
    dati = [
        {"nome": v["nome"], "partita_iva": v["partita_iva"],
         "metodo_pagamento": metodo_fornitore(v["metodi"])}
        for v in per_fornitore.values()
    ]
    esito = await metodi.importa(db, {"fornitori": dati}, dry_run=dry_run, attore=ATTORE)
    # In anagrafica alcuni fornitori sono registrati col codice fiscale
    # (P.IVA diversa dal CF, es. gruppi): secondo tentativo solo per loro.
    non_trovati = set(esito.get("fornitori_non_trovati") or [])
    if non_trovati:
        secondo = [
            {"nome": v["nome"], "codice_fiscale": v["codice_fiscale"],
             "metodo_pagamento": metodo_fornitore(v["metodi"])}
            for v in per_fornitore.values()
            if v["nome"] in non_trovati and v["codice_fiscale"]
        ]
        if secondo:
            esito_cf = await metodi.importa(
                db, {"fornitori": secondo}, dry_run=dry_run, attore=ATTORE,
            )
            esito["applicati"] += esito_cf.get("applicati", 0)
            esito["dettaglio"] = (esito.get("dettaglio") or []) + (esito_cf.get("dettaglio") or [])
            esito["fornitori_non_trovati"] = esito_cf.get("fornitori_non_trovati") or []
    esito["metodi_gia_impostati_non_toccati"] = len(gia_configurati)
    esito["metodi_ricavati"] = {
        m: sum(1 for d in dati if d["metodo_pagamento"] == m)
        for m in ("cassa", "banca", "misto")
    }
    return esito


async def _storna_cassa_provvisoria(db, fattura: Dict[str, Any], metodo: str) -> int:
    """La cassa d'ufficio e' sbagliata se il titolare ha pagato altrimenti."""
    righe = await db["prima_nota_cassa"].find(
        {"fattura_id": fattura["id"],
         "source": {"$in": list(SOURCES_NON_PAGAMENTO)},
         "status": {"$nin": ["deleted", "archived"]}},
        {"_id": 0, "id": 1},
    ).to_list(20)
    for riga in righe:
        await db["prima_nota_cassa"].update_one(
            {"id": riga["id"]},
            {"$set": {"status": "deleted",
                      "deleted_reason": f"{ATTORE}:pagata_con_{metodo}",
                      "deleted_at": _oggi()}},
        )
    if righe:
        ids = {r["id"] for r in righe}
        scollega = {c: "" for c in ("prima_nota_id", "prima_nota_cassa_id")
                    if fattura.get(c) in ids}
        if scollega:
            await db["invoices"].update_one(
                filtro_id(fattura["id"]),
                {"$unset": {**scollega, "prima_nota_tipo": ""}},
            )
    return len(righe)


async def _conferma_cassa(fattura: Dict[str, Any], riga: Dict[str, Any]) -> Dict[str, Any]:
    from app.routers.prima_nota_module.sync import conferma_fattura_provvisoria

    return await conferma_fattura_provvisoria({
        "fattura_id": fattura["id"],
        "metodo": "cassa",
        "approva_metodo_fattura": True,
        "data_pagamento": riga.get("data_pagamento_report")
        or str(fattura.get("invoice_date") or "")[:10],
        "performed_by": ATTORE,
    })


async def dichiara_pagamento_banca(
    db, fattura: Dict[str, Any], *,
    metodo: str, data: Any = None, assegno_numero: Any = None,
    metodo_testo: Any = None, source: str = ATTORE,
) -> tuple:
    """Il titolare dice «pagata in banca»: la fattura va in Prima Nota Banca.

    Un solo motore per ogni canale che fa questa dichiarazione: il report
    «Fatture ricevute» e la compilazione di un assegno (`assegni.py`,
    quando la quota copre l'intera fattura) chiamano qui, mai una scrittura
    propria.

    La riga nasce dal writer unico (``registra_pagamento_fattura``, ramo
    banca senza movimento) e porta ``dichiarato_titolare``: per l'utente la
    fattura e' pagata, ma finche' non arriva il movimento dell'estratto conto
    (bonifico, carta Nexi, PayPal, assegno) resta ``in_attesa_riscontro_banca``
    e i motori bancari la cercano ancora. Quando lo trovano, la loro riga con
    la prova sostituisce questa (``assorbi_righe_dichiarate``): mai due uscite.
    """
    from app.routers.prima_nota_module.sync import registra_pagamento_fattura
    from app.services.prima_nota_integrity import CAMPO_RIGA_DICHIARATA

    data = data or str(fattura.get("invoice_date") or "")[:10]
    esito = await registra_pagamento_fattura(
        fattura, "banca", source=source, allow_provisional_bank=True,
    )
    pn_id = esito.get("banca")
    if not pn_id:
        raise HTTPException(status_code=409, detail="Riga di Prima Nota Banca non scritta")
    if esito.get("gia_provata"):
        # Il pagamento e' gia' in banca con il movimento dell'estratto conto:
        # la dichiarazione e' confermata, la riga provata non si tocca.
        await db["invoices"].update_one(filtro_id(fattura["id"]), {"$set": {
            "metodo_pagamento_dichiarato": metodo,
            "pagamento_dichiarato_titolare": True,
            "in_attesa_riscontro_banca": False,
            "stato_finanziario": "riconciliato",
            "prima_nota_banca_id": pn_id,
            "updated_at": _oggi(),
        }})
        return pn_id, True
    campi_conto: Dict[str, Any] = {}
    if not esito.get("duplicato"):
        # Riga nuova: il conto di tesoreria lo dice il metodo dichiarato, non
        # il registro. Il writer unico la scrive su BPM; carta SumUp, PayPal
        # e carta Nexi non sono BPM.
        from app.services.piano_conti_ufficiale import CONTI_UFFICIALI

        conto = conto_metodo_dichiarato(metodo, metodo_testo)
        campi_conto = {"conto_contabile": conto,
                       "conto_nome": CONTI_UFFICIALI.get(conto) if conto else None}
    await db["prima_nota_banca"].update_one({"id": pn_id}, {"$set": {
        **campi_conto,
        CAMPO_RIGA_DICHIARATA: True,
        "data": data,
        "metodo_pagamento_dichiarato": metodo,
        "assegno_numero_dichiarato": assegno_numero or None,
        "motivo_provvisorio": "dichiarata_dal_titolare_in_attesa_estratto_conto",
        "updated_at": _oggi(),
    }})
    await db["invoices"].update_one(filtro_id(fattura["id"]), {"$set": {
        "pagato": True,
        "paid": True,
        "stato_pagamento": "pagata",
        "payment_status": "paid",
        "stato_finanziario": "pagata_dichiarata_in_attesa_banca",
        "pagamento_dichiarato_titolare": True,
        "in_attesa_riscontro_banca": True,
        "metodo_pagamento": "banca",
        "metodo_pagamento_dichiarato": metodo,
        "assegno_numero_dichiarato": assegno_numero or None,
        "metodo_pagamento_override_source": source,
        "prima_nota_id": pn_id,
        "prima_nota_banca_id": pn_id,
        "prima_nota_tipo": "banca",
        "data_pagamento": data,
        "updated_at": _oggi(),
    }})
    return pn_id, False


async def _scrivi_banca_dichiarata(
    db, fattura: Dict[str, Any], riga: Dict[str, Any],
) -> tuple:
    return await dichiara_pagamento_banca(
        db, fattura,
        metodo=riga.get("metodo_pagamento_titolare"),
        data=riga.get("data_pagamento_report") or str(fattura.get("invoice_date") or "")[:10],
        assegno_numero=riga.get("assegno_numero_titolare"),
        metodo_testo=riga.get("metodo_pagamento_titolare_testo"),
    )


async def ritira_dichiarazione_banca(db, fattura_id: str, *, motivo: str) -> bool:
    """Ritira una dichiarazione non ancora provata dalla banca: la fattura riapre.

    Chiamata quando l'assegno che l'aveva dichiarata pagata viene annullato o
    stornato prima dell'addebito. Una dichiarazione gia' sostituita dalla riga
    con la prova bancaria (``in_attesa_riscontro_banca`` falso) non si tocca:
    quel pagamento e' reale, indipendente dall'assegno.
    """
    from app.services.prima_nota_integrity import CAMPO_RIGA_DICHIARATA

    fattura = await db["invoices"].find_one(filtro_id(fattura_id), {"_id": 0})
    if not fattura or not fattura.get("pagamento_dichiarato_titolare"):
        return False
    if not fattura.get("in_attesa_riscontro_banca"):
        # Provata dalla banca (o gia' non piu' in attesa): non e' questa
        # dichiarazione a riaprire il conto.
        return False
    now = _oggi()
    pn_id = fattura.get("prima_nota_banca_id")
    if pn_id:
        riga_pn = await db["prima_nota_banca"].find_one({"id": pn_id}, {"_id": 0})
        if riga_pn and riga_pn.get(CAMPO_RIGA_DICHIARATA):
            await db["prima_nota_banca"].update_one({"id": pn_id}, {"$set": {
                "status": "deleted", "motivo_eliminazione": motivo,
                "eliminato_da": ATTORE, "eliminato_il": now, "updated_at": now,
            }})
    await db["invoices"].update_one(filtro_id(fattura_id), {"$set": {
        "pagato": False, "paid": False,
        "stato_pagamento": "non_pagata", "payment_status": "unpaid",
        "stato_finanziario": None,
        "pagamento_dichiarato_titolare": False,
        "in_attesa_riscontro_banca": False,
        "metodo_pagamento": "sospesa",  # vocabolario unico, metodi_pagamento.py
        "metodo_pagamento_dichiarato": None,
        "assegno_numero_dichiarato": None,
        "prima_nota_id": None, "prima_nota_banca_id": None, "prima_nota_tipo": None,
        "data_pagamento": None,
        "dichiarazione_ritirata_motivo": motivo,
        "updated_at": now,
    }})
    return True


async def ripara_righe_dichiarate(db) -> Dict[str, int]:
    """Riporta in ordine le righe di Prima Nota Banca legate al report.

    - una riga **con** la prova dell'estratto conto non e' una dichiarazione:
      se il report l'aveva declassata a provvisoria, torna confermata con la
      data della banca;
    - una riga dichiarata non supera il netto dovuto al fornitore: su una
      parcella la ritenuta va in F24, non esce col bonifico.
    """
    from app.services.prima_nota_integrity import (
        CAMPO_RIGA_DICHIARATA, _ha_evidenza_banca, totale_pagabile_al_fornitore,
        varianti_id,
    )

    righe = await db["prima_nota_banca"].find(
        {CAMPO_RIGA_DICHIARATA: True, "status": {"$nin": ["deleted", "archived"]}},
        {"_id": 0},
    ).to_list(5000)
    esito = {"provate_ripristinate": 0, "importi_al_netto": 0}
    for riga in righe:
        fattura_id = str(riga.get("fattura_id") or "")
        if _ha_evidenza_banca(riga):
            data_banca = (riga.get("data_riconciliazione") or riga.get("date")
                          or riga.get("data"))
            await db["prima_nota_banca"].update_one({"id": riga["id"]}, {
                "$set": {"riconciliato": True, "data": data_banca, "updated_at": _oggi()},
                "$unset": {CAMPO_RIGA_DICHIARATA: "", "provvisorio": "", "canonico": "",
                           "stato": "", "in_attesa_estratto_ufficiale": "",
                           "motivo_provvisorio": "", "metodo_pagamento_dichiarato": "",
                           "assegno_numero_dichiarato": ""},
            })
            if fattura_id:
                await db["invoices"].update_one({"id": {"$in": varianti_id(fattura_id)}}, {"$set": {
                    "in_attesa_riscontro_banca": False,
                    "stato_finanziario": "riconciliato",
                    "updated_at": _oggi(),
                }})
            esito["provate_ripristinate"] += 1
            continue
        if not fattura_id:
            continue
        fattura = await db["invoices"].find_one(
            {"id": {"$in": varianti_id(fattura_id)}}, {"_id": 0},
        ) or {}
        pagabile = totale_pagabile_al_fornitore(fattura)
        importo = abs(float(riga.get("importo") or 0))
        if pagabile and importo - pagabile > 0.01:
            segno = -1 if float(riga.get("importo") or 0) < 0 else 1
            await db["prima_nota_banca"].update_one({"id": riga["id"]}, {"$set": {
                "importo": segno * pagabile,
                "amount": segno * pagabile,
                "importo_lordo_fattura": importo,
                "updated_at": _oggi(),
            }})
            esito["importi_al_netto"] += 1
    return esito


def _numero_assegno_movimento(movimento: Dict[str, Any]) -> str:
    from app.services.assegni_estratto_conto import estrai_numero_assegno

    for campo in ("assegno_numero", "causale", "descrizione", "descrizione_originale"):
        valore = movimento.get(campo)
        if not valore:
            continue
        numero = (
            re.sub(r"\D", "", str(valore)) if campo == "assegno_numero"
            else estrai_numero_assegno(str(valore))
        )
        if numero:
            return numero
    return ""


async def _addebiti_assegno(db) -> List[Dict[str, Any]]:
    movimenti = await db["estratto_conto_movimenti"].find(
        {"$or": [
            {"causale": {"$regex": "ASSEGNO", "$options": "i"}},
            {"descrizione": {"$regex": "ASSEGNO", "$options": "i"}},
        ]},
        {"_id": 0},
    ).to_list(20000)
    uscite = []
    for m in movimenti:
        if to_cents(m.get("importo")) >= 0 and str(m.get("tipo") or "").lower() != "uscita":
            continue
        numero = _numero_assegno_movimento(m)
        if numero:
            uscite.append({**m, "_numero": numero, "_cents": abs(to_cents(m.get("importo")))})
    return uscite


async def _assegno_del_movimento(db, movimento: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    filtro = {"$or": [
        {"movimento_estratto_conto_id": movimento["id"]},
        {"movimento_id": movimento["id"]},
    ]}
    assegno = await db["assegni"].find_one(filtro, {"_id": 0})
    if assegno:
        return assegno
    from app.services.assegni_estratto_conto import sincronizza_assegni_da_estratto_conto

    await sincronizza_assegni_da_estratto_conto(db, movimento_ids=[movimento["id"]])
    return await db["assegni"].find_one(filtro, {"_id": 0})


async def _paga_con_assegni(
    db, gruppi: Dict[Tuple[str, str], List[Tuple[Dict[str, Any], Dict[str, Any]]]],
    *, dry_run: bool,
) -> Dict[str, str]:
    """Ogni gruppo = fatture dello stesso fornitore pagate con lo stesso
    assegno. Ritorna l'esito per fattura: ``registrata`` o il motivo."""
    esiti: Dict[str, str] = {}
    if not gruppi:
        return esiti
    addebiti = await _addebiti_assegno(db)
    for (_, numero), membri in gruppi.items():
        cifre = cifre_assegno(numero)
        totale = sum(_segno(f) * to_cents(f["_importo_residuo"]) for f, _ in membri)
        candidati = [
            m for m in addebiti
            if cifre and m["_numero"].endswith(cifre) and m["_cents"] == totale
        ]
        motivo = None
        if not cifre:
            motivo = "numero_assegno_illeggibile"
        elif len(candidati) != 1:
            motivo = ("assegno_non_in_estratto_conto" if not candidati
                      else "assegno_ambiguo")
        if motivo:
            for f, _ in membri:
                esiti[f["id"]] = motivo
            continue
        movimento = candidati[0]
        if dry_run:
            for f, _ in membri:
                esiti[f["id"]] = "registrata"
            continue
        try:
            assegno = await _assegno_del_movimento(db, movimento)
            if not assegno:
                raise ValueError("assegno non registrato dall'estratto conto")
            ids = {f["id"] for f, _ in membri}
            gia = {
                str(link.get("fattura_id")) for link in assegno.get("fatture_collegate") or []
                if isinstance(link, dict) and link.get("fattura_id")
            }
            if gia - ids:
                raise ValueError("assegno gia' collegato ad altre fatture")
            for f, riga in membri:
                await _storna_cassa_provvisoria(db, f, "assegno")
            completi = [
                await db["invoices"].find_one(filtro_id(f["id"]), _PROIEZIONE) for f, _ in membri
            ]
            from app.services.assegni_estratto_conto import collega_assegno_riconciliato_a_fatture

            await collega_assegno_riconciliato_a_fatture(
                db, assegno,
                [{"fattura": c, "quota": _segno(c) * float(f["_importo_residuo"])}
                 for c, (f, _) in zip(completi, membri)],
                match_livello="DICHIARAZIONE_TITOLARE",
            )
            for f, _ in membri:
                esiti[f["id"]] = "registrata"
        except (ValueError, HTTPException) as exc:
            dettaglio = getattr(exc, "detail", None) or str(exc) or type(exc).__name__
            logger.warning("Assegno %s non collegato (%s): %s",
                           numero, type(exc).__name__, dettaglio)
            for f, _ in membri:
                esiti[f["id"]] = f"assegno_non_collegato: {dettaglio}"
    return esiti


async def _registra_banca_dichiarata(
    db, fattura, riga, metodo, annota, *, dry_run: bool, motivo: Optional[str] = None,
) -> None:
    """Scrive la riga dichiarata una volta sola: il giro dei 30 minuti ripassa
    queste righe per cercare l'assegno o il bonifico, non per riscriverle."""
    gia_scritta = bool(
        fattura.get("in_attesa_riscontro_banca") and fattura.get("prima_nota_banca_id")
    )
    if dry_run or gia_scritta:
        annota(riga, "in_attesa_banca", fattura, motivo=motivo)
        return
    await _storna_cassa_provvisoria(db, fattura, metodo)
    try:
        pn_id, gia_provata = await _scrivi_banca_dichiarata(db, fattura, riga)
    except HTTPException as exc:
        annota(riga, "errore", fattura, motivo=str(exc.detail))
        await _salva_esito(db, riga, "errore", metodo=metodo, motivo=str(exc.detail))
        return
    if gia_provata:
        annota(riga, "registrata", fattura, motivo="gia_in_banca_con_estratto_conto")
        await _salva_esito(db, riga, "registrata", metodo=metodo,
                           motivo="gia_in_banca_con_estratto_conto",
                           prima_nota_banca_id=pn_id)
        return
    annota(riga, "in_attesa_banca", fattura, motivo=motivo)
    await _salva_esito(db, riga, "in_attesa_banca", metodo=metodo, motivo=motivo,
                       prima_nota_banca_dichiarata_id=pn_id)


async def applica_pagamenti_dichiarati(
    db, *, dry_run: bool = False, solo_pendenti: bool = False,
    aggiorna_fornitori: bool = True, report_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Porta in Prima Nota i pagamenti del report del titolare.

    ``solo_pendenti`` e' il giro automatico (riconciliazione ogni 30 minuti):
    ripassa le righe ancora in attesa, per esempio la fattura arrivata dopo il
    report o l'assegno comparso nel nuovo estratto conto, e non tocca
    l'anagrafica fornitori (un metodo cambiato a mano non si riscrive).
    """
    if solo_pendenti and _job_lock.locked():
        # Il giro lanciato dal caricamento del report e' in corso: due giri
        # insieme si contenderebbero le stesse fatture.
        return {"saltato": "giro_completo_in_corso"}
    filtro: Dict[str, Any] = {"metodo_pagamento_titolare": {"$nin": [None, ""]}}
    if solo_pendenti:
        filtro["pagamento_applicato.stato"] = {"$nin": sorted(ESITI_DEFINITIVI)}
    if report_keys is not None:
        filtro["report_key"] = {"$in": list(report_keys)}
    righe = await db[COLLECTION_REPORT].find(filtro, {"_id": 0}).to_list(20000)
    risultato: Dict[str, Any] = {"dry_run": dry_run, "righe": len(righe)}
    if not righe:
        return risultato

    await collega_righe_a_fatture(db, righe, salva=not dry_run)

    if aggiorna_fornitori and not solo_pendenti:
        risultato["fornitori"] = await _aggiorna_fornitori(db, righe, dry_run=dry_run)

    ids = [r["invoice_id"] for r in righe if r.get("invoice_id")]
    fatture = await db["invoices"].find(filtro_id_in(ids), _PROIEZIONE).to_list(len(ids) or 1)
    per_id = {str(f["id"]): f for f in fatture}
    aperte = {
        str(f["id"]): f for f in await fatture_senza_pagamento_contabile_confermato(db, fatture)
    }

    conteggi: Dict[str, int] = defaultdict(int)
    importi: Dict[str, int] = defaultdict(int)
    problemi: List[Dict[str, Any]] = []
    gruppi_assegno: Dict[Tuple[str, str], list] = defaultdict(list)
    righe_per_fattura: Dict[str, Dict[str, Any]] = {}

    def annota(riga, stato, fattura=None, motivo=None):
        conteggi[stato] += 1
        if fattura is not None:
            importi[stato] += to_cents(fattura.get("_importo_residuo") or 0)
        if motivo and len(problemi) < 300:
            problemi.append({
                "fornitore": riga.get("supplier_name"),
                "numero": riga.get("numero_fattura"),
                "data": riga.get("data_documento"),
                "totale": riga.get("totale_documento"),
                "metodo": riga.get("metodo_pagamento_titolare"),
                "assegno": riga.get("assegno_numero_titolare") or None,
                "esito": stato,
                "motivo": motivo,
            })

    # Il report dell'Agenzia elenca a volte la stessa fattura due volte (il
    # file .xml e il .xml.p7m): la seconda riga non e' un secondo pagamento.
    fatture_viste: set = set()
    for riga in righe:
        metodo = riga["metodo_pagamento_titolare"]
        if not riga.get("pagata_titolare"):
            annota(riga, "non_pagata")
            if not dry_run:
                await _salva_esito(db, riga, "non_pagata")
            continue
        fattura_id = str(riga.get("invoice_id") or "")
        if not fattura_id or fattura_id not in per_id:
            annota(riga, "fattura_non_ancora_arrivata", motivo="XML non ancora nel gestionale")
            if not dry_run:
                await _salva_esito(db, riga, "fattura_non_ancora_arrivata")
            continue
        fattura = aperte.get(fattura_id)
        doppione = fattura_id in fatture_viste
        fatture_viste.add(fattura_id)
        if fattura is None or doppione:
            annota(riga, "gia_pagata")
            if not dry_run:
                await _salva_esito(db, riga, "gia_pagata")
            continue
        righe_per_fattura[fattura_id] = riga

        if metodo == "cassa":
            if dry_run:
                annota(riga, "registrata", fattura)
                continue
            try:
                esito = await _conferma_cassa(fattura, riga)
                annota(riga, "registrata", fattura)
                await _salva_esito(db, riga, "registrata", metodo="cassa",
                                   prima_nota_id=esito.get("movimento_id"))
            except HTTPException as exc:
                annota(riga, "errore", fattura, motivo=str(exc.detail))
                await _salva_esito(db, riga, "errore", motivo=str(exc.detail))
            continue

        if metodo == "sumup":
            # Carta SumUp: nessun registro la sa ricevere per un fornitore.
            annota(riga, "da_decidere", fattura,
                   motivo="pagata con SumUp: scegli tu Cassa o Banca in Provvisoria")
            if not dry_run:
                await _storna_cassa_provvisoria(db, fattura, "sumup")
                await db["invoices"].update_one(filtro_id(fattura_id), {"$set": {
                    "metodo_pagamento_dichiarato": "sumup",
                    "metodo_pagamento_override_source": ATTORE,
                }})
                await _salva_esito(db, riga, "da_decidere", metodo="sumup")
            continue

        # Il numero d'assegno scritto dal titolare dice come ha pagato anche
        # quando il metodo dice «banca» (l'assegno esce dal conto): senza
        # questo le fatture 1/5716, 1/7786 e FEP 39_26 aspettavano un bonifico
        # che non arrivera' mai.
        if cifre_assegno(riga.get("assegno_numero_titolare")) and metodo in ("assegno", "banca"):
            chiave = (riga.get("supplier_vat") or "", str(riga["assegno_numero_titolare"]))
            gruppi_assegno[chiave].append((fattura, riga))
            continue

        # Banca, carta, PayPal, assegno senza numero: in Prima Nota Banca
        # subito, come dichiarata; la prova la porta l'estratto conto.
        await _registra_banca_dichiarata(db, fattura, riga, metodo, annota, dry_run=dry_run)

    esiti_assegno = await _paga_con_assegni(db, gruppi_assegno, dry_run=dry_run)
    for fattura_id, esito in esiti_assegno.items():
        riga = righe_per_fattura[fattura_id]
        fattura = aperte[fattura_id]
        if esito == "registrata":
            annota(riga, "registrata", fattura)
            if not dry_run:
                await _salva_esito(db, riga, "registrata", metodo="assegno")
            continue
        await _registra_banca_dichiarata(db, fattura, riga, "assegno", annota,
                                         dry_run=dry_run, motivo=esito)

    # Le fatture pagate in banca le chiude l'unico motore bonifico ↔ fattura;
    # il giro dei 30 minuti lo esegue gia' per conto suo.
    if not dry_run and conteggi.get("in_attesa_banca"):
        if not solo_pendenti:
            from app.services.bank_payment_allocations import (
                reconcile_deterministic_invoice_allocations,
            )
            risultato["riconciliazione_banca"] = await reconcile_deterministic_invoice_allocations(db)
        await _ricontrolla_attese(db, righe, risultato)

    risultato.update({
        "conteggi": dict(conteggi),
        "importi": {k: round(v / 100, 2) for k, v in importi.items()},
        "da_vedere": problemi,
    })
    return risultato


async def applica_per_fattura_arrivata(db, fattura: Dict[str, Any]) -> Dict[str, Any]:
    """La fattura e' appena entrata: se il report del titolare la dichiara
    pagata, il pagamento si applica adesso, non al giro dei 30 minuti.

    Guarda solo le righe ancora aperte dello stesso fornitore, le riaggancia
    alle fatture attive e applica quelle che puntano a questa fattura.
    """
    from app.services.fatture_report_ae import _vat

    piva = _vat(fattura.get("supplier_vat") or fattura.get("cedente_piva"))
    fattura_id = fattura.get("id")
    if not piva or not fattura_id:
        return {"applicate": 0, "motivo": "fattura_senza_piva_o_id"}
    righe = [
        r for r in await db[COLLECTION_REPORT].find(
            {"metodo_pagamento_titolare": {"$nin": [None, ""]},
             "pagamento_applicato.stato": {"$nin": sorted(ESITI_DEFINITIVI)}},
            {"_id": 0},
        ).to_list(20000)
        if _vat(r.get("supplier_vat")) == piva
    ]
    if not righe:
        return {"applicate": 0}
    await collega_righe_a_fatture(db, righe, salva=True)
    chiavi = [r["report_key"] for r in righe if r.get("invoice_id") == fattura_id]
    if not chiavi:
        return {"applicate": 0}
    esito = await applica_pagamenti_dichiarati(
        db, solo_pendenti=True, report_keys=chiavi,
    )
    return {"applicate": len(chiavi), "esito": esito}


async def _ricontrolla_attese(db, righe: List[Dict[str, Any]], risultato: Dict[str, Any]) -> None:
    """Dopo il motore bancario: le attese che ha chiuso diventano registrate."""
    in_attesa = [
        r for r in await db[COLLECTION_REPORT].find(
            {"report_key": {"$in": [r["report_key"] for r in righe]},
             "pagamento_applicato.stato": "in_attesa_banca"},
            {"_id": 0},
        ).to_list(20000)
        if r.get("invoice_id")
    ]
    if not in_attesa:
        return
    ids = [r["invoice_id"] for r in in_attesa]
    fatture = await db["invoices"].find(filtro_id_in(ids), _PROIEZIONE).to_list(len(ids))
    ancora_aperte = {str(f["id"]) for f in await fatture_senza_pagamento_contabile_confermato(db, fatture)}
    chiuse = 0
    for riga in in_attesa:
        if str(riga["invoice_id"]) not in ancora_aperte:
            chiuse += 1
            await _salva_esito(db, riga, "registrata",
                               metodo=(riga.get("pagamento_applicato") or {}).get("metodo"),
                               da="riconciliazione_banca")
    risultato["chiuse_dalla_banca"] = chiuse


# ── Esecuzione in background (§4: oltre i 5 minuti il proxy taglia) ─────────

_job_lock = asyncio.Lock()
_job_task: Optional[asyncio.Task] = None


async def _salva_stato(db, **campi) -> None:
    await db["sistema_stato"].update_one(
        {"chiave": CHIAVE_JOB},
        {"$set": {**campi, "updated_at": _oggi()}},
        upsert=True,
    )


async def _esegui(db, dry_run: bool) -> None:
    async with _job_lock:
        iniziato = _oggi()
        await _salva_stato(db, stato="in_corso", dry_run=dry_run, iniziato_at=iniziato,
                           terminato_at=None, risultato=None, errore=None)
        try:
            risultato = await applica_pagamenti_dichiarati(db, dry_run=dry_run)
            await _salva_stato(db, stato="completato", dry_run=dry_run,
                               iniziato_at=iniziato, terminato_at=_oggi(),
                               risultato=risultato, errore=None)
        except Exception as exc:  # noqa: BLE001 - l'esito va salvato comunque
            logger.exception("Pagamenti dichiarati: giro fallito (%s)", type(exc).__name__)
            await _salva_stato(db, stato="errore", dry_run=dry_run,
                               iniziato_at=iniziato, terminato_at=_oggi(),
                               risultato=None, errore=f"{type(exc).__name__}: {exc}")


async def avvia(db, *, dry_run: bool = False) -> Dict[str, Any]:
    global _job_task
    if _job_lock.locked() or (_job_task is not None and not _job_task.done()):
        return {"avviato": False, **await stato(db)}
    _job_task = asyncio.create_task(_esegui(db, dry_run))
    return {"avviato": True, "stato": "avvio", "dry_run": dry_run}


async def stato(db) -> Dict[str, Any]:
    documento = await db["sistema_stato"].find_one({"chiave": CHIAVE_JOB}, {"_id": 0})
    if not documento:
        return {"stato": "mai_avviato"}
    documento.pop("chiave", None)
    in_esecuzione = _job_lock.locked() or (_job_task is not None and not _job_task.done())
    if documento.get("stato") == "in_corso" and not in_esecuzione:
        # Un deploy riavvia il processo e uccide il giro a meta': lo stato
        # salvato resterebbe «in_corso» per sempre. Le righe senza esito le
        # riprende il giro dei 30 minuti (sono idempotenti).
        documento["stato"] = "interrotto"
        documento["nota"] = (
            "Giro interrotto da un riavvio: le righe senza esito le riprende "
            "la riconciliazione automatica, oppure rilancia questo comando."
        )
    return documento
