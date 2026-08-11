"""
Prima Nota Module - Sincronizzazione e Import.
Sync corrispettivi, fatture, import CSV/batch.
"""
from fastapi import HTTPException, Query, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from itertools import combinations
import logging
import re
import uuid

from app.database import Database, Collections
from app.engines.prima_nota_engine import decide_destinazione_fattura, normalizza_metodo_pagamento
from .common import (
    COLLECTION_PRIMA_NOTA_CASSA, COLLECTION_PRIMA_NOTA_BANCA
)

logger = logging.getLogger(__name__)


# Tipi documento che possono rappresentare fatture attive; la direzione
# effettiva viene confermata confrontando il cedente con l'azienda.
TIPI_FATTURA_ATTIVA = ["TD24", "TD25", "TD26", "TD27"]
from app.constants.tipi_documento import TIPI_NOTA_CREDITO
from app.services.scritture_contabili import scrivi_movimento
from app.services.prima_nota_integrity import (
    CAMPI_EVIDENZA_BANCA,
    CAMPI_ID_PRIMA_NOTA,
    fatture_senza_pagamento_contabile_confermato,
    totale_pagabile_al_fornitore,
)
from app.routers.invoices.invoices_main import _dedupe_invoices

# Metodi fornitore -> destinazione Prima Nota: REGOLA UNICA, delegata al
# motore centralizzato app.engines.prima_nota_engine (prima esistevano liste
# di parole chiave diverse in piu' punti del codice, non sincronizzate tra
# loro: un fornitore con metodo "assegno"/"carta" poteva risultare "Banca"
# in un punto e "sospeso" in un altro — vedi storia di questo file).


def classifica_metodo_fornitore(metodo: str) -> str:
    """Ritorna 'cassa' | 'banca' | 'sospesa' per un metodo pagamento fornitore.

    'sospesa' copre sia il fornitore Misto (Prima Nota Provvisoria, in attesa
    di conferma su come dividere il pagamento) sia il fornitore senza metodo
    definito: in entrambi i casi la fattura resta nei Provvisori.
    """
    canonico = normalizza_metodo_pagamento(metodo)
    if canonico in ("cassa", "banca"):
        return canonico
    return "sospesa"


