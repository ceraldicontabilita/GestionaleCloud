"""Il rebuild di prodotti_master e la persistenza dello store cedono il loop.

Il 02/10/2026 il catch-up di `job_pipeline_aggiornamento` teneva il loop fermo
~10 s a ogni giro: l'health check di Render scadeva e il servizio si riavviava.
"""
import inspect

from app.lotti import supabase_document_store as store
from app.lotti.routers import prodotti_master


def test_rebuild_cede_il_loop_nei_cicli_lunghi():
    sorgente = inspect.getsource(prodotti_master._esegui_rebuild)
    assert sorgente.count("await asyncio.sleep(0)") >= 3


def test_store_cede_il_loop_nel_confronto_e_nell_upsert():
    assert "await asyncio.sleep(0)" in inspect.getsource(store.PersistentCollection._persisti_differenza)
    assert "await asyncio.sleep(0)" in inspect.getsource(store.SupabaseRpcStore.upsert_docs)
    assert "await asyncio.sleep(0)" in inspect.getsource(store.PersistentCollection.bulk_write)
