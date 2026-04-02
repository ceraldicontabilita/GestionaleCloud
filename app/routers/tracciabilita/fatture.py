"""
Router per gestione fatture: CRUD, importa-xml, visualizza fattura HTML, backfill lotti.
"""
import re
import uuid
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from app.routers.tracciabilita.server import db
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/fatture", tags=["Fatture"])

# MongoDB connection (stessa logica degli altri router)

# XSL per visualizzazione Assosoftware
XSL_PATH = Path(__file__).parent.parent / "static" / "FoglioStileAssoSoftware.xsl"


def set_database(database):
    """Permette override del db dall'esterno (compatibilità)."""
    global db
    db = database


# ── Modello ──────────────────────────────────────────────────────────────────
class FatturaImportata(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    fornitore: str
    piva: str = ""
    numero_fattura: str
    data_fattura: str
    prodotti: List[dict] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── CRUD Base ────────────────────────────────────────────────────────────────
@router.get("")
async def get_fatture(escludi_fornitori: bool = True, limit: int = 2000):
    """Lista le fatture importate (limite default 2000, ordinato per data)"""
    if escludi_fornitori:
        fornitori_esclusi_docs = await db.fornitori.find({"escluso": True}, {"nome": 1}).to_list(1000)
        nomi_esclusi = {f["nome"].lower().strip() for f in fornitori_esclusi_docs}
        items = await db.fatture.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
        items = [f for f in items if f.get("fornitore", "").lower().strip() not in nomi_esclusi]
    else:
        items = await db.fatture.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return items


@router.delete("/{fattura_id}")
async def delete_fattura(fattura_id: str):
    result = await db.fatture.delete_one({"id": fattura_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    return {"message": "Eliminata con successo"}


# ── Backfill lotti SAIMA ─────────────────────────────────────────────────────
@router.post("/backfill-lotto-quantita")
async def backfill_lotto_quantita():
    """Backfill: aggiunge quantita_originale ai lotti SAIMA che ne sono privi."""
    fatture = await db.fatture.find(
        {"fornitore": {"$regex": "SAIMA", "$options": "i"}},
        {"_id": 0, "id": 1, "numero_fattura": 1, "prodotti": 1}
    ).to_list(5000)

    updated_fatture = 0
    updated_prodotti = 0

    for fattura in fatture:
        prodotti = fattura.get("prodotti", [])
        changed = False
        for prodotto in prodotti:
            lotto = prodotto.get("_lotto_data", {})
            if lotto and "lotto_id_fornitore" in lotto and "quantita_originale" not in lotto:
                try:
                    qty = float(str(prodotto.get("quantita", 0) or 0).replace(",", "."))
                    if qty > 0:
                        lotto["quantita_originale"] = qty
                        changed = True
                        updated_prodotti += 1
                except (ValueError, TypeError):
                    pass
        if changed:
            result = await db.fatture.update_one(
                {"id": fattura["id"]},
                {"$set": {"prodotti": prodotti}}
            )
            if result.modified_count > 0:
                updated_fatture += 1

    return {
        "fatture_aggiornate": updated_fatture,
        "prodotti_aggiornati": updated_prodotti,
        "message": f"Backfill completato: {updated_prodotti} prodotti aggiornati in {updated_fatture} fatture"
    }


# ── Visualizza fattura HTML (Assosoftware) ────────────────────────────────────
@router.get("/{fattura_id}/visualizza", response_class=HTMLResponse)
async def visualizza_fattura_html(fattura_id: str):
    """Trasforma la fattura XML con foglio stile Assosoftware."""
    try:
        from lxml import etree
    except ImportError:
        raise HTTPException(status_code=500, detail="lxml non disponibile")

    fattura = await db.fatture.find_one({"id": fattura_id})
    if not fattura:
        fattura = await db.fatture.find_one({"numero_fattura": fattura_id})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    xml_raw = fattura.get("xml_raw", "")
    if not xml_raw:
        return HTMLResponse(
            content=_genera_html_fallback(fattura),
            media_type="text/html; charset=utf-8"
        )

    if not XSL_PATH.exists():
        raise HTTPException(status_code=500, detail=f"File XSL non trovato: {XSL_PATH}")

    try:
        xml_bytes = xml_raw.encode("utf-8")
        if xml_bytes.startswith(b'\xef\xbb\xbf'):
            xml_bytes = xml_bytes[3:]
        xml_doc = etree.fromstring(xml_bytes)
        xsl_doc = etree.parse(str(XSL_PATH))
        transform = etree.XSLT(xsl_doc)
        result_tree = transform(xml_doc)
        html_output = str(result_tree)
        if not html_output or len(html_output) < 100:
            return HTMLResponse(
                content=_genera_html_fallback(fattura),
                media_type="text/html; charset=utf-8"
            )
        return HTMLResponse(content=html_output, media_type="text/html; charset=utf-8")
    except Exception as e:
        return HTMLResponse(
            content=_genera_html_fallback(fattura, str(e)),
            media_type="text/html; charset=utf-8"
        )


def _genera_html_fallback(fattura: dict, errore: str = None) -> str:
    """Genera una visualizzazione HTML semplice dai dati parsati della fattura."""
    num = fattura.get("numero_fattura", "N/D")
    forn = fattura.get("fornitore", "N/D")
    piva = fattura.get("piva", "N/D")
    data = fattura.get("data_fattura", "N/D")
    prodotti = fattura.get("prodotti", [])

    prodotti_html = ""
    totale = 0
    for p in prodotti:
        descrizione = p.get("descrizione", p.get("nome", ""))
        qty = p.get("quantita", 0)
        um = p.get("unita_misura", "")
        prezzo = p.get("prezzo_unitario", 0)
        importo = float(qty or 0) * float(prezzo or 0)
        totale += importo
        prodotti_html += f"""
        <tr>
            <td style="padding:6px;border-bottom:1px solid #eee;">{descrizione}</td>
            <td style="padding:6px;border-bottom:1px solid #eee;text-align:center;">{qty} {um}</td>
            <td style="padding:6px;border-bottom:1px solid #eee;text-align:right;">€{float(prezzo or 0):.4f}</td>
            <td style="padding:6px;border-bottom:1px solid #eee;text-align:right;">€{importo:.2f}</td>
        </tr>"""

    nota = (
        f'<div style="background:#fff3cd;border:1px solid #ffc107;padding:8px;margin:8px 0;font-size:11px;">'
        f'<b>Nota:</b> Visualizzazione XML non disponibile ({errore}). Dati estratti dal database.</div>'
        if errore else
        '<div style="background:#fff3cd;border:1px solid #ffc107;padding:8px;margin:8px 0;font-size:11px;">'
        '<b>Nota:</b> Fattura importata senza XML originale.</div>'
    )

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <title>Fattura N. {num}</title>
    <style>
        body {{ font-family: Arial, sans-serif; font-size: 13px; max-width: 900px; margin: 20px auto; padding: 20px; }}
        .header {{ border: 2px solid #1a3a6b; padding: 15px; margin-bottom: 15px; }}
        .header h1 {{ color: #1a3a6b; margin: 0 0 5px; font-size: 18px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        thead th {{ background: #1a3a6b; color: white; padding: 8px; text-align: left; font-size: 12px; }}
        .totale {{ font-weight: bold; text-align: right; padding: 10px 6px; border-top: 2px solid #333; }}
        .print-btn {{ position: fixed; top: 10px; right: 10px; background: #1a3a6b; color: white; border: none; padding: 8px 16px; cursor: pointer; border-radius: 4px; }}
    </style>
</head>
<body>
    <button class="print-btn" onclick="window.print()">Stampa</button>
    {nota}
    <div class="header">
        <h1>FATTURA ELETTRONICA N. {num}</h1>
        <table style="border:none;">
            <tr><td style="width:120px;color:#666;">Fornitore:</td><td><b>{forn}</b></td></tr>
            <tr><td style="color:#666;">P.IVA:</td><td>{piva}</td></tr>
            <tr><td style="color:#666;">Data:</td><td>{data}</td></tr>
        </table>
    </div>
    <table>
        <thead><tr><th>Descrizione</th><th>Qtà</th><th>Prezzo Unit.</th><th>Importo</th></tr></thead>
        <tbody>{prodotti_html}</tbody>
        <tfoot><tr><td colspan="3" class="totale">TOTALE IMPONIBILE:</td><td class="totale">€{totale:.2f}</td></tr></tfoot>
    </table>
</body>
</html>"""


# ── Import XML manuale ────────────────────────────────────────────────────────
@router.post("/importa-xml")
async def importa_fattura_xml(files: List[UploadFile] = File(...)):
    """Importa fatture XML e aggiorna automaticamente le materie prime."""
    from routers.xml_helpers import (
        parse_fattura_xml, fuzzy_match, estrai_quantita_da_descrizione
    )

    risultati = {
        "fatture_processate": 0,
        "fatture_saltate_escluse": 0,
        "prodotti_trovati": 0,
        "materie_aggiornate": 0,
        "nuove_materie": 0,
        "match_ingredienti": [],
        "errori": []
    }

    fornitori_esclusi_docs = await db.fornitori.find({"escluso": True}, {"nome": 1}).to_list(5000)
    fornitori_esclusi = {f["nome"].lower() for f in fornitori_esclusi_docs}

    ricette = await db.ricette.find({}, {"_id": 0}).to_list(5000)
    ingredienti_ricette = {}
    for ricetta in ricette:
        for ing in ricetta.get("ingredienti", []):
            ing_lower = ing.lower().strip()
            if ing_lower not in ingredienti_ricette:
                ingredienti_ricette[ing_lower] = ing

    mappature = await db.mappature.find({}, {"_id": 0}).to_list(10000)
    mappa_prodotto_ingrediente = {
        m.get("prodotto_fattura", "").lower(): m.get("ingrediente_ricetta", "")
        for m in mappature
    }

    def rileva_allergeni_materia(testo: str) -> str:
        testo_low = testo.lower()
        allergeni = []
        if any(k in testo_low for k in ["farina", "grano", "frumento", "semola", "glutine", "pasta", "orzo"]):
            allergeni.append("Cereali contenenti glutine")
        if any(k in testo_low for k in ["uova", "uovo", "tuorlo", "albume"]):
            allergeni.append("Uova")
        if any(k in testo_low for k in ["latte", "burro", "panna", "formaggio", "mozzarella", "ricotta", "lattosio", "caseina"]):
            allergeni.append("Latte e derivati")
        if any(k in testo_low for k in ["soia", "soy", "lecitina di soia"]):
            allergeni.append("Soia")
        if any(k in testo_low for k in ["nocciole", "mandorle", "pistacchio", "noci", "pinoli"]):
            allergeni.append("Frutta a guscio")
        return ("Contiene: " + ", ".join(allergeni)) if allergeni else "non contiene allergeni"

    for file in files:
        try:
            content = await file.read()
            fattura_data = parse_fattura_xml(content)

            if not fattura_data["fornitore"]:
                risultati["errori"].append(f"{file.filename}: Fornitore non trovato")
                continue

            if fattura_data["fornitore"].lower() in fornitori_esclusi:
                risultati["fatture_saltate_escluse"] += 1
                continue

            risultati["fatture_processate"] += 1
            risultati["prodotti_trovati"] += len(fattura_data["prodotti"])

            data_fmt = fattura_data["data_fattura"]
            if "-" in data_fmt:
                try:
                    data_fmt = datetime.strptime(data_fmt, "%Y-%m-%d").strftime("%d/%m/%Y")
                except (ValueError, TypeError):
                    pass

            fattura = FatturaImportata(
                fornitore=fattura_data["fornitore"],
                piva=fattura_data["piva"],
                numero_fattura=fattura_data["numero_fattura"],
                data_fattura=data_fmt,
                prodotti=fattura_data["prodotti"]
            )
            fattura_dict = fattura.model_dump()
            fattura_dict["created_at"] = fattura_dict["created_at"].isoformat()
            fattura_dict["xml_raw"] = content.decode("utf-8", errors="replace")

            await db.fatture.update_one(
                {"numero_fattura": fattura.numero_fattura, "fornitore": fattura.fornitore},
                {"$set": fattura_dict},
                upsert=True
            )

            # Crea fornitore se nuovo
            if not await db.fornitori.find_one({"nome": fattura_data["fornitore"]}):
                await db.fornitori.insert_one({
                    "id": str(uuid.uuid4()),
                    "nome": fattura_data["fornitore"],
                    "piva": fattura_data["piva"],
                    "escluso": False,
                    "in_attesa": True,
                    "first_seen": datetime.now(timezone.utc).isoformat(),
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
            elif fattura_data["piva"]:
                await db.fornitori.update_one(
                    {"nome": fattura_data["fornitore"], "piva": {"$exists": False}},
                    {"$set": {"piva": fattura_data["piva"]}}
                )

            # Salva lotti fornitori dai dati XML
            for prodotto in fattura_data["prodotti"]:
                lotto_data = prodotto.get("_lotto_data", {})
                if not lotto_data or not lotto_data.get("lotto_id_fornitore"):
                    continue
                if await db.lotti_fornitori.find_one({
                    "lotto_id_fornitore": lotto_data["lotto_id_fornitore"],
                    "fornitore": fattura_data["fornitore"]
                }):
                    continue
                qt = float(str(prodotto.get("quantita", "1")).strip() or "1")
                data_scad = lotto_data.get("data_scadenza", "")
                giorni_scad = None
                try:
                    if data_scad and "/" in data_scad:
                        dt_s = datetime.strptime(data_scad, "%d/%m/%Y")
                        giorni_scad = (dt_s - datetime.now()).days
                except Exception:
                    pass
                await db.lotti_fornitori.insert_one({
                    "id": str(uuid.uuid4()),
                    "fornitore": fattura_data["fornitore"],
                    "prodotto_nome": re.sub(r"\s+", " ", prodotto.get("descrizione", "").strip()),
                    "prodotto_nome_norm": re.sub(r"\s+", " ", prodotto.get("descrizione", "").strip().lower()),
                    "lotto_id_fornitore": lotto_data["lotto_id_fornitore"],
                    "data_scadenza": data_scad,
                    "giorni_alla_scadenza": giorni_scad,
                    "scaduto": (giorni_scad is not None and giorni_scad < 0),
                    "quantita_originale": lotto_data.get("quantita_originale", qt),
                    "quantita_acquistata": qt,
                    "quantita_disponibile": qt,
                    "unita_misura": (prodotto.get("unita_misura") or "PZ").upper(),
                    "prezzo_unitario": float(str(prodotto.get("prezzo", "0")).strip() or "0"),
                    "fattura_ref": fattura_data.get("numero_fattura", ""),
                    "data_fattura": data_fmt,
                    "esaurito": False,
                    "created_at": datetime.now(timezone.utc).isoformat()
                })

            # MODIFICA 2: Popola aliases nel dizionario_prodotti per ogni prodotto della fattura
            for prodotto in fattura_data["prodotti"]:
                try:
                    desc = prodotto.get("descrizione", "").strip()
                    desc_norm = re.sub(r'\s+', ' ', desc.lower().strip())
                    if not desc_norm:
                        continue
                    mapping = await db.nome_mapping.find_one(
                        {"descrizione_key": desc_norm[:200]}, {"_id": 0, "nome_canc": 1}
                    )
                    if mapping and mapping.get("nome_canc"):
                        nome_canc_norm = mapping["nome_canc"].lower().strip()
                        await db.dizionario_prodotti.update_one(
                            {"nome_normalizzato": {"$regex": re.escape(nome_canc_norm[:15]), "$options": "i"}},
                            {"$addToSet": {"aliases": desc_norm}},
                        )
                    else:
                        await db.dizionario_prodotti.update_one(
                            {"nome_normalizzato": desc_norm},
                            {"$addToSet": {"aliases": desc_norm}},
                        )
                except Exception:
                    pass

            # Match ingredienti <-> prodotti fattura
            for prodotto in fattura_data["prodotti"]:
                desc = prodotto.get("descrizione", "")
                desc_lower = desc.lower()
                ingrediente_mappato = mappa_prodotto_ingrediente.get(desc_lower)

                if not ingrediente_mappato:
                    for ing_lower, ing_originale in ingredienti_ricette.items():
                        if fuzzy_match(ing_lower, desc_lower, soglia=70):
                            ingrediente_mappato = ing_originale
                            await db.mappature.update_one(
                                {"prodotto_fattura": desc},
                                {"$set": {
                                    "id": str(uuid.uuid4()),
                                    "prodotto_fattura": desc,
                                    "ingrediente_ricetta": ing_originale,
                                    "fornitore": fattura_data["fornitore"],
                                    "created_at": datetime.now(timezone.utc).isoformat()
                                }},
                                upsert=True
                            )
                            break

                if ingrediente_mappato:
                    allergeni = rileva_allergeni_materia(desc)
                    descrizione_completa = f"{desc}  {allergeni} - {fattura_data['fornitore']} n° fatt {fattura_data['numero_fattura']} - {data_fmt}"

                    materia_esistente = await db.materie_prime.find_one({
                        "$or": [
                            {"materia_prima": {"$regex": f"^{re.escape(ingrediente_mappato)}$", "$options": "i"}},
                            {"materia_prima": {"$regex": ingrediente_mappato, "$options": "i"}}
                        ]
                    })

                    if materia_esistente:
                        await db.materie_prime.update_one(
                            {"id": materia_esistente["id"]},
                            {"$set": {
                                "azienda": fattura_data["fornitore"],
                                "data_fattura": data_fmt,
                                "numero_fattura": fattura_data["numero_fattura"],
                                "allergeni": allergeni,
                                "descrizione_completa": descrizione_completa,
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            }}
                        )
                        risultati["materie_aggiornate"] += 1
                    else:
                        await db.materie_prime.insert_one({
                            "id": str(uuid.uuid4()),
                            "azienda": fattura_data["fornitore"],
                            "data_fattura": data_fmt,
                            "numero_fattura": fattura_data["numero_fattura"],
                            "materia_prima": ingrediente_mappato,
                            "allergeni": allergeni,
                            "descrizione_completa": descrizione_completa,
                            "created_at": datetime.now(timezone.utc).isoformat()
                        })
                        risultati["nuove_materie"] += 1

                    risultati["match_ingredienti"].append({
                        "prodotto_fattura": desc[:50],
                        "ingrediente": ingrediente_mappato,
                        "fornitore": fattura_data["fornitore"],
                        "fattura": fattura_data["numero_fattura"]
                    })

        except Exception as e:
            risultati["errori"].append(f"{file.filename}: {str(e)}")

    # Trigger pipeline automatica
    if risultati["fatture_processate"] > 0:
        try:
            from routers.pipeline import esegui_pipeline_post_import
            import asyncio
            asyncio.create_task(
                esegui_pipeline_post_import(motivo=f"xml_manuale_{risultati['fatture_processate']}_fatture")
            )
        except Exception:
            pass

    return risultati
