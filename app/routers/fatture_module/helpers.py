"""
Fatture Module - Helper functions per import e gestione fatture.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid

from .common import COL_FORNITORI, COL_FATTURE_RICEVUTE, COL_DETTAGLIO_RIGHE, COL_ALLEGATI, logger


async def get_or_create_fornitore(db, parsed_data: Dict) -> Dict[str, Any]:
    """
    Verifica se il fornitore esiste (chiave: Partita IVA).
    Se non esiste, lo crea automaticamente.
    """
    fornitore_xml = parsed_data.get("fornitore", {})
    partita_iva = fornitore_xml.get("partita_iva") or parsed_data.get("supplier_vat")
    
    if not partita_iva:
        return {"fornitore_id": None, "nuovo": False, "error": "Partita IVA mancante"}
    
    partita_iva = partita_iva.strip().upper().replace(" ", "")
    
    existing = await db[COL_FORNITORI].find_one({"partita_iva": partita_iva}, {"_id": 0})
    
    if existing:
        await db[COL_FORNITORI].update_one(
            {"partita_iva": partita_iva},
            {"$inc": {"fatture_count": 1}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        return {
            "fornitore_id": existing.get("id"),
            "partita_iva": partita_iva,
            "ragione_sociale": existing.get("ragione_sociale"),
            "metodo_pagamento": existing.get("metodo_pagamento"),
            "iban": existing.get("iban"),
            "nuovo": False
        }
    
    nuovo_fornitore = {
        "id": str(uuid.uuid4()),
        "partita_iva": partita_iva,
        "codice_fiscale": fornitore_xml.get("codice_fiscale", partita_iva),
        "ragione_sociale": fornitore_xml.get("denominazione") or parsed_data.get("supplier_name", ""),
        "denominazione": fornitore_xml.get("denominazione") or parsed_data.get("supplier_name", ""),
        "indirizzo": fornitore_xml.get("indirizzo", ""),
        "cap": fornitore_xml.get("cap", ""),
        "comune": fornitore_xml.get("comune", ""),
        "provincia": fornitore_xml.get("provincia", ""),
        "nazione": fornitore_xml.get("nazione", "IT"),
        "telefono": fornitore_xml.get("telefono", ""),
        "email": fornitore_xml.get("email", ""),
        "pec": "",
        "iban": "",
        "metodo_pagamento": None,
        "giorni_pagamento": 30,
        "fatture_count": 1,
        "attivo": True,
        "source": "auto_import_xml",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Creato automaticamente da importazione fattura XML"
    }
    
    await db[COL_FORNITORI].insert_one(nuovo_fornitore.copy())
    logger.info(f"Nuovo fornitore creato: {nuovo_fornitore['ragione_sociale']} (P.IVA: {partita_iva})")
    
    return {
        "fornitore_id": nuovo_fornitore["id"],
        "partita_iva": partita_iva,
        "ragione_sociale": nuovo_fornitore["ragione_sociale"],
        "nuovo": True
    }


async def check_duplicato(db, partita_iva: str, numero_documento: str) -> Optional[Dict]:
    """Verifica duplicati per P.IVA + Numero Documento."""
    if not partita_iva or not numero_documento:
        return None
    
    partita_iva = partita_iva.strip().upper()
    numero_documento = numero_documento.strip().upper()
    
    return await db[COL_FATTURE_RICEVUTE].find_one(
        {
            "fornitore_partita_iva": partita_iva,
            "numero_documento": {"$regex": f"^{numero_documento}$", "$options": "i"}
        },
        {"_id": 0, "id": 1, "numero_documento": 1, "data_documento": 1, "importo_totale": 1}
    )


async def salva_dettaglio_righe(db, fattura_id: str, linee: List[Dict]) -> int:
    """Salva righe dettaglio fattura in collection separata."""
    if not linee:
        return 0
    
    righe_da_inserire = []
    for idx, linea in enumerate(linee):
        try:
            prezzo_unitario = float(linea.get("prezzo_unitario", 0))
            quantita = float(linea.get("quantita", 1))
            prezzo_totale = float(linea.get("prezzo_totale", 0))
            aliquota_iva = float(linea.get("aliquota_iva", 0))
        except (ValueError, TypeError):
            prezzo_unitario, quantita, prezzo_totale, aliquota_iva = 0, 1, 0, 0
        
        riga = {
            "id": str(uuid.uuid4()),
            "fattura_id": fattura_id,
            "numero_linea": linea.get("numero_linea", str(idx + 1)),
            "descrizione": linea.get("descrizione", ""),
            "quantita": quantita,
            "unita_misura": linea.get("unita_misura", ""),
            "prezzo_unitario": prezzo_unitario,
            "prezzo_totale": prezzo_totale,
            "aliquota_iva": aliquota_iva,
            "natura_iva": linea.get("natura", ""),
            "lotto_fornitore": linea.get("lotto_fornitore"),
            "data_scadenza": linea.get("scadenza_prodotto"),
            "lotto_estratto_auto": linea.get("lotto_estratto_automaticamente", False),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        righe_da_inserire.append(riga)
    
    if righe_da_inserire:
        await db[COL_DETTAGLIO_RIGHE].insert_many(righe_da_inserire)
    
    return len(righe_da_inserire)


async def salva_allegato_pdf(db, fattura_id: str, allegato: Dict) -> Optional[str]:
    """Salva allegato PDF decodificato."""
    if not allegato.get("base64_data"):
        return None
    
    allegato_doc = {
        "id": str(uuid.uuid4()),
        "fattura_id": fattura_id,
        "nome_file": allegato.get("nome", "allegato.pdf"),
        "formato": allegato.get("formato", "PDF"),
        "descrizione": allegato.get("descrizione", ""),
        "base64_data": allegato["base64_data"],
        "size_kb": allegato.get("size_kb", 0),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db[COL_ALLEGATI].insert_one(allegato_doc.copy())
    return allegato_doc["id"]


def generate_invoice_html(fattura: Dict, righe_fattura: List[Dict] = None) -> str:
    """Genera HTML preview della fattura stile AssoInvoice."""
    # Supporta entrambi i formati di campi (XML import e legacy)
    fornitore = (fattura.get("fornitore_ragione_sociale") or 
                 fattura.get("supplier_name") or 
                 fattura.get("cedente_denominazione") or 
                 fattura.get("fornitore", {}).get("denominazione") or "N/A")
    piva = (fattura.get("fornitore_partita_iva") or 
            fattura.get("supplier_vat") or 
            fattura.get("cedente_piva") or 
            fattura.get("fornitore", {}).get("partita_iva") or "N/A")
    numero = fattura.get("numero_documento") or fattura.get("invoice_number") or fattura.get("numero") or "N/A"
    data = fattura.get("data_documento") or fattura.get("invoice_date") or fattura.get("data") or "N/A"
    
    # Converti sempre in float per evitare errori di formattazione
    def safe_float(val):
        if val is None:
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0
    
    importo = safe_float(fattura.get("importo_totale") or fattura.get("total_amount"))
    imponibile = safe_float(fattura.get("imponibile"))
    iva = safe_float(fattura.get("imposta") or fattura.get("iva"))
    stato = fattura.get("stato_pagamento") or fattura.get("stato") or "non_pagata"
    metodo = fattura.get("metodo_pagamento") or "N/A"
    
    # Se le righe sono nel documento stesso, usale
    if not righe_fattura and fattura.get("linee"):
        righe_fattura = fattura.get("linee", [])
    
    stato_badge = {
        "pagata": '<span style="background:#22c55e;color:white;padding:4px 12px;border-radius:4px;">PAGATA</span>',
        "pagato": '<span style="background:#22c55e;color:white;padding:4px 12px;border-radius:4px;">PAGATA</span>',
        "non_pagata": '<span style="background:#ef4444;color:white;padding:4px 12px;border-radius:4px;">NON PAGATA</span>',
        "parziale": '<span style="background:#f59e0b;color:white;padding:4px 12px;border-radius:4px;">PARZIALE</span>'
    }.get(stato, f'<span style="background:#6b7280;color:white;padding:4px 12px;border-radius:4px;">{str(stato).upper()}</span>')
    
    righe_html = ""
    if righe_fattura:
        for r in righe_fattura:
            # Safe conversions per le righe
            prezzo_unit = safe_float(r.get('prezzo_unitario', 0))
            prezzo_tot = safe_float(r.get('prezzo_totale', 0))
            qta = safe_float(r.get('quantita', 1))
            aliq = safe_float(r.get('aliquota_iva', 22))
            righe_html += f"""
            <tr>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;">{r.get('numero_linea', '')}</td>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;">{r.get('descrizione', '')[:80]}</td>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;">{qta:.0f}</td>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;">€{prezzo_unit:.2f}</td>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;">{aliq:.0f}%</td>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:right;">€{prezzo_tot:.2f}</td>
            </tr>"""
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Fattura {numero}</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f3f4f6; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
            .header {{ background: linear-gradient(135deg, #1e40af, #3b82f6); color: white; padding: 24px; border-radius: 8px 8px 0 0; }}
            .content {{ padding: 24px; }}
            .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }}
            .section {{ background: #f9fafb; padding: 16px; border-radius: 8px; }}
            .label {{ font-size: 12px; color: #6b7280; text-transform: uppercase; margin-bottom: 4px; }}
            .value {{ font-size: 16px; font-weight: 500; color: #111827; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th {{ background: #f3f4f6; padding: 12px 8px; text-align: left; font-weight: 600; }}
            .totals {{ background: #1e40af; color: white; padding: 16px; border-radius: 8px; margin-top: 24px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div>
                        <h1 style="margin:0;font-size:24px;">Fattura #{numero}</h1>
                        <p style="margin:8px 0 0;opacity:0.9;">Data: {data}</p>
                    </div>
                    <div>{stato_badge}</div>
                </div>
            </div>
            <div class="content">
                <div class="grid">
                    <div class="section">
                        <div class="label">Fornitore</div>
                        <div class="value">{fornitore}</div>
                        <div style="margin-top:8px;color:#6b7280;">P.IVA: {piva}</div>
                    </div>
                    <div class="section">
                        <div class="label">Metodo Pagamento</div>
                        <div class="value">{metodo}</div>
                    </div>
                </div>
                
                <h3 style="margin-bottom:16px;">Dettaglio Righe</h3>
                <table>
                    <thead>
                        <tr>
                            <th style="width:50px;">#</th>
                            <th>Descrizione</th>
                            <th style="text-align:right;width:80px;">Qtà</th>
                            <th style="text-align:right;width:100px;">Prezzo</th>
                            <th style="text-align:right;width:60px;">IVA</th>
                            <th style="text-align:right;width:100px;">Totale</th>
                        </tr>
                    </thead>
                    <tbody>
                        {righe_html if righe_html else '<tr><td colspan="6" style="padding:16px;text-align:center;color:#9ca3af;">Nessun dettaglio righe disponibile</td></tr>'}
                    </tbody>
                </table>
                
                <div class="totals">
                    <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                        <span>Imponibile:</span>
                        <span>€{imponibile:.2f}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                        <span>IVA:</span>
                        <span>€{iva:.2f}</span>
                    </div>
                    <div style="display:flex;justify-content:space-between;font-size:20px;font-weight:bold;border-top:1px solid rgba(255,255,255,0.3);padding-top:8px;margin-top:8px;">
                        <span>TOTALE:</span>
                        <span>€{importo:.2f}</span>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html
