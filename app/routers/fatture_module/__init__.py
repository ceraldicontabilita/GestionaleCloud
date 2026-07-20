"""
Fatture Module - Gestione Fatture Ricevute (Passive).
Modulo suddiviso per funzionalità:
- helpers: Funzioni di utilità condivise
- crud: Archivio, visualizzazione, aggiornamento
- pagamento: Pagamento manuale, cambio metodo, riconciliazione

L'import fatture XML/P7M passa dalla pipeline unica in
app/routers/invoices/fatture_upload.py (Drive sync, upload manuale, email).
Il vecchio import_xml.py di questo modulo era una pipeline duplicata mai
collegata al frontend (nessun bottone la chiamava) che registrava anche
lotti HACCP nel gestionale: rimossa.
"""
from fastapi import APIRouter, UploadFile, File, Query
from typing import Dict, Any, List, Optional

router = APIRouter()

# Import functions from modules
from .crud import (
    get_archivio_fatture, view_fattura_assoinvoice, download_pdf_allegato,
    get_fattura_dettaglio, update_fattura, get_fornitori, get_statistiche,
    pulisci_duplicati_invoices, storia_fattura, download_xml_originale
)
from .pagamento import (
    paga_fattura_manuale, cambia_metodo_pagamento_fattura,
    riconcilia_fattura_con_estratto_conto, verifica_incoerenze_estratto_conto,
    aggiorna_metodi_pagamento_da_fornitori, backfill_autoroute_da_metodo_fornitore,
    riconcilia_fatture_paypal,
    auto_ricostruisci_dati, lista_fatture_paypal, import_paypal_file
)

# === ROTTE STATICHE (devono venire PRIMA delle dinamiche) ===

# Archivio e Lista
router.add_api_route("/archivio", get_archivio_fatture, methods=["GET"])
from .export_selezione import export_fatture_selezionate
router.add_api_route("/export-selezione", export_fatture_selezionate, methods=["POST"])
router.add_api_route("/fornitori", get_fornitori, methods=["GET"])
router.add_api_route("/statistiche", get_statistiche, methods=["GET"])
router.add_api_route("/pulisci-duplicati", pulisci_duplicati_invoices, methods=["POST"])
from .crud import elimina_fatture_guscio_vuoto, elimina_fatture_anni_vecchi
router.add_api_route("/elimina-gusci-vuoti", elimina_fatture_guscio_vuoto, methods=["POST"])
router.add_api_route("/elimina-anni-vecchi", elimina_fatture_anni_vecchi, methods=["POST"])

# Pagamento e Riconciliazione
router.add_api_route("/paga-manuale", paga_fattura_manuale, methods=["POST"])
router.add_api_route("/cambia-metodo-pagamento", cambia_metodo_pagamento_fattura, methods=["POST"])
router.add_api_route("/riconcilia-con-estratto-conto", riconcilia_fattura_con_estratto_conto, methods=["POST"])
router.add_api_route("/verifica-incoerenze-estratto-conto", verifica_incoerenze_estratto_conto, methods=["GET"])
router.add_api_route("/aggiorna-metodi-pagamento", aggiorna_metodi_pagamento_da_fornitori, methods=["POST"])
router.add_api_route("/backfill-autoroute", backfill_autoroute_da_metodo_fornitore, methods=["POST"])
router.add_api_route("/riconcilia-paypal", riconcilia_fatture_paypal, methods=["POST"])
router.add_api_route("/auto-ricostruisci-dati", auto_ricostruisci_dati, methods=["POST"])
router.add_api_route("/lista-paypal", lista_fatture_paypal, methods=["GET"])
router.add_api_route("/import-paypal", import_paypal_file, methods=["POST"])

# === ROTTE DINAMICHE (devono venire DOPO le statiche) ===

# Dettaglio fattura
router.add_api_route("/fattura/{fattura_id}/storia", storia_fattura, methods=["GET"])
router.add_api_route("/fattura/{fattura_id}/view-assoinvoice", view_fattura_assoinvoice, methods=["GET"])
router.add_api_route("/fattura/{fattura_id}/xml-originale", download_xml_originale, methods=["GET"])
router.add_api_route("/fattura/{fattura_id}/pdf/{allegato_id}", download_pdf_allegato, methods=["GET"])
router.add_api_route("/fattura/{fattura_id}", get_fattura_dettaglio, methods=["GET"])
router.add_api_route("/fattura/{fattura_id}", update_fattura, methods=["PUT"])
