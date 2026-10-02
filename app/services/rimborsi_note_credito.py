"""Rimborso bancario in entrata <-> nota di credito ricevuta.

Il fornitore che storna una fattura con una nota di credito (TD04/TD08)
restituisce il denaro con un bonifico in entrata ("BONIF. VS. FAVORE -
BON.DA AMAZON BUSINESS EU SARL, IT BRANCH ..."). Fino al 02/10/2026 il
motore bancario, sulle entrate, cercava solo POS e versamenti: il rimborso
restava «Rimborso» senza documento e la nota di credito restava aperta (o
in Cassa provvisoria, per un fornitore che paga in banca).

Regola, la stessa dei pagamenti: identita' coerente (l'ordinante del
bonifico e' il fornitore della nota, alias e collettori di gruppo compresi:
``identity_matching.soggetto_pagante_coerente``) **e** importo al centesimo,
rimborso da 0 a ``GIORNI_MASSIMI`` giorni dopo la nota. Un solo candidato
si applica; piu' note dello stesso fornitore e dello stesso importo si
chiudono in ordine di data (come gli SDD PayPal); altrimenti niente.

Scrive con i motori che ci sono: ``registra_pagamento_fattura`` (riga Prima
Nota Banca in entrata «Nota credito fornitore» con la prova del movimento),
``assorbi_righe_dichiarate`` (la riga dichiarata dal titolare lascia il
posto), e ritira per id la riga Cassa provvisoria nata dal metodo del
fornitore (soft delete con motivo, mai cancellazione).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from app.constants.tipi_documento import TIPI_NOTA_CREDITO
from app.services.alert_engine import chiudi_alert_movimento_riconciliato
from app.services.identity_matching import alias_fornitore, soggetto_pagante_coerente
from app.services.payment_invoice_matching import amounts_equal_to_cent
from app.services.prima_nota_integrity import (
    CAMPI_EVIDENZA_BANCA,
    assorbi_righe_dichiarate,
)
from app.utils.id_fattura import varianti_id

logger = logging.getLogger(__name__)

SOURCE = "rimborso_nota_credito"
TIPO_RICONCILIAZIONE = "rimborso_nota_credito"
GIORNI_MASSIMI = 62
#: Le righe Cassa che un rimborso in banca puo' ritirare: solo quelle scritte
#: d'ufficio (metodo del fornitore, cassa provvisoria), mai una confermata.
SOURCES_CASSA_PROVVISORIA = (
    "auto_metodo_fornitore", "metodo_fornitore_assente_provvisorio",
    "auto_registrazione_metodo_fornitore", "auto_confirm_provvisoria",
)
_STATI_FUORI = ("deleted", "archived", "archiviata", "sostituito")


def _data(valore: Any) -> Optional[date]:
    testo = str(valore or "")[:10]
    try:
        return date.fromisoformat(testo)
    except ValueError:
        return None


def _nome_fornitore(nota: Dict[str, Any]) -> str:
    return str(
        nota.get("supplier_name") or nota.get("cedente_denominazione")
        or nota.get("fornitore") or ""
    )


def _piva(nota: Dict[str, Any]) -> str:
    return str(nota.get("supplier_vat") or nota.get("cedente_piva") or "").strip()


async def candidati_nota_credito(db, mov: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Note di credito aperte che il rimborso ``mov`` puo' chiudere.

    Ordinate per data e numero. Vuoto se la causale non dichiara
    l'ordinante o se nessuna nota ha fornitore coerente, importo al
    centesimo e data entro la finestra.
    """
    importo = abs(float(mov.get("importo") or 0))
    data_mov = _data(mov.get("data"))
    if importo <= 0 or data_mov is None:
        return []
    descrizione = str(mov.get("descrizione_originale") or mov.get("descrizione") or "")
    if not descrizione.strip():
        return []
    note = await db["invoices"].find({
        "tipo_documento": {"$in": list(TIPI_NOTA_CREDITO)},
        "status": {"$nin": list(_STATI_FUORI)},
        "stato_import": {"$nin": ["collisione_identita_da_verificare", "archivio_storico"]},
        "$or": [
            {"riconciliato_con_ec": {"$exists": False}},
            {"riconciliato_con_ec": None},
            {"riconciliato_con_ec": False},
        ],
    }, {"_id": 0}).to_list(2000)
    trovate = []
    for nota in note:
        totale = abs(float(nota.get("total_amount") or nota.get("importo_totale") or 0))
        if not amounts_equal_to_cent(totale, importo):
            continue
        data_nota = _data(nota.get("invoice_date") or nota.get("data_fattura"))
        if data_nota is None:
            continue
        giorni = (data_mov - data_nota).days
        if giorni < 0 or giorni > GIORNI_MASSIMI:
            continue
        if soggetto_pagante_coerente(
            _nome_fornitore(nota), descrizione, alias=alias_fornitore(nota),
        ) is not True:
            continue
        trovate.append(nota)
    trovate.sort(key=lambda n: (
        str(n.get("invoice_date") or ""), str(n.get("invoice_number") or ""), str(n.get("id")),
    ))
    return trovate


