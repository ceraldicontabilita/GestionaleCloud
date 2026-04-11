"""
Prima Nota Module - Gestione Prima Nota Cassa, Banca e Salari.
Modulo suddiviso per funzionalità:
- cassa: CRUD e operazioni Prima Nota Cassa
- banca: CRUD e operazioni Prima Nota Banca
- salari: Gestione Prima Nota Salari
- stats: Statistiche e Export
- sync: Sincronizzazione corrispettivi, fatture, import batch
- manutenzione: Fix, cleanup, verifica
"""
from fastapi import APIRouter

router = APIRouter()

# Import functions from modules
from .stats import (
    get_anni_disponibili, get_prima_nota_stats, get_saldo_finale, export_prima_nota_excel
)
from .cassa import (
    list_prima_nota_cassa, create_prima_nota_cassa, update_prima_nota_cassa,
    delete_movimento_cassa, delete_all_prima_nota_cassa, delete_cassa_by_source,
    get_fattura_allegata_cassa, analisi_movimenti_bancari_errati_in_cassa,
    elimina_movimenti_bancari_da_cassa
)
from .banca import (
    list_prima_nota_banca, create_prima_nota_banca, update_prima_nota_banca,
    delete_movimento_banca, delete_all_prima_nota_banca, delete_banca_by_source,
    get_fattura_allegata_banca
)
from .salari import (
    get_prima_nota_salari, create_prima_nota_salari, delete_prima_nota_salari, get_salari_stats
)
from .sync import (
    registra_fattura_prima_nota, sync_corrispettivi_to_prima_nota,
    sync_corrispettivi_anno, sync_fatture_pagate, get_corrispettivi_sync_status,
    import_prima_nota_batch, create_movimento_generico, collega_fatture_movimenti,
    sync_estratto_conto_to_banca
)
from .manutenzione import (
    fix_tipo_movimento_fatture, recalculate_all_balances, cleanup_orphan_movements,
    regenerate_from_invoices, fix_versamenti_duplicati, fix_categories_and_duplicates,
    sposta_movimento, verifica_metodo_fattura, verifica_entrate_corrispettivi,
    fix_corrispettivi_importo, migrazione_pulisci_bancari_da_cassa
)

# === ROTTE STATICHE (devono venire PRIMA delle dinamiche) ===

# Stats e globali
router.add_api_route("/anni-disponibili", get_anni_disponibili, methods=["GET"])
router.add_api_route("/stats", get_prima_nota_stats, methods=["GET"])
router.add_api_route("/saldo-finale", get_saldo_finale, methods=["GET"])
router.add_api_route("/export/excel", export_prima_nota_excel, methods=["GET"])

# Cassa - Statiche
router.add_api_route("/cassa", list_prima_nota_cassa, methods=["GET"])
router.add_api_route("/cassa", create_prima_nota_cassa, methods=["POST"])
router.add_api_route("/cassa/delete-all", delete_all_prima_nota_cassa, methods=["DELETE"])
router.add_api_route("/cassa/analisi-movimenti-bancari-errati", analisi_movimenti_bancari_errati_in_cassa, methods=["GET"])
router.add_api_route("/cassa/elimina-movimenti-bancari-errati", elimina_movimenti_bancari_da_cassa, methods=["DELETE"])
router.add_api_route("/cassa/sync-corrispettivi", sync_corrispettivi_anno, methods=["POST"])
router.add_api_route("/cassa/sync-fatture-pagate", sync_fatture_pagate, methods=["POST"])
router.add_api_route("/cassa/verifica-entrate-corrispettivi", verifica_entrate_corrispettivi, methods=["GET"])
router.add_api_route("/cassa/fix-corrispettivi-importo", fix_corrispettivi_importo, methods=["POST"])
# rebuild-da-corrispettivi rimosso

# Banca - Statiche
router.add_api_route("/banca", list_prima_nota_banca, methods=["GET"])
router.add_api_route("/banca", create_prima_nota_banca, methods=["POST"])
router.add_api_route("/banca/delete-all", delete_all_prima_nota_banca, methods=["DELETE"])

# Salari
router.add_api_route("/salari", get_prima_nota_salari, methods=["GET"])
router.add_api_route("/salari", create_prima_nota_salari, methods=["POST"])
router.add_api_route("/salari/stats", get_salari_stats, methods=["GET"])

