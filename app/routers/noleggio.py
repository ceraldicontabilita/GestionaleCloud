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
    categorizza_spesa,
    estrai_causale_note,
    scegli_veicolo_per_fattura
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
            "data_verbale": str(v.get("data_verbale") or v.get("created_at") or "")[:10],
            "importo": float(v.get("importo") or 0),
            "stato": v.get("stato"),
            "pagato": bool(
                v.get("stato") in ("pagato", "riconciliato", "chiuso")
                or v.get("pagamento_id") or v.get("paypal_transaction_id")
                or v.get("ricevuta_pagopa_id") or v.get("movimento_banca_id")
            ),
            "fattura_id": v.get("fattura_id") or v.get("fattura_associata_id"),
            "fattura_numero": (
                v.get("fattura_numero") or v.get("fattura_associata_numero")
                or v.get("numero_fattura")
            ),
            "ha_ricevuta": bool(
                v.get("pdf_ricevuta_path") or v.get("quietanza_ricevuta")
                or v.get("ricevuta_pagopa_id")
            ),
            "metodo_pagamento": v.get("psp") or v.get("metodo_pagamento") or v.get("metodo"),
            "pagamento_id": (
                v.get("pagamento_id") or v.get("paypal_transaction_id")
                or v.get("ricevuta_pagopa_id") or v.get("movimento_banca_id")
            ),
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
            "data_verbale": str(esistente.get("data_verbale") or v.get("data_verbale") or v.get("data") or "")[:10],
            "importo": esistente.get("importo") or float(v.get("importo") or 0),
            "stato": esistente.get("stato") or stato_pagamento,
            "pagato": esistente.get("pagato", False) or stato_pagamento == "pagato",
            "fattura_id": esistente.get("fattura_id") or v.get("fattura_id"),
            "fattura_numero": esistente.get("fattura_numero") or v.get("numero_fattura"),
            "ha_ricevuta": esistente.get("ha_ricevuta", False),
            "fonte": "posta+fattura" if esistente else "fattura",
        }

    # Responsabile ALLA DATA dell'infrazione (storico assegnazioni, motore
    # controlli): il verbale di marzo va al driver che aveva l'auto a marzo,
    # non a quello attuale. Fallback esplicito al driver corrente se lo
    # storico non copre la data.
    veicolo = await db[COLLECTION].find_one({"targa": targa_upper}, {"_id": 0})
    if veicolo:
        from app.services.noleggio import driver_alla_data
        for v in verbali_per_numero.values():
            v["driver_competente"] = driver_alla_data(veicolo, v.get("data_verbale"))

    return sorted(
        verbali_per_numero.values(),
        key=lambda x: x.get("data_verbale") or "",
        reverse=True,
    )