def _scelta(candidati: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not candidati:
        return None
    if len(candidati) == 1:
        return candidati[0]
    # Stesso fornitore, stesso importo: le note sono intercambiabili per la
    # contabilita' e si chiudono in ordine di data (gli SDD PayPal fanno
    # uguale). Fornitori diversi con lo stesso importo: nessuna scelta.
    pive = {_piva(n) for n in candidati}
    if len(pive) == 1 and "" not in pive:
        return candidati[0]
    return None


async def _ritira_cassa_provvisoria(db, nota_id: Any, pn_banca_id: str, mov_id: str, ora: str) -> List[str]:
    righe = await db["prima_nota_cassa"].find(
        {"fattura_id": {"$in": varianti_id(nota_id)},
         "status": {"$nin": list(_STATI_FUORI)}},
        {"_id": 0},
    ).to_list(20)
    ritirate: List[str] = []
    for riga in righe:
        if any(riga.get(c) not in (None, "") for c in CAMPI_EVIDENZA_BANCA):
            continue
        provvisoria = bool(riga.get("provvisorio")) or riga.get("stato") == "DA_VERIFICARE" \
            or riga.get("source") in SOURCES_CASSA_PROVVISORIA
        if not provvisoria:
            continue
        await db["prima_nota_cassa"].update_one({"id": riga["id"]}, {"$set": {
            "status": "deleted",
            "deleted_reason": f"riscontrata_da_estratto_conto:{mov_id}",
            "deleted_at": ora,
            "sostituita_da": pn_banca_id,
            "sostituita_da_collezione": "prima_nota_banca",
        }})
        ritirate.append(str(riga["id"]))
    return ritirate


async def abbina_rimborso_nota_credito(db, mov: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Abbina un movimento in entrata alla sua nota di credito e scrive.

    Ritorna i dettagli dell'abbinamento, oppure ``None`` se il movimento non
    e' un rimborso riconoscibile (nessuna scrittura). Idempotente: un
    movimento gia' riconciliato o una nota gia' chiusa non si toccano.
    """
    if str(mov.get("tipo") or "").lower() not in ("entrata", "accredito", "incasso"):
        return None
    if mov.get("riconciliato") is True:
        return None
    candidati = await candidati_nota_credito(db, mov)
    nota = _scelta(candidati)
    if nota is None:
        if len(candidati) > 1:
            logger.info(
                "[rimborsi_note_credito] movimento %s: %d note candidate di fornitori diversi, nessuna scelta",
                mov.get("id"), len(candidati),
            )
        return None

    from app.routers.prima_nota_module.sync import registra_pagamento_fattura

    mov_id = str(mov.get("id"))
    nota_id = nota.get("id")
    ora = datetime.now(timezone.utc).isoformat()
    importo = abs(float(nota.get("total_amount") or nota.get("importo_totale") or 0))
    esito = await registra_pagamento_fattura(
        nota, "banca", source=SOURCE, movimento_bancario=mov,
    )
    pn_banca_id = esito.get("banca")
    if not pn_banca_id:
        logger.warning(
            "[rimborsi_note_credito] nota %s: nessuna riga Prima Nota Banca scritta (%s)",
            nota_id, esito,
        )
        return None
    await assorbi_righe_dichiarate(
        db, {str(nota_id): importo}, sostituita_da=pn_banca_id, movimento_id=mov_id,
    )
    cassa_ritirate = await _ritira_cassa_provvisoria(db, nota_id, pn_banca_id, mov_id, ora)

    aggiornamento = {
        "pagato": True, "paid": True,
        "stato_pagamento": "pagata", "payment_status": "paid",
        "stato_finanziario": "rimborsata_banca",
        "importo_pagato": importo, "importo_residuo": 0.0,
        "in_banca": True, "provvisorio": False,
        "metodo_pagamento": "bonifico", "metodo_pagamento_effettivo": "banca",
        "data_pagamento": str(mov.get("data") or "")[:10],
        "prima_nota_banca_id": pn_banca_id, "prima_nota_id": pn_banca_id,
        "prima_nota_tipo": "banca",
        "riconciliato": True, "riconciliato_con_ec": mov_id,
        "riconciliato_automaticamente": True,
        "rimborso_movimento_id": mov_id,
        "updated_at": ora,
    }
    if cassa_ritirate:
        aggiornamento["prima_nota_cassa_id"] = None
        aggiornamento["prima_nota_cassa_ritirata"] = cassa_ritirate
    await db["invoices"].update_one({"id": {"$in": varianti_id(nota_id)}}, {"$set": aggiornamento})

    dettagli = {
        "fattura_id": str(nota_id),
        "numero_fattura": nota.get("invoice_number") or nota.get("numero_fattura"),
        "fornitore": _nome_fornitore(nota),
        "tipo_documento": nota.get("tipo_documento"),
        "importo": importo,
        "prima_nota_banca_id": pn_banca_id,
        "prima_nota_cassa_ritirate": cassa_ritirate,
        "candidati": len(candidati),
        "scelta": "unica" if len(candidati) == 1 else "in_ordine_di_data",
    }
    await db["estratto_conto_movimenti"].update_one({"id": mov_id}, {"$set": {
        "riconciliato": True,
        "riconciliato_automaticamente": True,
        "tipo_riconciliazione": TIPO_RICONCILIAZIONE,
        "fattura_id": str(nota_id),
        "dettagli_riconciliazione": dettagli,
        "updated_at": ora,
    }})
    try:
        await chiudi_alert_movimento_riconciliato(db, mov_id)
    except Exception as exc:  # il rimborso e' scritto: l'alert non lo annulla
        logger.warning("[rimborsi_note_credito] chiusura alert %s non riuscita: %s %s",
                       mov_id, type(exc).__name__, exc)
    return dettagli