# Sync e Import
router.add_api_route("/sync-corrispettivi", sync_corrispettivi_to_prima_nota, methods=["POST"])
router.add_api_route("/corrispettivi-status", get_corrispettivi_sync_status, methods=["GET"])
router.add_api_route("/import-batch", import_prima_nota_batch, methods=["POST"])
router.add_api_route("/movimento", create_movimento_generico, methods=["POST"])
router.add_api_route("/collega-fatture", collega_fatture_movimenti, methods=["POST"])
router.add_api_route("/registra-fattura", registra_fattura_prima_nota, methods=["POST"])

# Manutenzione
router.add_api_route("/fix-tipo-movimento", fix_tipo_movimento_fatture, methods=["POST"])
router.add_api_route("/recalculate-balances", recalculate_all_balances, methods=["POST"])
router.add_api_route("/cleanup-orphan-movements", cleanup_orphan_movements, methods=["POST"])
router.add_api_route("/regenerate-from-invoices", regenerate_from_invoices, methods=["POST"])
router.add_api_route("/fix-versamenti-duplicati", fix_versamenti_duplicati, methods=["POST"])
router.add_api_route("/fix-categories-and-duplicates", fix_categories_and_duplicates, methods=["POST"])
router.add_api_route("/sposta-movimento", sposta_movimento, methods=["POST"])
router.add_api_route("/migrazione-pulisci-bancari-cassa", migrazione_pulisci_bancari_da_cassa, methods=["POST"])

# === ROTTE DINAMICHE (devono venire DOPO le statiche) ===

# Cassa - Dinamiche
router.add_api_route("/cassa/delete-by-source/{source}", delete_cassa_by_source, methods=["DELETE"])
router.add_api_route("/cassa/{movimento_id}", update_prima_nota_cassa, methods=["PUT"])
router.add_api_route("/cassa/{movimento_id}", delete_movimento_cassa, methods=["DELETE"])
router.add_api_route("/cassa/{movimento_id}/fattura", get_fattura_allegata_cassa, methods=["GET"])

# Banca - Dinamiche
# Banca - Sync estratto conto
router.add_api_route("/banca/sync-estratto-conto", sync_estratto_conto_to_banca, methods=["POST"])
router.add_api_route("/banca/delete-by-source/{source}", delete_banca_by_source, methods=["DELETE"])
router.add_api_route("/banca/{movimento_id}", update_prima_nota_banca, methods=["PUT"])
router.add_api_route("/banca/{movimento_id}", delete_movimento_banca, methods=["DELETE"])
router.add_api_route("/banca/{movimento_id}/fattura", get_fattura_allegata_banca, methods=["GET"])

# Salari - Dinamiche
router.add_api_route("/salari/{movimento_id}", delete_prima_nota_salari, methods=["DELETE"])


# Salari - Auto ricostruisci dati
async def _auto_ricostruisci_salari():
    """Ricalcola progressivi e corregge dati salari."""
    from app.database import Database
    db = Database.get_db()
    # Ricalcola progressivi
    salari = await db["prima_nota_salari"].find({}, {"_id": 0}).sort("data", 1).to_list(10000)
    righe_pulite = 0
    correzioni = 0
    for s in salari:
        update = {}
        netto = float(s.get("netto", 0) or 0)
        lordo = float(s.get("lordo", 0) or 0)
        if netto > 0 and lordo == 0:
            update["lordo"] = netto
            correzioni += 1
        if update:
            await db["prima_nota_salari"].update_one({"id": s["id"]}, {"$set": update})
            righe_pulite += 1
    return {"righe_pulite": righe_pulite, "correzioni": correzioni, "totale_salari": len(salari)}

router.add_api_route("/salari/auto-ricostruisci-dati", _auto_ricostruisci_salari, methods=["POST"])


# Template CSV per import
async def _template_csv_cassa():
    from fastapi.responses import Response
    csv = "data,descrizione,importo,tipo,fornitore,categoria\n2025-01-01,Esempio spesa,100.00,uscita,Fornitore SRL,merci\n"
    return Response(content=csv, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=template_cassa.csv"})

async def _template_csv_banca():
    from fastapi.responses import Response
    csv = "data,descrizione,importo,tipo,banca,categoria\n2025-01-01,Esempio bonifico,500.00,uscita,Banca Principale,fornitori\n"
    return Response(content=csv, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=template_banca.csv"})

router.add_api_route("/cassa/template-csv", _template_csv_cassa, methods=["GET"])
router.add_api_route("/banca/template-csv", _template_csv_banca, methods=["GET"])


# Verifica
router.add_api_route("/verifica-metodo-fattura/{fattura_id}", verifica_metodo_fattura, methods=["GET"])
