"""
Import Hub — Upload universale con riconoscimento automatico tipo documento.
Prefix: /api/import
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import hashlib
import logging

from app.database import get_database
from app.parsers.fattura_xml import parse_fattura_xml
from app.parsers.corrispettivi_xml import parse_corrispettivo_xml
from app.parsers.cedolino_zucchetti import parse_cedolino_pdf
from app.parsers.presenze_zucchetti import parse_presenze_pdf, is_presenze_pdf
from app.parsers.estratto_conto_bpm import parse_estratto_conto_pdf
from app.parsers.distinta_bpm import parse_distinta_pdf
from app.parsers.f24 import parse_f24_pdf
from app.parsers.verbale import parse_verbale_pdf

router = APIRouter()
logger = logging.getLogger(__name__)


def _oid(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _chiave_movimento(mov: dict) -> str:
    raw = f"{mov['data_operazione']}|{mov['descrizione'][:30]}|{mov['importo']}"
    return hashlib.md5(raw.encode()).hexdigest()


def _detect_type(filename: str, content: bytes) -> str:
    """Riconosce il tipo di documento dal nome file e dal contenuto."""
    fname = filename.lower()

    # ── Per estensione ──────────────────────────────────────────────
    if fname.endswith(".xml") or fname.endswith(".p7m") or fname.endswith(".zip"):
        # Prova a leggere il contenuto XML
        try:
            xml_str = content.decode("utf-8", errors="replace")
        except Exception:
            xml_str = ""

        # FatturaPA: contiene FatturaElettronica
        if "FatturaElettronica" in xml_str or "FatturaPA" in xml_str:
            return "fattura_xml"
        # Corrispettivi RT: contiene DatiCorrispettivi o matricola RT
        if "DatiCorrispettivi" in xml_str or "MatricolaDispositivo" in xml_str or "DataRiferimento" in xml_str:
            return "corrispettivo_xml"
        # Fallback: prova fattura
        return "fattura_xml"

    if fname.endswith(".pdf"):
        # Prova a estrarre testo grezzo per riconoscere
        try:
            import fitz
            doc = fitz.open(stream=content, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
                if len(text) > 2000:
                    break
            doc.close()
            text_up = text.upper()
        except Exception:
            text_up = ""

        # F24 — pattern univoci
        if "MODELLO F24" in text_up or "CODICI TRIBUTO" in text_up or "SEZIONE ERARIO" in text_up:
            return "f24"
        # Foglio presenze Aut.301 (deve venire PRIMA del cedolino)
        if ("301" in text_up and "GIUSTIFICATIVI" in text_up and "GIORNO" in text_up
                and "NETTODELMESE" not in text_up.replace(" ", "")
                and "TOTALECOMPETENZE" not in text_up.replace(" ", "")):
            return "presenze"
        # Cedolino Zucchetti Aut.299
        if "AUT. 299" in text_up or "NETTO IN BUSTA" in text_up \
                or "NETTO DA PAGARE" in text_up or "TOTALE COMPETENZE" in text_up \
                or "NETTODELMESE" in text_up.replace(" ", ""):
            return "cedolino"
        # Estratto conto BPM
        if "BANCO BPM" in text_up or "ESTRATTO CONTO" in text_up or "SALDO INIZIALE" in text_up \
                or "VOSTRA DISPOSIZIONE" in text_up:
            return "estratto_conto"
        # Distinta pagamento BPM
        if "DISTINTA" in text_up and ("BONIFICO" in text_up or "PAGAMENTO" in text_up):
            return "distinta"
        if "DISTINTA DI PAGAMENTO" in text_up or "DISTINTA STIPENDI" in text_up:
            return "distinta"
        # Verbale CdS / bollo
        if "CODICE DELLA STRADA" in text_up or "VERBALE" in text_up or "BOLLO AUTO" in text_up \
                or "TASSA AUTOMOBILISTICA" in text_up or "MUNICIPIA" in text_up:
            return "verbale"

    return "sconosciuto"


TIPO_LABELS = {
    "fattura_xml": "Fattura XML (SDI/FatturaPA)",
    "corrispettivo_xml": "Corrispettivo RT (XML)",
    "cedolino": "Cedolino Zucchetti (PDF)",
    "estratto_conto": "Estratto Conto Banco BPM (PDF)",
    "distinta": "Distinta Pagamento BPM (PDF)",
    "f24": "Modello F24 (PDF)",
    "verbale": "Verbale / Bollo auto (PDF)",
    "presenze":    "Foglio Presenze Aut.301 (PDF)",
    "sconosciuto": "Tipo non riconosciuto",
}


async def _process(tipo: str, content: bytes, filename: str, db: AsyncIOMotorDatabase) -> dict:
    """Processa il file in base al tipo riconosciuto."""

    if tipo == "fattura_xml":
        for enc in ("utf-8", "latin-1"):
            try:
                xml_str = content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return {"errore": "Encoding XML non riconosciuto"}

        try:
            fatture = parse_fattura_xml(xml_str)
        except Exception as e:
            return {"errore": f"Parsing XML fallito: {e}"}

        if not fatture:
            return {"errore": "Nessuna fattura trovata nel file"}

        inserite = duplicate = 0
        for f in fatture:
            if await db["fatture_passive"].find_one({"dedup_key": f["dedup_key"]}):
                duplicate += 1
                continue
            doc = {
                "fornitore_denominazione": f["cedente"].get("denominazione", ""),
                "fornitore_piva": f["cedente"].get("partita_iva", ""),
                "numero": f["numero"], "data": f["data"],
                "anno": int(f["data"][:4]) if f["data"] and len(f["data"]) >= 4 else 0,
                "tipo_documento": f["tipo_documento"],
                "importo_totale": f["importo_totale"], "imponibile": f["imponibile"], "iva": f["iva"],
                "causale": f["causale"], "linee": f["linee"],
                "riepilogo_iva": f["riepilogo_iva"], "pagamenti": f["pagamenti"],
                "dedup_key": f["dedup_key"], "stato": "da_confermare",
                "source": "upload", "xml_filename": filename,
                "created_at": datetime.utcnow(),
            }
            await db["fatture_passive"].insert_one(doc)
            if f["cedente"].get("partita_iva"):
                await db["fornitori"].update_one(
                    {"anagrafica.piva": f["cedente"]["partita_iva"]},
                    {"$set": {"anagrafica.ragione_sociale": f["cedente"].get("denominazione", ""),
                              "anagrafica.piva": f["cedente"]["partita_iva"],
                              "updated_at": datetime.utcnow()},
                     "$setOnInsert": {"created_at": datetime.utcnow()}},
                    upsert=True)
            inserite += 1
        return {"collection": "fatture_passive", "inserite": inserite, "duplicate": duplicate}

    elif tipo == "corrispettivo_xml":
        for enc in ("utf-8", "latin-1"):
            try:
                xml_str = content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return {"errore": "Encoding XML non riconosciuto"}

        try:
            parsed = parse_corrispettivo_xml(xml_str)
        except Exception as e:
            return {"errore": f"Parsing XML fallito: {e}"}

        if parsed.get("errore"):
            return {"errore": parsed["errore"]}

        dedup = parsed.get("dedup_key", "")
        if await db["corrispettivi"].find_one({"dedup_key": dedup}):
            return {"collection": "corrispettivi", "inserite": 0, "duplicate": 1}

        parsed["filename"] = filename
        parsed["imported_at"] = datetime.utcnow()
        await db["corrispettivi"].insert_one(parsed)
        return {
            "collection": "corrispettivi",
            "inserite": 1, "duplicate": 0,
            "data": parsed.get("data", ""),
            "totale": parsed.get("totale_corrispettivi", 0),
        }

    elif tipo == "cedolino":
        try:
            cedolini = parse_cedolino_pdf(pdf_bytes=content)
        except Exception as e:
            return {"errore": f"Parsing PDF fallito: {e}"}

        if not cedolini:
            return {"errore": "Nessun cedolino trovato nel PDF"}

        from app.routers.cedolini import aggiorna_dipendente_da_cedolino

        inserite = incompleti = 0
        for ced in cedolini:
            cf, mese, anno = ced.get("codice_fiscale"), ced.get("mese"), ced.get("anno")
            if not cf or not mese or not anno:
                incompleti += 1
                continue
            ced.update({"filename": filename, "imported_at": datetime.utcnow(), "riconciliato": False})
            # 1) Upsert cedolino — sempre
            await db["cedolini"].update_one(
                {"codice_fiscale": cf, "mese": mese, "anno": anno},
                {"$set": ced, "$setOnInsert": {"created_at": datetime.utcnow()}},
                upsert=True)
            # 2) Aggiorna dipendente con logica competenza (import misto sicuro)
            await aggiorna_dipendente_da_cedolino(db, ced)
            inserite += 1
        return {"collection": "cedolini", "inserite": inserite, "duplicate": 0, "incompleti": incompleti}

    elif tipo == "estratto_conto":
        try:
            parsed = parse_estratto_conto_pdf(pdf_bytes=content)
        except Exception as e:
            return {"errore": f"Parsing PDF fallito: {e}"}

        movimenti = parsed.get("movimenti", [])
        if not movimenti:
            return {"errore": "Nessun movimento trovato nel PDF"}

        importati = duplicate = 0
        for mov in movimenti:
            mov["chiave"] = _chiave_movimento(mov)
            mov["riconciliato"] = False
            if await db["estratto_conto_movimenti"].find_one({"chiave": mov["chiave"]}):
                duplicate += 1
                continue
            mov.update({"filename": filename, "imported_at": datetime.utcnow()})
            await db["estratto_conto_movimenti"].insert_one(mov)
            importati += 1
        return {
            "collection": "estratto_conto_movimenti",
            "inserite": importati, "duplicate": duplicate,
            "saldo_finale": parsed.get("saldo_finale", 0),
        }

    elif tipo == "distinta":
        try:
            parsed = parse_distinta_pdf(pdf_bytes=content)
        except Exception as e:
            return {"errore": f"Parsing PDF fallito: {e}"}

        parsed.update({"filename": filename, "imported_at": datetime.utcnow()})
        result = await db["distinte_pagamento"].insert_one(parsed)

        riconciliati = 0
        for bon in parsed.get("bonifici", []):
            if bon.get("iban"):
                dip = await db["dipendenti"].find_one({"iban_cedolino": bon["iban"]})
                if not dip:
                    dip = await db["dipendenti"].find_one({"iban": bon["iban"]})
                if dip:
                    bon["dipendente_nome"] = f"{dip.get('cognome','')} {dip.get('nome','')}".strip()
                    riconciliati += 1
        if riconciliati:
            await db["distinte_pagamento"].update_one(
                {"_id": result.inserted_id},
                {"$set": {"bonifici": parsed["bonifici"], "riconciliati": riconciliati}})
        return {
            "collection": "distinte_pagamento",
            "inserite": 1, "duplicate": 0,
            "n_bonifici": parsed.get("numero_bonifici", 0),
            "riconciliati": riconciliati,
        }

    elif tipo == "f24":
        try:
            parsed = parse_f24_pdf(pdf_bytes=content)
        except Exception as e:
            return {"errore": f"Parsing PDF fallito: {e}"}

        data = parsed.get("data_versamento", "")
        totale = parsed.get("totale", 0)
        chiave = hashlib.md5(f"{data}|{totale}".encode()).hexdigest()

        if await db["f24"].find_one({"chiave": chiave}):
            return {"collection": "f24", "inserite": 0, "duplicate": 1}

        n_tributi = (len(parsed.get("sezione_erario", [])) +
                     len(parsed.get("sezione_inps", [])) +
                     len(parsed.get("sezione_regioni", [])))
        parsed.update({
            "chiave": chiave, "n_tributi": n_tributi,
            "filename": filename, "imported_at": datetime.utcnow(),
            "stato": "importato", "riconciliato": False,
        })
        await db["f24"].insert_one(parsed)
        return {"collection": "f24", "inserite": 1, "duplicate": 0, "n_tributi": n_tributi, "totale": totale}

    elif tipo == "presenze":
        try:
            pres = parse_presenze_pdf(pdf_bytes=content)
        except Exception as e:
            return {"errore": f"Parsing PDF fallito: {e}"}

        if pres is None:
            return {"errore": "Nessun foglio presenze valido trovato"}

        cf, mese, anno = pres.get("codice_fiscale"), pres.get("mese"), pres.get("anno")
        if not cf or not mese or not anno:
            return {"errore": "Dati incompleti nel foglio presenze"}

        pres.update({"filename": filename, "imported_at": datetime.utcnow()})
        result = await db["presenze"].update_one(
            {"codice_fiscale": cf, "mese": mese, "anno": anno},
            {"$set": pres, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True)

        if pres.get("cessato") and pres.get("data_cessazione"):
            await db["dipendenti"].update_one(
                {"codice_fiscale": cf},
                {"$set": {"stato": "cessato", "data_cessazione": pres["data_cessazione"], "updated_at": datetime.utcnow()}}
            )

        return {
            "collection": "presenze", "inserite": 1 if result.upserted_id else 0,
            "duplicate": 0 if result.upserted_id else 1,
            "periodo": pres.get("periodo_label", ""),
            "totali": pres.get("totali", {}),
        }

    elif tipo == "verbale":
        try:
            parsed = parse_verbale_pdf(pdf_bytes=content)
        except Exception as e:
            return {"errore": f"Parsing PDF fallito: {e}"}

        doc = {**parsed, "pdf_filename": filename, "stato": "da_pagare", "created_at": datetime.utcnow()}
        result = await db["verbali"].insert_one(doc)
        return {"collection": "verbali", "inserite": 1, "duplicate": 0, "_id": str(result.inserted_id)}

    return {"errore": "Tipo non gestito"}


# ── ENDPOINT ───────────────────────────────────────────────────────────────

@router.post("/upload")
async def import_upload(
    file: UploadFile = File(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Upload universale: riconosce automaticamente il tipo e importa nel DB corretto.
    Accetta: .xml, .p7m, .zip, .pdf
    """
    content = await file.read()
    tipo = _detect_type(file.filename, content)

    if tipo == "sconosciuto":
        return {
            "ok": False,
            "tipo": "sconosciuto",
            "label": TIPO_LABELS["sconosciuto"],
            "filename": file.filename,
            "errore": "Formato non riconosciuto. Accettati: XML FatturaPA, XML RT corrispettivi, PDF cedolini Zucchetti, PDF estratto conto BPM, PDF distinta BPM, PDF F24, PDF verbali.",
        }

    result = await _process(tipo, content, file.filename, db)

    return {
        "ok": "errore" not in result,
        "tipo": tipo,
        "label": TIPO_LABELS[tipo],
        "filename": file.filename,
        **result,
    }


@router.post("/detect")
async def import_detect(file: UploadFile = File(...)):
    """Solo riconosce il tipo senza importare (anteprima)."""
    content = await file.read()
    tipo = _detect_type(file.filename, content)
    return {
        "tipo": tipo,
        "label": TIPO_LABELS[tipo],
        "filename": file.filename,
        "riconosciuto": tipo != "sconosciuto",
    }


