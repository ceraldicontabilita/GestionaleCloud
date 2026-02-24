"""
Fatture Module - Gestione Fatture Ricevute (Passive).
Modulo suddiviso per funzionalità:
- helpers: Funzioni di utilità condivise
- import_xml: Import fatture XML singole, multiple, ZIP
- crud: Archivio, visualizzazione, aggiornamento
- pagamento: Pagamento manuale, cambio metodo, riconciliazione
"""
from fastapi import APIRouter, UploadFile, File, Query
from typing import Dict, Any, List, Optional

router = APIRouter()

# Import functions from modules
from .import_xml import (
    import_fattura_xml, import_fatture_xml_multipli, import_fatture_zip
)
from .crud import (
    get_archivio_fatture, view_fattura_assoinvoice, download_pdf_allegato,
    get_fattura_dettaglio, update_fattura, get_fornitori, get_statistiche
)
from .pagamento import (
    paga_fattura_manuale, cambia_metodo_pagamento_fattura,
    riconcilia_fattura_con_estratto_conto, verifica_incoerenze_estratto_conto,
    aggiorna_metodi_pagamento_da_fornitori, riconcilia_fatture_paypal,
    auto_ricostruisci_dati, lista_fatture_paypal, import_paypal_file
)

# === ROTTE STATICHE (devono venire PRIMA delle dinamiche) ===

# Import
router.add_api_route("/import-xml", import_fattura_xml, methods=["POST"])
router.add_api_route("/import-xml-multipli", import_fatture_xml_multipli, methods=["POST"])
router.add_api_route("/import-zip", import_fatture_zip, methods=["POST"])

# Archivio e Lista
router.add_api_route("/archivio", get_archivio_fatture, methods=["GET"])
router.add_api_route("/fornitori", get_fornitori, methods=["GET"])
router.add_api_route("/statistiche", get_statistiche, methods=["GET"])

# Pagamento e Riconciliazione
router.add_api_route("/paga-manuale", paga_fattura_manuale, methods=["POST"])
router.add_api_route("/cambia-metodo-pagamento", cambia_metodo_pagamento_fattura, methods=["POST"])
router.add_api_route("/riconcilia-con-estratto-conto", riconcilia_fattura_con_estratto_conto, methods=["POST"])
router.add_api_route("/verifica-incoerenze-estratto-conto", verifica_incoerenze_estratto_conto, methods=["GET"])
router.add_api_route("/aggiorna-metodi-pagamento", aggiorna_metodi_pagamento_da_fornitori, methods=["POST"])
router.add_api_route("/riconcilia-paypal", riconcilia_fatture_paypal, methods=["POST"])
router.add_api_route("/auto-ricostruisci-dati", auto_ricostruisci_dati, methods=["POST"])
router.add_api_route("/lista-paypal", lista_fatture_paypal, methods=["GET"])
router.add_api_route("/import-paypal", import_paypal_file, methods=["POST"])

# === ROTTE DINAMICHE (devono venire DOPO le statiche) ===

# Dettaglio fattura
router.add_api_route("/fattura/{fattura_id}/view-assoinvoice", view_fattura_assoinvoice, methods=["GET"])
router.add_api_route("/fattura/{fattura_id}/pdf/{allegato_id}", download_pdf_allegato, methods=["GET"])
router.add_api_route("/fattura/{fattura_id}", get_fattura_dettaglio, methods=["GET"])
router.add_api_route("/fattura/{fattura_id}", update_fattura, methods=["PUT"])
