"""Checklist documentale viva per l'Area Commercialista.

La pagina non chiede di nuovo documenti gia' presenti: legge i registri del
Gestionale e il registro della cartella unica Drive.  Le tre risposte sono
deliberatamente prudenti:

* ``dato_esistente``: esiste il documento/prospetto richiesto;
* ``dato_incompleto``: esistono dati o una parte delle prove, ma non il
  pacchetto completo;
* ``dato_mancante``: nelle fonti controllate non e' stato trovato nulla.

Un file in ``DA VERIFICARE`` o ``ERRORI`` resta incompleto.  Il solo nome del
file non crea associazioni contabili e non prova pagamenti.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Iterable


logger = logging.getLogger(__name__)


ESISTENTE = "dato_esistente"
INCOMPLETO = "dato_incompleto"
MANCANTE = "dato_mancante"


async def _count(db, collection: str, query: dict[str, Any] | None = None) -> int:
    try:
        return int(await db[collection].count_documents(query or {}))
    except Exception:  # una collezione opzionale non deve oscurare le altre
        return 0


def _periodo_query(anno: int, dal: str, al: str, *date_fields: str) -> dict[str, Any]:
    condizioni: list[dict[str, Any]] = [
        {"anno": anno}, {"anno": str(anno)},
        {"year": anno}, {"year": str(anno)},
        {"anno_documento": anno}, {"anno_documento": str(anno)},
        {"periodo_imposta": anno}, {"periodo_imposta": str(anno)},
    ]
    for field in date_fields:
        condizioni.append({field: {"$gte": dal, "$lte": al + "~"}})
    return {"$or": condizioni}


def _testo_drive(row: dict[str, Any]) -> str:
    percorso = " ".join(str(x or "") for x in (row.get("percorso_categoria") or []))
    return " ".join(str(row.get(k) or "") for k in ("nome", "tipo", "cartella", "motivo", "anno_indice")) + " " + percorso


def _drive_matches(rows: Iterable[dict[str, Any]], patterns: Iterable[str], anno: int) -> dict[str, int]:
    regex = re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)
    anno_re = re.compile(rf"(?<!\d){anno}(?!\d)")
    elaborati = incompleti = 0
    for row in rows:
        testo = _testo_drive(row)
        if not regex.search(testo) or not anno_re.search(testo):
            continue
        if row.get("cartella") == "ELABORATE" and row.get("esito") == "elaborato":
            elaborati += 1
        elif row.get("cartella") in {"DA VERIFICARE", "ERRORI", "DA ELABORARE"}:
            incompleti += 1
    return {"elaborati": elaborati, "incompleti": incompleti}


def _riga(
    *, key: str, domanda: str, richiesto: str, ufficiali: int = 0,
    gestionali: int = 0, drive: dict[str, int] | None = None,
    richiede_tutti: bool = False, parti_presenti: int = 0, parti_totali: int = 0,
    route: str | None = None, nota: str | None = None, forza_incompleto: bool = False,
) -> dict[str, Any]:
    drive = drive or {"elaborati": 0, "incompleti": 0}
    trovati = ufficiali + drive["elaborati"]
    parziale = gestionali + drive["incompleti"]
    completo_parti = not richiede_tutti or (parti_totali > 0 and parti_presenti == parti_totali)
    if trovati > 0 and completo_parti and drive["incompleti"] == 0 and not forza_incompleto:
        stato = ESISTENTE
        risposta = "Dato esistente nelle fonti controllate. Non va richiesto di nuovo."
    elif trovati > 0 or parziale > 0:
        stato = INCOMPLETO
        risposta = "Dato incompleto: esistono elementi, ma manca una parte o una verifica."
    else:
        stato = MANCANTE
        risposta = "Dato non trovato: chiedere al commercialista o caricare la fonte corretta."

    fonti = []
    if ufficiali:
        fonti.append({"tipo": "documento", "etichetta": "Gestionale: documento/prospetto", "conteggio": ufficiali})
    if gestionali:
        fonti.append({"tipo": "dati", "etichetta": "Gestionale: dati disponibili", "conteggio": gestionali})
    if drive["elaborati"]:
        fonti.append({"tipo": "drive", "etichetta": "Drive: ELABORATE", "conteggio": drive["elaborati"]})
    if drive["incompleti"]:
        fonti.append({"tipo": "attenzione", "etichetta": "Drive: da elaborare/verificare o errore", "conteggio": drive["incompleti"]})

    return {
        "key": key,
        "domanda": domanda,
        "richiesto": richiesto,
        "stato": stato,
        "risposta": risposta,
        "fonti": fonti,
        "route": route,
        "nota": nota,
        "parti": {"presenti": parti_presenti, "totali": parti_totali} if parti_totali else None,
    }

async def genera_checklist(db, anno: int, *, dal: str, al: str) -> dict[str, Any]:
    """Legge solo fonti gia' presenti; non importa, sposta o modifica documenti."""
    q_doc = _periodo_query(anno, dal, al, "data", "created_at", "document_date", "data_documento")
    q_mov = _periodo_query(anno, dal, al, "data", "data_registrazione", "created_at")
    q_fatt = _periodo_query(anno, dal, al, "invoice_date", "data_emissione", "data")

    async def c(nome: str, query: dict[str, Any] | None = None) -> int:
        return await _count(db, nome, query)

    # Una sola lettura del registro Drive; e' aggiornato dallo smistatore della
    # cartella unica e quindi la pagina cambia ai giri successivi senza copiare file.
    try:
        drive_rows = await db["drive_cartella_unica"].find(
            {}, {"_id": 0, "nome": 1, "tipo": 1, "cartella": 1, "esito": 1,
                 "motivo": 1, "percorso_categoria": 1}
        ).to_list(None)
    except Exception:
        drive_rows = []

    # Lo storico precedente alla cartella unica vive nell'indice documentale
    # Drive. Il caricamento e' read-only e cacheato per ID+modifiedTime; se la
    # credenziale o l'indice non sono disponibili, il registro operativo resta
    # comunque utilizzabile e la checklist non blocca il resto della pagina.
    try:
        from app.services.drive_document_index import load_catalog

        _, indexed = await asyncio.to_thread(load_catalog)
        for record in indexed:
            stato = str(record.get("status") or "").strip().casefold().replace("_", " ")
            incompleto = stato in {"da verificare", "errore", "da elaborare"}
            drive_rows.append({
                "nome": record.get("filename"),
                "tipo": record.get("category") or record.get("domain"),
                "cartella": "DA VERIFICARE" if incompleto else "ELABORATE",
                "esito": "errore" if incompleto else "elaborato",
                "motivo": record.get("status"),
                "anno_indice": record.get("year"),
                "percorso_categoria": [record.get("drive_path")],
            })
    except Exception:
        logger.warning(
            "Indice documentale Drive non disponibile: la checklist usa solo il registro operativo",
            exc_info=True,
        )

    counts = dict(zip(
        (
            "dichiarazioni", "lipe", "liquidazioni_iva", "f24", "quietanze",
            "documenti_comm", "movimenti", "fornitori", "fatture_ricevute",
            "fatture_emesse", "cespiti", "cespiti_dv", "mutui_piani",
            "mutui_quietanze", "rimanenze", "magazzino", "cedolini",
            "calendario", "anomalie", "obblighi", "crediti", "scadenze_fornitori",
        ),
        await asyncio.gather(
            c("fiscal_documents", {"$and": [q_doc, {"$or": [
                {"document_type": {"$in": ["dichiarazione_fiscale", "dichiarazione_iva", "dichiarazione_redditi", "dichiarazione_irap", "isa"]}},
                {"category": {"$in": ["dichiarazione_fiscale", "dichiarazione_iva", "dichiarazione_redditi", "dichiarazione_irap", "isa"]}},
                {"tipo": {"$in": ["dichiarazione_fiscale", "dichiarazione_iva", "dichiarazione_redditi", "dichiarazione_irap", "isa"]}},
            ]}]}),
            c("lipe_periodi", {"$or": [{"anno": anno}, {"anno": str(anno)}]}),
            c("liquidazioni_iva", {"$or": [{"anno": anno}, {"anno": str(anno)}]}),
            c("f24_unificato", q_doc),
            c("quietanze_f24", q_doc),
            c("documenti_commercialista", q_doc),
            c("movimenti_contabili", q_mov),
            c("fornitori", {}),
            c("invoices", q_fatt),
            c("fatture_emesse", q_fatt),
            c("cespiti", {"data_acquisto": {"$lte": al + "~"}}),
            c("cespiti", {"$or": [{"stato": "da_verificare"}, {"data_entrata_funzione": {"$in": [None, ""]}}]}),
            c("mutui_piani_documentali", {}),
            c("mutui_quietanze", q_doc),
            c("rimanenze", {"$or": [{"anno": anno}, {"anno": str(anno)}]}),
            c("warehouse_inventory", {}),
            c("cedolini", q_doc),
            c("calendario_fiscale", q_doc),
            c("administrative_anomalies", {"status": {"$nin": ["resolved", "risolta", "chiusa"]}}),
            c("tax_obligations", q_doc),
            c("tax_credit_ledger", q_doc),
            c("scadenziario_fornitori", q_doc),
        ),
    ))

    def d(*patterns: str) -> dict[str, int]:
        return _drive_matches(drive_rows, patterns, anno)

    dichiarazioni_drive = d(r"dichiaraz", r"redditi", r"irap", r"\bisa\b")
    lipe_drive = d(r"\blipe\b", r"dichiarazione\s+iva")
    registri_drive = d(r"registr[oi].*iva", r"liquidazion[ei].*iva")
    f24_drive = d(r"\bf\s*24\b", r"quietanz")
    bilancino_drive = d(r"bilancino", r"situazione\s+contabile", r"bilancio")
    mastri_drive = d(r"mastr[oi]")
    giornale_drive = d(r"libro\s+giornale")
    partitario_drive = d(r"situazione.*client", r"situazione.*fornitor", r"partitari[oi]")
    cespiti_drive = d(r"cespit", r"ammortament")
    mutui_drive = d(r"mutu[oi]", r"finanziament")
    rimanenze_drive = d(r"rimanenz", r"inventari[oi]")
    cu_drive = d(r"certificazione\s+unica", r"\bcu\b")
    d770_drive = d(r"\b770\b")
    inps_drive = d(r"\binps\b")
    uniemens_drive = d(r"uniemens")
    inail_drive = d(r"\binail\b")
    calendario_drive = d(r"calendario.*fiscal", r"scadenz")
    debiti_drive = d(r"debiti?.*fiscal", r"crediti?.*fiscal", r"situazione.*fiscal")
    imposte_drive = d(r"prospetto.*impost", r"imposte.*previs")

    righe = [
        _riga(key="dichiarazioni", domanda="Quali dichiarazioni sono state trasmesse e quali ricevute sono disponibili?",
              richiesto="Dichiarazioni trasmesse e ricevute", ufficiali=counts["dichiarazioni"], drive=dichiarazioni_drive,
              route="/documenti/archivio"),
        _riga(key="lipe_iva", domanda="Sono presenti LIPE e dichiarazione IVA per il periodo?",
              richiesto="LIPE e dichiarazioni IVA", ufficiali=counts["lipe"], gestionali=counts["liquidazioni_iva"], drive=lipe_drive,
              route="/iva", nota="La liquidazione del gestionale non sostituisce la LIPE trasmessa."),
        _riga(key="registri_iva", domanda="I registri IVA sono disponibili e aggiornati?",
              richiesto="Registri IVA", gestionali=counts["liquidazioni_iva"], drive=registri_drive, route="/iva"),
        _riga(key="f24", domanda="Per gli F24 sono presenti modello, ricevuta e quietanza?",
              richiesto="F24, ricevute e quietanze", ufficiali=counts["f24"] + counts["quietanze"], drive=f24_drive,
              richiede_tutti=True, parti_presenti=int(counts["f24"] > 0) + int(counts["quietanze"] > 0), parti_totali=2,
              route="/riconciliazione/f24", nota="Modello, ricevuta, quietanza e addebito bancario restano prove distinte."),
        _riga(key="bilancino", domanda="È disponibile un bilancino aggiornato?", richiesto="Bilancino aggiornato",
              ufficiali=bilancino_drive["elaborati"], gestionali=counts["movimenti"],
              drive={"elaborati": 0, "incompleti": bilancino_drive["incompleti"]}, route="/contabilita/bilancio"),
        _riga(key="mastri", domanda="Sono disponibili i mastri contabili?", richiesto="Mastri contabili",
              ufficiali=mastri_drive["elaborati"], gestionali=counts["movimenti"],
              drive={"elaborati": 0, "incompleti": mastri_drive["incompleti"]}, route="/contabilita/giornale"),
        _riga(key="libro_giornale", domanda="Il libro giornale è disponibile per il periodo?", richiesto="Libro giornale",
              ufficiali=giornale_drive["elaborati"], gestionali=counts["movimenti"],
              drive={"elaborati": 0, "incompleti": giornale_drive["incompleti"]}, route="/contabilita/giornale"),
        _riga(key="clienti_fornitori", domanda="La situazione clienti e fornitori è completa?",
              richiesto="Situazione clienti e fornitori", ufficiali=partitario_drive["elaborati"],
              gestionali=counts["fornitori"] + counts["fatture_ricevute"] + counts["fatture_emesse"] + counts["scadenze_fornitori"],
              drive={"elaborati": 0, "incompleti": partitario_drive["incompleti"]},
              richiede_tutti=True,
              parti_presenti=int(counts["fatture_ricevute"] > 0) + int(counts["fatture_emesse"] > 0), parti_totali=2,
              route="/contabilita/finanziaria"),
        _riga(key="cespiti", domanda="Il registro cespiti è completo e documentato?", richiesto="Registro cespiti",
              ufficiali=counts["cespiti"], gestionali=counts["cespiti_dv"], drive=cespiti_drive, route="/contabilita/cespiti",
              nota=(f"{counts['cespiti_dv']} cespiti richiedono verifica." if counts["cespiti_dv"] else None),
              forza_incompleto=counts["cespiti_dv"] > 0),
        _riga(key="mutui", domanda="Sono disponibili piani e quietanze di mutui e finanziamenti?",
              richiesto="Prospetto mutui e finanziamenti", ufficiali=counts["mutui_piani"] + counts["mutui_quietanze"], drive=mutui_drive,
              richiede_tutti=True, parti_presenti=int(counts["mutui_piani"] > 0) + int(counts["mutui_quietanze"] > 0), parti_totali=2,
              route="/contabilita/mutui"),
        _riga(key="rimanenze", domanda="Inventario e rimanenze risultano valorizzati?", richiesto="Inventario e rimanenze",
              ufficiali=counts["rimanenze"], gestionali=counts["magazzino"], drive=rimanenze_drive, route="/lotti#magazzino_prodotti"),
        _riga(key="cu_770", domanda="Sono disponibili CU e modello 770?", richiesto="CU e 770",
              ufficiali=cu_drive["elaborati"] + d770_drive["elaborati"],
              drive={"elaborati": 0, "incompleti": cu_drive["incompleti"] + d770_drive["incompleti"]},
              richiede_tutti=True, parti_presenti=int(cu_drive["elaborati"] > 0) + int(d770_drive["elaborati"] > 0),
              parti_totali=2, route="/documenti/archivio"),
        _riga(key="inps_uniemens_inail", domanda="Sono disponibili i prospetti INPS, UNIEMENS e INAIL?",
              richiesto="Prospetti INPS, UNIEMENS e INAIL",
              ufficiali=inps_drive["elaborati"] + uniemens_drive["elaborati"] + inail_drive["elaborati"],
              gestionali=counts["cedolini"],
              drive={"elaborati": 0, "incompleti": inps_drive["incompleti"] + uniemens_drive["incompleti"] + inail_drive["incompleti"]},
              richiede_tutti=True,
              parti_presenti=int(inps_drive["elaborati"] > 0) + int(uniemens_drive["elaborati"] > 0) + int(inail_drive["elaborati"] > 0),
              parti_totali=3, route="/hr/"),
        _riga(key="scadenze", domanda="Il calendario delle prossime scadenze è aggiornato?",
              richiesto="Calendario delle prossime scadenze", ufficiali=counts["calendario"], drive=calendario_drive,
              route="/contabilita/calendario"),
        _riga(key="anomalie", domanda="Quali anomalie o documenti mancanti restano aperti?",
              richiesto="Elenco anomalie e documenti mancanti", ufficiali=counts["anomalie"],
              gestionali=sum(1 for r in drive_rows if r.get("cartella") in {"DA VERIFICARE", "ERRORI", "DA ELABORARE"}),
              route="/dashboard/alerts", nota="Zero righe non prova da solo che il controllo sia stato completato."),
        _riga(key="debiti_crediti", domanda="Quali debiti e crediti fiscali risultano documentati?",
              richiesto="Elenco debiti e crediti fiscali", ufficiali=counts["obblighi"] + counts["crediti"], drive=debiti_drive,
              richiede_tutti=True, parti_presenti=int(counts["obblighi"] > 0) + int(counts["crediti"] > 0), parti_totali=2,
              route="/situazione-fiscale"),
        _riga(key="imposte_previste", domanda="Qual è il prospetto aggiornato delle imposte previste?",
              richiesto="Prospetto delle imposte previste", ufficiali=imposte_drive["elaborati"], gestionali=counts["movimenti"],
              drive={"elaborati": 0, "incompleti": imposte_drive["incompleti"]}, route="/contabilita/avanzata",
              nota="Il calcolo gestionale è una previsione finché non viene validato."),
    ]

    riepilogo = {ESISTENTE: 0, INCOMPLETO: 0, MANCANTE: 0}
    for riga in righe:
        riepilogo[riga["stato"]] += 1
    return {
        "anno": anno, "dal": dal, "al": al,
        "aggiornato_il": datetime.now(timezone.utc).isoformat(),
        "regola": "Prima si controllano Gestionale e Drive; si chiede al commercialista solo ciò che manca o è incompleto.",
        "riepilogo": riepilogo,
        "items": righe,
    }
