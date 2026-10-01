"""
RITENUTE D'ACCONTO — richiesta utente 18/07/2026.

"Tra le fatture se trovi RT01 Ritenuta persone fisiche devi crearmi una
sezione ritenute: nella fattura c'è un importo, lo memorizzi e mi ricordi
che è da pagare entro il giorno 16 del mese successivo. La commercialista
invia un F24 con codice tributo 1040: lo trovi e lo associ. Se l'importo è
pagato leggendo l'estratto conto, riconcili con flag pagato alla scadenza;
altrimenti scrivi la data reale di pagamento. Se il pagamento non è
puntuale, guarda se nell'F24 c'è il codice tributo del ravvedimento e
scrivi 'pagato con ravvedimento'."

Flusso: la fattura XML con DatiRitenuta (RT01 persone fisiche / RT02
società) genera una riga in `ritenute_acconto` con scadenza il 16 del mese
successivo alla data fattura. La riconciliazione cerca l'F24 con codice
1040 e stesso importo, ne legge lo stato di pagamento (quietanza/estratto
conto — mai ricostruito, come da SPECIFICA F24) e classifica: puntuale,
con ravvedimento (codici 8906 sanzione + 1989 interessi), in ritardo senza
ravvedimento (alert).
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from app.database import Database
from app.utils.error_handler import handle_errors
from app.constants.codici_ravvedimento import CODICI_RAVVEDIMENTO
from app.services.f24_payment_evidence import stato_evidenza_pagamento
from app.services.f24_canonico import normalizza_righe_tributo
from app.services.payment_allocation_validator import to_cents

logger = logging.getLogger(__name__)
router = APIRouter()

COLLECTION = "ritenute_acconto"

# Ravvedimento operoso per ritenute (fonte: Agenzia delle Entrate,
# risoluzioni sui codici tributo; logica art. 13 D.Lgs. 472/1997):
# la sanzione ridotta e gli interessi legali si versano nello STESSO F24
# del tributo tardivo, con codici dedicati.
CODICI_RAVVEDIMENTO_RITENUTE = {
    "8906": "Sanzione pecuniaria sostituti d'imposta (ravvedimento su ritenute, es. 1040)",
    "8948": "Sanzione ravvedimento ritenute su redditi di lavoro autonomo",
    "1989": "Interessi sul ravvedimento - IRPEF e ritenute",
}
LOGICA_RAVVEDIMENTO = (
    "Ravvedimento operoso (art. 13 D.Lgs. 472/1997): se la ritenuta non è "
    "versata entro il 16 del mese successivo, si può regolarizzare pagando "
    "il tributo (1040) più la sanzione ridotta (codice 8948 per lavoro "
    "autonomo; 8906 nei flussi storici) e gli "
    "interessi legali (codice 1989) nello stesso F24. Sanzione ridotta: "
    "0,083%/giorno fino a 14 giorni (ravvedimento sprint), 1,25% entro 30 "
    "giorni, 1,39% entro 90 giorni, 3,125% entro 1 anno."
)

TIPI_RITENUTA = {"RT01": "Ritenuta persone fisiche", "RT02": "Ritenuta persone giuridiche"}


def _euro_string(cents: int) -> str:
    value = int(cents or 0)
    sign = "-" if value < 0 else ""
    value = abs(value)
    return f"{sign}{value // 100}.{value % 100:02d}"


def _scadenza_16_mese_successivo(data_iso: str) -> str:
    anno, mese = int(data_iso[:4]), int(data_iso[5:7])
    mese += 1
    if mese == 13:
        mese, anno = 1, anno + 1
    return f"{anno}-{mese:02d}-16"


def _scadenze_ritenuta(data_iso: str) -> Dict[str, Any]:
    from app.services.fiscal_deadlines import monthly_deadline

    return monthly_deadline(int(data_iso[:4]), int(data_iso[5:7]))


def _isola_body_xml(xml_raw: str, body_index: int) -> str:
    """Isola il testo del body_index-esimo <FatturaElettronicaBody> dentro
    xml_raw. Un file FatturaPA raggruppato condivide lo stesso xml_raw fra
    più fatture (vedi xml_body_index): senza isolare il body giusto, una
    fattura SENZA ritenuta poteva ereditare la <DatiRitenuta> di un'altra
    fattura nello stesso file (bug reale, review Codex PR #71). Stesso
    stile regex tollerante del resto del modulo (NON un parse XML vero:
    xml_raw può derivare da un .p7m "sporco")."""
    # Prefisso di namespace opzionale (es. <p:FatturaElettronicaBody>,
    # <ns2:FatturaElettronicaBody>): xml_raw è il testo ORIGINALE non
    # ripulito (a differenza della copia di lavoro del parser, che invece
    # normalizza via clean_xml_namespaces) — un file con tag prefissati
    # senza questa tolleranza non veniva isolato affatto, facendo
    # ricomparire il bug per l'esatto caso che gli altri percorsi
    # (parser/vista XSLT) già gestiscono (bug reale, review Codex PR #71).
    blocchi = re.findall(
        r"<(?:\w+:)?FatturaElettronicaBody\b.*?</(?:\w+:)?FatturaElettronicaBody\s*>", xml_raw, re.S
    )
    if not blocchi:
        return xml_raw  # formato inatteso/singolo body: comportamento invariato
    if 0 <= body_index < len(blocchi):
        return blocchi[body_index]
    return blocchi[0]


def _estrai_dati_ritenuta(xml_raw, body_index: int = 0) -> Optional[Dict[str, Any]]:
    """Estrae DatiRitenuta dall'XML (regex: regge anche i .p7m sporchi).
    body_index seleziona il body giusto quando xml_raw è condiviso da più
    fatture di un file raggruppato."""
    if not xml_raw:
        return None
    testo = xml_raw if isinstance(xml_raw, str) else str(xml_raw)
    testo = _isola_body_xml(testo, body_index)
    blocco = re.search(r"<DatiRitenuta>(.*?)</DatiRitenuta>", testo, re.S)
    if not blocco:
        return None
    b = blocco.group(1)

    def campo(tag):
        m = re.search(rf"<{tag}>\s*([^<]+?)\s*</{tag}>", b)
        return m.group(1) if m else None

    importo_cents = to_cents(campo("ImportoRitenuta") or 0)
    if importo_cents <= 0:
        return None
    return {
        "tipo": campo("TipoRitenuta") or "RT01",
        "importo_cents": importo_cents,
        "importo": _euro_string(importo_cents),
        "aliquota": campo("AliquotaRitenuta"),
        "causale": campo("CausalePagamento"),
    }


def _tributi_di(f24: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compatibilità router sulla vista canonica delle righe F24."""
    out = [{
        "indice": row["ordinal"] - 1,
        "sezione": row["section"],
        "codice": row["tax_code"],
        "importo": _euro_string(row["debit_cents"]),
        "importo_cents": row["debit_cents"],
        "periodo": row["reference_period"],
    } for row in normalizza_righe_tributo(f24)]
    codici_presenti = {row["codice"] for row in out}
    for c in (f24.get("codici_tributo") or []):
        codice = c.get("codice") if isinstance(c, dict) else c
        codice = str(codice or "").strip()
        if codice and codice not in codici_presenti:
            codici_presenti.add(codice)
            out.append({
                "indice": len(out), "sezione": "codici_tributo",
                "codice": codice, "importo": None, "importo_cents": None, "periodo": None,
            })
    return out


def _data_pagamento_f24(f24: Dict[str, Any]) -> Optional[str]:
    evidenza = stato_evidenza_pagamento(f24)
    data = evidenza.get("data_versamento_documentale") or evidenza.get("data_pagamento")
    return str(data)[:10] if data else None


def _periodo_ritenuta(rit: Dict[str, Any]) -> Optional[str]:
    periodo = str(rit.get("periodo_ritenuta") or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}", periodo):
        return periodo
    data = str(rit.get("data_fattura") or "")[:7]
    return data if re.fullmatch(r"\d{4}-\d{2}", data) else None


def _id_f24(f24: Dict[str, Any]) -> str:
    return str(
        f24.get("id") or f24.get("document_id") or f24.get("sha256")
        or f24.get("filename") or f24.get("file_name") or ""
    )


async def _carica_f24(db) -> List[Dict[str, Any]]:
    from app.services.tax_payment_query import TaxPaymentQueryService

    return await TaxPaymentQueryService(db).list_documents()


async def _carica_pagamenti_quietanza(db) -> List[Dict[str, Any]]:
    """Le quietanze AdE con le loro righe, una per pagamento (copie unite).

    Il commercialista non sempre manda il modello: la quietanza con il 1040
    del periodo basta come prova documentale del versamento della ritenuta.
    """
    from app.db_collections import COLL_QUIETANZE_F24
    from app.services.f24_controllo_incrociato import _quietanza_legacy, pagamenti_da_quietanze

    docs = await db[COLL_QUIETANZE_F24].find({}, {"_id": 0, "pdf_data": 0}).to_list(5000)
    quietanze = [
        _quietanza_legacy(d) for d in docs
        if d.get("entity_status") != "deleted"
        and str(d.get("status") or "").lower() not in {"eliminato", "deleted"}
    ]
    return pagamenti_da_quietanze([q for q in quietanze if q.get("righe")])


def _versato_copre(
    richiesto_cents: int, versato_cents: int, *, ravveduto: bool,
    scadenza: Optional[str], data_pagamento: Optional[str],
) -> bool:
    """La riga 1040 versata copre la ritenuta: uguale al centesimo, oppure ravveduta con gli interessi.

    Nel ravvedimento di una ritenuta gli interessi legali si cumulano al tributo (Ris. AdE 18/E del
    28/04/2023: 280,00 diventa 280,31) e la sanzione ha il suo codice. Una riga maggiore della ritenuta
    vale solo con una sanzione nello stesso periodo e se l'eccedenza e' quella degli interessi legali dalla
    scadenza al versamento (con la stessa tolleranza dello Scadenzario): mai un importo vicino qualunque.
    """
    if versato_cents == richiesto_cents:
        return True
    if not ravveduto or not scadenza or not data_pagamento:
        return False
    from app.services.scadenzario_tributi import eccedenza_da_interessi

    return eccedenza_da_interessi(richiesto_cents, versato_cents, scadenza, data_pagamento)


def _quietanze_1040(
    pagamenti: List[Dict[str, Any]], periodo: Optional[str], importo_cents: int,
    stesso_importo: int, totale_gruppo_cents: int, gruppo_multiplo: bool,
    scadenza: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Pagamenti con il 1040 del periodo che coprono la ritenuta al centesimo.

    Una riga uguale alla ritenuta (se nessun'altra ritenuta del periodo ha lo
    stesso importo), oppure le righe 1040 del periodo che sommate fanno il
    totale delle ritenute del periodo (il commercialista le raggruppa: 210 +
    490 per tre parcelle da 210, 280 e 210). Mai un importo vicino.
    """
    if not periodo or not re.fullmatch(r"\d{4}-\d{2}", periodo):
        return []
    anno, mese = int(periodo[:4]), int(periodo[5:7])
    trovati = []
    for pagamento in pagamenti:
        righe = [
            r for r in (pagamento.get("_righe") or [])
            if r.get("codice") == "1040" and r.get("anno") == anno and r.get("mese") == mese
            and int(r.get("importo_debito_cents") or 0) > 0
        ]
        if not righe:
            continue
        ravveduto = _ravveduta_da_quietanza(pagamento, periodo)

        def copre(richiesto: int, versato: int) -> bool:
            return _versato_copre(richiesto, versato, ravveduto=ravveduto, scadenza=scadenza,
                                  data_pagamento=pagamento.get("data"))

        if stesso_importo == 1 and any(copre(importo_cents, int(r["importo_debito_cents"])) for r in righe):
            trovati.append({"pagamento": pagamento, "tipo": "singola"})
        elif copre(totale_gruppo_cents, sum(int(r["importo_debito_cents"]) for r in righe)):
            trovati.append({"pagamento": pagamento, "tipo": "aggregata" if gruppo_multiplo else "singola"})
    return trovati


def _ravveduta_da_quietanza(pagamento: Dict[str, Any], periodo: str) -> bool:
    anno, mese = int(periodo[:4]), int(periodo[5:7])
    codici = set(CODICI_RAVVEDIMENTO) | set(CODICI_RAVVEDIMENTO_RITENUTE)
    return any(
        r.get("codice") in codici and r.get("anno") == anno and r.get("mese") in (mese, None)
        for r in (pagamento.get("_righe") or [])
    )


async def _riconcilia_ritenuta(
    db,
    rit: Dict[str, Any],
    *,
    ritenute_periodo: Optional[List[Dict[str, Any]]] = None,
    f24_docs: Optional[List[Dict[str, Any]]] = None,
    pagamenti_quietanza: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Associa la riga 1040 corretta, distinguendo F24 e prova bancaria.

    Una riga 1040 può coprire una sola ritenuta oppure la somma delle
    ritenute dello stesso periodo. Gli altri tributi dell'F24 non vengono
    confusi con la quota 1040 e l'addebito bancario resta prova dell'intero
    modello, non della singola ritenuta.
    """
    oggi = datetime.now(timezone.utc).date().isoformat()
    upd: Dict[str, Any] = {
        "f24_id": None,
        "f24_descrizione": None,
        "f24_tributo_indice": None,
        "f24_tributo_sezione": None,
        "f24_periodo": None,
        "f24_importo_tributo": None,
        "f24_importo_tributo_cents": None,
        "f24_associazione_tipo": None,
        "f24_quota_ritenuta": None,
        "f24_quota_ritenuta_cents": None,
        "f24_multi_tributo": False,
        "stato_evidenza_pagamento": None,
        "movimento_bancario_f24_id": None,
        "data_pagamento": None,
        "f24_candidati": [],
        "stato_obbligazione": "APERTA",
        "stato_evidenza_documentale": "NON_PRESENTE",
        "stato_banca": "NON_VERIFICATA",
        "versata_documentalmente": False,
        "quietanza_id": None,
        "quietanza_protocollo": None,
        "quietanza_data": None,
        "quietanza_pdf_url": None,
    }
    periodo = _periodo_ritenuta(rit)
    gruppo = [
        r for r in (ritenute_periodo or [rit])
        if _periodo_ritenuta(r) == periodo
    ] if periodo else [rit]
    importo_cents = int(rit.get("importo_cents") or to_cents(rit.get("importo")))
    totale_gruppo_cents = sum(
        int(r.get("importo_cents") or to_cents(r.get("importo"))) for r in gruppo
    )
    stesso_importo = sum(
        1 for r in gruppo
        if int(r.get("importo_cents") or to_cents(r.get("importo"))) == importo_cents
    )

    candidati = []
    for f24 in (f24_docs if f24_docs is not None else await _carica_f24(db)):
        for tributo in _tributi_di(f24):
            if tributo["codice"] != "1040" or tributo["importo"] is None:
                continue
            periodo_riga = tributo.get("periodo")
            if periodo and periodo_riga and periodo != periodo_riga:
                continue

            tipo = None
            ravveduto = bool(periodo_riga) and any(
                t["codice"] in set(CODICI_RAVVEDIMENTO) | set(CODICI_RAVVEDIMENTO_RITENUTE)
                and t.get("periodo") == periodo_riga for t in _tributi_di(f24))

            def copre(richiesto: int) -> bool:
                return _versato_copre(
                    richiesto, tributo["importo_cents"], ravveduto=ravveduto,
                    scadenza=rit.get("scadenza_legale") or rit.get("scadenza"),
                    data_pagamento=_data_pagamento_f24(f24))

            # Una riga senza periodo può essere usata solo per un importo
            # individuale univoco, mai per un'aggregazione mensile.
            if copre(importo_cents) and stesso_importo == 1:
                tipo = "singola"
            if (
                len(gruppo) > 1
                and periodo
                and periodo_riga == periodo
                and copre(totale_gruppo_cents)
            ):
                tipo = "aggregata"
            if not tipo:
                continue
            score = 100 + (30 if periodo_riga == periodo and periodo else 0)
            candidati.append({
                "f24": f24,
                "tributo": tributo,
                "tipo": tipo,
                "score": score,
            })

    if not candidati:
        due = rit.get("scadenza_legale") or rit["scadenza"]
        trovati = _quietanze_1040(
            pagamenti_quietanza or [], periodo, importo_cents, stesso_importo,
            totale_gruppo_cents, len(gruppo) > 1, scadenza=due,
        )
        if len(trovati) > 1:
            upd.update({
                "stato": "da_verificare_associazione_f24",
                "f24_candidati": sorted({
                    str(q.get("id")) for t in trovati for q in t["pagamento"]["quietanze"] if q.get("id")
                }),
            })
            return upd
        if len(trovati) == 1:
            pagamento = trovati[0]["pagamento"]
            prima = (pagamento.get("quietanze") or [{}])[0]
            data_pag = str(pagamento.get("data") or "")[:10] or None
            upd.update({
                "quietanza_id": prima.get("id"),
                "quietanza_protocollo": pagamento.get("protocollo"),
                "quietanza_data": data_pag,
                "quietanza_pdf_url": prima.get("pdf_url"),
                "f24_associazione_tipo": trovati[0]["tipo"],
                "f24_periodo": periodo,
                "f24_quota_ritenuta_cents": importo_cents,
                "f24_quota_ritenuta": _euro_string(importo_cents),
                "stato_evidenza_pagamento": "QUIETANZA_PRESENTE",
                "stato_evidenza_documentale": "VERSATA_DOCUMENTALMENTE",
                "versata_documentalmente": True,
                "stato_obbligazione": "VERSATA",
                "data_pagamento": data_pag,
            })
            if data_pag and data_pag <= due:
                upd["stato"] = "pagata_puntuale"
            elif _ravveduta_da_quietanza(pagamento, periodo):
                upd["stato"] = "pagata_con_ravvedimento"
            else:
                upd["stato"] = "pagata_in_ritardo_senza_ravvedimento"
            return upd
        upd["stato"] = "scaduta_da_versare" if oggi > due else "da_pagare"
        upd["f24_id"] = None
        return upd

    max_score = max(c["score"] for c in candidati)
    migliori = [c for c in candidati if c["score"] == max_score]
    identita = {
        (_id_f24(c["f24"]), c["tributo"]["indice"], c["tipo"])
        for c in migliori
    }
    if len(identita) != 1:
        upd.update({
            "stato": "da_verificare_associazione_f24",
            "f24_id": None,
            "f24_candidati": sorted({_id_f24(c["f24"]) for c in migliori if _id_f24(c["f24"])}),
        })
        return upd

    scelto = migliori[0]
    f24_match = scelto["f24"]
    tributo_1040 = scelto["tributo"]
    evidenza = stato_evidenza_pagamento(f24_match)
    upd["f24_id"] = _id_f24(f24_match)
    upd["f24_descrizione"] = (f24_match.get("descrizione") or f24_match.get("filename") or "")[:120]
    upd["f24_tributo_indice"] = tributo_1040["indice"]
    upd["f24_tributo_sezione"] = tributo_1040["sezione"]
    upd["f24_periodo"] = tributo_1040.get("periodo")
    upd["f24_importo_tributo"] = tributo_1040["importo"]
    upd["f24_importo_tributo_cents"] = tributo_1040["importo_cents"]
    upd["f24_associazione_tipo"] = scelto["tipo"]
    upd["f24_quota_ritenuta_cents"] = importo_cents
    upd["f24_quota_ritenuta"] = _euro_string(importo_cents)
    upd["f24_multi_tributo"] = len(_tributi_di(f24_match)) > 1
    upd["stato_evidenza_pagamento"] = evidenza["stato"]
    upd["movimento_bancario_f24_id"] = evidenza.get("movimento_bancario_id")
    upd["stato_evidenza_documentale"] = (
        "VERSATA_DOCUMENTALMENTE" if evidenza["versato_documentalmente"] else "NON_PRESENTE"
    )
    upd["stato_banca"] = "VERIFICATA" if evidenza["verificato_banca"] else "NON_VERIFICATA"
    upd["versata_documentalmente"] = evidenza["versato_documentalmente"]
    upd["payment_chain"] = f24_match.get("payment_chain")

    if not evidenza["versato_documentalmente"]:
        upd["stato"] = "f24_associato_da_pagare"
        return upd

    due = rit.get("scadenza_legale") or rit["scadenza"]
    data_pag = _data_pagamento_f24(f24_match) or due
    upd["data_pagamento"] = data_pag
    upd["stato_obbligazione"] = "VERSATA"
    if data_pag <= due:
        upd["stato"] = "pagata_puntuale"
    else:
        codici = {t["codice"] for t in _tributi_di(f24_match)}
        codici_quietanza = {
            str(codice) for codice in (f24_match.get("codici_ravvedimento") or [])
        }
        if (
            f24_match.get("ravveduto") is True
            or codici & set(CODICI_RAVVEDIMENTO_RITENUTE)
            or codici_quietanza & set(CODICI_RAVVEDIMENTO_RITENUTE)
        ):
            upd["stato"] = "pagata_con_ravvedimento"
        else:
            upd["stato"] = "pagata_in_ritardo_senza_ravvedimento"
    return upd


async def upsert_ritenuta_da_fattura(db, fattura: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Aggiorna la proiezione Ritenute durante l'import canonico Documenti."""
    dati = _estrai_dati_ritenuta(
        fattura.get("xml_raw"), int(fattura.get("xml_body_index") or 0),
    )
    invoice_date = str(fattura.get("invoice_date") or fattura.get("data_fattura") or "")[:10]
    fattura_id = fattura.get("id")
    if not dati or not fattura_id or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", invoice_date):
        return None
    existing = await db[COLLECTION].find_one({"fattura_id": fattura_id})
    now = datetime.now(timezone.utc).isoformat()
    document = {
        "id": existing.get("id") if existing else str(uuid.uuid4()),
        "fattura_id": fattura_id,
        "numero_fattura": fattura.get("invoice_number") or fattura.get("numero_fattura"),
        "data_fattura": invoice_date,
        "fornitore": fattura.get("supplier_name") or fattura.get("cedente_denominazione"),
        "piva": fattura.get("supplier_vat") or fattura.get("cedente_piva"),
        "tipo": dati["tipo"],
        "tipo_label": TIPI_RITENUTA.get(dati["tipo"], dati["tipo"]),
        "importo": dati["importo"],
        "importo_cents": dati["importo_cents"],
        "aliquota": dati["aliquota"],
        "causale": dati["causale"],
        "periodo_ritenuta": invoice_date[:7],
        "scadenza": _scadenza_16_mese_successivo(invoice_date),
        **_scadenze_ritenuta(invoice_date),
        "source_document_id": fattura_id,
        "projection_source": "documenti_import_auto",
        "updated_at": now,
    }
    if existing:
        await db[COLLECTION].update_one({"id": document["id"]}, {"$set": document})
    else:
        document["created_at"] = now
        await db[COLLECTION].insert_one(dict(document))
        await avvisa_ritenuta_da_versare(db, document)
    return document


def _data_it(data_iso: Optional[str]) -> str:
    testo = str(data_iso or "")[:10]
    return f"{testo[8:10]}/{testo[5:7]}/{testo[:4]}" if len(testo) == 10 else testo


def _euro_it(cents: int) -> str:
    intero, decimali = divmod(abs(int(cents or 0)), 100)
    return f"{intero:,}".replace(",", ".") + f",{decimali:02d} €"


async def avvisa_ritenuta_da_versare(db, ritenuta: Dict[str, Any]) -> None:
    """E' arrivata una parcella con ritenuta: il fatto crea subito l'attesa.

    Alert (chiuso quando l'F24 con il 1040 risulta versato) e messaggio
    Telegram. Un avviso mancato non ferma l'import della fattura.
    """
    scadenza = ritenuta.get("scadenza_legale") or ritenuta.get("scadenza")
    dettaglio = (
        f"Parcella {ritenuta.get('numero_fattura') or '?'} di "
        f"{ritenuta.get('fornitore') or 'fornitore sconosciuto'} del "
        f"{_data_it(ritenuta.get('data_fattura'))}: ritenuta d'acconto "
        f"{_euro_it(ritenuta.get('importo_cents'))} da versare con F24, codice 1040, "
        f"entro il {_data_it(scadenza)}."
    )
    try:
        from app.services.alert_engine import genera_alert

        alert = await genera_alert(
            "RITENUTA_DA_VERSARE", str(ritenuta["fattura_id"]), "invoices", dettaglio, db,
            extra={"ritenuta_id": ritenuta.get("id"), "scadenza": scadenza,
                   "importo_cents": ritenuta.get("importo_cents"), "codice_tributo": "1040"},
        )
    except Exception as exc:
        logger.warning("Alert ritenuta non creato per la fattura %s (%s): %s",
                       ritenuta.get("numero_fattura"), type(exc).__name__, exc)
        return
    if not alert:
        return
    try:
        from app.services.telegram_notifications import send_notification

        await send_notification(f"<b>Ritenuta da versare</b>\n{dettaglio}")
    except Exception as exc:
        logger.warning("Telegram ritenuta non inviato per la fattura %s (%s): %s",
                       ritenuta.get("numero_fattura"), type(exc).__name__, exc)


async def _chiudi_avviso_se_versata(db, ritenuta: Dict[str, Any], upd: Dict[str, Any]) -> None:
    if upd.get("stato_obbligazione") != "VERSATA" or not ritenuta.get("fattura_id"):
        return
    from app.services.alert_engine import risolvi_alert

    await risolvi_alert("RITENUTA_DA_VERSARE", str(ritenuta["fattura_id"]), db,
                        resolved_by="f24_1040_versato")


# Oltre questi giorni un versamento scoperto adesso e' storia: si segna senza
# mandare un messaggio per ogni parcella dei mesi passati.
GIORNI_AVVISO_VERSAMENTO = 45


def testo_ritenuta_versata(ritenuta: Dict[str, Any], upd: Dict[str, Any]) -> str:
    """La ritenuta e' pagata: fattura, importo, quando, come e con quale documento."""
    esito = {
        "pagata_puntuale": "nei termini",
        "pagata_con_ravvedimento": "in ritardo, con ravvedimento",
        "pagata_in_ritardo_senza_ravvedimento": "in ritardo, senza ravvedimento",
    }.get(upd.get("stato"), "")
    if upd.get("quietanza_protocollo"):
        prova = f"quietanza AdE protocollo {upd['quietanza_protocollo']}"
    elif upd.get("f24_descrizione") or upd.get("f24_id"):
        prova = f"F24 {upd.get('f24_descrizione') or upd.get('f24_id')}"
    else:
        prova = "F24"
    return (
        f"Ritenuta d'acconto {_euro_it(ritenuta.get('importo_cents'))} della parcella "
        f"{ritenuta.get('numero_fattura') or '?'} di {ritenuta.get('fornitore') or 'fornitore sconosciuto'} "
        f"(periodo {str(upd.get('f24_periodo') or ritenuta.get('periodo_ritenuta') or '')}): "
        f"versata il {_data_it(upd.get('data_pagamento'))} {esito}, codice 1040, {prova}."
    ).replace("  ", " ")


async def _avvisa_se_appena_versata(db, ritenuta: Dict[str, Any], upd: Dict[str, Any]) -> None:
    """Al primo riscontro del versamento: segna la ritenuta e avvisa su Telegram.

    Una volta sola per ritenuta (``avviso_versamento_at``). Un versamento
    vecchio scoperto ora si segna in silenzio.
    """
    if upd.get("stato_obbligazione") != "VERSATA" or ritenuta.get("avviso_versamento_at"):
        return
    ora = datetime.now(timezone.utc)
    testo = testo_ritenuta_versata(ritenuta, upd)
    upd["avviso_versamento_at"] = ora.isoformat()
    upd["avviso_versamento_testo"] = testo
    recente = False
    try:
        data_pag = datetime.fromisoformat(str(upd.get("data_pagamento"))[:10]).date()
        recente = (ora.date() - data_pag).days <= GIORNI_AVVISO_VERSAMENTO
    except ValueError:
        recente = False
    upd["avviso_versamento_inviato"] = recente
    if not recente:
        return
    try:
        from app.services.telegram_notifications import send_notification

        await send_notification(f"<b>Ritenuta pagata</b>\n{testo}")
    except Exception as exc:
        logger.warning("Telegram ritenuta versata non inviato per la fattura %s (%s): %s",
                       ritenuta.get("numero_fattura"), type(exc).__name__, exc)


CHIAVE_ALLINEAMENTO_RITENUTE = "ritenute_fatture_allineate_v1"


async def allinea_ritenute_fatture(db) -> Dict[str, Any]:
    """Una volta sola: porta ``importo_ritenuta`` sulle parcelle gia' importate.

    Il parser non leggeva ``DatiRitenuta`` e l'import da Drive non alimentava
    la proiezione: le parcelle restavano con un residuo aperto pari alla
    ritenuta, e il bonifico del netto non le chiudeva mai.
    """
    if await db["sistema_stato"].find_one({"chiave": CHIAVE_ALLINEAMENTO_RITENUTE}):
        return {"saltato": "gia_allineate"}
    fatture = await db["invoices"].find(
        {"status": {"$nin": ["deleted", "archived"]},
         "xml_raw": {"$regex": "DatiRitenuta"}},
        {"_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1,
         "supplier_name": 1, "supplier_vat": 1, "cedente_piva": 1, "xml_raw": 1,
         "xml_body_index": 1, "importo_ritenuta": 1},
    ).to_list(5000)
    aggiornate = 0
    for f in fatture:
        dati = _estrai_dati_ritenuta(f.get("xml_raw"), int(f.get("xml_body_index") or 0))
        if not dati:
            continue
        importo = dati["importo_cents"] / 100
        if abs(float(f.get("importo_ritenuta") or 0) - importo) > 0.005:
            await db["invoices"].update_one(
                {"id": f["id"]}, {"$set": {"importo_ritenuta": importo}},
            )
            aggiornate += 1
        await upsert_ritenuta_da_fattura(db, f)
    await db["sistema_stato"].update_one(
        {"chiave": CHIAVE_ALLINEAMENTO_RITENUTE},
        {"$set": {"chiave": CHIAVE_ALLINEAMENTO_RITENUTE,
                  "at": datetime.now(timezone.utc).isoformat(),
                  "fatture": len(fatture), "aggiornate": aggiornate}},
        upsert=True,
    )
    return {"fatture": len(fatture), "aggiornate": aggiornate}


async def riconcilia_ritenute_esistenti(db) -> Dict[str, Any]:
    """Ricalcola le ritenute gia censite quando cambia la prova F24.

    E' richiamata dall'import canonico delle quietanze: l'utente non deve
    premere manualmente "Aggiorna" per vedere la prova documentale.
    """
    ritenute = await db[COLLECTION].find({}, {"_id": 0}).to_list(10000)
    if not ritenute:
        return {"analizzate": 0, "aggiornate": 0}
    f24_docs = await _carica_f24(db)
    pagamenti = await _carica_pagamenti_quietanza(db)
    aggiornate = 0
    for rit in ritenute:
        upd = await _riconcilia_ritenuta(
            db, rit, ritenute_periodo=ritenute, f24_docs=f24_docs, pagamenti_quietanza=pagamenti,
        )
        await _avvisa_se_appena_versata(db, rit, upd)
        result = await db[COLLECTION].update_one({"id": rit["id"]}, {"$set": upd})
        aggiornate += int(getattr(result, "modified_count", 0) > 0)
        await _chiudi_avviso_se_versata(db, rit, upd)
    return {"analizzate": len(ritenute), "aggiornate": aggiornate,
            "f24_analizzati": len(f24_docs)}


@router.post("/scan")
@handle_errors
async def scan_ritenute(anno: int = Query(2026)) -> Dict[str, Any]:
    """Estrae le ritenute dalle fatture XML dell'anno (idempotente per
    fattura) e le riconcilia con gli F24 disponibili."""
    db = Database.get_db()
    fatture = await db["invoices"].find(
        {"invoice_date": {"$regex": f"^{anno}"},
         "status": {"$nin": ["deleted", "archived"]},
         "xml_raw": {"$regex": "DatiRitenuta"}},
        {"_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1,
         "supplier_name": 1, "supplier_vat": 1, "cedente_piva": 1, "xml_raw": 1,
         "xml_body_index": 1},
    ).to_list(5000)

    nuove = aggiornate = 0
    for f in fatture:
        esistente = await db[COLLECTION].find_one({"fattura_id": f["id"]})
        result = await upsert_ritenuta_da_fattura(db, f)
        if result:
            aggiornate += int(bool(esistente))
            nuove += int(not esistente)

    # Seconda fase: dopo aver acquisito tutte le ritenute, una singola riga
    # 1040 dell'F24 può essere riconosciuta come somma del periodo.
    ritenute_anno = await db[COLLECTION].find(
        {"data_fattura": {"$regex": f"^{anno}"}}, {"_id": 0}
    ).to_list(5000)
    f24_docs = await _carica_f24(db)
    pagamenti = await _carica_pagamenti_quietanza(db)
    for rit in ritenute_anno:
        upd = await _riconcilia_ritenuta(
            db, rit, ritenute_periodo=ritenute_anno, f24_docs=f24_docs, pagamenti_quietanza=pagamenti,
        )
        await _avvisa_se_appena_versata(db, rit, upd)
        await db[COLLECTION].update_one({"id": rit["id"]}, {"$set": upd})
        await _chiudi_avviso_se_versata(db, rit, upd)

    return {"anno": anno, "fatture_con_ritenuta": len(fatture),
            "nuove": nuove, "aggiornate": aggiornate,
            "f24_analizzati": len(f24_docs)}


@router.get("")
@handle_errors
async def lista_ritenute(anno: int = Query(2026)) -> Dict[str, Any]:
    """Sezione Ritenute: elenco con scadenze, F24 associato e stato."""
    db = Database.get_db()
    ritenute = await db[COLLECTION].find(
        {"data_fattura": {"$regex": f"^{anno}"}}, {"_id": 0}
    ).sort("scadenza", -1).to_list(2000)
    f24_docs = await _carica_f24(db)
    pagamenti = await _carica_pagamenti_quietanza(db)
    for row in ritenute:
        row.update(await _riconcilia_ritenuta(
            db, row, ritenute_periodo=ritenute, f24_docs=f24_docs, pagamenti_quietanza=pagamenti,
        ))
    oggi = datetime.now(timezone.utc).date().isoformat()
    per_stato: Dict[str, int] = {}
    for r in ritenute:
        # lo stato "da_pagare" scivola in "scaduta" col passare del tempo
        if r.get("stato") == "da_pagare" and oggi > (
            r.get("scadenza_legale") or r.get("scadenza") or "9999"
        ):
            r["stato"] = "scaduta_da_versare"
        per_stato[r.get("stato") or "?"] = per_stato.get(r.get("stato") or "?", 0) + 1
    return {
        "anno": anno,
        "ritenute": ritenute,
        "totale_importo_cents": sum(
            int(r.get("importo_cents") or to_cents(r.get("importo"))) for r in ritenute
        ),
        "totale_importo": _euro_string(sum(
            int(r.get("importo_cents") or to_cents(r.get("importo"))) for r in ritenute
        )),
        "per_stato": per_stato,
        "proiezione_sola_lettura": True,
        "fonte_pagamenti": "tax_payment_query_service",
        "logica_ravvedimento": LOGICA_RAVVEDIMENTO,
    }


@router.get("/codici-ravvedimento")
@handle_errors
async def codici_ravvedimento() -> Dict[str, Any]:
    """Sezione codici tributo: i codici del ravvedimento e la logica."""
    return {"codici": CODICI_RAVVEDIMENTO_RITENUTE, "logica": LOGICA_RAVVEDIMENTO}


@router.get("/verifica-caso-1040")
@handle_errors
async def verifica_caso_1040(
    periodo: str = Query("2026-06", pattern=r"^\d{4}-\d{2}$"),
    importo_cents: int = Query(28400, gt=0),
    data_quietanza: str = Query("2026-07-21", pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> Dict[str, Any]:
    """Collaudo live in sola lettura del caso 1040 richiesto dall'audit."""
    db = Database.get_db()
    all_rows = await db[COLLECTION].find(
        {"periodo_ritenuta": periodo}, {"_id": 0}
    ).to_list(5000)
    obligations = [
        row for row in all_rows
        if int(row.get("importo_cents") or to_cents(row.get("importo"))) == importo_cents
    ]
    docs = await _carica_f24(db)
    matching_docs = []
    for document in docs:
        rows = [
            row for row in _tributi_di(document)
            if row.get("codice") == "1040"
            and row.get("periodo") == periodo
            and row.get("importo_cents") == importo_cents
        ]
        evidence = stato_evidenza_pagamento(document)
        if rows and str(evidence.get("data_versamento_documentale") or "")[:10] == data_quietanza:
            matching_docs.append(document)
    unique = len(obligations) == 1 and len(matching_docs) == 1
    document = matching_docs[0] if len(matching_docs) == 1 else None
    evidence = stato_evidenza_pagamento(document) if document else None
    return {
        "caso": {
            "codice_tributo": "1040",
            "periodo": periodo,
            "importo_cents": importo_cents,
            "importo": _euro_string(importo_cents),
            "data_quietanza": data_quietanza,
        },
        "certificato_live": unique,
        "sola_lettura": True,
        "ritenute_trovate": len(obligations),
        "f24_quietanze_trovati": len(matching_docs),
        "ritenuta_id": obligations[0].get("id") if len(obligations) == 1 else None,
        "f24_id": document.get("id") if document else None,
        "quietanza_id": document.get("quietanza_id") if document else None,
        "evidenza_pagamento": evidence,
        "payment_chain": document.get("payment_chain") if document else None,
        "motivo_non_certificato": None if unique else (
            "Il database live non contiene una catena univoca ritenuta-F24-quietanza con i valori richiesti."
        ),
    }
