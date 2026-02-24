"""
Suppliers module - Gestione Fornitori.
Modulo suddiviso per funzionalità:
- base: CRUD e operazioni principali
- iban: Ricerca e gestione IBAN
- import_export: Import Excel
- validation: Validazione e dizionario metodi pagamento
- bulk: Operazioni massive
"""
from fastapi import APIRouter

# Router principale
router = APIRouter()

# Import tutti gli endpoint direttamente
from .validation import (
    get_payment_methods, get_payment_terms, get_fornitori_con_problemi_p0,
    get_dizionario_metodi_pagamento, aggiorna_dizionario_metodo
)
from .iban import (
    ricerca_iban_fornitori_web, ricerca_iban_singolo_web, sync_iban_from_invoices
)
from .import_export import (
    upload_suppliers_excel, import_suppliers_excel
)
from .bulk import (
    aggiorna_fornitori_bulk, aggiorna_metodi_pagamento_bulk,
    correggi_nomi_fornitori_mancanti, sincronizza_fornitori_da_fatture
)
from .base import (
    search_by_piva, list_suppliers, get_suppliers_stats, get_payment_deadlines,
    unifica_fornitori_collection, verifica_unificazione_stato,
    get_supplier, update_supplier, toggle_supplier_active, delete_supplier,
    get_supplier_fatturato, get_supplier_iban_from_invoices,
    update_supplier_payment_method, update_supplier_nome, get_fatture_fornitore
)

# === ROTTE STATICHE (devono venire PRIMA delle dinamiche) ===

# Validation
router.add_api_route("/payment-methods", get_payment_methods, methods=["GET"])
router.add_api_route("/payment-terms", get_payment_terms, methods=["GET"])
router.add_api_route("/validazione-p0", get_fornitori_con_problemi_p0, methods=["GET"])
router.add_api_route("/dizionario-metodi-pagamento", get_dizionario_metodi_pagamento, methods=["GET"])
router.add_api_route("/aggiorna-dizionario-metodo", aggiorna_dizionario_metodo, methods=["POST"])

# IBAN
router.add_api_route("/ricerca-iban-web", ricerca_iban_fornitori_web, methods=["POST"])
router.add_api_route("/sync-iban", sync_iban_from_invoices, methods=["POST"])

# Import/Export
router.add_api_route("/upload-excel", upload_suppliers_excel, methods=["POST"])
router.add_api_route("/import-excel", import_suppliers_excel, methods=["POST"])

# Bulk
router.add_api_route("/aggiorna-tutti-bulk", aggiorna_fornitori_bulk, methods=["POST"])
router.add_api_route("/aggiorna-metodi-bulk", aggiorna_metodi_pagamento_bulk, methods=["POST"])
router.add_api_route("/correggi-nomi-mancanti", correggi_nomi_fornitori_mancanti, methods=["POST"])
router.add_api_route("/sincronizza-da-fatture", sincronizza_fornitori_da_fatture, methods=["POST"])

# Base - Static routes
router.add_api_route("/search-piva/{partita_iva}", search_by_piva, methods=["GET"])
router.add_api_route("", list_suppliers, methods=["GET"])
router.add_api_route("/stats", get_suppliers_stats, methods=["GET"])
router.add_api_route("/scadenze", get_payment_deadlines, methods=["GET"])
router.add_api_route("/unifica-collection", unifica_fornitori_collection, methods=["POST"])
router.add_api_route("/verifica-unificazione", verifica_unificazione_stato, methods=["GET"])

# === ROTTE DINAMICHE (devono venire DOPO le statiche) ===
router.add_api_route("/ricerca-iban-singolo/{supplier_id}", ricerca_iban_singolo_web, methods=["POST"])
router.add_api_route("/{supplier_id}", get_supplier, methods=["GET"])
router.add_api_route("/{supplier_id}", update_supplier, methods=["PUT"])
router.add_api_route("/{supplier_id}/toggle-active", toggle_supplier_active, methods=["POST"])
router.add_api_route("/{supplier_id}", delete_supplier, methods=["DELETE"])
router.add_api_route("/{supplier_id}/fatturato", get_supplier_fatturato, methods=["GET"])
router.add_api_route("/{supplier_id}/iban-from-invoices", get_supplier_iban_from_invoices, methods=["GET"])
router.add_api_route("/{supplier_id}/metodo-pagamento", update_supplier_payment_method, methods=["PUT"])
router.add_api_route("/{supplier_id}/nome", update_supplier_nome, methods=["PUT"])
router.add_api_route("/{supplier_id}/fatture", get_fatture_fornitore, methods=["GET"])