def _estrai_riferimenti_ddt(fattura: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Restituisce i DDT della fattura, anche per i documenti gia' importati.

    I nuovi import persistono ``dati_ddt``. Per le fatture storiche usiamo
    il relativo body di ``xml_raw`` e leggiamo soltanto NumeroDDT/DataDDT,
    senza interpretare allegati o altri campi del documento.
    """
    dati_salvati = fattura.get("dati_ddt") or []
    if isinstance(dati_salvati, dict):
        dati_salvati = [dati_salvati]
    riferimenti = [
        {
            "numero": str(item.get("numero") or item.get("numero_ddt") or "").strip(),
            "data": str(item.get("data") or item.get("data_ddt") or "").strip(),
            "riferimenti_linea": item.get("riferimenti_linea") or [],
        }
        for item in dati_salvati
        if isinstance(item, dict)
        and (item.get("numero") or item.get("numero_ddt") or item.get("data") or item.get("data_ddt"))
    ]
    if riferimenti:
        return riferimenti

    def riferimenti_da_causali() -> list[Dict[str, Any]]:
        # Alcuni fornitori riportano il DDT nella causale anziche' nel blocco
        # XML DatiDDT. E' comunque una fonte documentale della fattura: la
        # leggiamo senza dedurre nulla da date o importi.
        trovati = []
        causali = fattura.get("causali") or []
        if isinstance(causali, (str, dict)):
            causali = [causali]
        for causale in causali:
            if isinstance(causale, dict):
                testo_causale = " ".join(str(value) for value in causale.values() if value)
            else:
                testo_causale = str(causale or "")
            for match in re.finditer(
                r"\b(?:D\.?D\.?T\.?|DOCUMENTO\s+DI\s+TRASPORTO)"
                r"\s*(?:N(?:UMERO)?\.?\s*)?([A-Z0-9][A-Z0-9./_-]{1,39})"
                r"(?:\s*(?:DEL|DATA)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}))?",
                testo_causale,
                flags=re.IGNORECASE,
            ):
                numero = match.group(1).strip()
                data = (match.group(2) or "").strip()
                if data and ("/" in data or "-" in data) and not re.match(r"^\d{4}-", data):
                    separatore = "/" if "/" in data else "-"
                    formato = (
                        f"%d{separatore}%m{separatore}%Y"
                        if len(data.rsplit(separatore, 1)[-1]) == 4
                        else f"%d{separatore}%m{separatore}%y"
                    )
                    try:
                        data = datetime.strptime(data, formato).strftime("%Y-%m-%d")
                    except ValueError:
                        pass
                trovati.append({
                    "numero": numero,
                    "data": data,
                    "riferimenti_linea": [],
                    "fonte": "causale_fattura",
                })
        return trovati

    xml_raw = fattura.get("xml_raw") or fattura.get("xml_content")
    if not xml_raw:
        return riferimenti_da_causali()
    testo = xml_raw.decode("utf-8", errors="replace") if isinstance(xml_raw, bytes) else str(xml_raw)
    bodies = re.findall(
        r"<(?:\w+:)?FatturaElettronicaBody\b.*?</(?:\w+:)?FatturaElettronicaBody\s*>",
        testo,
        flags=re.IGNORECASE | re.DOTALL,
    )
    indice = int(fattura.get("xml_body_index") or 0)
    corpo = bodies[indice] if bodies and 0 <= indice < len(bodies) else (bodies[0] if bodies else testo)
    blocchi = re.findall(
        r"<(?:\w+:)?DatiDDT\b.*?</(?:\w+:)?DatiDDT\s*>",
        corpo,
        flags=re.IGNORECASE | re.DOTALL,
    )

    def valore_tag(blocco: str, tag: str) -> str:
        match = re.search(
            rf"<(?:\w+:)?{tag}\b[^>]*>\s*(.*?)\s*</(?:\w+:)?{tag}\s*>",
            blocco,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""

    visti = set()
    for blocco in blocchi:
        numero = valore_tag(blocco, "NumeroDDT")
        data = valore_tag(blocco, "DataDDT")
        chiave = (numero.casefold(), data)
        if not numero and not data or chiave in visti:
            continue
        visti.add(chiave)
        riferimenti.append({"numero": numero, "data": data, "riferimenti_linea": []})
    return riferimenti or riferimenti_da_causali()


def _arricchisci_distanza_ddt(
    riferimenti: list[Dict[str, Any]], data_fattura: Any,
) -> list[Dict[str, Any]]:
    data_documento = str(data_fattura or "")[:10]
    try:
        giorno_fattura = datetime.strptime(data_documento, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        giorno_fattura = None
    risultato = []
    for riferimento in riferimenti:
        item = dict(riferimento)
        try:
            giorno_ddt = datetime.strptime(str(item.get("data") or "")[:10], "%Y-%m-%d").date()
            if giorno_fattura:
                item["giorni_prima_fattura"] = (giorno_fattura - giorno_ddt).days
        except (TypeError, ValueError):
            pass
        risultato.append(item)
    return risultato


async def _riepilogo_prima_nota_per_fattura(
    db, fatture: list[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Raccoglie in batch dove e quanto e' stato registrato per fattura.

    La funzione e' di sola lettura. Per Banca considera definitivo soltanto
    un movimento dotato di evidenza finanziaria reale, con la stessa regola
    usata per decidere se una fattura deve rimanere in Provvisoria.
    """
    alias_fattura: Dict[str, str] = {}
    id_prima_nota: Dict[str, str] = {}
    riepilogo: Dict[str, Dict[str, Any]] = {}
    for fattura in fatture:
        fattura_id = str(fattura.get("id") or fattura.get("invoice_key") or "")
        if not fattura_id:
            continue
        riepilogo[fattura_id] = {
            "cassa_importo": 0.0,
            "banca_importo": 0.0,
            "banca_in_attesa_importo": 0.0,
            "cassa_presente": False,
            "banca_presente": False,
            "banca_in_attesa_presente": False,
            "movimenti": [],
        }
        for alias in (fattura.get("id"), fattura.get("invoice_key")):
            if alias not in (None, ""):
                alias_fattura[str(alias)] = fattura_id
        for campo in CAMPI_ID_PRIMA_NOTA:
            if fattura.get(campo) not in (None, ""):
                id_prima_nota[str(fattura[campo])] = fattura_id

    condizioni = []
    if alias_fattura:
        alias = list(alias_fattura)
        condizioni.extend([
            {"fattura_id": {"$in": alias}},
            {"invoice_id": {"$in": alias}},
            {"fattura_ids": {"$in": alias}},
            {"riferimento": {"$in": [f"FATT-{value}" for value in alias]}},
        ])
    if id_prima_nota:
        condizioni.append({"id": {"$in": list(id_prima_nota)}})
    if not condizioni:
        return riepilogo

    projection = {
        "_id": 0, "id": 1, "data": 1, "data_contabile": 1,
        "importo": 1, "fattura_id": 1, "invoice_id": 1,
        "fattura_ids": 1, "riferimento": 1, "status": 1,
        "entity_status": 1,
        **{campo: 1 for campo in CAMPI_EVIDENZA_BANCA},
    }
    for collection in (COLLECTION_PRIMA_NOTA_CASSA, COLLECTION_PRIMA_NOTA_BANCA):
        righe = await db[collection].find({"$or": condizioni}, projection).to_list(10000)
        for riga in righe:
            if riga.get("status") in ("deleted", "archived") or riga.get("entity_status") == "deleted":
                continue
            fatture_collegate = set()
            for campo in ("fattura_id", "invoice_id"):
                if riga.get(campo) not in (None, ""):
                    fatture_collegate.add(str(riga[campo]))
            fatture_collegate.update(
                str(value) for value in (riga.get("fattura_ids") or []) if value
            )
            riferimento = str(riga.get("riferimento") or "")
            if riferimento.startswith("FATT-"):
                fatture_collegate.add(riferimento[5:])

            canoniche = {
                alias_fattura[value]
                for value in fatture_collegate
                if value in alias_fattura
            }
            movimento_id = str(riga.get("id") or "")
            if movimento_id in id_prima_nota:
                canoniche.add(id_prima_nota[movimento_id])
            if not canoniche:
                continue

            valore = riga.get("importo")
            try:
                importo = abs(float(valore)) if valore not in (None, "") else 0.0
            except (TypeError, ValueError):
                importo = 0.0
            evidenza_banca = any(
                riga.get(campo) not in (None, "") for campo in CAMPI_EVIDENZA_BANCA
            )
            for fattura_id in canoniche:
                stato = riepilogo[fattura_id]
                if collection == COLLECTION_PRIMA_NOTA_CASSA:
                    stato["cassa_presente"] = True
                    stato["cassa_importo"] = round(stato["cassa_importo"] + importo, 2)
                    posizione = "cassa"
                    confermato = True
                elif evidenza_banca:
                    stato["banca_presente"] = True
                    stato["banca_importo"] = round(stato["banca_importo"] + importo, 2)
                    posizione = "banca"
                    confermato = True
                else:
                    stato["banca_in_attesa_presente"] = True
                    stato["banca_in_attesa_importo"] = round(
                        stato["banca_in_attesa_importo"] + importo, 2
                    )
                    posizione = "banca_in_attesa"
                    confermato = False
                stato["movimenti"].append({
                    "id": riga.get("id"),
                    "posizione": posizione,
                    "data": riga.get("data") or riga.get("data_contabile"),
                    "importo": importo,
                    "confermato": confermato,
                })
    return riepilogo


# NB: app/config/azienda.py (che avrebbe questa costante centralizzata) è
# irraggiungibile — app/config.py (modulo) oscura app/config/ (package)
# nell'import system, bug preesistente e separato, non toccato qui. Stesso
# valore hardcoded già usato altrove nel codice (accounting/bilancio.py::
# PIVA_AZIENDA).
PIVA_AZIENDA = "04523831214"


def _parti_numero_assegno(valore: Any) -> tuple[str, str]:
    """Separa numero bancario e suffisso preservando gli zeri iniziali."""
    testo = re.sub(r"\s+", "", str(valore or ""))
    match = re.fullmatch(r"(\d+)(?:-(\d+))?", testo)
    if not match:
        return "", ""
    return match.group(1), match.group(2) or ""


def _numero_assegno_corrisponde_frammento(numero: Any, frammento: str) -> bool:
    """Confronta il finale guidato ``123-01`` con il numero completo.

    Le tre cifre prima del trattino identificano la coda del numero bancario;
    le due successive identificano il foglio del carnet. Gli estratti BPM
    riportano pero' soltanto il numero bancario completo (``0208769328``),
    senza il suffisso del foglio: in quel caso il finale ``328-01`` deve
    comunque ritrovare il movimento ufficiale. Non e' un match sul solo
    importo: il candidato resta vincolato al numero estratto dalla causale,
    all'importo esatto e al movimento bancario ufficiale. I vecchi dati con
    suffisso non riempito di zeri (``-1``) restano leggibili.
    """
    base, suffisso = _parti_numero_assegno(numero)
    frag_base, frag_suffisso = _parti_numero_assegno(frammento)
    if (
        not base or len(frag_base) != 3 or len(frag_suffisso) != 2
    ):
        return False
    if not base.endswith(frag_base):
        return False
    # Il PDF/CSV BPM non espone il numero del foglio dopo il trattino. In
    # assenza di tale dato non lo inventiamo: conserviamo il numero ufficiale
    # e lasciamo la scelta esplicita all'utente fra gli eventuali candidati.
    if not suffisso:
        return True
    return suffisso.lstrip("0") == frag_suffisso.lstrip("0")


def _movimento_assegno_ufficiale(movimento: Dict[str, Any]) -> bool:
    livello = str(movimento.get("livello_evidenza") or "").lower()
    if livello and livello != "ufficiale" and not movimento.get("evidenza_bancaria_ufficiale"):
        return False
    descrizione = str(
        movimento.get("descrizione_originale") or movimento.get("descrizione") or ""
    )
    tipo = str(movimento.get("tipo") or movimento.get("type") or "").lower()
    try:
        importo = float(movimento.get("importo") or 0)
    except (TypeError, ValueError):
        importo = 0
    return bool(
        (tipo == "uscita" or importo < 0)
        and re.search(r"(?:PRELIEVO|VOSTRO).*ASSEGNO", descrizione, re.IGNORECASE)
    )


async def _candidati_assegno_per_fattura(
    db, fattura: Dict[str, Any], frammento: str = "",
) -> tuple[list[Dict[str, Any]], float]:
    """Unisce registro assegni ed estratto conto senza creare collegamenti."""
    from app.services.assegni_estratto_conto import estrai_numero_assegno

    aperte = await fatture_senza_pagamento_contabile_confermato(db, [fattura])
    if not aperte:
        raise HTTPException(
            status_code=409,
            detail="La fattura ha gia' un pagamento contabile completo.",
        )
    fattura = aperte[0]
    importo = round(abs(float(
        fattura.get("_importo_residuo")
        if fattura.get("_importo_residuo") is not None
        else fattura.get("total_amount") or fattura.get("importo_totale") or 0
    )), 2)
    data_fattura = str(
        fattura.get("invoice_date") or fattura.get("data_documento")
        or fattura.get("data_fattura") or ""
    )
    anno = data_fattura[:4] if data_fattura[:4].isdigit() else ""

    candidati: list[Dict[str, Any]] = []
    assegni = await db["assegni"].find(
        {"importo": {"$gte": importo - 0.005, "$lte": importo + 0.005}},
        {"_id": 0},
    ).to_list(2000)
    for assegno in assegni:
        if assegno.get("entity_status") == "deleted" or assegno.get("stato") in {"annullato", "stornato"}:
            continue
        numero = assegno.get("numero") or assegno.get("assegno_numero")
        base, _ = _parti_numero_assegno(numero)
        if not base:
            continue
        candidati.append({
            "assegno_id": assegno.get("id"),
            "numero_completo": str(numero),
            "numero_bancario": None,
            "importo": importo,
            "data": assegno.get("data_incasso") or assegno.get("data_emissione") or assegno.get("data"),
            "movimento_estratto_conto_id": (
                assegno.get("movimento_estratto_conto_id") or assegno.get("movimento_id")
            ),
            "fonte_registro": True,
            "fonte_estratto_conto": bool(
                assegno.get("movimento_estratto_conto_id") or assegno.get("movimento_id")
            ),
            "gia_collegato_fattura_id": (
                assegno.get("fattura_collegata") or assegno.get("fattura_id")
            ),
        })

    filtro_movimenti: Dict[str, Any] = {}
    if anno:
        filtro_movimenti = {"$or": [
            {"data": {"$regex": f"^{anno}"}},
            {"data_contabile": {"$regex": f"/{anno}$"}},
        ]}
    movimenti = await db["estratto_conto_movimenti"].find(
        filtro_movimenti,
        {
            "_id": 0, "id": 1, "data": 1, "data_contabile": 1,
            "importo": 1, "tipo": 1, "type": 1, "descrizione": 1,
            "descrizione_originale": 1, "livello_evidenza": 1,
            "evidenza_bancaria_ufficiale": 1,
        },
    ).to_list(None)
    for movimento in movimenti:
        if not _movimento_assegno_ufficiale(movimento):
            continue
        importo_movimento = round(abs(float(movimento.get("importo") or 0)), 2)
        if abs(importo_movimento - importo) > 0.005:
            continue
        descrizione = str(
            movimento.get("descrizione_originale") or movimento.get("descrizione") or ""
        )
        numero_bancario = estrai_numero_assegno(descrizione)
        base, _ = _parti_numero_assegno(numero_bancario)
        if not base:
            continue
        stessi_base = [
            candidato for candidato in candidati
            if _parti_numero_assegno(candidato.get("numero_completo"))[0] == base
        ]
        if stessi_base:
            # Un numero bancario puo' corrispondere a piu' moduli del carnet
            # (es. ...9431-6 e ...9431-7). Conserviamo TUTTE le alternative:
            # solo il suffisso digitato dall'utente rende il candidato unico.
            for candidato in stessi_base:
                candidato.update({
                    "numero_bancario": numero_bancario,
                    "data": movimento.get("data") or movimento.get("data_contabile"),
                    "movimento_estratto_conto_id": movimento.get("id"),
                    "fonte_estratto_conto": True,
                })
        else:
            candidati.append({
                "assegno_id": None,
                "numero_completo": numero_bancario,
                "numero_bancario": numero_bancario,
                "importo": importo,
                "data": movimento.get("data") or movimento.get("data_contabile"),
                "movimento_estratto_conto_id": movimento.get("id"),
                "fonte_registro": False,
                "fonte_estratto_conto": True,
                "gia_collegato_fattura_id": None,
            })
    if frammento:
        if not re.fullmatch(r"\d{3}-\d{2}", re.sub(r"\s+", "", frammento)):
            raise HTTPException(
                status_code=400,
                detail="Inserisci il finale dell'assegno nel formato 123-01.",
            )
        candidati = [
            candidato for candidato in candidati
            if _numero_assegno_corrisponde_frammento(
                candidato.get("numero_completo"), frammento,
            )
        ]
    candidati.sort(key=lambda item: (
        not item.get("fonte_estratto_conto"),
        not item.get("fonte_registro"),
        str(item.get("data") or ""),
        str(item.get("numero_completo") or ""),
    ))
    return candidati, importo


async def proponi_assegni_fattura(
    fattura_id: str = Query(...),
    frammento: str = Query(""),
) -> Dict[str, Any]:
    """Propone numeri reali senza associare sulla sola uguaglianza importo."""
    db = Database.get_db()
    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    candidati, importo = await _candidati_assegno_per_fattura(db, fattura, frammento)
    return {
        "fattura_id": fattura_id,
        "importo": importo,
        "frammento": frammento,
        "candidati": candidati,
        "univoco": len(candidati) == 1,
        "message": (
            "Numero assegno completo trovato. Verifica e conferma il collegamento."
            if len(candidati) == 1 else
            "Nessun assegno compatibile trovato."
            if not candidati else
            f"Trovati {len(candidati)} assegni dello stesso importo: inserisci il finale, per esempio 123-01."
        ),
    }


async def associa_assegno_fattura_provvisoria(data: Dict = Body(...)) -> Dict[str, Any]:
    """Conferma il candidato scelto e riusa il motore assegni canonico."""
    db = Database.get_db()
    fattura_id = str(data.get("fattura_id") or "").strip()
    assegno_id = str(data.get("assegno_id") or "").strip()
    movimento_id = str(data.get("movimento_estratto_conto_id") or "").strip()
    numero = str(data.get("numero_completo") or "").strip()
    if not fattura_id or not numero:
        raise HTTPException(status_code=400, detail="Fattura e numero assegno sono obbligatori")
    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    candidati, importo = await _candidati_assegno_per_fattura(db, fattura)
    # Se il client ha scelto un assegno di registro, il suo id e' la chiave
    # primaria e non va allargato al movimento EC condiviso. Un movimento
    # bancario senza suffisso puo' infatti essere la prova comune di piu'
    # assegni dello stesso carnet (es. ...9431-6 e ...9431-7).
    if assegno_id:
        candidati = [
            candidato for candidato in candidati
            if str(candidato.get("assegno_id") or "") == assegno_id
            and str(candidato.get("numero_completo") or "") == numero
        ]
    elif movimento_id:
        candidati = [
            candidato for candidato in candidati
            if str(candidato.get("movimento_estratto_conto_id") or "") == movimento_id
            and str(candidato.get("numero_completo") or "") == numero
        ]
    else:
        candidati = []
    if len(candidati) != 1:
        raise HTTPException(
            status_code=409,
            detail="Il numero non identifica piu' un solo assegno compatibile: ripeti la ricerca.",
        )
    candidato = candidati[0]
    assegno = None
    if candidato.get("assegno_id"):
        assegno = await db["assegni"].find_one(
            {"id": candidato["assegno_id"]}, {"_id": 0},
        )
    if not assegno and candidato.get("movimento_estratto_conto_id"):
        from app.services.assegni_estratto_conto import sincronizza_assegni_da_estratto_conto
        await sincronizza_assegni_da_estratto_conto(
            db, [candidato["movimento_estratto_conto_id"]],
        )
        assegno = await db["assegni"].find_one({
            "$or": [
                {"movimento_estratto_conto_id": candidato["movimento_estratto_conto_id"]},
                {"movimento_id": candidato["movimento_estratto_conto_id"]},
                {"numero": candidato.get("numero_bancario") or numero},
            ]
        }, {"_id": 0})
    if not assegno:
        raise HTTPException(status_code=409, detail="Assegno non disponibile nel registro")

    ids_collegati = {
        str(value) for value in (
            assegno.get("fattura_collegata"), assegno.get("fattura_id")
        ) if value
    }
    ids_collegati.update(
        str(link.get("fattura_id"))
        for link in (assegno.get("fatture_collegate") or [])
        if isinstance(link, dict) and link.get("fattura_id")
    )
    if ids_collegati and ids_collegati != {fattura_id}:
        raise HTTPException(status_code=409, detail="Assegno gia' collegato a un'altra fattura")

    movimento_id = (
        candidato.get("movimento_estratto_conto_id")
        or assegno.get("movimento_estratto_conto_id") or assegno.get("movimento_id")
    )
    if movimento_id:
        movimento = await db["estratto_conto_movimenti"].find_one(
            {"id": movimento_id}, {"_id": 0},
        )
        if not movimento or not _movimento_assegno_ufficiale(movimento):
            raise HTTPException(status_code=409, detail="Movimento assegno non ufficiale o non disponibile")
        now_iso = datetime.now(timezone.utc).isoformat()
        await db["assegni"].update_one({"id": assegno["id"]}, {"$set": {
            "movimento_id": movimento_id,
            "movimento_estratto_conto_id": movimento_id,
            "incassato_confermato_banca": True,
            "data_incasso": movimento.get("data") or movimento.get("data_contabile"),
            "updated_at": now_iso,
        }})
        assegno = await db["assegni"].find_one({"id": assegno["id"]}, {"_id": 0}) or assegno
        from app.services.assegni_estratto_conto import collega_assegno_riconciliato_a_fattura
        risultato = await collega_assegno_riconciliato_a_fattura(
            db, assegno, fattura, match_auto=False,
            match_livello="MANUALE_PRIMA_NOTA_NUMERO_ASSEGNO",
        )
        stato = "riconciliato"
    else:
        from app.services.assegni_fattura_intent import collega_assegno_compilato_a_fattura
        risultato = await collega_assegno_compilato_a_fattura(db, assegno, fattura)
        stato = "in_attesa_estratto_conto"

    return {
        "success": True,
        "fattura_id": fattura_id,
        "fattura_numero": fattura.get("invoice_number") or fattura.get("numero_fattura"),
        "assegno_id": assegno.get("id"),
        "assegno_numero": assegno.get("numero") or numero,
        "importo": importo,
        "stato": stato,
        "risultato": risultato,
        "message": (
            f"Assegno {assegno.get('numero') or numero} collegato alla fattura "
            f"{fattura.get('invoice_number') or fattura.get('numero_fattura') or fattura_id}."
        ),
    }


def _normalizza_piva(piva: str) -> str:
    """Confronto tollerante al prefisso 'IT' e agli spazi (stessa
    convenzione di suppliers_module/base.py::_varianti_piva — le fatture
    elettroniche portano la P.IVA con o senza prefisso paese a seconda del
    canale di import). Review Codex su PR #72: un confronto esatto avrebbe
    trattato IT04523831214 come fornitore terzo, capovolgendo per errore
    le fatture attive genuine il cui cedente è salvato col prefisso."""
    base = (piva or "").strip().upper().replace(" ", "")
    return base[2:] if base.startswith("IT") else base


def determina_tipo_movimento_fattura(fattura: Dict) -> tuple:
    """Determina tipo movimento (entrata/uscita) e categoria dalla fattura.

    Questo modulo gestisce ESCLUSIVAMENTE fatture PASSIVE (fatture ricevute
    da fornitori, da pagare) — mai fatture emesse dall'azienda. Il
    TipoDocumento FatturaPA (TD01, TD24, TD25...) è assegnato da chi EMETTE
    il documento e descrive solo la natura del documento (fattura normale,
    fattura differita...), non la direzione attiva/passiva per chi la
    riceve: una fattura TD24 ricevuta da un fornitore resta un debito da
    pagare, mai un incasso. Bug reale corretto 19/07/2026: la fattura 20 di
    DI MASSA DARIO & c. sas (TD24) veniva registrata come "Incasso cliente"
    in Prima Nota Banca invece che come pagamento fornitore, perché prima
    qui esisteva un ramo TIPI_FATTURA_ATTIVA = TD24/25/26/27 → "entrata"
    pensato per fatture attive, mai applicabile in questo modulo.
    """
    tipo_doc = fattura.get("tipo_documento", "TD01").upper()
    supplier_vat = fattura.get("supplier_vat") or fattura.get("cedente_piva") or ""

    is_nota_credito = tipo_doc in TIPI_NOTA_CREDITO
    # FIX (caso "fattura 20 - DI MASSA", 19/07/2026): TD24-27 indicano il TIPO
    # di cessione (es. TD26 "beni ammortizzabili"), NON la direzione — un
    # fornitore reale può emettere una fattura di acquisto (es. macchinario)
    # con questi codici. Questa collection (fatture RICEVUTE) contiene per
    # definizione documenti dove Ceraldi è il cessionario/committente
    # (acquirente): può essere "fattura attiva" (emessa DA noi) SOLO se il
    # cedente in anagrafica è Ceraldi stessa. Senza questo controllo, la
    # fattura di DI MASSA (fornitore reale, P.IVA diversa dalla nostra,
    # acquisto di un'impastatrice) veniva registrata come "Incasso cliente"
    # (entrata) invece di "Pagamento fattura" (uscita) solo per il codice
    # TD del documento. Se il cedente non è noto (dato mancante), si resta
    # sul comportamento storico (solo codice TD) per non introdurre
    # regressioni su fatture attive prive di questo campo.
    cedente_e_terzo = bool(supplier_vat) and _normalizza_piva(supplier_vat) != _normalizza_piva(PIVA_AZIENDA)
    is_fattura_attiva = tipo_doc in TIPI_FATTURA_ATTIVA and not cedente_e_terzo

    if is_nota_credito:
        return ("entrata", "Nota credito fornitore", "Nota credito")
    elif is_fattura_attiva:
        return ("entrata", "Incasso cliente", "Incasso fattura")
    else:
        # Unificazione categorie (utente 17/07/2026): tutti i pagamenti di
        # fatture fornitori usano la categoria unica "Fatture" (prima
        # convivevano "Pagamento fornitore", "Fornitori", "fornitori").
        return ("uscita", "Fatture", "Pagamento fattura")


def costruisci_campi_movimento_fattura(
    fattura: Dict, importo: float, *, lunghezza_fornitore: int = 30, suffisso: str = ""
) -> Dict[str, Any]:
    """Punto UNICO per calcolare i campi comuni di un movimento Prima Nota
    generato da una fattura: tipo/categoria (via determina_tipo_movimento_fattura),
    descrizione, numero_fattura e tipo_documento.

    Unifica (14/07/2026, richiesta utente: "tieni dei 5 punti solo la logica
    di adesso") la logica che prima era duplicata, con piccole differenze
    l'una dall'altra, in 5 punti diversi che scrivono un movimento fattura
    in Prima Nota: registra_pagamento_fattura, sync_fatture_pagate,
    conferma_fattura_provvisoria, bank/estratto_conto.py (riconciliazione EC
    automatica), services/dati_provvisori_service.py::conferma_proposta,
    multi_pagamento.py::registra_pagamento. Ogni punto resta responsabile
    delle proprie chiavi specifiche (id, data, riferimento, source, dedup,
    collection cassa/banca): qui si calcola solo la parte comune, quella
    che il bug della nota di credito e del numero fattura mancante avevano
    reso incoerente tra un punto e l'altro.
    """
    tipo_movimento, categoria, desc_prefisso = determina_tipo_movimento_fattura(fattura)
    # Bug 14/07/2026 (errore 400 segnalato dall'utente su una "BOLLETTE...":
    # una rettifica di credito fornitore, es. utenze, arrivata con
    # tipo_documento ancora TD01 ma importo già negativo nella sorgente,
    # veniva trattata come uscita normale). Il segno dell'importo è un
    # indizio più forte del tipo_documento su una sorgente dati non sempre
    # affidabile: un importo negativo su quella che sarebbe un'uscita è
    # sempre un'entrata/nota di credito, mai bloccata o forzata in uscita.
    if importo < 0 and tipo_movimento == "uscita":
        tipo_movimento, categoria, desc_prefisso = "entrata", "Nota credito fornitore", "Nota credito"
    numero_fattura = fattura.get("invoice_number") or fattura.get("numero_fattura") or ""
    fornitore = fattura.get("supplier_name") or fattura.get("cedente_denominazione") or "Fornitore"
    descrizione = f"{desc_prefisso} {numero_fattura} - {fornitore[:lunghezza_fornitore]}"
    if suffisso:
        descrizione = f"{descrizione} {suffisso}"
    return {
        "tipo": tipo_movimento,
        "categoria": categoria,
        "descrizione": descrizione,
        "importo": abs(importo),
        "numero_fattura": numero_fattura,
        "fornitore": fornitore,
        "tipo_documento": fattura.get("tipo_documento"),
    }


async def registra_pagamento_fattura(
    fattura: Dict,
    metodo_pagamento: str,
    importo_cassa: float = 0,
    importo_banca: float = 0,
    source: str = "fattura_pagata",
    movimento_bancario: Optional[Dict[str, Any]] = None,
    session=None,
) -> Dict:
    """Registra automaticamente il pagamento di una fattura.

    Per il lato banca ``movimento_bancario`` e' obbligatorio: il metodo
    abituale del fornitore e il piano XML indicano come si prevede di pagare,
    ma non dimostrano che il denaro sia uscito.

    IDEMPOTENTE: se esiste già un movimento con stesso fattura_id sulla
    collection di destinazione, NON crea duplicati. Ritorna l'id esistente.
    """
    db = Database.get_db()

    now = datetime.now(timezone.utc).isoformat()
    data_fattura = fattura.get("invoice_date") or fattura.get("data_fattura") or now[:10]
    importo_totale = fattura.get("total_amount") or fattura.get("importo_totale") or 0
    numero_fattura = fattura.get("invoice_number") or fattura.get("numero_fattura") or "N/A"
    fornitore = fattura.get("supplier_name") or fattura.get("cedente_denominazione") or "Fornitore"
    fornitore_piva = fattura.get("supplier_vat") or fattura.get("cedente_piva") or ""
    fattura_id = fattura.get("id") or fattura.get("invoice_key")

    tipo_movimento, categoria, desc_prefisso = determina_tipo_movimento_fattura(fattura)

    risultato = {
        "cassa": None,
        "banca": None,
        "provvisoria": False,
        "tipo_movimento": tipo_movimento,
        "duplicato": False,
    }
    descrizione_base = f"{desc_prefisso} {numero_fattura} - {fornitore[:40]}"

    # Riferimento UNIFORME in tutto il modulo: "FATT-{id}"
    # Questo allinea dedup con sync_fatture_pagate e conferma_fattura_provvisoria.
    riferimento = f"FATT-{fattura_id}" if fattura_id else numero_fattura

    movimento_base = {
        "data": data_fattura,
        "tipo": tipo_movimento,
        "categoria": categoria,
        "riferimento": riferimento,
        "numero_fattura": numero_fattura,  # mantenuto per retrocompatibilità UI
        "fornitore": fornitore,
        "fornitore_piva": fornitore_piva,
        "fattura_id": fattura_id,
        "tipo_documento": fattura.get("tipo_documento"),
        "source": source,
        "created_at": now
    }

    async def _insert_idempotente(collection: str, importo: float, desc: str) -> tuple:
        """Inserisce movimento solo se non esiste già per questa fattura.
        Ritorna (id_movimento, was_duplicate)."""
        if fattura_id:
            existing = await db[collection].find_one({
                "$or": [
                    {"fattura_id": fattura_id},
                    {"riferimento": riferimento},
                ],
                "status": {"$nin": ["deleted", "archived"]},
            }, session=session)
            if existing:
                return (existing.get("id") or str(existing.get("_id")), True)

        # L'import dell'estratto conto può avere già creato la riga bancaria
        # generica. Quando la fattura viene riconosciuta, completiamo quella
        # stessa riga invece di rappresentare due volte il medesimo addebito.
        if collection == COLLECTION_PRIMA_NOTA_BANCA and movimento_bancario:
            evidenza_id = movimento_bancario.get("id") or movimento_bancario.get("movimento_id")
            generic = await db[collection].find_one({
                "$and": [
                    {"$or": [
                        {"estratto_conto_id": evidenza_id},
                        {"movimento_bancario_id": evidenza_id},
                    ]},
                    {"$or": [
                        {"fattura_id": {"$exists": False}}, {"fattura_id": None},
                    ]},
                    {"$or": [
                        {"invoice_id": {"$exists": False}}, {"invoice_id": None},
                    ]},
                ],
                "source": "estratto_conto_auto",
                "importo": {"$gte": float(importo) - 0.01, "$lte": float(importo) + 0.01},
                "status": {"$nin": ["deleted", "archived"]},
            }, session=session)
            if generic:
                await db[collection].update_one(
                    {"id": generic["id"]},
                    {"$set": {
                        "tipo": tipo_movimento, "categoria": categoria,
                        "descrizione": desc, "riferimento": riferimento,
                        "numero_fattura": numero_fattura, "fornitore": fornitore,
                        "fornitore_piva": fornitore_piva, "fattura_id": fattura_id,
                        "tipo_documento": fattura.get("tipo_documento"),
                        "estratto_conto_id": evidenza_id,
                        "movimento_bancario_id": evidenza_id,
                        "riconciliato": True,
                        "confidenza": movimento_bancario.get("match_score", 1.0),
                        "updated_at": now,
                    }},
                    session=session,
                )
                return (generic.get("id") or str(generic.get("_id")), False)

        mov = {**movimento_base, "id": str(uuid.uuid4()), "importo": float(importo), "descrizione": desc}
        if collection == COLLECTION_PRIMA_NOTA_BANCA and movimento_bancario:
            evidenza_id = movimento_bancario.get("id") or movimento_bancario.get("movimento_id")
            mov.update({
                "estratto_conto_id": evidenza_id,
                "movimento_bancario_id": evidenza_id,
                "riconciliato": True,
                "confidenza": movimento_bancario.get("match_score", 1.0),
            })
        await db[collection].insert_one(mov.copy(), session=session)
        return (mov["id"], False)

    canonico = normalizza_metodo_pagamento(metodo_pagamento)

    if canonico == "cassa":
        importo_effettivo = importo_cassa if importo_cassa > 0 else importo_totale
        mid, dup = await _insert_idempotente(
            COLLECTION_PRIMA_NOTA_CASSA, importo_effettivo, descrizione_base
        )
        risultato["cassa"] = mid
        risultato["duplicato"] = dup

    elif canonico == "banca":
        if not movimento_bancario or not (
            movimento_bancario.get("id") or movimento_bancario.get("movimento_id")
        ):
            risultato["provvisoria"] = True
            return risultato
        importo_effettivo = importo_banca if importo_banca > 0 else importo_totale
        mid, dup = await _insert_idempotente(
            COLLECTION_PRIMA_NOTA_BANCA, importo_effettivo, descrizione_base
        )
        risultato["banca"] = mid
        risultato["duplicato"] = dup

        evidenza_id = movimento_bancario.get("id") or movimento_bancario.get("movimento_id")
        await db["estratto_conto_movimenti"].update_one(
            {"id": evidenza_id, "$or": [
                {"fattura_id": {"$exists": False}},
                {"fattura_id": None},
                {"fattura_id": fattura_id},
            ]},
            {"$set": {
                "riconciliato": True,
                "abbinato": True,
                "tipo_abbinamento": "fattura",
                "documento_id": fattura_id,
                "fattura_id": fattura_id,
                "confidenza": movimento_bancario.get("match_score", 1.0),
                "riconciliato_at": now,
            }},
            session=session,
        )

    elif canonico == "misto":
        if importo_cassa > 0:
            mid, dup_c = await _insert_idempotente(
                COLLECTION_PRIMA_NOTA_CASSA, importo_cassa, f"{descrizione_base} (contanti)"
            )
            risultato["cassa"] = mid
            risultato["duplicato"] = risultato["duplicato"] or dup_c
        if importo_banca > 0 and movimento_bancario:
            mid, dup_b = await _insert_idempotente(
                COLLECTION_PRIMA_NOTA_BANCA, importo_banca, f"{descrizione_base} (bonifico)"
            )
            risultato["banca"] = mid
            risultato["duplicato"] = risultato["duplicato"] or dup_b
        elif importo_banca > 0:
            risultato["provvisoria"] = True

    return risultato


async def registra_fattura_prima_nota(
    fattura_id: str = Body(...),
    metodo_pagamento: str = Body(None),
    importo_cassa: float = Body(0),
    importo_banca: float = Body(0)
) -> Dict:
    """Registra manualmente il pagamento di una fattura."""
    db = Database.get_db()
    
    fattura = await db[Collections.INVOICES].find_one(
        {"$or": [{"id": fattura_id}, {"invoice_key": fattura_id}]}
    )
    
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    fornitore_piva = fattura.get("supplier_vat") or fattura.get("cedente_piva")
    if fattura.get("esclusa_da_cassa_banca"):
        raise HTTPException(
            status_code=409,
            detail="Fattura esclusa da Cassa e Banca; resta registrata ai fini contabili e IVA",
        )
    if fornitore_piva:
        fornitore_escluso = await db[Collections.SUPPLIERS].find_one(
            {"$and": [
                {"$or": [
                    {"partita_iva": fornitore_piva}, {"piva": fornitore_piva},
                    {"vat_number": fornitore_piva},
                ]},
                {"$or": [{"esclude_cassa_banca": True}, {"cessato": True}]},
            ]},
            {"_id": 0, "id": 1},
        )
        if fornitore_escluso:
            raise HTTPException(
                status_code=409,
                detail="Fornitore escluso da Cassa e Banca; la fattura resta valida ai fini IVA",
            )

    if not metodo_pagamento:
        fornitore_piva = fattura.get("supplier_vat") or fattura.get("cedente_piva")
        if fornitore_piva:
            fornitore = await db[Collections.SUPPLIERS].find_one(
                {"$or": [{"partita_iva": fornitore_piva}, {"piva": fornitore_piva},
                         {"vat_number": fornitore_piva}]},
                {"_id": 0})
            if fornitore:
                metodo_fornitore = (fornitore.get("metodo_pagamento") or "").lower()
                metodo_pagamento = "cassa" if metodo_fornitore in ["contanti", "cassa", "cash"] else "banca"
            else:
                metodo_pagamento = "banca"
        else:
            metodo_pagamento = "banca"

    rate_xml = fattura.get("pagamento_rate") or []
    if len(rate_xml) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                f"La fattura contiene {len(rate_xml)} rate XML. Il totale documento non puo' "
                "essere registrato come pagamento unico senza evidenza: collega e conferma "
                "i singoli assegni o movimenti bancari."
            ),
        )
    
    risultato = await registra_pagamento_fattura(
        fattura=fattura,
        metodo_pagamento=metodo_pagamento,
        importo_cassa=importo_cassa,
        importo_banca=importo_banca
    )
    
    registrato = bool(risultato.get("cassa") or risultato.get("banca"))
    await db[Collections.INVOICES].update_one(
        {"_id": fattura["_id"]},
        {"$set": {
            "pagato": registrato,
            "stato_pagamento": "pagata" if registrato else "da_pagare",
            "stato_finanziario": (
                "pagato" if registrato else "in_attesa_estratto_conto"
            ),
            "data_pagamento": datetime.now(timezone.utc).isoformat()[:10] if registrato else None,
            "metodo_pagamento": metodo_pagamento,
            "prima_nota_cassa_id": risultato.get("cassa"),
            "prima_nota_banca_id": risultato.get("banca")
        }}
    )
    
    return {
        "message": (
            "Pagamento registrato" if registrato
            else "Fattura lasciata in Provvisoria: manca un movimento reale dell'estratto conto"
        ),
        "prima_nota_cassa": risultato.get("cassa"),
        "prima_nota_banca": risultato.get("banca")
    }


