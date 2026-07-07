"""
Router Gestione Noleggio Auto
Endpoint API per gestione flotta veicoli a noleggio.

Questo file contiene solo gli endpoint REST API.
La business logic è in /app/services/noleggio/
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Query, Body, HTTPException

from app.database import Database

# Import dal modulo noleggio services
from app.services.noleggio import (
    FORNITORI_NOLEGGIO,
    COLLECTION,
    scan_fatture_noleggio,
    categorizza_spesa
)

from app.utils.error_handler import handle_errors

router = APIRouter()
logger = logging.getLogger(__name__)

# Le due fonti di verbali/multe che esistono nel sistema: quelli scaricati
# dalla posta PEC/Gmail (verbali_noleggio) e quelli estratti dalle fatture
# dei noleggiatori (verbali_noleggio_completi, popolata da verbali_service.py).
# Stesso verbale può comparire in entrambe — vengono uniti qui per numero_verbale
# così il veicolo mostra un'unica lista, mai duplicata. Vedi
# memoria/endpoints/07-hr-noleggio-verbali.md per la mappa completa del modulo.
COLLECTION_VERBALI_POSTA = "verbali_noleggio"
COLLECTION_VERBALI_FATTURE = "verbali_noleggio_completi"


async def _get_verbali_completi_per_targa(
    db, targa: str, anno: Optional[int] = None
) -> list:
    """
    Motore centralizzato verbali per veicolo: unisce verbali_noleggio (posta)
    e verbali_noleggio_completi (fatture), deduplicati per numero_verbale.
    Ogni verbale riporta stato pagamento, riferimento fattura e se è
    disponibile un bollettino/ricevuta di pagamento scaricabile.
    """
    targa_upper = (targa or "").upper()
    if not targa_upper:
        return []

    verbali_per_numero: Dict[str, Dict[str, Any]] = {}

    query_posta: Dict[str, Any] = {"targa": targa_upper}
    if anno:
        query_posta["$or"] = [
            {"data_verbale": {"$regex": f"^{anno}"}},
            {"created_at": {"$regex": f"^{anno}"}},
        ]
    cursor_posta = db[COLLECTION_VERBALI_POSTA].find(
        query_posta, {"_id": 0, "pdf_data": 0, "pdf_allegati": 0, "quietanza_pdf": 0}
    )
    async for v in cursor_posta:
        numero = v.get("numero_verbale") or v.get("numero_verbale_old")
        if not numero:
            continue
        verbali_per_numero[numero] = {
            "numero_verbale": numero,
            "data_verbale": v.get("data_verbale") or (v.get("created_at") or "")[:10],
            "importo": float(v.get("importo") or 0),
            "stato": v.get("stato"),
            "pagato": v.get("stato") == "pagato",
            "fattura_id": v.get("fattura_id"),
            "fattura_numero": v.get("fattura_numero"),
            "ha_ricevuta": bool(v.get("pdf_ricevuta_path") or v.get("quietanza_ricevuta")),
            "metodo_pagamento": v.get("psp") or v.get("metodo"),
            "fonte": "posta",
        }

    query_fatture: Dict[str, Any] = {"targa": targa_upper}
    if anno:
        query_fatture["anno"] = anno
    cursor_fatture = db[COLLECTION_VERBALI_FATTURE].find(query_fatture, {"_id": 0})
    async for v in cursor_fatture:
        numero = v.get("numero_verbale")
        if not numero:
            continue
        esistente = verbali_per_numero.get(numero, {})
        stato_pagamento = v.get("stato_pagamento")
        verbali_per_numero[numero] = {
            **esistente,
            "numero_verbale": numero,
            "data_verbale": esistente.get("data_verbale") or v.get("data_verbale") or v.get("data"),
            "importo": esistente.get("importo") or float(v.get("importo") or 0),
            "stato": esistente.get("stato") or stato_pagamento,
            "pagato": esistente.get("pagato", False) or stato_pagamento == "pagato",
            "fattura_id": esistente.get("fattura_id") or v.get("fattura_id"),
            "fattura_numero": esistente.get("fattura_numero") or v.get("numero_fattura"),
            "ha_ricevuta": esistente.get("ha_ricevuta", False),
            "fonte": "posta+fattura" if esistente else "fattura",
        }

    return sorted(
        verbali_per_numero.values(),
        key=lambda x: x.get("data_verbale") or "",
        reverse=True,
    )


@router.get("/veicoli")
@handle_errors
async def get_veicoli(
    anno: Optional[int] = Query(None, description="Filtra per anno")
) -> Dict[str, Any]:
    """
    Lista tutti i veicoli a noleggio con i relativi costi.
    Combina dati estratti dalle fatture con dati salvati (driver, date).
    """
    db = Database.get_db()
    
    # Scansiona fatture
    veicoli_fatture, fatture_senza_targa = await scan_fatture_noleggio(anno)
    
    # Carica dati salvati
    veicoli_salvati = {}
    cursor = db[COLLECTION].find({}, {"_id": 0})
    async for v in cursor:
        veicoli_salvati[v["targa"]] = v
    
    # Associa fatture senza targa ai veicoli salvati
    for fattura in fatture_senza_targa:
        piva = fattura["supplier_vat"]
        tipo_doc = fattura.get("tipo_documento", "").lower()
        is_nota_credito = "nota" in tipo_doc or tipo_doc == "td04"
        fattura_id = fattura.get("invoice_id", "")
        
        # Trova tutti i veicoli di questo fornitore
        veicoli_fornitore = [
            (targa, salvato) for targa, salvato in veicoli_salvati.items()
            if salvato.get("fornitore_piva") == piva
        ]
        
        if not veicoli_fornitore:
            continue
        
        # Scegli il veicolo giusto
        target_targa = None
        oggi = datetime.now().strftime('%Y-%m-%d')
        
        # Prima cerca veicoli non presenti in veicoli_fatture
        for targa, salvato in veicoli_fornitore:
            if targa not in veicoli_fatture:
                target_targa = targa
                break
        
        # Se tutti i veicoli sono presenti, cerca quello con contratto scaduto
        if not target_targa:
            for targa, salvato in veicoli_fornitore:
                data_fine = salvato.get("data_fine", "")
                if data_fine and data_fine < oggi:
                    target_targa = targa
                    break
        
        if not target_targa:
            target_targa = veicoli_fornitore[0][0]
        
        salvato = veicoli_salvati[target_targa]
        
        # Aggiungi le spese a questo veicolo
        if target_targa not in veicoli_fatture:
            veicoli_fatture[target_targa] = {
                "targa": target_targa,
                "fornitore_noleggio": fattura["supplier"],
                "fornitore_piva": piva,
                "codice_cliente": fattura.get("codice_cliente"),
                "modello": salvato.get("modello", ""),
                "marca": salvato.get("marca", ""),
                "driver": salvato.get("driver"),
                "driver_id": salvato.get("driver_id"),
                "contratto": salvato.get("contratto"),
                "data_inizio": salvato.get("data_inizio"),
                "data_fine": salvato.get("data_fine"),
                "note": salvato.get("note"),
                "canoni": [],
                "pedaggio": [],
                "verbali": [],
                "bollo": [],
                "costi_extra": [],
                "riparazioni": [],
                "totale_canoni": 0,
                "totale_pedaggio": 0,
                "totale_verbali": 0,
                "totale_bollo": 0,
                "totale_costi_extra": 0,
                "totale_riparazioni": 0,
                "totale_generale": 0
            }
        
        # Raggruppa linee per categoria
        linee_per_cat: Dict[str, Any] = {}
        for linea in fattura.get("linee", []):
            desc = linea.get("descrizione", "")
            prezzo = float(linea.get("prezzo_totale") or linea.get("prezzo_unitario") or 0)
            categoria, importo, metadata = categorizza_spesa(desc, prezzo, is_nota_credito)
            
            if categoria not in linee_per_cat:
                linee_per_cat[categoria] = {"voci": [], "imponibile": 0, "metadata": {}}
            linee_per_cat[categoria]["voci"].append({"descrizione": desc, "importo": round(importo, 2)})
            linee_per_cat[categoria]["imponibile"] += importo
            for k, v in metadata.items():
                if k not in linee_per_cat[categoria]["metadata"]:
                    linee_per_cat[categoria]["metadata"][k] = v
        
        for categoria, dati in linee_per_cat.items():
            imponibile = round(dati["imponibile"], 2)
            iva = 0 if categoria == "bollo" else round(imponibile * 0.22, 2)
            record = {
                "data": fattura["invoice_date"],
                "numero_fattura": fattura["invoice_number"],
                "fattura_id": fattura_id,
                "fornitore": fattura["supplier"],
                "voci": dati["voci"],
                "imponibile": imponibile,
                "iva": iva,
                "totale": round(imponibile + iva, 2),
                "pagato": fattura.get("pagato", False)
            }
            if categoria == "verbali" and dati["metadata"]:
                record["numero_verbale"] = dati["metadata"].get("numero_verbale")
                record["data_verbale"] = dati["metadata"].get("data_verbale")
            
            veicoli_fatture[target_targa][categoria].append(record)
            veicoli_fatture[target_targa][f"totale_{categoria}"] += round(imponibile + iva, 2)
        
        # Ricalcola totale
        veicoli_fatture[target_targa]["totale_generale"] = round(sum(
            veicoli_fatture[target_targa][f"totale_{cat}"] 
            for cat in ["canoni", "pedaggio", "verbali", "bollo", "costi_extra", "riparazioni"]
        ), 2)
    
    # Merge con dati salvati
    risultato = []
    for targa, dati in veicoli_fatture.items():
        veicolo = {**dati}
        
        if targa in veicoli_salvati:
            salvato = veicoli_salvati[targa]
            veicolo["driver"] = salvato.get("driver")
            veicolo["driver_id"] = salvato.get("driver_id")
            veicolo["modello"] = salvato.get("modello") or veicolo.get("modello", "")
            veicolo["marca"] = salvato.get("marca") or veicolo.get("marca", "")
            veicolo["contratto"] = salvato.get("contratto") or veicolo.get("contratto")
            veicolo["codice_cliente"] = salvato.get("codice_cliente") or veicolo.get("codice_cliente")
            veicolo["centro_fatturazione"] = salvato.get("centro_fatturazione")
            veicolo["data_inizio"] = salvato.get("data_inizio")
            veicolo["data_fine"] = salvato.get("data_fine")
            veicolo["note"] = salvato.get("note")
            veicolo["id"] = salvato.get("id")
        
        risultato.append(veicolo)
    
    # Aggiungi veicoli salvati non presenti nelle fatture dell'anno
    for targa, salvato in veicoli_salvati.items():
        if targa not in veicoli_fatture:
            risultato.append({
                **salvato,
                "canoni": [],
                "pedaggio": [],
                "verbali": [],
                "bollo": [],
                "costi_extra": [],
                "riparazioni": [],
                "totale_canoni": 0,
                "totale_pedaggio": 0,
                "totale_verbali": 0,
                "totale_bollo": 0,
                "totale_costi_extra": 0,
                "totale_riparazioni": 0,
                "totale_generale": 0
            })
    
    # ── ARRICCHISCI CON I VERBALI (motore centralizzato, entrambe le fonti) ──
    # Per ogni veicolo del risultato, unisce verbali_noleggio (posta/PEC) e
    # verbali_noleggio_completi (estratti dalle fatture) deduplicati per
    # numero_verbale — un veicolo mostra così TUTTI i suoi verbali con stato
    # pagamento e disponibilità del bollettino/ricevuta, indipendentemente
    # da dove sono arrivati.
    for veicolo_target in risultato:
        targa = veicolo_target.get("targa")
        if not targa:
            continue
        verbali_completi = await _get_verbali_completi_per_targa(db, targa, anno)
        existing_nums = {v.get("numero_verbale") for v in veicolo_target.get("verbali", [])}
        for verbale in verbali_completi:
            if verbale["numero_verbale"] in existing_nums:
                continue
            importo = verbale["importo"]
            veicolo_target.setdefault("verbali", []).append({
                "data": verbale["data_verbale"],
                "numero_verbale": verbale["numero_verbale"],
                "descrizione": f"Verbale {verbale['numero_verbale']}",
                "importo": importo,
                "iva": 0,
                "totale": importo,
                "stato": verbale["stato"],
                "pagato": verbale["pagato"],
                "ha_ricevuta": verbale["ha_ricevuta"],
                "fonte": verbale["fonte"],
                "fattura_id": verbale["fattura_id"],
                "fattura_numero": verbale["fattura_numero"],
            })
            veicolo_target["totale_verbali"] = veicolo_target.get("totale_verbali", 0) + importo
            veicolo_target["totale_generale"] = veicolo_target.get("totale_generale", 0) + importo

    # Conta fatture davvero non associate
    fornitori_con_veicoli = set(v.get("fornitore_piva") for v in veicoli_salvati.values())
    fatture_davvero_non_associate = [
        f for f in fatture_senza_targa 
        if f.get("supplier_vat") not in fornitori_con_veicoli
    ]
    
    # Statistiche (DOPO arricchimento con verbali DB)
    statistiche = {
        "totale_canoni": round(sum(v.get("totale_canoni", 0) for v in risultato), 2),
        "totale_pedaggio": round(sum(v.get("totale_pedaggio", 0) for v in risultato), 2),
        "totale_verbali": round(sum(v.get("totale_verbali", 0) for v in risultato), 2),
        "totale_bollo": round(sum(v.get("totale_bollo", 0) for v in risultato), 2),
        "totale_costi_extra": round(sum(v.get("totale_costi_extra", 0) for v in risultato), 2),
        "totale_riparazioni": round(sum(v.get("totale_riparazioni", 0) for v in risultato), 2),
        "totale_generale": round(sum(v.get("totale_generale", 0) for v in risultato), 2)
    }
    
    return {
        "veicoli": sorted(risultato, key=lambda x: x.get("totale_generale", 0), reverse=True),
        "statistiche": statistiche,
        "count": len(risultato),
        "fatture_non_associate": len(fatture_davvero_non_associate),
        "anno": anno
    }


@router.get("/veicoli/{targa}/completo")
@handle_errors
async def get_veicolo_completo(targa: str, anno: Optional[int] = Query(None)) -> Dict[str, Any]:
    """
    Motore centralizzato del veicolo: un'unica vista con anagrafica,
    contratto, tutte le fatture/costi per categoria e tutti i verbali
    (posta + fatture, deduplicati) con stato pagamento e disponibilità
    del bollettino/ricevuta. Stessa aggregazione di GET /veicoli, filtrata
    su una targa — nessuna logica duplicata, nessun rischio di incoerenza
    tra la lista e il dettaglio.
    """
    dati = await get_veicoli(anno=anno)
    targa_upper = targa.upper()
    veicolo = next(
        (v for v in dati["veicoli"] if (v.get("targa") or "").upper() == targa_upper),
        None,
    )
    if not veicolo:
        raise HTTPException(status_code=404, detail=f"Veicolo {targa} non trovato")
    return veicolo


@router.get("/export-pdf-costi")
@handle_errors
async def export_pdf_costi(anno: Optional[int] = Query(None)) -> Any:
    """
    Genera PDF riepilogo costi noleggio auto per il commercialista.
    Include: canoni, verbali, bollo, pedaggio, riparazioni per veicolo.
    """
    from fastapi.responses import Response
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    import io
    
    if not anno:
        anno = datetime.now().year
    
    db = Database.get_db()
    veicoli_data, _ = await scan_fatture_noleggio(anno)
    
    # Merge con dati salvati
    veicoli_salvati = {}
    async for v in db[COLLECTION].find({}, {"_id": 0}):
        veicoli_salvati[v["targa"]] = v
    
    # Arricchisci con verbali
    verbali_db = await db["verbali_noleggio"].find(
        {"targa": {"$nin": [None, ""]}},
        {"_id": 0, "pdf_data": 0, "quietanza_pdf": 0}
    ).to_list(500)
    
    risultato = []
    for targa, dati in veicoli_data.items():
        salvato = veicoli_salvati.get(targa, {})
        v = {**dati, "driver": salvato.get("driver", ""), "marca": salvato.get("marca", ""), "modello": salvato.get("modello", "")}
        # Add verbali
        verb_importo = sum(float(vb.get("importo", 0) or 0) for vb in verbali_db if (vb.get("targa") or "").upper() == targa.upper())
        v["totale_verbali"] = v.get("totale_verbali", 0) + verb_importo
        risultato.append(v)
    
    for targa, salvato in veicoli_salvati.items():
        if targa not in veicoli_data:
            verb_importo = sum(float(vb.get("importo", 0) or 0) for vb in verbali_db if (vb.get("targa") or "").upper() == targa.upper())
            risultato.append({**salvato, "totale_canoni": 0, "totale_verbali": verb_importo, "totale_bollo": 0, "totale_pedaggio": 0, "totale_costi_extra": 0, "totale_riparazioni": 0})
    
    # Generate PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20*mm, bottomMargin=15*mm, leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()
    elements = []
    
    # Title
    title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=16, spaceAfter=6)
    elements.append(Paragraph(f"RIEPILOGO COSTI NOLEGGIO AUTO {anno}", title_style))
    elements.append(Paragraph("Ceraldi Group SRL - P.IVA 04523831214", styles['Normal']))
    elements.append(Spacer(1, 10*mm))
    
    # Summary table
    cat_labels = [("Canoni", "totale_canoni"), ("Verbali/Multe", "totale_verbali"), ("Bollo", "totale_bollo"), ("Pedaggio", "totale_pedaggio"), ("Costi Extra", "totale_costi_extra"), ("Riparazioni", "totale_riparazioni")]
    
    summary_data = [["Categoria", "Importo"]]
    totale_gen = 0
    for label, key in cat_labels:
        val = round(sum(v.get(key, 0) for v in risultato), 2)
        totale_gen += val
        summary_data.append([label, f"€ {val:,.2f}"])
    summary_data.append(["TOTALE GENERALE", f"€ {totale_gen:,.2f}"])
    
    t = Table(summary_data, colWidths=[120*mm, 50*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0f4ff')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f9fafb')]),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 8*mm))
    
    # Detail per vehicle
    elements.append(Paragraph("DETTAGLIO PER VEICOLO", ParagraphStyle('H2', parent=styles['Heading2'], fontSize=13)))
    elements.append(Spacer(1, 4*mm))
    
    detail_data = [["Targa", "Veicolo", "Driver", "Canoni", "Verbali", "Bollo", "Altro", "TOTALE"]]
    for v in risultato:
        tot = sum(v.get(k, 0) for _, k in cat_labels)
        detail_data.append([
            v.get("targa", ""),
            f"{v.get('marca', '')} {v.get('modello', '')[:20]}",
            v.get("driver", "-"),
            f"€ {v.get('totale_canoni', 0):,.2f}",
            f"€ {v.get('totale_verbali', 0):,.2f}",
            f"€ {v.get('totale_bollo', 0):,.2f}",
            f"€ {(v.get('totale_pedaggio', 0) + v.get('totale_costi_extra', 0) + v.get('totale_riparazioni', 0)):,.2f}",
            f"€ {tot:,.2f}",
        ])
    detail_data.append(["", "", "TOTALE", f"€ {sum(v.get('totale_canoni',0) for v in risultato):,.2f}", f"€ {sum(v.get('totale_verbali',0) for v in risultato):,.2f}", f"€ {sum(v.get('totale_bollo',0) for v in risultato):,.2f}", "", f"€ {totale_gen:,.2f}"])
    
    dt = Table(detail_data, colWidths=[18*mm, 35*mm, 28*mm, 22*mm, 22*mm, 18*mm, 18*mm, 22*mm])
    dt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0f4ff')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f9fafb')]),
    ]))
    elements.append(dt)
    elements.append(Spacer(1, 6*mm))
    
    # Footer
    elements.append(Paragraph(f"Documento generato il {datetime.now().strftime('%d-%m-%Y %H:%M')} — Ceraldi ERP", ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey)))
    
    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="riepilogo_costi_noleggio_{anno}.pdf"'}
    )



@router.get("/fatture-non-associate")
@handle_errors
async def get_fatture_non_associate(
    anno: Optional[int] = Query(None, description="Filtra per anno")
) -> Dict[str, Any]:
    """
    Restituisce le fatture di fornitori noleggio che non hanno targa.
    Utile per LeasePlan che richiede associazione manuale.
    """
    db = Database.get_db()
    _, fatture_senza_targa = await scan_fatture_noleggio(anno)
    
    # Carica veicoli salvati per filtrare
    veicoli_salvati = {}
    cursor = db[COLLECTION].find()
    async for v in cursor:
        veicoli_salvati[v["targa"]] = v
    
    # Filtra solo fatture di fornitori SENZA veicoli salvati o non ancora associate
    fornitori_con_veicoli = set(v.get("fornitore_piva") for v in veicoli_salvati.values())
    
    # Formatta correttamente le fatture per il frontend
    fatture_formattate = []
    for f in fatture_senza_targa:
        fatture_formattate.append({
            "id": f.get("invoice_id"),
            "numero": f.get("invoice_number"),
            "data": f.get("invoice_date"),
            "fornitore": f.get("supplier"),
            "piva": f.get("supplier_vat"),
            "importo": f.get("total", 0),
            "descrizione": ", ".join([l.get("descrizione", "")[:50] for l in f.get("linee", [])[:2]]),
            "tipo": f.get("tipo_documento"),
            "codice_cliente": f.get("codice_cliente")
        })
    
    return {
        "fatture": fatture_formattate,
        "count": len(fatture_formattate),
        "nota": "Queste fatture richiedono associazione manuale ad un veicolo"
    }


@router.get("/fornitori")
@handle_errors
async def get_fornitori() -> Dict[str, Any]:
    """Restituisce la lista dei fornitori noleggio supportati."""
    return {
        "fornitori": [
            {"nome": "ALD Automotive Italia S.r.l.", "piva": "01924961004", "targa_in_fattura": True, "contratto_in_fattura": True},
            {"nome": "ARVAL SERVICE LEASE ITALIA SPA", "piva": "04911190488", "targa_in_fattura": True, "contratto_in_fattura": True},
            {"nome": "Leasys Italia S.p.A", "piva": "06714021000", "targa_in_fattura": True, "contratto_in_fattura": False},
            {"nome": "LeasePlan Italia S.p.A.", "piva": "02615080963", "targa_in_fattura": False, "contratto_in_fattura": False}
        ]
    }


@router.get("/drivers")
@handle_errors
async def get_drivers() -> Dict[str, Any]:
    """Lista dipendenti disponibili come driver."""
    db = Database.get_db()
    
    dipendenti = []
    cursor = db["dipendenti"].find({}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1})
    async for d in cursor:
        dipendenti.append({
            "id": d.get("id"),
            "nome_completo": f"{d.get('nome', '')} {d.get('cognome', '')}".strip()
        })
    
    return {"drivers": dipendenti}


@router.post("/veicoli")
@handle_errors
async def create_veicolo(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea un nuovo veicolo a noleggio."""
    db = Database.get_db()
    targa = (data.get("targa") or "").upper().strip()
    if not targa:
        raise HTTPException(status_code=400, detail="Targa obbligatoria")

    existing = await db[COLLECTION].find_one({"targa": targa})
    if existing:
        raise HTTPException(status_code=409, detail=f"Veicolo {targa} già esistente")

    veicolo = {
        "targa": targa,
        "marca": data.get("marca", ""),
        "modello": data.get("modello", ""),
        "driver_id": data.get("driver_id"),
        "driver_nome": data.get("driver_nome", ""),
        "fornitore_piva": data.get("fornitore_piva", ""),
        "data_inizio": data.get("data_inizio"),
        "data_fine": data.get("data_fine"),
        "canone_mensile": float(data.get("canone_mensile", 0) or 0),
        "anno_immatricolazione": data.get("anno_immatricolazione"),
        "alimentazione": data.get("alimentazione"),
        "potenza_kw": data.get("potenza_kw"),
        "cilindrata": data.get("cilindrata"),
        "note": data.get("note", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[COLLECTION].insert_one(veicolo.copy())
    veicolo.pop("_id", None)
    return veicolo


@router.put("/veicoli/{targa}")
@handle_errors
async def update_veicolo(
    targa: str,
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """Aggiorna i dati di un veicolo (driver, date noleggio, marca, modello, contratto)."""
    db = Database.get_db()
    
    # Verifica driver se passato
    if data.get("driver_id"):
        dipendente = await db["dipendenti"].find_one(
            {"id": data["driver_id"]}, 
            {"_id": 0, "id": 1, "nome": 1, "cognome": 1}
        )
        if not dipendente:
            raise HTTPException(status_code=400, detail=f"Dipendente con ID {data['driver_id']} non trovato")
        data["driver"] = f"{dipendente.get('nome', '')} {dipendente.get('cognome', '')}".strip()
    
    update_data = {
        "targa": targa.upper(),
        "updated_at": datetime.now(timezone.utc)
    }
    
    # Campi aggiornabili. Include i campi specifica veicolo (anno_immatricolazione,
    # alimentazione, potenza_kw, cilindrata) valorizzati dal lookup OpenAPI
    # Automotive e canone_mensile: prima venivano persi in salvataggio perché
    # assenti da questa whitelist, nonostante il frontend li raccogliesse.
    for campo in ["driver", "driver_id", "marca", "modello", "contratto",
                  "codice_cliente", "centro_fatturazione",
                  "data_inizio", "data_fine", "note", "fornitore_noleggio", "fornitore_piva",
                  "canone_mensile", "anno_immatricolazione", "alimentazione",
                  "potenza_kw", "cilindrata"]:
        if campo in data:
            update_data[campo] = data[campo]
    
    result = await db[COLLECTION].update_one(
        {"targa": targa.upper()},
        {"$set": update_data, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    
    return {
        "success": True,
        "targa": targa.upper(),
        "message": "Veicolo aggiornato" if result.modified_count else "Veicolo creato"
    }


@router.delete("/veicoli/{targa}")
@handle_errors
async def delete_veicolo(targa: str) -> Dict[str, Any]:
    """Elimina un veicolo dalla gestione (non elimina le fatture)."""
    db = Database.get_db()
    
    result = await db[COLLECTION].delete_one({"targa": targa.upper()})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Veicolo non trovato")
    
    return {"success": True, "message": f"Veicolo {targa} rimosso dalla gestione"}


@router.post("/associa-fornitore")
@handle_errors
async def associa_fornitore(
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Associa manualmente un fornitore (es: LeasePlan) ad una targa.
    Necessario per fornitori che non includono la targa nelle fatture.
    """
    db = Database.get_db()
    
    targa = data.get("targa", "").upper()
    fornitore_piva = data.get("fornitore_piva")
    
    if not targa or not fornitore_piva:
        raise HTTPException(status_code=400, detail="Targa e fornitore_piva sono obbligatori")
    
    if fornitore_piva not in FORNITORI_NOLEGGIO.values():
        raise HTTPException(status_code=400, detail=f"Fornitore non riconosciuto. Validi: {list(FORNITORI_NOLEGGIO.values())}")
    
    fornitore_nome = next((k for k, v in FORNITORI_NOLEGGIO.items() if v == fornitore_piva), "")
    
    update_data = {
        "targa": targa,
        "fornitore_piva": fornitore_piva,
        "fornitore_noleggio": fornitore_nome,
        "marca": data.get("marca", ""),
        "modello": data.get("modello", ""),
        "contratto": data.get("contratto", ""),
        "updated_at": datetime.now(timezone.utc)
    }
    
    result = await db[COLLECTION].update_one(
        {"targa": targa},
        {"$set": update_data, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    
    _ = result  # Upsert always succeeds
    
    return {
        "success": True,
        "targa": targa,
        "fornitore": fornitore_nome,
        "message": f"Targa {targa} associata a {fornitore_nome}"
    }




@router.get("/verbali-dipendente")
@handle_errors
async def get_verbali_dipendente(
    dipendente_id: str = Query(default="", description="ID dipendente"),
    codice_fiscale: str = Query(default="", description="Codice fiscale dipendente")
) -> Dict[str, Any]:
    """
    Lista verbali/multe associati a un dipendente (tramite driver_id o driver_cf).
    Usato nella sezione HR → Tab Verbali del dipendente.
    """
    db = Database.get_db()
    
    if not dipendente_id and not codice_fiscale:
        return {"verbali": [], "totale": 0}
    
    # Cerca verbali per driver_id, driver_cf, o codice_fiscale
    query_conditions = []
    if dipendente_id:
        query_conditions.append({"driver_id": dipendente_id})
    if codice_fiscale:
        query_conditions.append({"driver_cf": codice_fiscale})
    
    if not query_conditions:
        return {"verbali": [], "totale": 0}
    
    cursor = db["verbali_noleggio"].find(
        {"$or": query_conditions},
        {"_id": 0, "pdf_data": 0, "quietanza_pdf": 0}
    ).sort("created_at", -1)
    
    verbali = await cursor.to_list(500)
    
    return {
        "verbali": verbali,
        "totale": len(verbali),
        "pagati": sum(1 for v in verbali if v.get("stato") == "pagato"),
        "da_pagare": sum(1 for v in verbali if v.get("stato") != "pagato"),
        "importo_totale": sum(float(v.get("importo", 0) or 0) for v in verbali)
    }
