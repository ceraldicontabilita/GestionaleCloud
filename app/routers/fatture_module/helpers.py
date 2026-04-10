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

    # ── EVENTO: pubblica sul Bus per Learning Machine e check IBAN ──
    try:
        from app.core.event_bus import bus
        await bus.publish("fornitore.creato", payload={
            "fornitore_id":    nuovo_fornitore["id"],
            "ragione_sociale": nuovo_fornitore["ragione_sociale"],
            "partita_iva":     partita_iva,
            "iban":            nuovo_fornitore.get("iban", ""),
            "metodo_pagamento": nuovo_fornitore.get("metodo_pagamento", ""),
        }, db=db, save_to_db=False)
    except Exception as _ev:
        logger.debug(f"[Helpers] Event Bus fornitore.creato: {_ev}")

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
    """Genera HTML preview della fattura stile AssoInvoice - layout intuitivo e leggibile."""
    fornitore = (fattura.get("fornitore_ragione_sociale") or 
                 fattura.get("supplier_name") or 
                 fattura.get("cedente_denominazione") or 
                 fattura.get("fornitore", {}).get("denominazione") or "N/A")
    piva = (fattura.get("fornitore_partita_iva") or 
            fattura.get("supplier_vat") or 
            fattura.get("cedente_piva") or 
            fattura.get("fornitore", {}).get("partita_iva") or "N/A")
    cf = (fattura.get("fornitore_codice_fiscale") or 
          fattura.get("cedente_cf") or 
          fattura.get("fornitore", {}).get("codice_fiscale") or "")
    indirizzo_fornitore = (fattura.get("fornitore_indirizzo") or 
                           fattura.get("cedente_indirizzo") or 
                           fattura.get("fornitore", {}).get("indirizzo") or "")
    numero = fattura.get("numero_documento") or fattura.get("invoice_number") or fattura.get("numero") or "N/A"
    data = fattura.get("data_documento") or fattura.get("invoice_date") or fattura.get("data") or "N/A"
    
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
    # Calcola imponibile/IVA se mancanti
    if imponibile == 0 and iva == 0 and importo > 0:
        # Try to compute from righe
        if righe_fattura:
            imponibile = sum(safe_float(r.get('prezzo_totale', 0)) for r in righe_fattura)
            iva = importo - imponibile if imponibile > 0 else 0
        if imponibile == 0:
            imponibile = round(importo / 1.22, 2)
            iva = round(importo - imponibile, 2)
    
    is_paid = fattura.get("pagato", False) or fattura.get("stato_pagamento") == "pagata"
    stato = fattura.get("stato_pagamento") or fattura.get("stato") or ("pagata" if is_paid else "non_pagata")
    metodo = fattura.get("metodo_pagamento") or "Non specificato"
    data_pagamento = fattura.get("data_pagamento") or ""
    fattura_id = fattura.get("id", "")
    
    if not righe_fattura and fattura.get("linee"):
        righe_fattura = fattura.get("linee", [])
    
    stato_badge_html = {
        "pagata": '<span class="badge badge-green">PAGATA</span>',
        "pagato": '<span class="badge badge-green">PAGATA</span>',
        "non_pagata": '<span class="badge badge-red">DA PAGARE</span>',
        "importata": '<span class="badge badge-red">DA PAGARE</span>',
        "parziale": '<span class="badge badge-yellow">PARZIALE</span>'
    }.get(stato, f'<span class="badge badge-gray">{str(stato).upper()}</span>')
    
    righe_html = ""
    if righe_fattura:
        for idx, r in enumerate(righe_fattura):
            prezzo_unit = safe_float(r.get('prezzo_unitario', 0))
            prezzo_tot = safe_float(r.get('prezzo_totale', 0))
            qta = safe_float(r.get('quantita', 1))
            aliq = safe_float(r.get('aliquota_iva', 22))
            bg = '#f8fafc' if idx % 2 == 0 else 'white'
            righe_html += f"""
            <tr style="background:{bg}">
                <td class="td-center">{r.get('numero_linea', idx+1)}</td>
                <td class="td-desc">{r.get('descrizione', '')[:100]}</td>
                <td class="td-right">{qta:g}</td>
                <td class="td-right">{prezzo_unit:,.2f}</td>
                <td class="td-center">{aliq:g}%</td>
                <td class="td-right"><strong>{prezzo_tot:,.2f}</strong></td>
            </tr>"""
    
    # Mark as Paid buttons (only if not already paid)
    pay_buttons = ""
    if not is_paid and fattura_id:
        pay_buttons = f"""
        <div class="pay-section">
            <h3 style="margin:0 0 12px;font-size:15px;color:#1e293b;">Segna come Pagata</h3>
            <div style="display:flex;gap:12px;flex-wrap:wrap;">
                <button onclick="pagaFattura('{fattura_id}', 'cassa', {importo}, '{data}', '{fornitore.replace(chr(39), "")}', '{numero}')" class="btn btn-green">
                    Paga in CASSA
                </button>
                <button onclick="pagaFattura('{fattura_id}', 'banca', {importo}, '{data}', '{fornitore.replace(chr(39), "")}', '{numero}')" class="btn btn-blue">
                    Paga in BANCA
                </button>
            </div>
        </div>
        """
    
    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fattura {numero} - {fornitore}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: #f1f5f9; padding: 20px; color: #1e293b; }}
        .invoice {{ max-width: 860px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: white; padding: 28px 32px; }}
        .header-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; }}
        .header h1 {{ font-size: 26px; font-weight: 700; margin-bottom: 4px; }}
        .header .subtitle {{ opacity: 0.85; font-size: 14px; }}
        .badge {{ display: inline-block; padding: 6px 16px; border-radius: 6px; font-size: 13px; font-weight: 700; letter-spacing: 0.5px; }}
        .badge-green {{ background: #22c55e; color: white; }}
        .badge-red {{ background: #ef4444; color: white; }}
        .badge-yellow {{ background: #f59e0b; color: white; }}
        .badge-gray {{ background: #94a3b8; color: white; }}
        .body {{ padding: 28px 32px; }}
        .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 28px; }}
        .info-box {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 18px; }}
        .info-box .label {{ font-size: 11px; color: #94a3b8; text-transform: uppercase; font-weight: 600; letter-spacing: 0.8px; margin-bottom: 6px; }}
        .info-box .value {{ font-size: 16px; font-weight: 600; color: #0f172a; }}
        .info-box .detail {{ font-size: 13px; color: #64748b; margin-top: 4px; }}
        .amounts {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 28px; }}
        .amount-card {{ text-align: center; padding: 18px 12px; border-radius: 10px; }}
        .amount-card .amount-label {{ font-size: 11px; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; margin-bottom: 6px; }}
        .amount-card .amount-value {{ font-size: 22px; font-weight: 700; }}
        .amount-imponibile {{ background: #f0f9ff; border: 1px solid #bae6fd; }}
        .amount-imponibile .amount-label {{ color: #0369a1; }}
        .amount-imponibile .amount-value {{ color: #0c4a6e; }}
        .amount-iva {{ background: #fef3c7; border: 1px solid #fde68a; }}
        .amount-iva .amount-label {{ color: #92400e; }}
        .amount-iva .amount-value {{ color: #78350f; }}
        .amount-totale {{ background: #1e3a5f; }}
        .amount-totale .amount-label {{ color: rgba(255,255,255,0.7); }}
        .amount-totale .amount-value {{ color: white; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
        th {{ background: #1e3a5f; color: white; padding: 12px 14px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; }}
        th:first-child {{ border-radius: 8px 0 0 8px; }}
        th:last-child {{ border-radius: 0 8px 8px 0; }}
        td {{ padding: 10px 14px; font-size: 13px; border-bottom: 1px solid #f1f5f9; }}
        .td-center {{ text-align: center; }}
        .td-right {{ text-align: right; font-family: 'SF Mono', 'Menlo', monospace; }}
        .td-desc {{ max-width: 300px; }}
        .section-title {{ font-size: 15px; font-weight: 600; color: #1e293b; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 2px solid #e2e8f0; }}
        .pay-section {{ background: #fef3c7; border: 2px solid #fbbf24; border-radius: 10px; padding: 18px; margin-top: 24px; }}
        .btn {{ padding: 10px 24px; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s; }}
        .btn-green {{ background: #16a34a; color: white; }}
        .btn-green:hover {{ background: #15803d; }}
        .btn-blue {{ background: #2563eb; color: white; }}
        .btn-blue:hover {{ background: #1d4ed8; }}
        .empty-rows {{ padding: 32px; text-align: center; color: #94a3b8; font-style: italic; }}
        @media (max-width: 600px) {{
            .info-grid, .amounts {{ grid-template-columns: 1fr; }}
            .body {{ padding: 20px 16px; }}
            .header {{ padding: 20px 16px; }}
        }}
    </style>
</head>
<body>
    <div class="invoice">
        <div class="header">
            <div class="header-top">
                <div>
                    <h1>Fattura {numero}</h1>
                    <div class="subtitle">Data documento: {data}</div>
                </div>
                <div>{stato_badge_html}</div>
            </div>
        </div>
        <div class="body">
            <div class="info-grid">
                <div class="info-box">
                    <div class="label">Fornitore / Cedente</div>
                    <div class="value">{fornitore}</div>
                    <div class="detail">P.IVA: {piva}</div>
                    {'<div class="detail">C.F.: ' + cf + '</div>' if cf and cf != piva else ''}
                    {'<div class="detail">' + indirizzo_fornitore + '</div>' if indirizzo_fornitore else ''}
                </div>
                <div class="info-box">
                    <div class="label">Dettagli Pagamento</div>
                    <div class="value">{metodo.replace('_', ' ').title()}</div>
                    {'<div class="detail">Pagata il: ' + data_pagamento + '</div>' if data_pagamento else ''}
                </div>
            </div>
            
            <div class="amounts">
                <div class="amount-card amount-imponibile">
                    <div class="amount-label">Imponibile</div>
                    <div class="amount-value">&euro; {imponibile:,.2f}</div>
                </div>
                <div class="amount-card amount-iva">
                    <div class="amount-label">IVA</div>
                    <div class="amount-value">&euro; {iva:,.2f}</div>
                </div>
                <div class="amount-card amount-totale">
                    <div class="amount-label">Totale Fattura</div>
                    <div class="amount-value">&euro; {importo:,.2f}</div>
                </div>
            </div>
            
            <div class="section-title">Dettaglio Righe</div>
            <table>
                <thead>
                    <tr>
                        <th style="width:50px;text-align:center">#</th>
                        <th>Descrizione</th>
                        <th style="text-align:right;width:70px">Qta</th>
                        <th style="text-align:right;width:100px">Prezzo Unit.</th>
                        <th style="text-align:center;width:60px">IVA %</th>
                        <th style="text-align:right;width:110px">Totale</th>
                    </tr>
                </thead>
                <tbody>
                    {righe_html if righe_html else '<tr><td colspan="6" class="empty-rows">Nessun dettaglio righe disponibile</td></tr>'}
                </tbody>
            </table>
            
            {pay_buttons}
        </div>
    </div>
    <script>
    async function pagaFattura(fatturaId, metodo, importo, data, fornitore, numero) {{
        if (!confirm('Confermi il pagamento in ' + metodo.toUpperCase() + ' di EUR ' + importo.toFixed(2) + '?')) return;
        try {{
            const res = await fetch('/api/fatture-ricevute/paga-manuale', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    fattura_id: fatturaId,
                    importo: importo,
                    metodo: metodo,
                    data_pagamento: data,
                    fornitore: fornitore,
                    numero_fattura: numero
                }})
            }});
            const result = await res.json();
            if (result.success) {{
                alert('Pagamento registrato in ' + metodo.toUpperCase() + '!\\nMovimento creato in Prima Nota.');
                location.reload();
            }} else {{
                alert('Errore: ' + (result.detail || 'Errore sconosciuto'));
            }}
        }} catch (e) {{
            alert('Errore: ' + e.message);
        }}
    }}
    </script>
</body>
</html>"""
    return html
