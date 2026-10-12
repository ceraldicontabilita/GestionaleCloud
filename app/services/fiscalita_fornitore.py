"""Memoria fiscale del fornitore e valutazione IVA della singola fattura.

Il JSON versionato è una sorgente da importare esplicitamente, non un secondo
archivio usato all'import delle fatture. Il dato operativo vive solo in
``Collections.SUPPLIERS.profilo_fiscale``. Attività e ATECO non determinano,
da soli, una percentuale IVA; IRES/IRAP restano nel loro motore separato.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from app.database import Collections
from app.services.piva_validazione import normalizza_piva, piva_valida


MEMORIA_PATH = Path(__file__).resolve().parents[1] / "data" / "profili_fiscali_fornitori.json"
CAMPI_PIVA = ("partita_iva", "piva", "vat_number", "vat")
STATI_LIQUIDAZIONE_CHIUSA = {"CONFERMATA", "CHIUSA", "CONCLUSA"}
REGOLA_VERSIONE = 1
VALIDITA_REGOLE_CONDIZIONALI = {"dal": "2026-01-01", "al": "2026-12-31"}


def carica_memoria(path: Optional[Path] = None) -> Dict[str, Any]:
    """Legge la sorgente versionata; non legge rete e non modifica il database."""
    data = json.loads(Path(path or MEMORIA_PATH).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("versione") != 1:
        raise ValueError("Versione della memoria fiscale non supportata")
    if not isinstance(data.get("profili"), list) or any(
        not isinstance(p, dict) for p in data["profili"]
    ):
        raise ValueError("La memoria fiscale deve contenere una lista di profili")
    return data


def _piva_record(record: Dict[str, Any]) -> str:
    return normalizza_piva(next((record.get(k) for k in CAMPI_PIVA if record.get(k)), ""))


def _attivo(record: Dict[str, Any]) -> bool:
    return not record.get("merged_into") and not record.get("deleted_at") and not record.get("deleted")


def _nome_esatto(value: Any) -> str:
    # Nessuna rimozione della forma societaria, nessun alias/fuzzy matching.
    return " ".join(str(value or "").upper().split())


def _cf(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _corrisponde_gruppo(record: Dict[str, Any], profilo: Dict[str, Any]) -> bool:
    if not profilo.get("gruppo_iva"):
        return True
    cf = _cf(profilo.get("codice_fiscale"))
    nome = _nome_esatto(profilo.get("nome"))
    nome_record = _nome_esatto(record.get("ragione_sociale") or record.get("nome") or record.get("name"))
    return bool(cf and nome and _cf(record.get("codice_fiscale")) == cf and nome_record == nome)


def _fingerprint(value: Dict[str, Any]) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _id_record(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if record.get("_id") is not None:
        return {"_id": record["_id"]}
    if record.get("id") is not None:
        return {"id": record["id"]}
    return None


async def importa_memoria(db, dry_run: bool = True) -> Dict[str, Any]:
    """Anteprima/applicazione idempotente ai soli fornitori già esistenti.

    P.IVA valida ed esatta, senza togliere zeri iniziali. Doppioni attivi,
    gruppi IVA non disambiguati e profili confermati dall'utente non vengono
    sovrascritti. Non crea fornitori, fatture o scritture contabili.
    """
    memoria = carica_memoria()
    records = await db[Collections.SUPPLIERS].find({}).to_list(None)
    records = [r for r in records if _attivo(r)]
    report = {"dry_run": dry_run, "totale": len(memoria["profili"]), "abbinate": 0,
              "da_aggiornare": 0, "aggiornate": 0, "invariate": 0, "protette": 0,
              "non_trovate": 0, "conflitti": 0, "dettagli": []}
    identita = [(normalizza_piva(p.get("partita_iva")), _cf(p.get("codice_fiscale"))
                 if p.get("gruppo_iva") else "") for p in memoria["profili"]]
    for indice, sorgente in enumerate(memoria["profili"]):
        piva, _ = identita[indice]
        dettaglio = {"partita_iva": piva, "nome": sorgente.get("nome"), "supplier_id": None}
        report["dettagli"].append(dettaglio)
        if not piva_valida(piva) or identita.count(identita[indice]) != 1:
            report["conflitti"] += 1
            dettaglio.update(esito="conflitto", motivo="P.IVA non valida o identità duplicata nella memoria")
            continue
        candidati = [r for r in records if _piva_record(r) == piva and _corrisponde_gruppo(r, sorgente)]
        if not candidati:
            report["non_trovate"] += 1
            dettaglio.update(esito="non_trovato", motivo="Nessun fornitore con la stessa identità fiscale esatta")
            continue
        if len(candidati) != 1 or _id_record(candidati[0]) is None:
            report["conflitti"] += 1
            dettaglio.update(esito="conflitto", motivo="Identità fiscale ambigua nell'anagrafica")
            continue
        record = candidati[0]
        dettaglio["supplier_id"] = record.get("id")
        report["abbinate"] += 1
        attuale = record.get("profilo_fiscale") or {}
        if attuale.get("confermato_da"):
            report["protette"] += 1
            dettaglio.update(esito="protetto", motivo="Profilo confermato dall'utente: mantenuto")
            continue
        if attuale.get("partita_iva") and normalizza_piva(attuale["partita_iva"]) != piva:
            report["conflitti"] += 1
            dettaglio.update(esito="conflitto", motivo="Il profilo esistente riporta un'altra P.IVA")
            continue
        profilo = deepcopy(sorgente)
        profilo["partita_iva"] = piva
        if "riferimenti_normativi" not in profilo and memoria.get("riferimenti_normativi"):
            profilo["riferimenti_normativi"] = deepcopy(memoria["riferimenti_normativi"])
        profilo["memoria_versione"] = memoria["versione"]
        profilo["memoria_fingerprint"] = _fingerprint(profilo)
        confronto = {k: v for k, v in attuale.items() if k != "importato_il"}
        if confronto == profilo:
            report["invariate"] += 1
            dettaglio.update(esito="invariato", motivo="Profilo già presente")
            continue
        report["da_aggiornare"] += 1
        dettaglio.update(esito="da_aggiornare", motivo="Profilo da importare nell'anagrafica")
        if not dry_run:
            profilo["importato_il"] = datetime.now(timezone.utc).isoformat()
            filtro = _id_record(record)
            # Compare-and-set: protegge una conferma/manuale o un cambio di
            # identità avvenuti durante l'anteprima/applicazione.
            filtro.update({"profilo_fiscale": record.get("profilo_fiscale"),
                           "merged_into": record.get("merged_into")})
            campo_piva = next(k for k in CAMPI_PIVA if record.get(k))
            filtro[campo_piva] = record[campo_piva]
            esito = await db[Collections.SUPPLIERS].update_one(filtro, {"$set": {"profilo_fiscale": profilo}})
            if getattr(esito, "matched_count", 0):
                report["aggiornate"] += 1
                dettaglio.update(esito="aggiornato", motivo="Profilo importato")
            else:
                report["conflitti"] += 1
                dettaglio.update(esito="conflitto", motivo="Anagrafica cambiata durante l'applicazione")
    return report


async def risolvi_profilo(db, fattura: Dict[str, Any]) -> Dict[str, Any]:
    """Consulta solo il master: non applica il JSON e non usa il nome fuzzy."""
    fornitore = fattura.get("fornitore") or {}
    if not isinstance(fornitore, dict):
        fornitore = {}
    valori = [fattura.get("supplier_vat"), fattura.get("fornitore_piva"), fornitore.get("partita_iva")]
    pive = {normalizza_piva(v) for v in valori if v}
    risultato = {"stato": "assente", "partita_iva": next(iter(pive), None),
                 "supplier_id": None, "profilo": None, "motivo": "Profilo fiscale non presente"}
    if len(pive) > 1:
        return {**risultato, "stato": "da_verificare", "motivo": "Identità fiscali discordanti nella fattura"}
    if not pive or not piva_valida(next(iter(pive))):
        return {**risultato, "motivo": "P.IVA assente/non valida: nessun profilo applicabile"}
    piva = next(iter(pive))
    forme = [piva, "IT" + piva] if piva.isdigit() else [piva]
    query = {"$or": [{k: {"$in": forme}} for k in CAMPI_PIVA]}
    records = await db[Collections.SUPPLIERS].find(query).to_list(None)
    records = [r for r in records if _attivo(r) and _piva_record(r) == piva]
    sid = fattura.get("supplier_id") or fattura.get("fornitore_id")
    if sid is not None:
        from app.utils.id_fattura import filtro_id
        collegato = await db[Collections.SUPPLIERS].find_one(filtro_id(sid))
        if collegato and _attivo(collegato):
            if _piva_record(collegato) != piva:
                return {**risultato, "stato": "da_verificare", "motivo": "ID fornitore e P.IVA della fattura non corrispondono"}
            if not any(str(r.get("id")) == str(collegato.get("id")) for r in records):
                records.append(collegato)
    candidati = []
    for record in records:
        profilo = record.get("profilo_fiscale") or {}
        if profilo.get("gruppo_iva"):
            cf_doc = _cf(fattura.get("supplier_cf") or fattura.get("fornitore_cf") or fornitore.get("codice_fiscale"))
            nome_doc = _nome_esatto(fattura.get("supplier_name") or fattura.get("fornitore_ragione_sociale") or fornitore.get("ragione_sociale"))
            if not cf_doc or cf_doc != _cf(profilo.get("codice_fiscale")) or nome_doc != _nome_esatto(profilo.get("nome")):
                continue
        candidati.append(record)
    if len(candidati) != 1:
        if records:
            return {**risultato, "stato": "da_verificare", "motivo": "P.IVA ambigua o gruppo IVA senza identità documentata"}
        return risultato
    record = candidati[0]
    if sid is not None and str(sid) != str(record.get("id")):
        return {**risultato, "stato": "da_verificare", "motivo": "ID fornitore e P.IVA della fattura non corrispondono"}
    risultato["supplier_id"] = record.get("id")
    profilo = record.get("profilo_fiscale")
    if not isinstance(profilo, dict):
        return risultato
    if normalizza_piva(profilo.get("partita_iva")) != piva:
        return {**risultato, "stato": "da_verificare", "motivo": "Profilo fiscale con P.IVA discordante"}
    if profilo.get("stato") == "verificato" and profilo.get("identita_verificata") is False:
        return {**risultato, "stato": "da_verificare", "motivo": "Profilo verificato con identità fiscale dichiarata non verificata"}
    return {**risultato, "stato": "risolto", "profilo": deepcopy(profilo), "motivo": None}


async def motivo_fattura_protetta(db, fattura: Dict[str, Any]) -> Optional[str]:
    """Le decisioni manuali e le liquidazioni chiuse non si riclassificano."""
    if fattura.get("iva_utilizzata") is True or fattura.get("stato_detrazione_iva") in {
        "INSERITA_IN_LIQUIDAZIONE", "RECUPERATA_IN_DICHIARAZIONE_ANNUALE",
    }:
        return "IVA già utilizzata"
    if fattura.get("liquidazione_id"):
        liquidazione = await db["liquidazioni_iva"].find_one({"id": fattura["liquidazione_id"]})
    else:
        periodo = fattura.get("periodo_iva_utilizzato") or fattura.get("periodo_iva_attribuito")
        liquidazione = (await db["liquidazioni_iva"].find_one(
            {"periodo": periodo}, sort=[("versione", -1)]) if periodo else None)
    if liquidazione and str(liquidazione.get("stato") or "").upper() in STATI_LIQUIDAZIONE_CHIUSA:
        return "Liquidazione del periodo chiusa: riapertura necessaria"
    if fattura.get("classificazione_manuale") or fattura.get("classificato_da") == "manuale":
        return "Classificazione confermata manualmente"
    if fattura.get("stato_detrazione_iva") in {"INDETRAIBILE", "ESCLUSA", "RINVIATA"}:
        return "Trattamento IVA confermato manualmente"
    return None


def _data(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _valido_nel_periodo(profilo: Dict[str, Any], data_doc: Optional[date]) -> bool:
    validita = profilo.get("validita_fiscale") or {}
    dal, al = _data(validita.get("dal")), _data(validita.get("al"))
    return bool(data_doc and dal and data_doc >= dal and (al is None or data_doc <= al))


def _identita_documentata(profilo: Dict[str, Any]) -> bool:
    piva = normalizza_piva(profilo.get("partita_iva"))
    if profilo.get("identita_verificata") is not True or not piva_valida(piva):
        return False
    for fonte in profilo.get("fonti") or []:
        if not isinstance(fonte, dict):
            continue
        primaria = fonte.get("primaria") is True or fonte.get("tipo") == "primaria"
        evidenza = re.sub(r"[\s.\-/]", "", str(fonte.get("evidenza") or "").upper())
        if (primaria and fonte.get("url") and _data(fonte.get("verificata_il"))
                and re.search(r"(?<!\d)" + re.escape(piva) + r"(?!\d)", evidenza)):
            return True
    return False


def _contesto_documentato(fattura: Dict[str, Any], data_doc: Optional[date]) -> Dict[str, Any]:
    contesto = fattura.get("contesto_fiscale_iva") or {}
    if not isinstance(contesto, dict) or not contesto.get("confermato_da") or not contesto.get("fonte_documento"):
        return {}
    return contesto if _valido_nel_periodo(contesto, data_doc) else {}


def adatta_classificazione_al_profilo(
    fattura: Dict[str, Any], risoluzione: Dict[str, Any], descrizione: str,
    righe: List[Dict[str, Any]], classificazione,
):
    """Fallback merceologico del master solo quando il contenuto tace.

    Una categoria unica verificata sostituisce il fallback sul nome. Più
    categorie possibili non si risolvono scegliendo a caso: una vecchia
    categoria fuori gamma viene lasciata indeterminata. Segnali reali del
    contenuto restano al classificatore, mai forzati dal fornitore.
    """
    from app.services.learning_machine_cdc import (
        CENTRI_COSTO, punteggi_contenuto, risolvi_centro_costo,
    )
    profilo = risoluzione.get("profilo") or {}
    if (risoluzione.get("stato") != "risolto" or profilo.get("stato") != "verificato"
            or not _identita_documentata(profilo)
            or not _valido_nel_periodo(profilo, _data(fattura.get("invoice_date") or fattura.get("data_documento")))):
        return classificazione
    ammessi = [risolvi_centro_costo(c)[0] for c in profilo.get("centri_costo_ammessi") or []]
    ammessi = list(dict.fromkeys(c for c in ammessi if c))
    if not ammessi or punteggi_contenuto("", descrizione, righe):
        return classificazione
    if len(ammessi) == 1:
        cdc = ammessi[0]
        return cdc, CENTRI_COSTO[cdc], 0.65, "profilo_fiscale_fornitore"
    if classificazione[0] not in ammessi:
        return "99_ALTRI_COSTI", CENTRI_COSTO["99_ALTRI_COSTI"], 0.0, "profilo_fiscale_ambiguo"
    return classificazione


def _frazione(value: Any) -> Optional[Decimal]:
    try:
        numero = Decimal(str(value))
        return numero if numero.is_finite() and 0 <= numero <= 1 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def valuta_iva_fattura(
    fattura: Dict[str, Any], risoluzione: Dict[str, Any], cdc_id: str,
    cdc_config: Dict[str, Any], classificazioni_righe: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Valuta l'IVA separatamente da CDC/IRES, con una percentuale esplicita.

    La percentuale canonica è una frazione 0..1. ``None`` significa non
    deciso, mai zero. Auto e telefonia richiedono l'uso documentato; per
    beni misti/cespiti l'attività del venditore non prova l'inerenza.
    """
    profilo = risoluzione.get("profilo") or {}
    data_doc = _data(fattura.get("invoice_date") or fattura.get("data_documento"))
    audit = {"versione_regola": REGOLA_VERSIONE, "stato": "da_verificare",
             "fonte": "profilo_fiscale_fornitore" if profilo else "classificazione_documento",
             "supplier_id": risoluzione.get("supplier_id"), "partita_iva": risoluzione.get("partita_iva"),
             "memoria_fingerprint": profilo.get("memoria_fingerprint"),
             "regola_iva": profilo.get("regola_iva"), "fonti": deepcopy(profilo.get("fonti") or []),
             "riferimenti_normativi": deepcopy(profilo.get("riferimenti_normativi") or []),
             "validita_fiscale": deepcopy(profilo.get("validita_fiscale")), "motivo": None}

    def esito(pct: Optional[Decimal], motivo: str) -> Dict[str, Any]:
        audit.update(stato="valutata" if pct is not None else "da_verificare", motivo=motivo)
        importo = None
        iva_non = None
        if pct is not None:
            importo = float((iva * pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            iva_non = float((iva - Decimal(str(importo))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        return {"percentuale_detraibilita_iva": float(pct) if pct is not None else None,
                "iva_detraibile": importo, "iva_indetraibile": iva_non,
                "valutazione_fiscale_iva": deepcopy(audit), "motivo": motivo}

    try:
        iva = Decimal(str(fattura.get("iva") if fattura.get("iva") is not None else fattura.get("iva_documento")))
        if not iva.is_finite():
            raise InvalidOperation
    except (InvalidOperation, ValueError, TypeError):
        iva = Decimal(0)
        return esito(None, "IVA esposta non disponibile o non valida")
    if risoluzione.get("stato") == "da_verificare":
        return esito(None, risoluzione.get("motivo") or "Identità fiscale da verificare")
    if profilo.get("stato") == "verificato" and profilo.get("identita_verificata") is False:
        return esito(None, "Stato del profilo e verifica dell'identità fiscale discordanti")
    profilo_applicabile = True
    motivo_profilo = None
    if profilo:
        if profilo.get("stato") != "verificato" or not _identita_documentata(profilo):
            profilo_applicabile = False
            motivo_profilo = "Attività/identità del fornitore non ancora verificata"
        elif not _valido_nel_periodo(profilo, data_doc):
            profilo_applicabile = False
            motivo_profilo = "Profilo fiscale non verificato per la data della fattura"
    contesto = _contesto_documentato(fattura, data_doc)
    if contesto:
        audit["contesto_documentato"] = deepcopy(contesto)
        if contesto.get("inerente") is False:
            return esito(Decimal(0), "Acquisto non inerente documentato")
    if (fattura.get("pro_rata") is not None or fattura.get("pro_rata_applicabile") is True
            or (isinstance(fattura.get("contesto_fiscale_iva"), dict)
                and (fattura["contesto_fiscale_iva"].get("pro_rata_applicabile") is True
                     or fattura["contesto_fiscale_iva"].get("pro_rata") is not None))) and not contesto:
        return esito(None, "Pro rata segnalato ma non documentato per la data della fattura")
    if fattura.get("pro_rata") is not None:
        quota_esterna = _frazione(fattura["pro_rata"])
        quota_interna = _frazione(contesto.get("pro_rata"))
        if quota_esterna is None or quota_interna is None or quota_esterna != quota_interna:
            return esito(None, "Pro rata della fattura discordante o assente nel contesto fiscale documentato")
    if fattura.get("pro_rata_applicabile") is True and contesto.get("pro_rata_applicabile") is not True:
        return esito(None, "Applicabilità del pro rata discordante nel contesto fiscale documentato")
    if iva == 0:
        return esito(Decimal(0), "Documento senza IVA esposta")

    from app.services.learning_machine_cdc import (
        contenuto_decide_con_margine, risolvi_centro_costo,
    )
    cdc_canonico, config_static = risolvi_centro_costo(cdc_id)
    if not config_static or cdc_canonico == "99_ALTRI_COSTI":
        return esito(None, "Natura dell'acquisto non determinata")
    cdc_id = cdc_canonico
    if not profilo_applicabile:
        # Una memoria ancora da verificare non invalida una prova reale
        # del documento. Per il fallback serve contenuto inequivoco di OGNI
        # riga, senza inferenza dal nome/ATECO o dalla sola testata.
        linee = fattura.get("linee") or fattura.get("righe_linee") or []
        if not linee or not classificazioni_righe or len(classificazioni_righe) != len(linee) or not all(
            isinstance(r, dict) and contenuto_decide_con_margine("", "", [r]) for r in linee
        ):
            return esito(None, motivo_profilo)
        audit.update(fonte="classificazione_documento", profilo_applicato=False,
                     motivo_profilo_non_applicato=motivo_profilo)
        profilo = {}
    ammessi = profilo.get("centri_costo_ammessi") or []
    if ammessi and cdc_id not in ammessi and cdc_config.get("codice") not in ammessi:
        return esito(None, "Contenuto della fattura non coerente con il profilo del fornitore")
    pct_cdc = _frazione(cdc_config.get("detraibilita_iva"))
    righe = classificazioni_righe or []
    for riga in righe:
        riga_canonica, config_riga = risolvi_centro_costo(riga.get("centro_costo_id") or "")
        pct_riga = _frazione(config_riga.get("detraibilita_iva")) if config_riga else None
        if not config_riga or riga_canonica == "99_ALTRI_COSTI":
            return esito(None, "Natura di una riga non determinata: trattamento IVA da verificare")
        if pct_riga is not None and pct_cdc is not None and pct_riga != pct_cdc:
            return esito(None, "Righe con trattamento IVA diverso: valutazione separata necessaria")

    regola = profilo.get("regola_iva") or "ordinaria_documento"
    condizionale = (regola in {"telefonia", "noleggio_veicoli"}
                   or cdc_id in {"10.1_TELEFONIA", "6.1_NOLEGGIO_AUTO", "6.2_CARBURANTE", "6.4_MANUTENZIONE_AUTO"}
                   or contesto.get("pro_rata_applicabile") is True)
    if condizionale:
        audit["validita_regole_condizionali"] = deepcopy(VALIDITA_REGOLE_CONDIZIONALI)
        if not _valido_nel_periodo({"validita_fiscale": VALIDITA_REGOLE_CONDIZIONALI}, data_doc):
            return esito(None, "Regola IVA condizionale verificata per il 2026: data fuori periodo, verifica normativa necessaria")
    testo = " ".join(str(r.get("descrizione") or r.get("description") or "")
                     for r in (fattura.get("linee") or fattura.get("righe_linee") or []) if isinstance(r, dict)).lower()
    if regola == "merci_attivita":
        if not cdc_id.startswith("1.") or pct_cdc != 1 or not testo:
            return esito(None, "Profilo merci: contenuto della fattura da verificare")
        if re.search(r"\b(omaggio|omaggi|rappresentanza|autovettura|telefonia|cellulare)\b|uso personale", testo):
            return esito(None, "Riga con trattamento fiscale particolare: verifica necessaria")
        pct = Decimal(1)
    elif regola == "telefonia" or cdc_id == "10.1_TELEFONIA":
        pct = _frazione(contesto.get("percentuale_utilizzo_aziendale"))
        if contesto.get("inerente") is not True or pct is None:
            return esito(None, "Telefonia: quota di utilizzo aziendale non documentata; nessun 50% automatico")
    elif regola == "noleggio_veicoli" or cdc_id in {"6.1_NOLEGGIO_AUTO", "6.2_CARBURANTE", "6.4_MANUTENZIONE_AUTO"}:
        if contesto.get("inerente") is not True or contesto.get("tipo_veicolo") != "autovettura":
            return esito(None, "Veicolo e inerenza non documentati: IVA da verificare")
        uso = contesto.get("uso_veicolo")
        if uso == "promiscuo":
            pct = Decimal("0.4")
        elif uso == "esclusivo":
            pct = Decimal(1)
        else:
            return esito(None, "Utilizzo del veicolo non documentato: nessun 40%/100% automatico")
    elif regola in {"beni_servizi_misti", "cespiti", "ordinaria"}:
        if contesto.get("inerente") is not True or pct_cdc != 1 or not testo:
            return esito(None, "Attività del fornitore insufficiente: documentare natura e inerenza dell'acquisto")
        if not righe or (regola != "cespiti" and any(r.get("richiede_verifica") for r in righe)):
            return esito(None, "Righe dell'acquisto non ancora classificate con certezza")
        pct = Decimal(1)
    elif regola == "ordinaria_documento":
        # Compatibilità per fornitori senza memoria: non si usa ATECO né un
        # profilo incerto. Le categorie condizionali sono già escluse sopra.
        if pct_cdc is None:
            return esito(None, "Nessuna regola IVA determinata per il documento")
        pct = pct_cdc
    else:
        return esito(None, "Regola fiscale del fornitore da verificare")

    if contesto.get("pro_rata_applicabile") is True:
        pro_rata = _frazione(contesto.get("pro_rata"))
        if pro_rata is None:
            return esito(None, "Pro rata applicabile ma percentuale non documentata")
        pct *= pro_rata
    elif "pro_rata" in contesto:
        return esito(None, "Applicabilità del pro rata non confermata")
    return esito(pct, "IVA valutata dal documento e dalle condizioni fiscali disponibili")