@router.post("/controllo-canoni")
@handle_errors
async def controllo_canoni_manuale() -> Dict[str, Any]:
    """Lancia subito il controllo regolarità canoni (di norma gira ogni
    giorno alle 7:45). Contratti cessati esclusi per regola."""
    db = Database.get_db()
    from app.services.noleggio import controlla_regolarita_canoni
    return await controlla_regolarita_canoni(db)


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
    
    # Associa fatture senza targa ai veicoli salvati. Traccia quali sono
    # state associate con certezza (fornitore con un solo veicolo, o
    # numero contratto combaciante) — quelle NON compaiono più tra le
    # "fatture non associate" più sotto, perché la scelta non è una stima.
    fatture_id_confidenti: set = set()
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

        target_targa, certo = scegli_veicolo_per_fattura(
            fattura, veicoli_fornitore, set(veicoli_fatture.keys())
        )
        if certo and fattura_id:
            fatture_id_confidenti.add(fattura_id)

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
                "contratto": salvato.get("contratto") or fattura.get("contratto"),
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
            note_extra = estrai_causale_note(linea)
            categoria, importo, metadata = categorizza_spesa(desc, prezzo, is_nota_credito, note_extra)
            
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
            veicolo["canone_mensile"] = salvato.get("canone_mensile")
            # Specifiche veicolo: preferisci il valore inserito/confermato a
            # mano, altrimenti usa quello estratto dalla fattura (AltriDatiGestionali).
            # Prima questi campi non venivano proprio applicati dal merge:
            # un valore modificato manualmente non veniva mai mostrato.
            data_immat = veicolo.get("data_immatricolazione") or ""
            veicolo["anno_immatricolazione"] = salvato.get("anno_immatricolazione") or (data_immat[:4] or None)
            veicolo["alimentazione"] = salvato.get("alimentazione") or veicolo.get("alimentazione")
            veicolo["potenza_kw"] = salvato.get("potenza_kw") or veicolo.get("potenza_kw")
            veicolo["cilindrata"] = salvato.get("cilindrata") or veicolo.get("cilindrata")
            veicolo["telaio"] = salvato.get("telaio") or veicolo.get("telaio")
            # Specifica Noleggio 10-07-2026: stato contratto (deciso solo
            # dall'utente), canone previsto, fringe benefit, storico driver
            veicolo["stato_contratto"] = salvato.get("stato_contratto") or "attivo"
            veicolo["stato_veicolo"] = salvato.get("stato_veicolo")
            veicolo["canone_previsto"] = salvato.get("canone_previsto")
            veicolo["fringe_benefit"] = salvato.get("fringe_benefit")
            veicolo["assegnazioni"] = salvato.get("assegnazioni") or []

        # Canone mensile: se non è stato configurato a mano, lo stimiamo dal
        # canone più recente effettivamente fatturato — meglio di lasciarlo
        # sempre vuoto. Segnaliamo la stima con canone_mensile_stimato=True
        # così la UI può distinguerla da un valore inserito manualmente.
        if not veicolo.get("canone_mensile"):
            canoni_ordinati = sorted(
                veicolo.get("canoni", []), key=lambda c: c.get("data") or "", reverse=True
            )
            if canoni_ordinati:
                veicolo["canone_mensile"] = canoni_ordinati[0].get("imponibile")
                veicolo["canone_mensile_stimato"] = True

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
        existing_by_numero = {
            v.get("numero_verbale"): v
            for v in veicolo_target.get("verbali", []) if v.get("numero_verbale")
        }
        for verbale in verbali_completi:
            if verbale["numero_verbale"] in existing_by_numero:
                riga = existing_by_numero[verbale["numero_verbale"]]
                riga.update({
                    "stato": verbale["stato"],
                    "pagato": verbale["pagato"],
                    "ha_ricevuta": verbale["ha_ricevuta"],
                    "fonte": verbale["fonte"],
                    "fattura_id": verbale["fattura_id"] or riga.get("fattura_id"),
                    "fattura_numero": verbale["fattura_numero"] or riga.get("numero_fattura"),
                    "pagamento_id": verbale.get("pagamento_id"),
                    "metodo_pagamento": verbale.get("metodo_pagamento"),
                })
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
                "pagamento_id": verbale.get("pagamento_id"),
                "metodo_pagamento": verbale.get("metodo_pagamento"),
            })
            veicolo_target["totale_verbali"] = veicolo_target.get("totale_verbali", 0) + importo
            veicolo_target["totale_generale"] = veicolo_target.get("totale_generale", 0) + importo

    # Conta le fatture che richiedono DAVVERO una revisione manuale: quelle
    # associate con certezza (scegli_veicolo_per_fattura -> certo=True,
    # fornitore con un solo veicolo o numero contratto combaciante) NON
    # compaiono qui, perché non sono una stima ma un'associazione affidabile.
    # Restano invece le fatture di fornitori senza alcun veicolo salvato, e
    # quelle assegnate "per ripiego" quando il fornitore ha più veicoli e
    # nessun contratto combacia (scelta arbitraria, va verificata).
    fatture_davvero_non_associate = [
        f for f in fatture_senza_targa
        if f.get("invoice_id") not in fatture_id_confidenti
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
    
    # Il PDF deve essere una rappresentazione della stessa vista mostrata
    # nella pagina, non un secondo motore contabile. ``get_veicoli`` unisce
    # gia fatture, anagrafica, verbali da posta/fatture e deduplica per numero.
    # Riutilizzandolo evitiamo totali divergenti e doppi conteggi dei verbali.
    dati_aggregati = await get_veicoli(anno=anno)
    risultato = dati_aggregati["veicoli"]
    
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
    Restituisce le fatture di fornitori noleggio che non hanno targa E che
    richiedono davvero una scelta manuale — stessa logica/stesso conteggio
    di GET /veicoli::fatture_non_associate (scegli_veicolo_per_fattura):
    le fatture associate con certezza (fornitore con un solo veicolo, o
    numero contratto combaciante) non compaiono, perché già risolte.
    """
    db = Database.get_db()
    _, fatture_senza_targa = await scan_fatture_noleggio(anno)

    veicoli_salvati: Dict[str, Any] = {}
    cursor = db[COLLECTION].find({}, {"_id": 0})
    async for v in cursor:
        veicoli_salvati[v["targa"]] = v

    fatture_formattate = []
    for f in fatture_senza_targa:
        veicoli_fornitore = [
            (targa, salvato) for targa, salvato in veicoli_salvati.items()
            if salvato.get("fornitore_piva") == f["supplier_vat"]
        ]
        _, certo = scegli_veicolo_per_fattura(f, veicoli_fornitore, set())
        if certo:
            continue
        fatture_formattate.append({
            "id": f.get("invoice_id"),
            "numero": f.get("invoice_number"),
            "data": f.get("invoice_date"),
            "fornitore": f.get("supplier"),
            "piva": f.get("supplier_vat"),
            "importo": f.get("total", 0),
            "descrizione": ", ".join([l.get("descrizione", "")[:50] for l in f.get("linee", [])[:2]]),
            "tipo": f.get("tipo_documento"),
            "codice_cliente": f.get("codice_cliente"),
            "contratto": f.get("contratto")
        })

    return {
        "fatture": fatture_formattate,
        "count": len(fatture_formattate),
        "nota": "Queste fatture richiedono associazione manuale ad un veicolo"
    }


@router.get("/riepilogo-controlli")
@handle_errors
async def get_riepilogo_controlli(
    anno: Optional[int] = Query(None, description="Anno per le fatture non associate")
) -> Dict[str, Any]:
    """
    Cruscotto di controllo del noleggio: in un colpo solo i conteggi e le
    prime 10 voci di tutto ciò che richiede attenzione — verbali non
    pagati/chiusi (unione delle due fonti, dedup per numero_verbale come
    _get_verbali_completi_per_targa ma senza filtro targa), trattenute
    da confermare, contratti cessati, auto senza driver, fatture non
    associate, pagamenti fornitori noleggio non riconciliati (anno
    corrente) e alert NOL_* aperti del motore alert.
    """
    db = Database.get_db()
    LIMITE_VOCI = 10
    STATI_VERBALE_CHIUSI = ("pagato", "chiuso")

    # ── 1) Verbali aperti: unione posta + fatture, dedup numero_verbale ──
    verbali_per_numero: Dict[str, Dict[str, Any]] = {}
    proiezione_posta = {
        "_id": 0, "numero_verbale": 1, "numero_verbale_old": 1, "targa": 1,
        "data_verbale": 1, "created_at": 1, "importo": 1, "stato": 1, "driver": 1,
    }
    async for v in db[COLLECTION_VERBALI_POSTA].find({}, proiezione_posta):
        numero = v.get("numero_verbale") or v.get("numero_verbale_old")
        if not numero:
            continue
        stato = v.get("stato")
        verbali_per_numero[numero] = {
            "numero_verbale": numero,
            "targa": (v.get("targa") or "").upper(),
            "data_verbale": str(v.get("data_verbale") or v.get("created_at") or "")[:10],
            "importo": float(v.get("importo") or 0),
            "stato": stato,
            "chiuso": stato in STATI_VERBALE_CHIUSI,
            "driver": v.get("driver"),
            "fonte": "posta",
        }
    proiezione_fatture = {
        "_id": 0, "numero_verbale": 1, "targa": 1, "data_verbale": 1,
        "data": 1, "importo": 1, "stato_pagamento": 1,
    }
    async for v in db[COLLECTION_VERBALI_FATTURE].find({}, proiezione_fatture):
        numero = v.get("numero_verbale")
        if not numero:
            continue
        esistente = verbali_per_numero.get(numero, {})
        stato_pagamento = v.get("stato_pagamento")
        verbali_per_numero[numero] = {
            **esistente,
            "numero_verbale": numero,
            "targa": esistente.get("targa") or (v.get("targa") or "").upper(),
            "data_verbale": str(esistente.get("data_verbale") or v.get("data_verbale") or v.get("data") or "")[:10],
            "importo": esistente.get("importo") or float(v.get("importo") or 0),
            "stato": esistente.get("stato") or stato_pagamento,
            # Chiuso se ALMENO UNA delle due fonti lo dà pagato/chiuso —
            # stessa semantica del flag "pagato" del motore per targa.
            "chiuso": esistente.get("chiuso", False) or stato_pagamento in STATI_VERBALE_CHIUSI,
            "fonte": "posta+fattura" if esistente else "fattura",
        }
    verbali_aperti = sorted(
        (v for v in verbali_per_numero.values() if not v.pop("chiuso", False)),
        key=lambda x: x.get("data_verbale") or "",
        reverse=True,
    )

    # ── 2) Trattenute dipendenti da confermare: stato 'proposta', il
    # legacy 'da_applicare' (record pre-ciclo di vita) o assente ──
    query_trattenute = {"$or": [
        {"stato": {"$in": ["proposta", "da_applicare"]}},
        {"stato": None},
    ]}
    proiezione_trattenute = {
        "_id": 0, "id": 1, "dipendente_id": 1, "dipendente_nome": 1, "importo": 1,
        "descrizione": 1, "mese": 1, "anno": 1, "numero_verbale": 1, "targa": 1, "stato": 1,
    }
    trattenute_count = await db["trattenute_dipendenti"].count_documents(query_trattenute)
    trattenute_items = await db["trattenute_dipendenti"].find(
        query_trattenute, proiezione_trattenute
    ).sort("created_at", -1).to_list(LIMITE_VOCI)

    # ── 3) Contratti cessati/chiusi ──
    query_cessati = {"stato_contratto": {"$in": ["cessato", "chiuso"]}}
    proiezione_veicolo = {
        "_id": 0, "targa": 1, "marca": 1, "modello": 1, "driver": 1,
        "fornitore_noleggio": 1, "data_fine": 1, "stato_contratto": 1,
    }
    cessati_count = await db[COLLECTION].count_documents(query_cessati)
    cessati_items = await db[COLLECTION].find(
        query_cessati, proiezione_veicolo
    ).sort("data_fine", -1).to_list(LIMITE_VOCI)

    # ── 4) Auto senza driver (contratto non cessato) ──
    # $in con None copre sia campo assente sia campo nullo/vuoto.
    query_senza_driver = {
        "driver": {"$in": [None, ""]},
        "driver_id": {"$in": [None, ""]},
        "stato_contratto": {"$nin": ["cessato", "chiuso"]},
    }
    senza_driver_count = await db[COLLECTION].count_documents(query_senza_driver)
    senza_driver_items = await db[COLLECTION].find(
        query_senza_driver, proiezione_veicolo
    ).sort("targa", 1).to_list(LIMITE_VOCI)

    # ── 5) Fatture non associate: riusa l'endpoint esistente ──
    dati_fatture = await get_fatture_non_associate(anno=anno)
    fatture_items = dati_fatture.get("fatture", [])

    # ── 6) Pagamenti non riconciliati: fatture fornitori noleggio anno
    # corrente né pagate né riconciliate, proiezione minima ──
    anno_corrente = datetime.now().year
    query_pagamenti = {
        "supplier_vat": {"$in": list(FORNITORI_NOLEGGIO.values())},
        "invoice_date": {"$regex": f"^{anno_corrente}"},
        "pagato": {"$ne": True},
        "riconciliato": {"$ne": True},
    }
    proiezione_pagamenti = {
        "_id": 0, "invoice_number": 1, "invoice_date": 1,
        "supplier_name": 1, "supplier_vat": 1, "total_amount": 1,
    }
    pagamenti_count = await db["invoices"].count_documents(query_pagamenti)
    pagamenti_items = await db["invoices"].find(
        query_pagamenti, proiezione_pagamenti
    ).sort("invoice_date", -1).to_list(LIMITE_VOCI)

    # ── 7) Alert NOL_* aperti dal motore alert (collection 'alerts') ──
    query_alert = {"codice": {"$regex": "^NOL_"}, "stato": "aperto"}
    proiezione_alert = {
        "_id": 0, "id": 1, "codice": 1, "titolo": 1, "dettaglio": 1,
        "severita": 1, "entita_id": 1, "created_at": 1,
    }
    alert_count = await db["alerts"].count_documents(query_alert)
    alert_items = await db["alerts"].find(
        query_alert, proiezione_alert
    ).sort("created_at", -1).to_list(LIMITE_VOCI)

    sezioni = {
        "verbali_aperti": {"count": len(verbali_aperti), "items": verbali_aperti[:LIMITE_VOCI]},
        "trattenute_da_confermare": {"count": trattenute_count, "items": trattenute_items},
        "contratti_cessati": {"count": cessati_count, "items": cessati_items},
        "auto_senza_driver": {"count": senza_driver_count, "items": senza_driver_items},
        "fatture_non_associate": {"count": len(fatture_items), "items": fatture_items[:LIMITE_VOCI]},
        "pagamenti_non_riconciliati": {"count": pagamenti_count, "items": pagamenti_items},
        "alert_aperti": {"count": alert_count, "items": alert_items},
    }
    return {
        **sezioni,
        "totale_segnalazioni": sum(s["count"] for s in sezioni.values()),
        "anno_pagamenti": anno_corrente,
        "anno": anno,
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
    # stato_contratto/stato_veicolo/canone_previsto/fringe_benefit/assegnazioni:
    # specifica Noleggio 10-07-2026 (lo stato contratto lo cambia SOLO l'utente;
    # assegnazioni = storico driver [{driver, driver_id, dal, al}]).
    for campo in ["driver", "driver_id", "marca", "modello", "contratto",
                  "codice_cliente", "centro_fatturazione",
                  "data_inizio", "data_fine", "note", "fornitore_noleggio", "fornitore_piva",
                  "canone_mensile", "anno_immatricolazione", "alimentazione",
                  "potenza_kw", "cilindrata",
                  "stato_contratto", "stato_veicolo", "canone_previsto",
                  "fringe_benefit", "assegnazioni"]:
        if campo in data:
            update_data[campo] = data[campo]

    # Cambio driver = nuovo capitolo dello storico assegnazioni: chiudiamo
    # l'assegnazione aperta e ne apriamo una nuova, così i verbali futuri
    # trovano il responsabile GIUSTO alla data dell'infrazione.
    if data.get("driver") or data.get("driver_id"):
        oggi = datetime.now(timezone.utc).date().isoformat()
        esistente = await db[COLLECTION].find_one(
            {"targa": targa.upper()}, {"_id": 0, "driver": 1, "driver_id": 1, "assegnazioni": 1}
        ) or {}
        if (esistente.get("driver_id") or esistente.get("driver")) and (
            esistente.get("driver_id") != data.get("driver_id")
        ):
            storico = esistente.get("assegnazioni") or []
            aperte = [a for a in storico if not a.get("al")]
            for a in aperte:
                a["al"] = oggi
            storico = [a for a in storico if a.get("al")] + [{
                "driver": update_data.get("driver", esistente.get("driver")),
                "driver_id": update_data.get("driver_id", esistente.get("driver_id")),
                "dal": oggi,
                "al": None,
            }]
            update_data["assegnazioni"] = data.get("assegnazioni", storico)
    
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