async def sync_corrispettivi_to_prima_nota() -> Dict:
    """Sincronizza corrispettivi in Prima Nota Cassa."""
    return await _sync_corrispettivi_impl()


async def sync_corrispettivi_anno(anno: int = Query(...)) -> Dict:
    """Sincronizza corrispettivi dell'anno specificato nella Prima Nota Cassa."""
    return await _sync_corrispettivi_impl(anno)


async def _sync_corrispettivi_impl(anno: int = None) -> Dict:
    """Implementazione sync corrispettivi → prima nota cassa/banca.

    Catch-up periodico (scheduler ogni 30 min) per i corrispettivi che non
    sono ancora passati dal percorso di caricamento diretto. Unificato
    (14/07/2026, richiesta utente) su un'unica implementazione condivisa con
    quel percorso — corrispettivi_helpers.py::_create_prima_nota_movements —
    così la regola contabile (cassa entrata=totale/uscita=POS, banca
    entrata=POS) e la lettura dei campi pagamento vivono in un solo posto,
    non due copie che potevano divergere.
    """
    from app.routers.invoices.corrispettivi_helpers import _create_prima_nota_movements
    from .common import COLLECTION_PRIMA_NOTA_CASSA
    db = Database.get_db()

    query = {}
    if anno:
        query["anno"] = anno

    corrispettivi = await db["corrispettivi"].find(query, {"_id": 0}).to_list(5000)

    inseriti = 0
    duplicati = 0
    saltati_importo_zero = []  # diagnostica: quali corrispettivi vengono scartati

    for c in corrispettivi:
        corr_id = c.get("id", "")

        # Bug corretto 17/07/2026 (verificato live: cassa da 428k a 4,3M in
        # 24 ore): i corrispettivi legacy SENZA campo id producevano qui
        # corr_id="" — il find_one({"corrispettivo_id": ""}) non matchava mai
        # il movimento scritto (corrispettivo_id None) e il sync ricreava
        # l'entrata a ogni giro. Ora: 1) al documento senza id viene
        # assegnato un id stabile; 2) il dedup copre anche il caso per
        # data (un solo registratore → una sola entrata per giornata).
        if not corr_id:
            corr_id = str(uuid.uuid4())
            await db["corrispettivi"].update_one(
                {"data": c.get("data"), "id": {"$exists": False},
                 "created_at": c.get("created_at")},
                {"$set": {"id": corr_id}},
            )
            c["id"] = corr_id

        # Check dedup: se questo corrispettivo ha già un movimento cassa
        # (da questo stesso sync o dal caricamento diretto), non rigenerare.
        existing = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({"$or": [
            {"corrispettivo_id": corr_id},
            # Stessa chiave (data+matricola) della guardia di idempotenza del
            # writer: il giorno del risigillo (cambio matricola) restano
            # legittime due entrate nella stessa data.
            {"data": c.get("data"), "tipo": "entrata", "categoria": "Corrispettivi",
             "matricola_rt": c.get("matricola_rt") or c.get("id_dispositivo") or None},
        ]})
        if existing:
            duplicati += 1
            continue

        risultato = await _create_prima_nota_movements(db, c)

        if not risultato.get("prima_nota_cassa_id"):
            # Totale non ricostruibile da nessun campo noto: stessa diagnostica
            # di prima, per non perdere visibilità sui corrispettivi scartati.
            saltati_importo_zero.append({
                "id": corr_id,
                "data": c.get("data", c.get("data_operazione", "")),
                "anno": c.get("anno"),
                "campi_totale": {
                    "totale": c.get("totale"),
                    "totale_complessivo": c.get("totale_complessivo"),
                    "importo": c.get("importo"),
                    "pagato_contanti": c.get("pagato_contanti"),
                    "pagato_elettronico": c.get("pagato_elettronico"),
                    "pagato_pos": c.get("pagato_pos"),
                },
            })
            logger.warning(
                "Corrispettivo %s (data=%s) saltato: totale=0 su tutti i campi noti",
                corr_id, c.get("data", ""),
            )
            continue

        inseriti += 1

    return {
        "message": f"Sincronizzati {inseriti} corrispettivi in Prima Nota Cassa",
        "inseriti": inseriti,
        "duplicati": duplicati,
        "saltati": len(saltati_importo_zero),
        "saltati_dettaglio": saltati_importo_zero[:50],  # primi 50 per diagnostica
        "anno": anno,
        "ok": True
    }


CLAIM_PAGAMENTO_TTL_MINUTI = 10


async def _acquisisci_claim_pagamento(
    db, fattura_id: str, operazione: str
) -> str:
    """Serializza le decisioni Cassa/Banca sulla stessa fattura.

    Il blocco vive sulla fattura, quindi protegge anche da due richieste che
    tentano destinazioni diverse. Scade automaticamente dopo dieci minuti per
    non lasciare il documento bloccato dopo un arresto del processo.
    """
    token = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    scaduto_prima = (
        now - timedelta(minutes=CLAIM_PAGAMENTO_TTL_MINUTI)
    ).isoformat()
    claimed = await db["invoices"].find_one_and_update(
        {
            "id": fattura_id,
            "$or": [
                {"prima_nota_payment_claim": {"$exists": False}},
                {"prima_nota_payment_claim": None},
                {"prima_nota_payment_claim": ""},
                {"prima_nota_payment_claim_at": {"$lt": scaduto_prima}},
            ],
        },
        {"$set": {
            "prima_nota_payment_claim": token,
            "prima_nota_payment_claim_at": now.isoformat(),
            "prima_nota_payment_operation": operazione,
        }},
    )
    if claimed is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "La fattura e' gia' in lavorazione. Attendi il completamento "
                "e ricarica Prima Nota prima di riprovare."
            ),
        )
    return token


async def _rilascia_claim_pagamento(db, fattura_id: str, token: str) -> None:
    await db["invoices"].update_one(
        {"id": fattura_id, "prima_nota_payment_claim": token},
        {"$unset": {
            "prima_nota_payment_claim": "",
            "prima_nota_payment_claim_at": "",
            "prima_nota_payment_operation": "",
        }},
    )


async def sync_fatture_pagate(anno: int = Query(...)) -> Dict:
    """Sincronizza fatture pagate nella Prima Nota."""
    db = Database.get_db()
    
    date_start = f"{anno}-01-01"
    date_end = f"{anno}-12-31"
    
    fatture = await db["invoices"].find(
        {"invoice_date": {"$gte": date_start, "$lte": date_end}, "stato_pagamento": "pagata"},
        {"_id": 0}
    ).to_list(10000)
    
    if not fatture:
        return {"message": "Nessuna fattura pagata trovata", "importati": 0}
    
    # IMPORTANTE: il dedup NON deve filtrare per categoria.
    # Dopo la PR #1, registra_pagamento_fattura salva con categoria variabile
    # ("Pagamento fornitore", "Incasso cliente", "Nota credito fornitore") e
    # NON "Fatture". Se filtrassimo per categoria="Fatture" come prima, questa
    # funzione non vedrebbe quei movimenti e creerebbe duplicati.
    # Il riferimento è ormai uniforme (FATT-{id}), basta quello.
    existing_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find(
        {
            "data": {"$gte": date_start, "$lte": date_end},
            "riferimento": {"$regex": "^FATT-"},
            "status": {"$nin": ["deleted", "archived"]},
        },
        {"riferimento": 1, "fattura_id": 1, "_id": 0}
    ).to_list(10000)
    existing_banca = await db[COLLECTION_PRIMA_NOTA_BANCA].find(
        {
            "data": {"$gte": date_start, "$lte": date_end},
            "riferimento": {"$regex": "^FATT-"},
            "status": {"$nin": ["deleted", "archived"]},
        },
        {"riferimento": 1, "fattura_id": 1, "_id": 0}
    ).to_list(10000)
    existing_refs = set(e.get("riferimento") for e in existing_cassa + existing_banca if e.get("riferimento"))
    # Dedup anche per fattura_id (caso: vecchi movimenti col riferimento nel formato "numero_fattura")
    existing_fids = set(e.get("fattura_id") for e in existing_cassa + existing_banca if e.get("fattura_id"))
    
    importati_cassa = 0
    importati_banca = 0
    banca_senza_evidenza = 0
    totale_cassa = 0
    totale_banca = 0
    
    for fatt in fatture:
        fattura_id = fatt.get('id', '')
        ref = f"FATT-{fattura_id}"

        # Dedup: o per riferimento FATT-, o per fattura_id (in caso di vecchi movimenti)
        if ref in existing_refs or (fattura_id and fattura_id in existing_fids):
            continue
        
        totale = float(fatt.get("total_amount", 0) or 0)
        if totale <= 0:
            continue
        
        metodo = fatt.get("metodo_pagamento", "bonifico").lower()

        if metodo in ["contanti", "cassa"]:
            risultato = await registra_pagamento_fattura(
                fatt, "cassa", source="sync_fatture"
            )
            if risultato.get("cassa"):
                importati_cassa += 1
                totale_cassa += totale
        else:
            from app.routers.invoices.fatture_upload import find_ec_match_for_invoice
            ec_id = (fatt.get("movimento_bancario_id") or
                     fatt.get("estratto_conto_id"))
            evidenza = (
                await db["estratto_conto_movimenti"].find_one({"id": ec_id})
                if ec_id else None
            )
            if not evidenza:
                evidenza = await find_ec_match_for_invoice(
                    db, totale,
                    fatt.get("supplier_name") or fatt.get("cedente_denominazione") or "",
                    fatt.get("invoice_date") or fatt.get("data_fattura") or "",
                    fatt.get("invoice_number") or fatt.get("numero_fattura") or "",
                )
            if not evidenza:
                banca_senza_evidenza += 1
                await db["invoices"].update_one(
                    {"id": fattura_id},
                    {"$set": {"pagato": False, "paid": False,
                              "stato_pagamento": "da_pagare",
                              "stato_finanziario": "in_attesa_estratto_conto"}},
                )
                continue
            risultato = await registra_pagamento_fattura(
                fatt, "banca", source="estratto_conto_auto",
                movimento_bancario=evidenza,
            )
            if risultato.get("banca"):
                importati_banca += 1
                totale_banca += totale
    
    return {
        "message": "Sincronizzazione completata",
        "importati_cassa": importati_cassa,
        "importati_banca": importati_banca,
        "totale_cassa": round(totale_cassa, 2),
        "totale_banca": round(totale_banca, 2),
        "banca_senza_evidenza_lasciate_provvisorie": banca_senza_evidenza,
        "fatture_pagate_anno": len(fatture)
    }


async def get_corrispettivi_sync_status() -> Dict:
    """Verifica stato sincronizzazione corrispettivi."""
    db = Database.get_db()
    
    total_corrispettivi = await db["corrispettivi"].count_documents({})
    synced = await db[COLLECTION_PRIMA_NOTA_CASSA].count_documents({"corrispettivo_id": {"$exists": True, "$ne": None}})
    
    pipeline = [{"$group": {"_id": None, "totale": {"$sum": "$totale"}}}]
    totals = await db["corrispettivi"].aggregate(pipeline).to_list(1)
    
    pipeline_pn = [
        {"$match": {"categoria": "Corrispettivi", "tipo": "entrata"}},
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}}
    ]
    totals_pn = await db[COLLECTION_PRIMA_NOTA_CASSA].aggregate(pipeline_pn).to_list(1)
    
    return {
        "corrispettivi_totali": total_corrispettivi,
        "corrispettivi_sincronizzati": synced,
        "da_sincronizzare": total_corrispettivi - synced,
        "totale_corrispettivi_euro": totals[0].get("totale", 0) if totals else 0,
        "totale_in_prima_nota_euro": totals_pn[0].get("totale", 0) if totals_pn else 0
    }



