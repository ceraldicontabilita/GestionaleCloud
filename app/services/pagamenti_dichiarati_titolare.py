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
  ``collega_assegno_riconciliato_a_fatture``. Senza addebito univoco la
  fattura aspetta la banca.
- Banca, carta, PayPal → la fattura aspetta la banca
  (``imposta_fattura_in_attesa_banca``) e la chiude il motore unico
  ``reconcile_deterministic_invoice_allocations`` quando trova il movimento:
  il metodo dichiarato non e' la prova che il denaro sia uscito.
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
                {"id": fattura["id"]},
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


async def _attendi_banca(db, fattura: Dict[str, Any], riga: Dict[str, Any]) -> None:
    from app.routers.prima_nota_module.sync import imposta_fattura_in_attesa_banca

    if fattura.get("stato_finanziario") != "aperta_in_attesa_banca":
        await imposta_fattura_in_attesa_banca({
            "fattura_id": fattura["id"], "performed_by": ATTORE,
        })
    await db["invoices"].update_one({"id": fattura["id"]}, {"$set": {
        "metodo_pagamento_dichiarato": riga.get("metodo_pagamento_titolare"),
        "assegno_numero_dichiarato": riga.get("assegno_numero_titolare") or None,
        "metodo_pagamento_override_source": ATTORE,
    }})


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
                await db["invoices"].find_one({"id": f["id"]}, _PROIEZIONE) for f, _ in membri
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


async def applica_pagamenti_dichiarati(
    db, *, dry_run: bool = False, solo_pendenti: bool = False,
    aggiorna_fornitori: bool = True,
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
    righe = await db[COLLECTION_REPORT].find(filtro, {"_id": 0}).to_list(20000)
    risultato: Dict[str, Any] = {"dry_run": dry_run, "righe": len(righe)}
    if not righe:
        return risultato

    await collega_righe_a_fatture(db, righe, salva=not dry_run)

    if aggiorna_fornitori and not solo_pendenti:
        risultato["fornitori"] = await _aggiorna_fornitori(db, righe, dry_run=dry_run)

    ids = [r["invoice_id"] for r in righe if r.get("invoice_id")]
    fatture = await db["invoices"].find({"id": {"$in": ids}}, _PROIEZIONE).to_list(len(ids) or 1)
    per_id = {f["id"]: f for f in fatture}
    aperte = {
        f["id"]: f for f in await fatture_senza_pagamento_contabile_confermato(db, fatture)
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
        fattura_id = riga.get("invoice_id")
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
                await db["invoices"].update_one({"id": fattura_id}, {"$set": {
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

        # Banca, carta, PayPal, assegno senza numero: la prova e' la banca.
        annota(riga, "in_attesa_banca", fattura)
        if not dry_run:
            await _storna_cassa_provvisoria(db, fattura, metodo)
            await _attendi_banca(db, fattura, riga)
            await _salva_esito(db, riga, "in_attesa_banca", metodo=metodo)

    esiti_assegno = await _paga_con_assegni(db, gruppi_assegno, dry_run=dry_run)
    for fattura_id, esito in esiti_assegno.items():
        riga = righe_per_fattura[fattura_id]
        fattura = aperte[fattura_id]
        if esito == "registrata":
            annota(riga, "registrata", fattura)
            if not dry_run:
                await _salva_esito(db, riga, "registrata", metodo="assegno")
            continue
        annota(riga, "in_attesa_banca", fattura, motivo=esito)
        if not dry_run:
            await _storna_cassa_provvisoria(db, fattura, "assegno")
            await _attendi_banca(db, fattura, riga)
            await _salva_esito(db, riga, "in_attesa_banca", metodo="assegno", motivo=esito)

    # Le fatture pagate in banca le chiude l'unico motore bonifico ↔ fattura.
    if not dry_run and conteggi.get("in_attesa_banca") and not solo_pendenti:
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
    fatture = await db["invoices"].find({"id": {"$in": ids}}, _PROIEZIONE).to_list(len(ids))
    ancora_aperte = {f["id"] for f in await fatture_senza_pagamento_contabile_confermato(db, fatture)}
    chiuse = 0
    for riga in in_attesa:
        if riga["invoice_id"] not in ancora_aperte:
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