async def sync_estratto_conto_to_banca(anno: int = Query(...)) -> Dict:
    """
    Sincronizza movimenti dall'estratto conto bancario alla prima nota banca.
    Importa tutti i movimenti dell'anno specificato.
    """
    db = Database.get_db()
    
    # Trova movimenti dell'anno nell'estratto conto
    # Le date sono in formato DD/MM/YYYY
    anno_str = str(anno)
    
    # Query: data_contabile contiene l'anno (potrebbe essere DD/MM/YYYY o YYYY-MM-DD)
    query = {"$or": [
        {"data_contabile": {"$regex": f"/{anno_str}$"}},  # DD/MM/YYYY
        {"data_contabile": {"$regex": f"^{anno_str}-"}},   # YYYY-MM-DD
    ]}
    
    movimenti_ec = await db["estratto_conto_movimenti"].find(query, {"_id": 0}).to_list(15000)
    
    if not movimenti_ec:
        return {"message": f"Nessun movimento estratto conto per {anno}", "importati": 0}
    
    # Get existing prima nota banca for dedup
    existing_ids = set()
    async for pn in db[COLLECTION_PRIMA_NOTA_BANCA].find(
        {"data": {"$regex": f"^{anno_str}"}},
        {"_id": 0, "estratto_conto_id": 1, "id": 1}
    ):
        if pn.get("estratto_conto_id"):
            existing_ids.add(pn["estratto_conto_id"])
    
    importati = 0
    batch = []
    
    for mov in movimenti_ec:
        ec_id = mov.get("id", "")
        if ec_id in existing_ids:
            continue
        
        # Converti data DD/MM/YYYY → YYYY-MM-DD
        data_raw = mov.get("data_contabile", "")
        if "/" in data_raw:
            parts = data_raw.split("/")
            if len(parts) == 3:
                data_iso = f"{parts[2]}-{parts[1]}-{parts[0]}"
            else:
                data_iso = data_raw
        else:
            data_iso = data_raw
        
        importo = float(mov.get("importo", 0) or 0)
        if importo == 0:
            continue
        
        tipo = "entrata" if importo > 0 else "uscita"
        
        movimento_pn = {
            "id": str(uuid.uuid4()),
            "data": data_iso,
            "tipo": tipo,
            "importo": abs(importo),
            "descrizione": mov.get("descrizione", "")[:200],
            "categoria": mov.get("categoria", "Bancario"),
            "causale": mov.get("causale", ""),
            "beneficiario": mov.get("beneficiario", ""),
            "estratto_conto_id": ec_id,
            "source": "estratto_conto_sync",
            "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
        
        batch.append(movimento_pn)
        importati += 1
        
        # Insert in batches of 500
        if len(batch) >= 500:
            await db[COLLECTION_PRIMA_NOTA_BANCA].insert_many(batch)
            batch = []
    
    if batch:
        await db[COLLECTION_PRIMA_NOTA_BANCA].insert_many(batch)
    
    return {
        "message": f"Sincronizzati {importati} movimenti estratto conto → prima nota banca {anno}",
        "anno": anno,
        "movimenti_estratto_conto": len(movimenti_ec),
        "gia_sincronizzati": len(existing_ids),
        "importati": importati,
    }



def _movimento_non_consumato_da_altra_fattura(
    movimento: Dict[str, Any], fattura_id: str,
) -> bool:
    """Un flag ``riconciliato`` non basta a escludere l'evidenza.

    Gli assegni vengono marcati riconciliati appena compaiono in banca, anche
    se non hanno ancora una fattura. Si esclude il movimento soltanto quando
    porta davvero l'id di una fattura diversa.
    """
    assegnate = {
        str(value) for value in (
            [movimento.get("fattura_id"), movimento.get("invoice_id")]
            + list(movimento.get("fattura_ids") or [])
        ) if value
    }
    return not assegnate or str(fattura_id) in assegnate


def _rimborso_duplica_pagamento(
    fattura: Dict[str, Any],
    candidati_forti: list,
    movimenti_anno: list,
    importo: float,
):
    """Riduce due pagamenti + un rimborso a un pagamento netto certo.

    Non sceglie quale CRO sia stato materialmente stornato (sono equivalenti),
    ma conserva tutti gli id come prova. Il risultato contabile netto e'
    invece univoco: una sola uscita resta a saldo della fattura.
    """
    if len(candidati_forti) < 2:
        return None
    from app.services.riconciliazione_bancaria import match_fornitore_descrizione

    fornitore = (
        fattura.get("supplier_name") or fattura.get("cedente_denominazione") or ""
    )
    date_uscite = {
        str(movimento.get("data") or movimento.get("data_contabile") or "")[:10]
        for movimento, _evidenza in candidati_forti
    }
    rimborsi = []
    for movimento in movimenti_anno:
        tipo = str(movimento.get("tipo") or movimento.get("type") or "").lower()
        descrizione = (
            movimento.get("descrizione_originale")
            or movimento.get("descrizione") or ""
        )
        testo = descrizione.upper()
        if tipo != "entrata" or not any(
            token in testo for token in ("RIMBORS", "RESTITUZ", "STORNO")
        ):
            continue
        if round(abs(float(movimento.get("importo") or 0)), 2) != round(importo, 2):
            continue
        data = str(movimento.get("data") or movimento.get("data_contabile") or "")[:10]
        if data not in date_uscite:
            continue
        if match_fornitore_descrizione(fornitore, descrizione) <= 0:
            continue
        rimborsi.append(movimento)
    if len(candidati_forti) - len(rimborsi) != 1:
        return None
    movimento = sorted(
        (item[0] for item in candidati_forti),
        key=lambda item: str(item.get("id") or ""),
    )[0]
    return movimento, {
        "tipo": "pagamento_netto_dopo_rimborso_duplicato",
        "uscite_ids": [item[0].get("id") for item in candidati_forti],
        "rimborsi_ids": [item.get("id") for item in rimborsi],
    }


def _risolvi_rivendicazioni_movimenti(
    provvisori: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Rende univoca l'assegnazione fattura -> movimento bancario.

    L'importo al centesimo e' necessario, ma non autorizza a scegliere per
    ordine di lettura. Una prova con numero fattura/SDD prevale su una prova
    generica basata su strumento + fornitore; se piu' fatture hanno la stessa
    prova migliore, tutte restano sospese con i candidati visibili.
    """
    rivendicazioni: Dict[str, List[Dict[str, Any]]] = {}
    for riga in provvisori:
        movimento_id = (riga.get("movimento_banca") or {}).get("id")
        if movimento_id:
            rivendicazioni.setdefault(str(movimento_id), []).append(riga)

    priorita_evidenza = {
        "identita_fattura_importo": 3,
        "sdd_fornitore_importo_data": 3,
        "strumento_fornitore_importo_data": 2,
    }
    for righe in rivendicazioni.values():
        if len(righe) < 2:
            continue
        priorita_massima = max(
            priorita_evidenza.get(str(riga.get("evidenza_banca") or ""), 1)
            for riga in righe
        )
        migliori = [
            riga for riga in righe
            if priorita_evidenza.get(str(riga.get("evidenza_banca") or ""), 1)
            == priorita_massima
        ]
        da_sospendere = (
            [riga for riga in righe if riga is not migliori[0]]
            if len(migliori) == 1 else righe
        )
        candidati = [
            {
                "fattura_id": riga.get("fattura_id"),
                "numero": riga.get("fattura_numero"),
                "fornitore": riga.get("fornitore"),
                "importo": riga.get("importo"),
            }
            for riga in migliori
        ]
        for riga in da_sospendere:
            riga["movimento_banca"] = None
            riga["evidenza_banca"] = None
            riga["strumento_bancario"] = None
            riga["stato_match"] = (
                "in_attesa_evidenza_specifica"
                if len(migliori) == 1 else "ambiguo_importo_al_centesimo"
            )
            riga["candidati_ambigui"] = candidati
            riga["motivo_sospensione"] = (
                "Il movimento con lo stesso importo e stato assegnato alla "
                "fattura citata esplicitamente nella causale"
                if len(migliori) == 1 else
                f"Importo al centesimo, ma {len(migliori)} fatture hanno "
                "la stessa identita bancaria: scegli il documento esatto"
            )
    return provvisori


async def get_fatture_provvisorie(anno: int = Query(...)) -> Dict:
    """
    Lista fatture NON ancora registrate in Prima Nota.
    Per ogni fattura, il sistema suggerisce CASSA o BANCA basandosi su:
    1. Metodo pagamento XML (MP01=contanti→cassa, MP05=bonifico→banca)
    2. Ricerca importo nell'estratto conto (se trovato → BANCA confermato)
    """
    db = Database.get_db()
    
    # Tutte le fatture attive dell'anno. I flag pagato/paid legacy non sono
    # sufficienti: sotto verifichiamo la riga contabile reale e, per banca,
    # la presenza dell'evidenza dell'estratto conto.
    fatture_tutte = await db["invoices"].find(
        {
            "status": {"$nin": ["deleted", "archived"]},
            "entity_status": {"$ne": "deleted"},
            "$or": [
                {"invoice_date": {"$regex": f"^{anno}"}},
                {"data_documento": {"$regex": f"^{anno}"}},
                {"data_fattura": {"$regex": f"^{anno}"}},
            ],
        },
        {"_id": 0, "xml_raw": 0, "xml_content": 0, "linee": 0}
    ).sort("invoice_date", -1).to_list(None)
    fatture_tutte = _dedupe_invoices([
        f for f in fatture_tutte
        if float(f.get("total_amount") or f.get("importo_totale") or 0) > 0
    ])
    totale_fatture_attive = len(fatture_tutte)

    # La ritenuta e' un debito verso l'Erario, non un residuo da bonificare
    # al professionista. La collection fiscale e' la fonte documentale gia'
    # estratta dall'XML; la riportiamo in memoria prima di calcolare i residui.
    fatture_ids = [str(f.get("id")) for f in fatture_tutte if f.get("id")]
    ritenute_per_fattura = {}
    if fatture_ids:
        async for ritenuta in db["ritenute_acconto"].find(
            {"fattura_id": {"$in": fatture_ids}},
            {"_id": 0, "fattura_id": 1, "importo": 1},
        ):
            try:
                ritenute_per_fattura[str(ritenuta.get("fattura_id"))] = abs(
                    float(ritenuta.get("importo") or 0)
                )
            except (TypeError, ValueError):
                continue
    for fattura in fatture_tutte:
        importo_ritenuta = ritenute_per_fattura.get(str(fattura.get("id")))
        if importo_ritenuta:
            fattura["ritenuta_importo"] = importo_ritenuta

    # Gli import nuovi hanno `dati_ddt` gia' strutturato. Per i documenti
    # esistenti carichiamo xml_raw/xml_content soltanto quando contiene
    # DatiDDT, evitando di trasferire centinaia di XML (spesso con PDF base64
    # allegati) ad ogni apertura della Prima Nota. La scansione riguarda tutte
    # le fatture dell'anno, non solo quelle ancora aperte.
    ddt_per_fattura: Dict[str, list[Dict[str, Any]]] = {}
    stato_ddt_per_fattura: Dict[str, str] = {}
    legacy_ddt_ids = []
    for fattura in fatture_tutte:
        fattura_id = str(fattura.get("id") or "")
        riferimenti = _estrai_riferimenti_ddt(fattura)
        if riferimenti:
            ddt_per_fattura[fattura_id] = riferimenti
            stato_ddt_per_fattura[fattura_id] = "presente"
        elif "dati_ddt" in fattura:
            stato_ddt_per_fattura[fattura_id] = "non_indicato_nell_xml"
        elif fattura.get("id"):
            legacy_ddt_ids.append(str(fattura["id"]))
            stato_ddt_per_fattura[fattura_id] = "xml_non_disponibile"
    if legacy_ddt_ids:
        async for documento_ddt in db["invoices"].find(
            {
                "id": {"$in": legacy_ddt_ids},
                "$or": [
                    {"xml_raw": {"$regex": "DatiDDT"}},
                    {"xml_content": {"$regex": "DatiDDT"}},
                ],
            },
            {
                "_id": 0, "id": 1, "xml_raw": 1, "xml_content": 1,
                "xml_body_index": 1, "causali": 1,
            },
        ):
            riferimenti = _estrai_riferimenti_ddt(documento_ddt)
            if riferimenti:
                fattura_id = str(documento_ddt.get("id") or "")
                ddt_per_fattura[fattura_id] = riferimenti
                stato_ddt_per_fattura[fattura_id] = "presente"

    pagamenti_per_fattura = await _riepilogo_prima_nota_per_fattura(
        db, fatture_tutte,
    )
    fatture = await fatture_senza_pagamento_contabile_confermato(
        db, fatture_tutte,
    )
    totale_fatture_aperte = len(fatture)
    totale_gia_registrate = totale_fatture_attive - totale_fatture_aperte

    # Movimenti banca per match.
    # NB: l'importer EC scrive la data nel campo "data" (YYYY-MM-DD); i record
    # legacy usano "data_contabile" (DD/MM/YYYY). Coprire entrambi, e indicizzare
    # per importo ASSOLUTO arrotondato (la collection ha sia importi assoluti
    # sia con segno negativo).
    movimenti_banca = {}
    movimenti_anno = []
    # Una fattura di dicembre viene normalmente addebitata a gennaio. Il
    # filtro storico sul solo anno fattura lasciava quindi molti documenti in
    # "Da decidere" pur avendo una prova bancaria forte nell'anno successivo.
    # Le regole di identita/importo/data sotto restano comunque bloccanti.
    anni_movimenti = (anno - 1, anno, anno + 1)
    async for m in db["estratto_conto_movimenti"].find(
        {"$or": [
             *({"data": {"$regex": f"^{anno_movimento}"}} for anno_movimento in anni_movimenti),
             *({"data_contabile": {"$regex": f"/{anno_movimento}$"}} for anno_movimento in anni_movimenti),
         ]},
        {
            "_id": 0, "id": 1, "importo": 1, "descrizione": 1,
            "descrizione_originale": 1, "data": 1, "data_contabile": 1,
            "tipo": 1, "type": 1, "riconciliato": 1,
            "fattura_id": 1, "invoice_id": 1, "fattura_ids": 1,
            "assegno_id": 1, "assegno_numero": 1,
        }
    ):
        movimenti_anno.append(m)
        tipo = str(m.get("tipo") or m.get("type") or "").lower()
        if tipo != "uscita":
            continue
        imp = round(abs(float(m.get("importo", 0))), 2)
        if imp not in movimenti_banca:
            movimenti_banca[imp] = []
        movimenti_banca[imp].append(m)
    
    # Carica metodo pagamento per fornitore (da anagrafica fornitori).
    # NB: i fornitori storici hanno la P.IVA in "piva" o "vat_number", non
    # solo in "partita_iva" — vanno letti tutti, altrimenti il metodo
    # impostato in scheda fornitore NON viene rispettato.
    metodo_per_piva = {}
    esclusi_cassa_banca = set()
    async for s in db["fornitori"].find(
        {},
        {"_id": 0, "partita_iva": 1, "piva": 1, "vat_number": 1,
         "metodo_pagamento": 1, "esclude_cassa_banca": 1, "cessato": 1}
    ):
        metodo = s.get("metodo_pagamento", "")
        for k in (s.get("partita_iva"), s.get("piva"), s.get("vat_number")):
            if not k:
                continue
            chiave = str(k).strip()
            if metodo:
                metodo_per_piva[chiave] = metodo
            if s.get("esclude_cassa_banca") or s.get("cessato"):
                esclusi_cassa_banca.add(chiave)

    provvisori = []
    totale_escluse_cassa_banca = 0
    for f in fatture:
        totale_fattura = float(
            f.get("total_amount") or f.get("importo_totale") or 0
        )
        importo_pagato_confermato = float(
            f.get("_importo_pagato_confermato") or 0
        )
        importo = float(
            f.get("_importo_residuo")
            if f.get("_importo_residuo") is not None
            else totale_fattura
        )
        metodo_xml = f.get("payment_method", "")
        metodo_code = f.get("payment_method_code", "")
        piva = (f.get("supplier_vat") or f.get("cedente_piva") or "").strip()

        # Fuori dal flusso finanziario, non fuori da contabilita'/IVA.
        if f.get("esclusa_da_cassa_banca") or piva in esclusi_cassa_banca:
            totale_escluse_cassa_banca += 1
            continue
        
        assegni_collegati = [
            link for link in (f.get("assegni_collegati") or []) if isinstance(link, dict)
        ]
        assegno_specifico = (
            f.get("metodo_pagamento_previsto") == "assegno"
            or f.get("metodo_pagamento_override_source") == "assegno_compilato"
            or bool(assegni_collegati)
        )
        metodo_previsto_fattura = normalizza_metodo_pagamento(
            f.get("metodo_pagamento_previsto")
        )
        fonte_metodo = "fornitore"
        stato_pag = f.get("stato_pagamento", "")

        # PRIORITÀ 0: la scelta esplicita sulla singola fattura prevale sul
        # metodo abituale del fornitore, anche se cassa o misto.
        if (
            str(f.get("metodo_pagamento_previsto") or "").lower() == "da_decidere"
            and f.get("metodo_pagamento_override_source") == "operatore_prima_nota"
        ):
            suggerimento = "sospesa"
            stato_match = "in_attesa"
            fonte_metodo = "operatore_prima_nota"
        elif assegno_specifico:
            suggerimento = "banca"
            stato_match = "in_attesa_estratto_conto"
            fonte_metodo = "assegno_compilato"
        # Una scelta esplicita dell'operatore sulla singola fattura stabilisce
        # soltanto il canale ATTESO. Non prova il pagamento e non crea una riga
        # in Prima Nota Banca: quella nascera' esclusivamente dalla
        # riconciliazione con un movimento reale dell'estratto conto.
        elif (
            metodo_previsto_fattura == "banca"
            and f.get("metodo_pagamento_override_source") == "operatore_prima_nota"
        ):
            suggerimento = "banca"
            stato_match = "in_attesa_estratto_conto"
            fonte_metodo = "operatore_prima_nota"
        # PRIORITÀ 1: Se la fattura è stata marcata come sospesa dall'utente
        elif stato_pag == "sospesa":
            suggerimento = "sospesa"
            stato_match = "in_attesa"
        # PRIORITÀ 2: Metodo dal fornitore in anagrafica, con la
        # STESSA classificazione usata dal job automatico (classifica_metodo_fornitore)
        # REGOLA: il metodo XML della fattura NON viene MAI usato
        else:
            suggerimento = classifica_metodo_fornitore(metodo_per_piva.get(piva, ""))
            stato_match = "confermato" if suggerimento != "sospesa" else "in_attesa"
        
        # Se banca: cerca INTELLIGENTEMENTE nell'estratto conto
        movimento_match = None
        evidenza_banca = None
        if suggerimento == "banca":
            from app.services.riconciliazione_bancaria import (
                _evidenza_forte_fattura_banca,
                _evidenza_pagamento_fornitore_banca,
                _evidenza_sdd_fattura_banca,
                classifica_strumento_bancario,
            )

            candidati = [
                movimento
                for movimento in movimenti_banca.get(round(importo, 2), [])
                if _movimento_non_consumato_da_altra_fattura(
                    movimento, str(f.get("id") or ""),
                )
            ]
            candidati_forti = []
            for m in candidati:
                descrizione = m.get("descrizione_originale") or m.get("descrizione") or ""
                data_movimento = m.get("data") or m.get("data_contabile") or ""
                forte = _evidenza_forte_fattura_banca(f, descrizione, importo)
                sdd = _evidenza_sdd_fattura_banca(
                    f, descrizione, importo, data_movimento,
                )
                pagamento_diretto = _evidenza_pagamento_fornitore_banca(
                    f, descrizione, importo, data_movimento,
                )
                if forte.get("auto_ammesso"):
                    candidati_forti.append((m, "identita_fattura_importo"))
                elif sdd.get("auto_ammesso"):
                    candidati_forti.append((m, "sdd_fornitore_importo_data"))
                elif pagamento_diretto.get("auto_ammesso"):
                    candidati_forti.append((m, "strumento_fornitore_importo_data"))

            # Il solo importo non identifica il pagamento. Inoltre, se due
            # movimenti hanno la stessa evidenza, il caso resta ambiguo.
            if len(candidati_forti) == 1:
                movimento_match, evidenza_banca = candidati_forti[0]
                stato_match = "riscontro_forte_in_elaborazione"
            elif len(candidati_forti) > 1:
                netto = _rimborso_duplica_pagamento(
                    f, candidati_forti, movimenti_anno, importo,
                )
                if netto:
                    movimento_match, evidenza_banca = netto
                    stato_match = "riscontro_forte_in_elaborazione"
        
        provvisori.append({
            "fattura_id": f.get("id"),
            "fattura_numero": (
                f.get("invoice_number") or f.get("numero_fattura") or ""
            ),
            "fattura_data": (
                f.get("invoice_date") or f.get("data_documento")
                or f.get("data_fattura") or ""
            ),
            "fornitore": (
                f.get("supplier_name") or f.get("cedente_denominazione") or ""
            ),
            "fornitore_piva": (
                f.get("supplier_vat") or f.get("cedente_piva") or ""
            ),
            "dati_ddt": _arricchisci_distanza_ddt(
                ddt_per_fattura.get(str(f.get("id")), []),
                f.get("invoice_date") or f.get("data_documento") or f.get("data_fattura"),
            ),
            "anomalia_pagamento": f.get("anomalia_pagamento"),
            "importo": importo,
            "totale_fattura": totale_fattura,
            "totale_pagabile_fornitore": f.get("_totale_pagabile_fornitore", totale_fattura),
            "ritenuta_non_pagabile_fornitore": f.get("_ritenuta_non_pagabile_fornitore", 0),
            "importo_pagato_confermato": importo_pagato_confermato,
            "importo_residuo": importo,
            "metodo_xml": metodo_xml,
            "metodo_pagamento_previsto": f.get("metodo_pagamento_previsto"),
            "fonte_metodo": fonte_metodo,
            "assegno_numero": (
                assegni_collegati[0].get("numero") if assegni_collegati else None
            ),
            "suggerimento": suggerimento,
            "stato_match": stato_match,
            "evidenza_banca": evidenza_banca,
            "strumento_bancario": (
                classifica_strumento_bancario(
                    movimento_match.get("descrizione_originale")
                    or movimento_match.get("descrizione") or ""
                ) if movimento_match else None
            ),
            "motivo_sospensione": None,
            "movimento_banca": {
                "data": (movimento_match.get("data") or movimento_match.get("data_contabile", "")) if movimento_match else None,
                "descrizione": (
                    movimento_match.get("descrizione_originale")
                    or movimento_match.get("descrizione", "")
                )[:80] if movimento_match else None,
                "id": movimento_match.get("id") if movimento_match else None,
            } if movimento_match else None,
        })

    # La scansione parte dalle fatture: due documenti dello stesso fornitore
    # e dello stesso importo possono quindi rivendicare la stessa RiBa. La
    # decisione viene resa globale prima di mostrarla: una prova con numero
    # fattura prevale su quella generica; due prove dello stesso livello
    # restano sospese e mostrano il motivo, senza scegliere per ordine DB.
    _risolvi_rivendicazioni_movimenti(provvisori)

    # Un assegno puo' saldare piu' fatture dello stesso fornitore. La prova
    # viene mostrata soltanto quando esiste una sola combinazione globale di
    # 2..4 fatture dello stesso lotto (fornitore + data documento) la cui
    # somma coincide al centesimo con un assegno ancora privo di fatture.
    # In questo modo il caso SIRO 12/06 (tre fatture = EUR 1.082,52) emerge,
    # mentre due assegni uguali e due fatture uguali restano ambigui.
    gruppi = {}
    for item in provvisori:
        if item.get("suggerimento") != "banca" or item.get("movimento_banca"):
            continue
        chiave_fornitore = (
            str(item.get("fornitore_piva") or "").strip()
            or re.sub(r"\W", "", str(item.get("fornitore") or "").upper())
        )
        chiave = (chiave_fornitore, str(item.get("fattura_data") or "")[:10])
        if chiave_fornitore and chiave[1]:
            gruppi.setdefault(chiave, []).append(item)

    for movimento in (
        m for m in movimenti_anno
        if str(m.get("tipo") or m.get("type") or "").lower() == "uscita"
        and not (m.get("fattura_id") or m.get("invoice_id") or m.get("fattura_ids"))
        and re.search(
            r"(?:PRELIEVO|VOSTRO).*ASSEGNO",
            str(m.get("descrizione") or m.get("descrizione_originale") or ""),
            re.IGNORECASE,
        )
    ):
        importo_movimento = round(abs(float(movimento.get("importo") or 0)), 2)
        try:
            data_movimento_dt = datetime.fromisoformat(
                str(movimento.get("data") or movimento.get("data_contabile") or "")[:10]
            )
        except ValueError:
            continue
        combinazioni_trovate = []
        for (_fornitore, data_lotto), righe in gruppi.items():
            try:
                data_lotto_dt = datetime.fromisoformat(data_lotto)
            except ValueError:
                continue
            giorni = (data_movimento_dt - data_lotto_dt).days
            if giorni < -7 or giorni > 90:
                continue
            for numero_righe in range(2, min(4, len(righe)) + 1):
                for combo in combinations(righe, numero_righe):
                    if round(sum(float(riga.get("importo") or 0) for riga in combo), 2) == importo_movimento:
                        combinazioni_trovate.append(combo)
        if len(combinazioni_trovate) != 1:
            continue
        combo = combinazioni_trovate[0]
        evidenza = {
            "tipo": "assegno_cumulativo_lotto_fatture",
            "fatture_ids": [riga["fattura_id"] for riga in combo],
            "somma": importo_movimento,
        }
        for riga in combo:
            riga["stato_match"] = "riscontro_forte_in_elaborazione"
            riga["evidenza_banca"] = evidenza
            riga["movimento_banca"] = {
                "data": movimento.get("data") or movimento.get("data_contabile"),
                "descrizione": (
                    movimento.get("descrizione_originale")
                    or movimento.get("descrizione") or ""
                )[:80],
                "id": movimento.get("id"),
            }

    # Sequenza 1:1 per assegni senza beneficiario: se per uno stesso importo
    # esistono N assegni bancari liberi e N sole fatture aperte, tutte dello
    # stesso fornitore, l'ordine cronologico rende l'abbinamento determinato.
    # Esempio reale: due fatture KIMBO da EUR 1.498,96 e due assegni successivi
    # dello stesso importo. Una cardinalita' diversa o un secondo fornitore
    # lascia invece il caso in attesa.
    assegni_liberi_per_importo = {}
    for movimento in movimenti_anno:
        descrizione = str(
            movimento.get("descrizione") or movimento.get("descrizione_originale") or ""
        )
        if (
            str(movimento.get("tipo") or movimento.get("type") or "").lower() != "uscita"
            or movimento.get("fattura_id") or movimento.get("invoice_id")
            or movimento.get("fattura_ids")
            or not re.search(r"(?:PRELIEVO|VOSTRO).*ASSEGNO", descrizione, re.IGNORECASE)
        ):
            continue
        assegni_liberi_per_importo.setdefault(
            round(abs(float(movimento.get("importo") or 0)), 2), []
        ).append(movimento)

    fatture_libere_per_importo = {}
    for riga in provvisori:
        if riga.get("suggerimento") == "banca" and not riga.get("movimento_banca"):
            fatture_libere_per_importo.setdefault(
                round(float(riga.get("importo") or 0), 2), []
            ).append(riga)

    for importo, righe in fatture_libere_per_importo.items():
        movimenti = assegni_liberi_per_importo.get(importo, [])
        if len(righe) < 2 or len(movimenti) != len(righe):
            continue
        fornitori = {
            str(riga.get("fornitore_piva") or "").strip()
            or re.sub(r"\W", "", str(riga.get("fornitore") or "").upper())
            for riga in righe
        }
        if len(fornitori) != 1 or not next(iter(fornitori), ""):
            continue
        righe_ordinate = sorted(righe, key=lambda r: (str(r.get("fattura_data") or ""), r["fattura_id"]))
        movimenti_ordinati = sorted(
            movimenti,
            key=lambda m: (str(m.get("data") or m.get("data_contabile") or ""), str(m.get("id") or "")),
        )
        coppie = []
        for riga, movimento in zip(righe_ordinate, movimenti_ordinati):
            try:
                data_fattura = datetime.fromisoformat(str(riga.get("fattura_data") or "")[:10])
                data_movimento = datetime.fromisoformat(
                    str(movimento.get("data") or movimento.get("data_contabile") or "")[:10]
                )
            except ValueError:
                coppie = []
                break
            if not -7 <= (data_movimento - data_fattura).days <= 90:
                coppie = []
                break
            coppie.append((riga, movimento))
        if len(coppie) != len(righe):
            continue
        for riga, movimento in coppie:
            riga["stato_match"] = "riscontro_forte_in_elaborazione"
            riga["evidenza_banca"] = {
                "tipo": "sequenza_assegni_fatture_stesso_fornitore_importo",
                "cardinalita": len(coppie),
            }
            riga["movimento_banca"] = {
                "data": movimento.get("data") or movimento.get("data_contabile"),
                "descrizione": (
                    movimento.get("descrizione_originale")
                    or movimento.get("descrizione") or ""
                )[:80],
                "id": movimento.get("id"),
            }
    
    # Nessuna auto-conferma automatica: il "pagamento certo" è stato rimosso
    # perché il sistema non può sapere con certezza dove imputare il
    # pagamento di una fattura solo dal metodo impostato in anagrafica — vedi
    # memoria/moduli/FATTURE_RICEVUTE.md. Il metodo fornitore resta solo un
    # SUGGERIMENTO (cassa/banca/sospesa): ogni fattura resta in provvisorio
    # fino a conferma manuale dell'utente.
    auto_confermati = 0

    # RICHIESTA UTENTE 18/07/2026 ("tu sai quali fornitori si pagano per
    # banca: perché li metti in provvisori?"): le fatture di fornitori a
    # metodo BANCA non sono decisioni da prendere — aspettano solo
    # l'addebito in estratto conto (la riconciliazione oraria le registra
    # da sola). Vanno in una lista separata "in attesa banca", fuori dal
    # conteggio dei provvisori da lavorare.
    in_attesa_banca = [p for p in provvisori if p["suggerimento"] == "banca"]
    provvisori_finali = [p for p in provvisori if p["suggerimento"] != "banca"]

    # Registro completo: la Provvisoria deve distinguere cio' che richiede
    # un'azione da cio' che e' gia' stato registrato, senza far sparire le
    # fatture. La vista e' di sola lettura per i documenti gia' saldati e usa
    # le stesse prove contabili che governano i contatori Cassa/Banca.
    aperte_per_id = {
        str(fattura.get("id") or fattura.get("invoice_key") or ""): fattura
        for fattura in fatture
    }
    azione_per_id = {
        str(item.get("fattura_id") or ""): item for item in provvisori
    }
    etichette_stato = {
        "da_decidere": "Da decidere",
        "anomalia_pagamento": "Metodo da verificare",
        "in_attesa_banca": "Attesa banca",
        "parziale_cassa": "Parziale: quota in Cassa",
        "parziale_banca": "Parziale: quota in Banca",
        "parziale_mista": "Parziale: Cassa e Banca",
        "registrata_cassa": "Registrata in Cassa",
        "registrata_banca": "Registrata in Banca",
        "registrata_mista": "Registrata tra Cassa e Banca",
        "esclusa_flusso_finanziario": "Esclusa dal flusso Cassa/Banca",
        "registrata_origine_da_verificare": "Registrata: origine da verificare",
    }
    tutte_fatture = []
    for documento in fatture_tutte:
        fattura_id = str(documento.get("id") or documento.get("invoice_key") or "")
        aperta = aperte_per_id.get(fattura_id)
        azione = azione_per_id.get(fattura_id)
        riepilogo = pagamenti_per_fattura.get(fattura_id, {})
        totale_fattura = abs(float(
            documento.get("total_amount") or documento.get("importo_totale") or 0
        ))
        totale_pagabile = totale_pagabile_al_fornitore(documento)
        pagato_confermato = round(
            float(riepilogo.get("cassa_importo") or 0)
            + float(riepilogo.get("banca_importo") or 0),
            2,
        )
        if aperta is not None:
            pagato_confermato = round(float(
                aperta.get("_importo_pagato_confermato") or pagato_confermato
            ), 2)
            residuo = round(float(
                aperta.get("_importo_residuo")
                if aperta.get("_importo_residuo") is not None
                else max(totale_pagabile - pagato_confermato, 0)
            ), 2)
        else:
            # I movimenti storici senza importo sono comunque prova di una
            # registrazione completa; mostriamo il totale pagabile senza
            # alterare il documento o creare nuove scritture.
            if pagato_confermato <= 0 and (
                riepilogo.get("cassa_presente") or riepilogo.get("banca_presente")
            ):
                pagato_confermato = totale_pagabile
            residuo = 0.0

        piva = str(
            documento.get("supplier_vat") or documento.get("cedente_piva") or ""
        ).strip()
        esclusa = bool(
            documento.get("esclusa_da_cassa_banca") or piva in esclusi_cassa_banca
        )
        cassa = bool(riepilogo.get("cassa_presente"))
        banca = bool(riepilogo.get("banca_presente"))
        if aperta is not None and esclusa:
            stato = "esclusa_flusso_finanziario"
        elif aperta is not None and pagato_confermato > 0:
            stato = "parziale_mista" if cassa and banca else (
                "parziale_banca" if banca else "parziale_cassa"
            )
        elif aperta is not None and azione:
            if (azione.get("anomalia_pagamento") or {}).get("stato") == "aperta":
                stato = "anomalia_pagamento"
            elif azione.get("suggerimento") == "banca":
                stato = "in_attesa_banca"
            else:
                stato = "da_decidere"
        elif aperta is not None:
            stato = "da_decidere"
        elif cassa and banca:
            stato = "registrata_mista"
        elif banca:
            stato = "registrata_banca"
        elif cassa:
            stato = "registrata_cassa"
        else:
            stato = "registrata_origine_da_verificare"

        data_fattura = (
            documento.get("invoice_date") or documento.get("data_documento")
            or documento.get("data_fattura") or ""
        )
        tutte_fatture.append({
            "fattura_id": fattura_id,
            "fattura_numero": (
                documento.get("invoice_number") or documento.get("numero_fattura") or ""
            ),
            "fattura_data": data_fattura,
            "fornitore": (
                documento.get("supplier_name") or documento.get("cedente_denominazione") or ""
            ),
            "fornitore_piva": piva,
            "totale_fattura": round(totale_fattura, 2),
            "totale_pagabile_fornitore": round(totale_pagabile, 2),
            "importo_pagato_confermato": round(pagato_confermato, 2),
            "importo_residuo": round(residuo, 2),
            "importo": round(residuo if aperta is not None else totale_pagabile, 2),
            "stato": stato,
            "stato_label": etichette_stato[stato],
            "stato_ddt": stato_ddt_per_fattura.get(
                fattura_id, "xml_non_disponibile"
            ),
            "dati_ddt": _arricchisci_distanza_ddt(
                ddt_per_fattura.get(fattura_id, []), data_fattura,
            ),
            "anomalia_pagamento": documento.get("anomalia_pagamento"),
            "movimenti_prima_nota": riepilogo.get("movimenti") or [],
            "richiede_azione": aperta is not None and not esclusa,
        })

    tot_cassa = sum(p["importo"] for p in provvisori_finali if p["suggerimento"] == "cassa")
    tot_banca = sum(p["importo"] for p in in_attesa_banca)

    return {
        "provvisori": provvisori_finali,
        "in_attesa_banca": in_attesa_banca,
        "tutte_fatture": tutte_fatture,
        "totale": len(provvisori),
        "totale_da_decidere": len(provvisori_finali),
        "totale_in_attesa_banca": len(in_attesa_banca),
        "totale_cassa": round(tot_cassa, 2),
        "totale_banca": round(tot_banca, 2),
        "confermati": sum(1 for p in provvisori_finali if p["stato_match"] == "confermato"),
        "probabili": sum(1 for p in provvisori_finali if p["stato_match"] == "probabile"),
        "in_attesa": sum(1 for p in provvisori_finali if p["stato_match"] == "in_attesa"),
        "auto_confermati_banca": auto_confermati,
        "completezza": {
            "anno": anno,
            "fatture_attive_positive": totale_fatture_attive,
            "gia_registrate_pagamento_completo": totale_gia_registrate,
            "aperte_prima_delle_esclusioni": totale_fatture_aperte,
            "escluse_cassa_banca": totale_escluse_cassa_banca,
            "aperte_mostrate": len(provvisori),
            "tutte_visibili": len(tutte_fatture),
        },
    }


async def imposta_fattura_in_attesa_banca(data: Dict = Body(...)) -> Dict:
    """Imposta il canale bancario previsto senza registrare un pagamento.

    Body: {fattura_id, performed_by?}. La fattura resta aperta e viene mostrata
    tra i pagamenti in attesa banca. Solo una successiva riconciliazione con
    una riga reale dell'estratto conto potra' creare la scrittura bancaria.
    """
    db = Database.get_db()
    fattura_id = data.get("fattura_id")
    if not fattura_id:
        raise HTTPException(status_code=400, detail="Fattura obbligatoria")

    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    fatture_aperte = await fatture_senza_pagamento_contabile_confermato(
        db, [fattura]
    )
    if not fatture_aperte:
        raise HTTPException(
            status_code=409,
            detail=(
                "La fattura ha gia' un pagamento contabile completo. "
                "Ricarica Prima Nota e verifica la scrittura esistente."
            ),
        )
    fattura = fatture_aperte[0]

    now_iso = datetime.now(timezone.utc).isoformat()
    campi_attesa = {
        "metodo_pagamento_previsto": "banca",
        "metodo_pagamento_override_source": "operatore_prima_nota",
        "stato_pagamento": "in_attesa_banca",
        "stato_finanziario": "aperta_in_attesa_banca",
        "pagato": False,
        "paid": False,
        "updated_at": now_iso,
    }
    if (fattura.get("anomalia_pagamento") or {}).get("stato") == "aperta":
        campi_attesa["anomalia_pagamento"] = {
            **fattura["anomalia_pagamento"],
            "stato": "risolta",
            "risolta_il": now_iso,
            "risolta_da": str(data.get("performed_by") or "operatore"),
            "esito": "banca",
        }
    await db["invoices"].update_one(
        {"id": fattura_id},
        {
            "$set": campi_attesa,
            "$unset": {
                "prima_nota_id": "",
                "prima_nota_banca_id": "",
                "data_pagamento": "",
            },
        },
    )

    try:
        from app.services.audit_logger import log_evento
        await log_evento(
            modulo="prima_nota",
            azione="imposta_attesa_banca",
            entita_id=fattura_id,
            entita_collection="invoices",
            db=db,
            nuovo_stato={
                "metodo_pagamento_previsto": "banca",
                "stato_finanziario": "aperta_in_attesa_banca",
                "pagato": False,
            },
            fonte="prima_nota_provvisori",
            utente=str(data.get("performed_by") or "operatore"),
        )
    except Exception:
        logger.exception("Audit impostazione attesa banca fallito")

    return {
        "success": True,
        "fattura_id": fattura_id,
        "stato": "in_attesa_banca",
        "pagato": False,
        "message": (
            "Fattura spostata tra i pagamenti attesi in banca. "
            "La Prima Nota Banca sara' aggiornata solo dopo la riconciliazione."
        ),
    }


async def riporta_fattura_da_decidere(data: Dict = Body(...)) -> Dict:
    """Corregge una classificazione automatica senza inventare pagamenti."""
    db = Database.get_db()
    fattura_id = data.get("fattura_id")
    if not fattura_id:
        raise HTTPException(status_code=400, detail="Fattura obbligatoria")
    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    fatture_aperte = await fatture_senza_pagamento_contabile_confermato(
        db, [fattura]
    )
    if not fatture_aperte:
        raise HTTPException(
            status_code=409,
            detail="La fattura ha gia' un pagamento contabile completo.",
        )
    fattura = fatture_aperte[0]
    now_iso = datetime.now(timezone.utc).isoformat()
    await db["invoices"].update_one(
        {"id": fattura_id},
        {"$set": {
            "metodo_pagamento_previsto": "da_decidere",
            "metodo_pagamento_override_source": "operatore_prima_nota",
            "stato_pagamento": "da_decidere",
            "stato_finanziario": "aperta_da_decidere",
            "pagato": False,
            "paid": False,
            "updated_at": now_iso,
        }, "$unset": {
            "prima_nota_id": "",
            "prima_nota_banca_id": "",
            "data_pagamento": "",
        }},
    )

    numero = (
        fattura.get("invoice_number") or fattura.get("numero_fattura")
        or "senza numero"
    )
    data_fattura = (
        fattura.get("invoice_date") or fattura.get("data_documento")
        or fattura.get("data_fattura") or "data non disponibile"
    )
    fornitore = (
        fattura.get("supplier_name") or fattura.get("cedente_denominazione")
        or "fornitore non disponibile"
    )
    importo = round(abs(float(
        fattura.get("_importo_residuo")
        if fattura.get("_importo_residuo") is not None
        else fattura.get("total_amount") or fattura.get("importo_totale") or 0
    )), 2)
    importo_it = f"{importo:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    riferimento = {
        "id": fattura_id,
        "numero": str(numero),
        "data": str(data_fattura),
        "fornitore": str(fornitore),
        "importo": importo,
    }

    try:
        from app.services.audit_logger import log_evento
        await log_evento(
            modulo="prima_nota",
            azione="riporta_da_decidere",
            entita_id=fattura_id,
            entita_collection="invoices",
            db=db,
            vecchio_stato={
                "metodo_pagamento_previsto": fattura.get("metodo_pagamento_previsto"),
                "stato_pagamento": fattura.get("stato_pagamento"),
                "stato_finanziario": fattura.get("stato_finanziario"),
            },
            nuovo_stato={
                "metodo_pagamento_previsto": "da_decidere",
                "stato_pagamento": "da_decidere",
                "stato_finanziario": "aperta_da_decidere",
                "pagato": False,
            },
            fonte="prima_nota_provvisori",
            utente=str(data.get("performed_by") or "operatore"),
            extra={"fattura": riferimento},
        )
    except Exception:
        logger.exception("Audit ritorno fattura da decidere fallito")

    return {
        "success": True,
        "fattura_id": fattura_id,
        "stato": "da_decidere",
        "pagato": False,
        "fattura": riferimento,
        "message": (
            f"Fattura {numero} di {fornitore}, del {data_fattura}, "
            f"EUR {importo_it}, riportata in Da decidere. "
            "Ora puoi scegliere Cassa, Banca o Parziale."
        ),
    }


async def segnala_dubbio_pagamento(data: Dict = Body(...)) -> Dict[str, Any]:
    """Marca una fattura aperta come anomalia senza creare o cancellare pagamenti."""
    db = Database.get_db()
    fattura_id = str(data.get("fattura_id") or "").strip()
    nota = str(data.get("nota") or "").strip()[:500]
    if not fattura_id:
        raise HTTPException(status_code=400, detail="Fattura obbligatoria")
    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    aperte = await fatture_senza_pagamento_contabile_confermato(db, [fattura])
    if not aperte:
        raise HTTPException(
            status_code=409,
            detail="La fattura ha gia' un pagamento contabile completo: verifica la riga in Cassa o Banca.",
        )

    fattura = aperte[0]
    now_iso = datetime.now(timezone.utc).isoformat()
    anomalia = {
        "tipo": "metodo_pagamento_incerto",
        "stato": "aperta",
        "segnalata_il": now_iso,
        "segnalata_da": str(data.get("performed_by") or "operatore"),
        "nota": nota,
        "stato_precedente": {
            "metodo_pagamento_previsto": fattura.get("metodo_pagamento_previsto"),
            "stato_pagamento": fattura.get("stato_pagamento"),
            "stato_finanziario": fattura.get("stato_finanziario"),
        },
    }
    await db["invoices"].update_one({"id": fattura_id}, {"$set": {
        "metodo_pagamento_previsto": "da_decidere",
        "metodo_pagamento_override_source": "operatore_prima_nota",
        "metodo_pagamento_override_at": now_iso,
        "stato_pagamento": "da_decidere",
        "stato_finanziario": "anomalia_metodo_pagamento",
        "anomalia_pagamento": anomalia,
        "pagato": False,
        "paid": False,
        "updated_at": now_iso,
    }})

    numero = fattura.get("invoice_number") or fattura.get("numero_fattura") or "senza numero"
    fornitore = fattura.get("supplier_name") or fattura.get("cedente_denominazione") or "fornitore non disponibile"
    try:
        from app.services.audit_logger import log_evento
        await log_evento(
            modulo="prima_nota",
            azione="segnala_dubbio_pagamento",
            entita_id=fattura_id,
            entita_collection="invoices",
            db=db,
            vecchio_stato=anomalia["stato_precedente"],
            nuovo_stato={
                "metodo_pagamento_previsto": "da_decidere",
                "stato_pagamento": "da_decidere",
                "stato_finanziario": "anomalia_metodo_pagamento",
                "anomalia_pagamento": anomalia,
            },
            fonte="prima_nota_provvisori",
            utente=anomalia["segnalata_da"],
            extra={"fattura_numero": numero, "fornitore": fornitore},
        )
    except Exception:
        logger.exception("Audit dubbio pagamento fallito")

    return {
        "success": True,
        "fattura_id": fattura_id,
        "fattura_numero": numero,
        "fornitore": fornitore,
        "anomalia_pagamento": anomalia,
        "message": (
            f"Anomalia aperta sulla fattura {numero} di {fornitore}: "
            "il metodo di pagamento deve essere verificato."
        ),
    }


async def conferma_fattura_provvisoria(data: Dict = Body(...)) -> Dict:
    """
    Conferma una fattura provvisoria: registra in Prima Nota cassa/banca.
    Body: { fattura_id, metodo: "cassa"|"banca"|"sospesa", movimento_banca_id? }
    """
    db = Database.get_db()
    
    fattura_id = data.get("fattura_id")
    metodo = data.get("metodo", "banca")
    
    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    fatture_aperte = await fatture_senza_pagamento_contabile_confermato(
        db, [fattura]
    )
    if not fatture_aperte:
        raise HTTPException(
            status_code=409,
            detail=(
                "La fattura ha gia' un pagamento contabile completo. "
                "Ricarica Prima Nota e verifica la scrittura esistente."
            ),
        )
    fattura = fatture_aperte[0]

    importo_gia_pagato = round(float(
        fattura.get("_importo_pagato_confermato") or 0
    ), 2)
    if metodo == "cassa" and importo_gia_pagato > 0.01:
        raise HTTPException(
            status_code=409,
            detail=(
                "La fattura ha gia' un pagamento parziale confermato. "
                "Il residuo non puo' essere chiuso riutilizzando la stessa "
                "scrittura Cassa: attendi e riconcilia il movimento bancario."
            ),
        )

    piva_fornitore = fattura.get("supplier_vat") or fattura.get("cedente_piva")
    esclusa = bool(fattura.get("esclusa_da_cassa_banca"))
    if piva_fornitore and not esclusa:
        esclusa = bool(await db[Collections.SUPPLIERS].find_one(
            {"$and": [
                {"$or": [
                    {"partita_iva": piva_fornitore}, {"piva": piva_fornitore},
                    {"vat_number": piva_fornitore},
                ]},
                {"$or": [{"esclude_cassa_banca": True}, {"cessato": True}]},
            ]},
            {"_id": 0, "id": 1},
        ))
    if esclusa:
        raise HTTPException(
            status_code=409,
            detail=(
                "Fattura esclusa da Cassa e Banca. Resta conservata e "
                "conteggiata ai fini contabili e IVA."
            ),
        )
    
    totale_fattura = abs(float(
        fattura.get("total_amount") or fattura.get("importo_totale") or 0
    ))
    importo = float(
        fattura.get("_importo_residuo")
        if fattura.get("_importo_residuo") is not None
        else totale_fattura
    )
    fornitore = fattura.get("supplier_name", "")
    data_fatt = fattura.get("invoice_date", "")
    
    # SOSPESA: non creare movimento in prima nota, solo aggiorna stato fattura
    if metodo == "sospesa":
        await db["invoices"].update_one(
            {"id": fattura_id},
            {"$set": {
                "stato_pagamento": "sospesa",
                "metodo_pagamento_effettivo": "sospesa",
                "prima_nota_tipo": "sospesa",
            },
            "$unset": {
                "prima_nota_id": "",
            }}
        )
        return {"success": True, "metodo": "sospesa", "importo": importo, "fornitore": fornitore,
                "message": "Fattura sospesa — resta nei provvisori"}
    
    rate_xml = fattura.get("pagamento_rate") or []
    if len(rate_xml) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                f"La fattura contiene {len(rate_xml)} rate XML. Il totale documento non puo' "
                "essere registrato come pagamento unico senza evidenza: collega e conferma "
                "i singoli assegni o movimenti bancari."
            ),
        )

    if metodo not in {"cassa", "banca"}:
        raise HTTPException(status_code=400, detail="Metodo non valido")

    # La conferma non cambia di nascosto il metodo configurato. Per la Cassa
    # e' valida una regola gia' approvata nella scheda fornitore/fattura oppure
    # la conferma esplicita dell'operatore per questa singola fattura. Questo
    # override resta sulla fattura e non modifica il metodo del fornitore.
    metodo_previsto = (
        fattura.get("metodo_pagamento_effettivo")
        or fattura.get("metodo_pagamento_fornitore")
        or fattura.get("payment_method")
        or fattura.get("metodo_pagamento")
    )
    if piva_fornitore:
        supplier = await db[Collections.SUPPLIERS].find_one(
            {"$or": [
                {"partita_iva": piva_fornitore},
                {"piva": piva_fornitore},
                {"vat_number": piva_fornitore},
            ]},
            {"_id": 0, "metodo_pagamento": 1, "metodo_pagamento_predefinito": 1},
        )
        if supplier:
            metodo_previsto = (
                supplier.get("metodo_pagamento_predefinito")
                or supplier.get("metodo_pagamento")
                or metodo_previsto
            )

    approvazione_cassa_esplicita = data.get("approva_metodo_fattura") is True
    if (
        metodo == "cassa"
        and normalizza_metodo_pagamento(metodo_previsto) != "cassa"
        and not approvazione_cassa_esplicita
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "La fattura puo' essere registrata in Cassa solo se il metodo "
                "approvato del fornitore/fattura e' Cassa oppure se confermi "
                "esplicitamente il pagamento in contanti per questa fattura."
            ),
        )

    # Per Banca e' obbligatoria una riga reale dell'estratto conto. Metodo
    # fornitore, rate XML, assegno emesso e proposte AI non provano il pagamento.
    movimento_bancario = None
    if metodo == "banca":
        evidenza_id = data.get("movimento_banca_id") or data.get("estratto_conto_id")
        if not evidenza_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Pagamento bancario non dimostrato: collega una riga reale "
                    "dell'estratto conto. La fattura resta provvisoria."
                ),
            )
        movimento_bancario = await db["estratto_conto_movimenti"].find_one(
            {"id": evidenza_id}, {"_id": 0}
        )
        if not movimento_bancario:
            raise HTTPException(status_code=404, detail="Movimento di estratto conto non trovato")
        collegata_a = movimento_bancario.get("fattura_id") or movimento_bancario.get("documento_id")
        if collegata_a and str(collegata_a) != str(fattura_id):
            raise HTTPException(
                status_code=409,
                detail="Il movimento bancario e' gia' collegato a un altro documento",
            )
        importo_evidenza = abs(float(
            movimento_bancario.get("importo")
            or movimento_bancario.get("amount")
            or movimento_bancario.get("uscite")
            or 0
        ))
        if abs(importo_evidenza - abs(importo)) > 0.01:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Importo estratto conto ({importo_evidenza:.2f}) diverso dal "
                    f"totale fattura ({abs(importo):.2f}). Usa la riconciliazione "
                    "multipla se il movimento paga piu' fatture."
                ),
            )
        movimento_bancario = {
            **movimento_bancario,
            "match_score": float(movimento_bancario.get("confidenza") or 1.0),
        }

    claim_token = await _acquisisci_claim_pagamento(
        db, fattura_id, f"conferma_{metodo}"
    )
    try:
        # La decisione viene ricalcolata dopo il claim. In questo modo un
        # doppio click o due operatori non possono usare lo stesso residuo.
        fattura_corrente = await db["invoices"].find_one(
            {"id": fattura_id}, {"_id": 0}
        )
        fatture_aperte = await fatture_senza_pagamento_contabile_confermato(
            db, [fattura_corrente]
        )
        if not fatture_aperte:
            raise HTTPException(
                status_code=409,
                detail=(
                    "La fattura e' gia' stata registrata. Ricarica Prima Nota "
                    "prima di eseguire altre operazioni."
                ),
            )
        fattura = fatture_aperte[0]
        importo_gia_pagato = round(float(
            fattura.get("_importo_pagato_confermato") or 0
        ), 2)
        if metodo == "cassa" and importo_gia_pagato > 0.01:
            raise HTTPException(
                status_code=409,
                detail=(
                    "La fattura ha gia' un pagamento parziale confermato. "
                    "Il residuo deve essere riconciliato con la relativa "
                    "evidenza bancaria."
                ),
            )
        totale_fattura = abs(float(
            fattura.get("total_amount") or fattura.get("importo_totale") or 0
        ))
        importo = float(
            fattura.get("_importo_residuo")
            if fattura.get("_importo_residuo") is not None
            else totale_fattura
        )
        if importo <= 0:
            raise HTTPException(status_code=409, detail="Residuo fattura gia' azzerato")

        if metodo == "banca":
            evidenza_id = movimento_bancario.get("id")
            movimento_bancario = await db["estratto_conto_movimenti"].find_one(
                {"id": evidenza_id}, {"_id": 0}
            )
            if not movimento_bancario:
                raise HTTPException(
                    status_code=404,
                    detail="Movimento di estratto conto non trovato",
                )
            collegata_a = (
                movimento_bancario.get("fattura_id")
                or movimento_bancario.get("documento_id")
            )
            if collegata_a and str(collegata_a) != str(fattura_id):
                raise HTTPException(
                    status_code=409,
                    detail="Il movimento bancario e' gia' collegato a un altro documento",
                )
            importo_evidenza = abs(float(
                movimento_bancario.get("importo")
                or movimento_bancario.get("amount")
                or movimento_bancario.get("uscite")
                or 0
            ))
            if abs(importo_evidenza - importo) > 0.01:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Importo estratto conto ({importo_evidenza:.2f}) diverso "
                        f"dal residuo fattura ({importo:.2f}). Usa la "
                        "riconciliazione multipla se il movimento paga piu' fatture."
                    ),
                )
            movimento_bancario = {
                **movimento_bancario,
                "match_score": float(
                    movimento_bancario.get("confidenza") or 1.0
                ),
            }

        risultato = await registra_pagamento_fattura(
            fattura=fattura,
            metodo_pagamento=metodo,
            importo_cassa=importo if metodo == "cassa" else 0,
            importo_banca=importo if metodo == "banca" else 0,
            source="conferma_provvisori",
            movimento_bancario=movimento_bancario,
        )
        pn_id = risultato.get(metodo)
        if not pn_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Pagamento non registrato: manca l'evidenza prevista "
                    "dalla regola contabile"
                ),
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        campi_fattura = {
            "stato_pagamento": "pagata",
            "payment_status": "paid",
            "stato_finanziario": (
                "pagata_e_riconciliata" if metodo == "banca" else "pagata"
            ),
            "pagato": True,
            "paid": True,
            "totale_pagato": round(totale_fattura, 2),
            "importo_pagato": round(totale_fattura, 2),
            "importo_residuo": 0,
            "residuo_da_pagare": 0,
            "prima_nota_tipo": metodo,
            "prima_nota_id": pn_id,
            f"prima_nota_{metodo}_id": pn_id,
            "metodo_pagamento_effettivo": metodo,
            "data_pagamento": now_iso[:10],
            "updated_at": now_iso,
        }
        if metodo == "cassa" and approvazione_cassa_esplicita:
            campi_fattura.update({
                "metodo_pagamento_previsto": "cassa",
                "metodo_pagamento_override_source": "operatore_prima_nota",
                "metodo_pagamento_override_at": now_iso,
            })
        if metodo == "banca":
            campi_fattura.update({
                "riconciliato": True,
                "pagata_e_riconciliata": True,
                "movimento_banca_id": movimento_bancario.get("id"),
                "estratto_conto_id": movimento_bancario.get("id"),
            })
        if (fattura.get("anomalia_pagamento") or {}).get("stato") == "aperta":
            campi_fattura["anomalia_pagamento"] = {
                **fattura["anomalia_pagamento"],
                "stato": "risolta",
                "risolta_il": now_iso,
                "risolta_da": str(data.get("performed_by") or "operatore"),
                "esito": metodo,
            }
        await db["invoices"].update_one(
            {"id": fattura_id}, {"$set": campi_fattura}
        )
    finally:
        await _rilascia_claim_pagamento(db, fattura_id, claim_token)

    try:
        from app.services.audit_logger import log_evento
        await log_evento(
            modulo="prima_nota",
            azione="conferma_fattura_provvisoria",
            entita_id=fattura_id,
            entita_collection="invoices",
            db=db,
            nuovo_stato={
                "metodo": metodo,
                "importo": importo,
                "movimento_id": pn_id,
                "estratto_conto_id": movimento_bancario.get("id") if movimento_bancario else None,
                "approvazione_metodo_fattura": (
                    approvazione_cassa_esplicita if metodo == "cassa" else False
                ),
            },
            fonte="provvisori_conferma",
            utente=str(data.get("performed_by") or "operatore"),
        )
    except Exception:
        logger.exception("Audit conferma provvisoria fallito")

    return {
        "success": True,
        "metodo": metodo,
        "importo": importo,
        "fornitore": fornitore,
        "movimento_id": pn_id,
        "riconciliato": metodo == "banca",
    }

async def conferma_divisione_provvisoria(data: Dict = Body(...)) -> Dict:
    """
    Conferma la DIVISIONE di una fattura di fornitore "Misto" tra cassa e banca.
    Body: { fattura_id, importo_cassa, importo_banca, performed_by? }

    Regola canonica: la fattura di un fornitore Misto resta in Prima Nota
    Provvisoria finche' l'utente non conferma come dividere l'importo. La quota
    Cassa diventa una scrittura reale; la quota Banca resta un residuo atteso e
    non genera una scrittura finche' manca l'estratto conto.
    La somma cassa+banca deve coincidere col totale fattura (tolleranza 1 cent).
    """
    db = Database.get_db()

    fattura_id = data.get("fattura_id")
    try:
        importo_cassa = round(float(data.get("importo_cassa", 0) or 0), 2)
        importo_banca = round(float(data.get("importo_banca", 0) or 0), 2)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="importo_cassa/importo_banca non numerici")

    if not fattura_id:
        raise HTTPException(status_code=400, detail="fattura_id obbligatorio")
    if importo_cassa <= 0 or importo_banca <= 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "Il pagamento parziale richiede una quota Cassa e un residuo "
                "Banca entrambi maggiori di zero"
            ),
        )

    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    claim_token = await _acquisisci_claim_pagamento(
        db, fattura_id, "conferma_divisione"
    )
    try:
        fattura_corrente = await db["invoices"].find_one(
            {"id": fattura_id}, {"_id": 0}
        )
        fatture_aperte = await fatture_senza_pagamento_contabile_confermato(
            db, [fattura_corrente]
        )
        if not fatture_aperte:
            raise HTTPException(
                status_code=409,
                detail="La fattura ha gia' un pagamento contabile completo",
            )
        fattura = fatture_aperte[0]
        gia_pagato = round(float(
            fattura.get("_importo_pagato_confermato") or 0
        ), 2)
        if gia_pagato > 0.01:
            raise HTTPException(
                status_code=409,
                detail=(
                    "La fattura ha gia' un pagamento parziale. Il residuo deve "
                    "essere riconciliato con la relativa evidenza bancaria."
                ),
            )

        totale = round(abs(float(
            fattura.get("total_amount") or fattura.get("importo_totale") or 0
        )), 2)
        if abs((importo_cassa + importo_banca) - totale) > 0.01:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"La somma cassa ({importo_cassa}) + banca ({importo_banca}) "
                    f"deve coincidere col totale fattura ({totale})"
                ),
            )

        # La quota Cassa e' confermata dall'operatore. La quota Banca e' solo
        # un residuo atteso: nessuna riga bancaria nasce senza estratto conto.
        risultato = await registra_pagamento_fattura(
            fattura=fattura,
            metodo_pagamento="misto",
            importo_cassa=importo_cassa,
            importo_banca=importo_banca,
            source="conferma_provvisori_parziale",
        )
        if not risultato.get("cassa"):
            raise HTTPException(
                status_code=409,
                detail="Quota Cassa non registrata; nessuno stato e' stato chiuso",
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        campi_divisione = {
            "stato_pagamento": "parzialmente_pagata",
            "payment_status": "partial",
            "stato_finanziario": "aperta_in_attesa_banca",
            "pagato": False,
            "paid": False,
            "totale_pagato": importo_cassa,
            "importo_pagato": importo_cassa,
            "importo_residuo": importo_banca,
            "residuo_da_pagare": importo_banca,
            "prima_nota_id": risultato.get("cassa"),
            "prima_nota_cassa_id": risultato.get("cassa"),
            "prima_nota_tipo": "misto",
            "divisione_misto": {
                "cassa": importo_cassa,
                "banca": importo_banca,
            },
            "metodo_pagamento_previsto": "banca",
            "metodo_pagamento_override_source": "operatore_prima_nota",
            "metodo_pagamento_override_at": now_iso,
            "updated_at": now_iso,
        }
        if (fattura.get("anomalia_pagamento") or {}).get("stato") == "aperta":
            campi_divisione["anomalia_pagamento"] = {
                **fattura["anomalia_pagamento"],
                "stato": "risolta",
                "risolta_il": now_iso,
                "risolta_da": str(data.get("performed_by") or "operatore"),
                "esito": "misto",
            }
        await db["invoices"].update_one(
            {"id": fattura_id},
            {
                "$set": campi_divisione,
                "$unset": {
                    "prima_nota_banca_id": "",
                    "movimento_banca_id": "",
                    "estratto_conto_id": "",
                    "data_pagamento": "",
                },
            },
        )
    finally:
        await _rilascia_claim_pagamento(db, fattura_id, claim_token)

    # Audit: chi ha confermato la divisione e come.
    try:
        from app.services.audit_logger import log_evento
        await log_evento(
            modulo="prima_nota",
            azione="conferma_divisione_misto",
            entita_id=fattura_id,
            entita_collection="invoices",
            db=db,
            nuovo_stato={"importo_cassa": importo_cassa, "importo_banca": importo_banca,
                         "movimenti": risultato},
            fonte="provvisori_conferma_divisione",
            utente=str(data.get("performed_by") or "operatore"),
        )
    except Exception:
        logger.exception("Audit conferma divisione misto fallito")

    return {
        "success": True,
        "fattura_id": fattura_id,
        "stato": "parzialmente_pagata_in_attesa_banca",
        "importo_cassa": importo_cassa,
        "importo_banca": importo_banca,
        "movimento_cassa_id": risultato.get("cassa"),
        "movimento_banca_id": risultato.get("banca"),
        "message": (
            "Quota Cassa registrata. Il residuo resta aperto e sara' chiuso "
            "solo dalla riconciliazione con l'estratto conto."
        ),
    }



async def sposta_scrittura_prima_nota(data: Dict = Body(...)) -> Dict:
    """
    Sposta una scrittura da Cassa a Banca o viceversa.
    Quando l'utente cambia il metodo di pagamento, il sistema:
    1. Rimuove dalla collection originale
    2. Inserisce nella nuova collection
    3. Aggiorna la fattura collegata
    """
    db = Database.get_db()
    
    movimento_id = data.get("movimento_id")
    nuova_destinazione = data.get("destinazione")  # "cassa" o "banca"
    
    if nuova_destinazione not in ["cassa", "banca"]:
        raise HTTPException(status_code=400, detail="Destinazione deve essere 'cassa' o 'banca'")
    
    # Cerca il movimento in entrambe le collection
    movimento = None
    origine = None
    for coll in [COLLECTION_PRIMA_NOTA_CASSA, COLLECTION_PRIMA_NOTA_BANCA]:
        mov = await db[coll].find_one({"id": movimento_id})
        if mov:
            movimento = mov
            origine = "cassa" if "cassa" in coll else "banca"
            break
    
    if not movimento:
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    
    if origine == nuova_destinazione:
        return {"success": True, "message": "Già nella destinazione corretta"}
    
    # Rimuovi dalla collection originale
    coll_origine = COLLECTION_PRIMA_NOTA_CASSA if origine == "cassa" else COLLECTION_PRIMA_NOTA_BANCA
    await db[coll_origine].delete_one({"id": movimento_id})
    
    # Inserisci nella nuova collection
    coll_dest = COLLECTION_PRIMA_NOTA_CASSA if nuova_destinazione == "cassa" else COLLECTION_PRIMA_NOTA_BANCA
    movimento.pop("_id", None)
    movimento["spostato_da"] = origine
    movimento["spostato_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    await db[coll_dest].insert_one(movimento)
    
    # Aggiorna la fattura collegata
    fattura_id = movimento.get("fattura_id")
    if fattura_id:
        metodo_label = "contanti" if nuova_destinazione == "cassa" else "bonifico"
        await db["invoices"].update_one(
            {"id": fattura_id},
            {"$set": {
                "prima_nota_tipo": nuova_destinazione,
                "payment_method": metodo_label,
            }}
        )
    
    return {
        "success": True,
        "spostato": f"{origine} → {nuova_destinazione}",
        "movimento_id": movimento_id,
        "importo": movimento.get("importo"),
    }




async def import_prima_nota_batch(data: Dict = Body(...)) -> Dict:
    """Importa batch di movimenti."""
    db = Database.get_db()
    
    created_cassa = 0
    created_banca = 0
    errors = []
    
    for mov in data.get("cassa", []):
        try:
            movimento = {
                "id": str(uuid.uuid4()),
                "data": mov["data"],
                "tipo": mov["tipo"],
                "importo": float(mov["importo"]),
                "descrizione": mov.get("descrizione", ""),
                "categoria": mov.get("categoria", "Altro"),
                "riferimento": mov.get("riferimento"),
                "fornitore_piva": mov.get("fornitore_piva"),
                "fattura_id": mov.get("fattura_id"),
                "source": mov.get("source", "excel_import"),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento.copy())
            created_cassa += 1
        except Exception as e:
            errors.append(f"Cassa: {str(e)}")
    
    for mov in data.get("banca", []):
        try:
            movimento = {
                "id": str(uuid.uuid4()),
                "data": mov["data"],
                "tipo": mov["tipo"],
                "importo": float(mov["importo"]),
                "descrizione": mov.get("descrizione", ""),
                "categoria": mov.get("categoria", "Altro"),
                "riferimento": mov.get("riferimento"),
                "fornitore_piva": mov.get("fornitore_piva"),
                "fattura_id": mov.get("fattura_id"),
                "source": mov.get("source", "excel_import"),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db[COLLECTION_PRIMA_NOTA_BANCA].insert_one(movimento.copy())
            created_banca += 1
        except Exception as e:
            errors.append(f"Banca: {str(e)}")
    
    return {
        "message": "Import completato",
        "cassa_created": created_cassa,
        "banca_created": created_banca,
        "errors": errors[:10]
    }


async def create_movimento_generico(data: Dict = Body(...)) -> Dict:
    """Crea un movimento Prima Nota generico (cassa o banca)."""
    db = Database.get_db()
    
    tipo_nota = data.get("tipo", "banca")
    tipo_movimento = data.get("tipo_movimento", "entrata")
    
    required = ["data", "importo", "descrizione"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Campo obbligatorio mancante: {field}")
    
    movimento = {
        "id": str(uuid.uuid4()),
        "data": data["data"],
        "tipo": tipo_movimento,
        "importo": float(data["importo"]),
        "descrizione": data["descrizione"],
        "categoria": data.get("categoria", "Altro"),
        "riferimento": data.get("riferimento"),
        "fornitore_piva": data.get("fornitore_piva"),
        "fonte": data.get("fonte", "manual_entry"),
        "riconciliato": data.get("riconciliato", False),
        "note": data.get("note"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    collection = COLLECTION_PRIMA_NOTA_BANCA if tipo_nota == "banca" else COLLECTION_PRIMA_NOTA_CASSA

    # CAS_DUPLICATO era definito in alert_engine.py ma mai generato: nessun
    # controllo esisteva sui movimenti cassa inseriti manualmente (a
    # differenza dell'import massivo estratto conto, che ha già un
    # anti-duplicato — vedi BNK_DUPLICATO). Additivo: segnala soltanto, non
    # blocca l'inserimento (l'utente potrebbe intenzionalmente registrare due
    # movimenti identici, es. due versamenti uguali in giorni diversi con
    # stessa descrizione generica).
    if tipo_nota != "banca":
        try:
            duplicato = await db[collection].find_one({
                "data": movimento["data"],
                "tipo": movimento["tipo"],
                "descrizione": movimento["descrizione"],
                "importo": {"$gte": movimento["importo"] - 0.005, "$lte": movimento["importo"] + 0.005},
            }, {"_id": 0, "id": 1})
            if duplicato:
                from app.services.alert_engine import genera_alert
                await genera_alert(
                    "CAS_DUPLICATO", movimento["id"], collection,
                    f"Movimento cassa del {movimento['data']} (€{movimento['importo']}, "
                    f"{movimento['descrizione'][:60]}) uguale a uno già esistente (id {duplicato.get('id')})",
                    db, extra={"movimento_esistente_id": duplicato.get("id")},
                )
        except Exception:
            logger.exception(f"Errore generazione alert CAS_DUPLICATO per {movimento['id']}")

    await db[collection].insert_one(movimento.copy())

    return {"message": f"Movimento {tipo_nota} creato", "id": movimento["id"]}


async def collega_fatture_movimenti() -> Dict:
    """Collega automaticamente fatture ai movimenti."""
    db = Database.get_db()
    
    collegati = 0
    
    for coll in [COLLECTION_PRIMA_NOTA_CASSA, COLLECTION_PRIMA_NOTA_BANCA]:
        cursor = db[coll].find({
            "numero_fattura": {"$exists": True, "$nin": [None, ""]},
            "fattura_id": {"$in": [None, ""]}
        })
        
        async for mov in cursor:
            numero_fattura = mov.get("numero_fattura", "")
            if not numero_fattura:
                continue
            
            fattura = await db["invoices"].find_one({
                "$or": [
                    {"numero": numero_fattura},
                    {"invoice_number": numero_fattura},
                    {"numero_fattura": numero_fattura}
                ]
            }, {"_id": 0, "id": 1})
            
            if fattura:
                await db[coll].update_one(
                    {"id": mov["id"]},
                    {"$set": {"fattura_id": fattura["id"]}}
                )
                collegati += 1
    
    return {"success": True, "movimenti_collegati": collegati}


async def auto_conferma_provvisori_per_metodo(
    anno: int = Query(..., description="Anno da processare"),
) -> Dict[str, Any]:
    """Applica al PREGRESSO dell'anno la regola metodo-fornitore (utente
    17/07/2026, la stessa dell'ingresso fattura XML): fornitore con metodo
    univoco cassa/banca → la fattura provvisoria viene registrata subito
    nella prima nota corrispondente; misto/senza metodo/ambiguo → resta in
    Provvisoria. Le fatture già pagate o con un movimento esistente non
    vengono mai toccate (nessun doppio movimento possibile).
    """
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Carica il dizionario metodo-per-piva dall'anagrafica fornitori
    # (P.IVA in partita_iva, piva o vat_number: record storici inclusi)
    metodo_per_piva: Dict[str, str] = {}
    esclusi_cassa_banca = set()
    async for s in db["fornitori"].find(
        {},
        {"_id": 0, "partita_iva": 1, "piva": 1, "vat_number": 1,
         "metodo_pagamento": 1, "esclude_cassa_banca": 1, "cessato": 1}
    ):
        metodo = (s.get("metodo_pagamento") or "").strip().lower()
        for k in (s.get("partita_iva"), s.get("piva"), s.get("vat_number")):
            if not k:
                continue
            chiave = str(k).strip()
            if metodo:
                metodo_per_piva[chiave] = metodo
            if s.get("esclude_cassa_banca") or s.get("cessato"):
                esclusi_cassa_banca.add(chiave)

    # Fatture provvisorie dell'anno
    fatture = await db["invoices"].find(
        {
            "invoice_date": {"$regex": f"^{anno}"},
            "total_amount": {"$gt": 0},
            "$or": [
                {"prima_nota_id": None},
                {"prima_nota_id": ""},
                {"prima_nota_id": {"$exists": False}},
            ],
            "stato_pagamento": {"$nin": ["sospesa"]},  # le sospese non le tocco
        },
        {"_id": 0, "xml_raw": 0, "linee": 0}
    ).to_list(5000)

    report = {
        "anno": anno,
        "totali_provvisorie_analizzate": len(fatture),
        "mosse_cassa": 0,
        "mosse_banca": 0,
        "restate_in_provvisoria_banca_non_pagata": 0,
        "restate_in_provvisoria_paypal_o_carta": 0,
        "restate_in_provvisoria_fornitore_senza_metodo": 0,
        "restate_in_provvisoria_richiede_conferma_manuale": 0,
        "restate_escluse_cassa_banca": 0,
        "skipped_gia_in_prima_nota": 0,
        "skipped_errori": [],
        "dettaglio_mosse": [],  # prime 100 per log
    }

    for f in fatture:
        try:
            fid = f.get("id") or f.get("invoice_key")
            if not fid:
                continue

            piva = (f.get("supplier_vat") or f.get("cedente_piva") or "").strip()
            stato_pagamento = (f.get("stato_pagamento") or "").lower()
            pagata = stato_pagamento in ("pagata", "paid")

            if f.get("esclusa_da_cassa_banca") or piva in esclusi_cassa_banca:
                report["restate_escluse_cassa_banca"] += 1
                continue

            # Dedup sicuro: se esiste già un movimento in cassa o banca per
            # questa fattura, non tocco nulla (può esserci stato movimento
            # manuale). Aggiorno solo il flag sulla fattura per toglierla dai
            # provvisori.
            rif = f"FATT-{fid}"
            existing_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({
                "$or": [{"riferimento": rif}, {"fattura_id": fid}],
                "status": {"$nin": ["deleted", "archived"]},
            })
            existing_banca = await db[COLLECTION_PRIMA_NOTA_BANCA].find_one({
                "$or": [{"riferimento": rif}, {"fattura_id": fid}],
                "status": {"$nin": ["deleted", "archived"]},
            })
            if existing_cassa or existing_banca:
                existing = existing_cassa or existing_banca
                tipo_pn = "cassa" if existing_cassa else "banca"
                await db["invoices"].update_one(
                    {"id": fid},
                    {"$set": {
                        "prima_nota_id": existing.get("id"),
                        "prima_nota_tipo": tipo_pn,
                        "stato_pagamento": "pagata" if pagata else stato_pagamento,
                    }}
                )
                report["skipped_gia_in_prima_nota"] += 1
                continue

            metodo = metodo_per_piva.get(piva, "")

            # Fattura già marcata pagata (es. "segna pagata manualmente",
            # pagamento fuori sistema): mai creare un movimento nuovo, si
            # duplicherebbe una spesa già avvenuta altrove.
            if pagata or f.get("pagato"):
                report["restate_in_provvisoria_richiede_conferma_manuale"] += 1
                continue

            # --- REGOLA utente 17/07/2026 (applicata anche al pregresso):
            # fornitore con metodo UNIVOCO cassa/banca → registrazione
            # diretta nella prima nota corrispondente; misto/assente/ambiguo
            # → resta provvisoria. Stessa identica implementazione usata
            # all'ingresso della fattura XML (auto_registra_prima_nota).
            from app.routers.invoices.fatture_upload import auto_registra_prima_nota
            update = await auto_registra_prima_nota(db, f, None)

            if update:
                if update.get("prima_nota_tipo") == "cassa":
                    report["mosse_cassa"] += 1
                else:
                    report["mosse_banca"] += 1
                if len(report["dettaglio_mosse"]) < 100:
                    report["dettaglio_mosse"].append({
                        "fattura_id": fid,
                        "fornitore": f.get("supplier_name") or f.get("cedente_denominazione"),
                        "importo": f.get("total_amount") or f.get("importo_totale"),
                        "destinazione": update.get("prima_nota_tipo"),
                    })
            else:
                destinazione_calcolata = classifica_metodo_fornitore(metodo)
                if destinazione_calcolata == "sospesa":
                    if metodo:
                        report["restate_in_provvisoria_paypal_o_carta"] += 1
                    else:
                        report["restate_in_provvisoria_fornitore_senza_metodo"] += 1
                else:
                    report["restate_in_provvisoria_richiede_conferma_manuale"] += 1

        except Exception as e:
            logger.exception(f"Errore auto-conferma fattura {f.get('id')}: {e}")
            report["skipped_errori"].append({
                "fattura_id": f.get("id"),
                "errore": str(e)[:200],
            })

    return {
        "success": True,
        "message": (
            f"Regola metodo-fornitore applicata: {report['mosse_cassa']} fatture "
            f"registrate in Cassa, {report['mosse_banca']} in Banca; le fatture di "
            "fornitori misto/senza metodo/ambiguo restano in Provvisoria."
        ),
        **report,
    }


async def annulla_auto_conferma(
    operazione_id: Optional[str] = Query(None, description="Se fornito annulla solo i movimenti di quella operazione; altrimenti annulla TUTTI i movimenti auto-confirm"),
) -> Dict[str, Any]:
    """Rollback dell'operazione auto_conferma_provvisori_per_metodo.

    Se operazione_id è fornito, annulla solo quella run specifica.
    Altrimenti annulla TUTTI i movimenti con source='auto_confirm_provvisoria'.

    Il rollback:
      1. Soft-delete dei movimenti (status='deleted') — reversibile dal DB
      2. Riporta le fatture allo stato prima-nota-id vuoto + stato_pagamento
         al valore precedente (salvato in auto_confirm_meta.stato_pagamento_al_momento)
    """
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()

    filtro: Dict[str, Any] = {
        "source": "auto_confirm_provvisoria",
        "status": {"$nin": ["deleted", "archived"]},
    }
    if operazione_id:
        filtro["auto_confirm_meta.operazione_id"] = operazione_id

    movimenti_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find(filtro, {"_id": 0}).to_list(10000)
    movimenti_banca = await db[COLLECTION_PRIMA_NOTA_BANCA].find(filtro, {"_id": 0}).to_list(10000)

    ids_cassa = [m["id"] for m in movimenti_cassa]
    ids_banca = [m["id"] for m in movimenti_banca]
    fatture_ids = list({m.get("fattura_id") for m in (movimenti_cassa + movimenti_banca) if m.get("fattura_id")})

    # Soft-delete movimenti
    if ids_cassa:
        await db[COLLECTION_PRIMA_NOTA_CASSA].update_many(
            {"id": {"$in": ids_cassa}},
            {"$set": {"status": "deleted", "deleted_at": now, "deleted_reason": "rollback_auto_confirm"}}
        )
    if ids_banca:
        await db[COLLECTION_PRIMA_NOTA_BANCA].update_many(
            {"id": {"$in": ids_banca}},
            {"$set": {"status": "deleted", "deleted_at": now, "deleted_reason": "rollback_auto_confirm"}}
        )

    # Ripristina le fatture: ciclo uno per uno per ripristinare il giusto stato_pagamento
    fatture_ripristinate = 0
    for m in movimenti_cassa + movimenti_banca:
        fid = m.get("fattura_id")
        if not fid:
            continue
        stato_originale = (m.get("auto_confirm_meta") or {}).get("stato_pagamento_al_momento", "")
        set_ops = {"prima_nota_id": "", "prima_nota_tipo": ""}
        if stato_originale:
            set_ops["stato_pagamento"] = stato_originale
        await db["invoices"].update_one({"id": fid}, {"$set": set_ops})
        fatture_ripristinate += 1

    return {
        "success": True,
        "operazione_id": operazione_id,
        "movimenti_cassa_annullati": len(ids_cassa),
        "movimenti_banca_annullati": len(ids_banca),
        "fatture_ripristinate_a_provvisoria": fatture_ripristinate,
    }

async def crea_entrata_cassa_da_corrispettivo(
    data: str = Query(..., description="Data corrispettivo YYYY-MM-DD"),
    includi_uscita_pos: bool = Query(False, description="Parametro legacy ignorato: il POS nasce solo dal totale manuale"),
) -> Dict[str, Any]:
    """Crea manualmente l'entrata in Prima Nota Cassa dal corrispettivo XML già importato.

    Utilizzo previsto: l'operatore la sera non ha tempo di inserire l'entrata
    cassa a mano, preme questo bottone (dalla UI) e il sistema crea:
      - Entrata in Prima Nota Cassa = totale corrispettivo (contanti + POS)
      - Uscita in Prima Nota Cassa = pagato_elettronico (solo se includi_uscita_pos=True)

    Idempotente: se esistono già movimenti con source='manuale_da_xml' + corrispettivo_id
    per questa data, non li duplica.

    NOTA: questo endpoint è SOLO per il flusso opzionale manuale. Il flusso
    normale è che l'utente inserisca i movimenti a mano la sera; l'XML serve
    solo per controllo coerenza POS.
    """
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Cerca il corrispettivo per quella data
    corrispettivo = await db["corrispettivi"].find_one({"data": data}, {"_id": 0})
    if not corrispettivo:
        raise HTTPException(
            status_code=404,
            detail=f"Nessun corrispettivo trovato per la data {data}. Importa prima l'XML del registratore telematico."
        )

    corr_id = corrispettivo.get("id")
    if not corr_id:
        raise HTTPException(status_code=400, detail="Corrispettivo senza id, impossibile deduplicare")

    # Idempotenza: se esiste già un movimento da questo endpoint per il corrispettivo, non duplicare
    existing_entrata = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({
        "corrispettivo_id": corr_id,
        "source": "manuale_da_xml",
        "tipo": "entrata",
        "status": {"$nin": ["deleted", "archived"]},
    })
    if existing_entrata:
        return {
            "success": True,
            "duplicato": True,
            "message": f"Movimenti per il {data} già creati in precedenza (id: {existing_entrata.get('id')})",
        }

    # CLAIM ATOMICO sul corrispettivo: un doppio click sulla Conferma trova il
    # flag già impostato e viene rifiutato (niente movimenti doppi anche con
    # due richieste concorrenti).
    claim = await db["corrispettivi"].find_one_and_update(
        {"id": corr_id, "prima_nota_cassa_generata": {"$ne": True}},
        {"$set": {"prima_nota_cassa_generata": True,
                  "prima_nota_cassa_generata_at": now}},
    )
    if claim is None:
        return {
            "success": True,
            "duplicato": True,
            "message": f"Movimenti per il {data} già confermati (richiesta concorrente rifiutata)",
        }

    # Estrai valori dal corrispettivo (tolleranti a schema legacy)
    contanti = float(corrispettivo.get("pagato_contanti", 0) or 0)
    elettronico = float(
        corrispettivo.get("pagato_pos", 0)
        or corrispettivo.get("pagato_elettronico", 0)
        or 0
    )
    totale = float(
        corrispettivo.get("totale", 0)
        or corrispettivo.get("totale_complessivo", 0)
        or (contanti + elettronico)
        or 0
    )

    if totale <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"Corrispettivo {data} ha totale 0. Verifica l'XML importato."
        )

    risultati = {"entrata_cassa_id": None, "uscita_pos_id": None}

    # 1) ENTRATA CASSA = totale corrispettivo
    entrata_id = str(uuid.uuid4())
    movimento_entrata = {
        "id": entrata_id,
        "data": data,
        "tipo": "entrata",
        "categoria": "Corrispettivi",
        "descrizione": f"Corrispettivi {data} (da XML)",
        "importo": round(totale, 2),
        "corrispettivo_id": corr_id,
        "pagato_contanti": round(contanti, 2),
        "pagato_elettronico": round(elettronico, 2),
        "totale_giornata": round(totale, 2),
        "source": "manuale_da_xml",
        "created_at": now,
    }
    await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento_entrata.copy())
    risultati["entrata_cassa_id"] = entrata_id

    # 2) USCITA CASSA = quota POS (opzionale)
    if False:  # XML RT: solo coerenza fiscale, mai scritture POS in Prima Nota
        uscita_id = str(uuid.uuid4())
        movimento_uscita = {
            "id": uscita_id,
            "data": data,
            "tipo": "uscita",
            "categoria": "POS Verso Banca",
            "descrizione": f"Battuto POS {data} (da XML) → Banca",
            "importo": round(elettronico, 2),
            "corrispettivo_id": corr_id,
            "source": "manuale_da_xml",
            "created_at": now,
        }
        await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento_uscita.copy())
        risultati["uscita_pos_id"] = uscita_id

    return {
        "success": True,
        "duplicato": False,
        "data": data,
        "totale_corrispettivo": round(totale, 2),
        "contanti": round(contanti, 2),
        "elettronico": round(elettronico, 2),
        "include_uscita_pos": False,
        **risultati,
        "message": f"Movimenti creati in Prima Nota Cassa per il {data}. Sono annullabili normalmente dalla pagina Prima Nota.",
    }


async def sposta_fatture_cassa_pagate_in_banca(
    dry_run: bool = Query(True, description="Solo conteggio"),
    anno: int = Query(2026),
) -> Dict[str, Any]:
    """RICHIESTA UTENTE 18/07/2026: "se trovi un fornitore che è per cassa
    ma la fattura viene pagata per banca, metti in evidenza e paga per
    banca nonostante il metodo cassa".

    Per ogni pagamento fattura registrato in Prima Nota CASSA, cerca
    nell'estratto conto un addebito con lo stesso importo E il nome del
    fornitore nella descrizione (match forte: mai solo per importo). Se lo
    trova, l'estratto conto vince sull'anagrafica: la riga di cassa viene
    soft-deletata, l'uscita registrata in Prima Nota Banca agganciata al
    movimento reale, la fattura marcata pagata per bonifico, e viene
    generato un ALERT di evidenza (FATTURA_CASSA_PAGATA_BANCA).
    """
    from app.services.alert_engine import genera_alert

    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()

    righe_cassa = await db["prima_nota_cassa"].find(
        {"data": {"$regex": f"^{anno}"}, "tipo": "uscita",
         "fattura_id": {"$exists": True, "$nin": [None, ""]},
         "status": {"$nin": ["deleted", "archived"]}},
        {"_id": 0, "id": 1, "fattura_id": 1, "importo": 1, "data": 1, "descrizione": 1},
    ).to_list(5000)

    movimenti_ec = await db["estratto_conto_movimenti"].find(
        {"data": {"$regex": f"^{anno}"}, "tipo": "uscita",
         "riconciliato": {"$ne": True}},
        {"_id": 0, "id": 1, "data": 1, "importo": 1,
         "descrizione_originale": 1, "descrizione": 1},
    ).to_list(20000)
    per_importo: Dict[float, list] = {}
    for m in movimenti_ec:
        per_importo.setdefault(round(abs(float(m.get("importo") or 0)), 2), []).append(m)

    spostate = 0
    dettaglio = []
    for riga in righe_cassa:
        fatt = await db["invoices"].find_one(
            {"id": riga["fattura_id"]}, {"_id": 0, "xml_raw": 0, "linee": 0})
        if not fatt:
            continue
        nome = (fatt.get("supplier_name") or "").upper()
        token = [p for p in nome.replace(".", " ").split() if len(p) > 3][:3]
        if not token:
            continue
        candidati = per_importo.get(round(abs(float(riga.get("importo") or 0)), 2), [])
        match = None
        for m in candidati:
            desc = (m.get("descrizione_originale") or m.get("descrizione") or "").upper()
            if any(t in desc for t in token):
                match = m
                break
        if not match:
            continue

        spostate += 1
        if len(dettaglio) < 50:
            dettaglio.append({
                "fattura": fatt.get("invoice_number"), "fornitore": fatt.get("supplier_name"),
                "importo": riga.get("importo"), "addebito_ec": match.get("data"),
                "descrizione_ec": (match.get("descrizione_originale") or "")[:60],
            })
        if dry_run:
            continue

        await db["prima_nota_cassa"].update_one(
            {"id": riga["id"]},
            {"$set": {"status": "deleted", "deleted": True,
                      "deleted_reason": "pagata_in_banca_da_estratto_conto",
                      "deleted_at": now}})
        pn_id = str(uuid.uuid4())
        rif = f"FATT-{fatt['id']}"
        esistente = await db["prima_nota_banca"].find_one(
            {"$or": [{"riferimento": rif}, {"fattura_id": fatt["id"]}],
             "status": {"$nin": ["deleted", "archived"]}})
        if esistente:
            pn_id = esistente["id"]
        else:
            await scrivi_movimento(db, "banca", {
                "id": pn_id,
                "data": match.get("data") or riga.get("data"),
                **costruisci_campi_movimento_fattura(fatt, float(riga.get("importo") or 0)),
                "fattura_id": fatt["id"],
                "riferimento": rif,
                "fornitore_piva": fatt.get("supplier_vat", ""),
                "estratto_conto_id": match.get("id"),
                "pagato_con": "bonifico",
                "source": "ec_override_metodo_cassa",
                "created_at": now,
            })
        await db["invoices"].update_one({"id": fatt["id"]}, {"$set": {
            "prima_nota_id": pn_id, "prima_nota_tipo": "banca",
            "prima_nota_banca_id": pn_id,
            "stato_pagamento": "pagata", "pagato": True, "paid": True,
            "metodo_pagamento": "bonifico",
            "data_pagamento": match.get("data"),
            "riconciliato_con_ec": match.get("id"),
            "pagata_banca_nonostante_metodo_cassa": True,
        }})
        await db["estratto_conto_movimenti"].update_one(
            {"id": match["id"]},
            {"$set": {"riconciliato": True,
                      "tipo_riconciliazione": "fattura_metodo_cassa_override",
                      "dettagli_riconciliazione": {"fattura_id": fatt["id"], "prima_nota_id": pn_id}}})
        match["riconciliato"] = True
        candidati.remove(match)
        try:
            await genera_alert(
                "FATTURA_CASSA_PAGATA_BANCA", fatt["id"], "invoices",
                f"Fatt. {fatt.get('invoice_number')} di {fatt.get('supplier_name')} "
                f"(€ {riga.get('importo')}): fornitore a metodo CASSA ma addebito "
                f"reale in banca il {match.get('data')} — registrata in Prima Nota Banca.",
                db)
        except Exception:
            logger.exception("Alert FATTURA_CASSA_PAGATA_BANCA non generato")

    return {
        "dry_run": dry_run,
        "anno": anno,
        "righe_cassa_analizzate": len(righe_cassa),
        "spostate_in_banca" if not dry_run else "da_spostare_in_banca": spostate,
        "dettaglio": dettaglio,
    }


async def conferma_provvisorie_multiple(data: Dict = Body(...)) -> Dict:
    """Conferma PIU' fatture provvisorie in un giro solo.

    Nata da una richiesta esplicita dell'utente (07/08/2026): confermare una
    fattura alla volta ricaricava la pagina a ogni clic, e con cento fatture
    in coda diventava una tortura. Qui si spuntano N fatture e si sceglie una
    volta sola: Cassa oppure Attendi banca.

    Body: { fattura_ids: [...], metodo: "cassa" | "attendi_banca" }

    Non e' una scorciatoia contabile: ogni fattura passa ESATTAMENTE dalle
    stesse funzioni della conferma singola, con tutte le loro guardie (gia'
    pagata, esclusa, pagamento parziale). Un rifiuto su una fattura non ferma
    le altre: l'esito arriva riga per riga, con il motivo di ogni scarto.
    """
    ids_raw = data.get("fattura_ids") or []
    if not isinstance(ids_raw, list):
        raise HTTPException(status_code=400, detail="fattura_ids deve essere una lista")
    # Deduplica prima del limite: cento ripetizioni accidentali dello stesso
    # ID non devono trasformare una richiesta valida in un errore artificiale.
    fattura_ids = list(dict.fromkeys(
        str(f).strip() for f in ids_raw if str(f or "").strip()
    ))
    metodo = str(data.get("metodo") or "").strip().lower()

    if not fattura_ids:
        raise HTTPException(status_code=400, detail="Nessuna fattura selezionata")
    if len(fattura_ids) > 200:
        raise HTTPException(
            status_code=400,
            detail="Massimo 200 fatture per giro: seleziona un blocco piu' piccolo",
        )
    if metodo not in ("cassa", "attendi_banca"):
        raise HTTPException(
            status_code=400,
            detail="Metodo non valido: scegli 'cassa' oppure 'attendi_banca'",
        )

    esiti = []
    riuscite = 0
    for fattura_id in fattura_ids:
        try:
            if metodo == "cassa":
                await conferma_fattura_provvisoria({
                    "fattura_id": fattura_id,
                    "metodo": "cassa",
                    # La selezione esplicita nel riquadro multiplo VALE come
                    # approvazione: e' l'utente che ha spuntato la fattura.
                    "approva_metodo_fattura": True,
                })
            else:
                await imposta_fattura_in_attesa_banca({"fattura_id": fattura_id})
            riuscite += 1
            esiti.append({"fattura_id": fattura_id, "success": True})
        except HTTPException as exc:
            # Il motivo del rifiuto resta leggibile: e' la stessa guardia
            # che l'utente avrebbe visto confermando la singola fattura.
            esiti.append({
                "fattura_id": fattura_id,
                "success": False,
                "detail": str(exc.detail),
            })
        except Exception:  # una fattura rotta non ferma il lotto
            logger.exception(f"Conferma multipla: errore su {fattura_id}")
            esiti.append({
                "fattura_id": fattura_id,
                "success": False,
                "detail": "Errore interno durante l'elaborazione",
            })

    scartate = len(esiti) - riuscite
    return {
        "success": scartate == 0,
        "metodo": metodo,
        "riuscite": riuscite,
        "scartate": scartate,
        "esiti": esiti,
        "message": (
            f"{riuscite} fatture registrate"
            + (f", {scartate} scartate (vedi dettaglio)" if scartate else "")
        ),
    }
