from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "frontend_colazioni" / "index.html").read_text(encoding="utf-8")
SQL = (ROOT / "frontend_colazioni" / "sql" / "supabase-29.sql").read_text(
    encoding="utf-8"
)


def test_visita_recensione_e_collegata_al_voucher_cliente():
    assert "add column if not exists voucher_id" in SQL
    assert "bb_recensioni_voucher_apri(vid text)" in SQL
    assert "v.struttura_id,v.id,'qr'" in SQL
    assert "'informativa_versione',r.informativa_versione" in SQL


def test_completamento_restituisce_destinazioni_senza_un_secondo_link_iniziale():
    assert "'review_token',v.review_token" in SQL
    assert "'google_url',bb_cfg('recensioni_google_url','')" in SQL
    assert "'tripadvisor_url',bb_cfg('recensioni_tripadvisor_url','')" in SQL


def test_rpc_pubblica_minima_e_tabelle_non_esposte():
    assert "revoke all on function bb_recensioni_voucher_apri(text) from public" in SQL
    assert "grant execute on function bb_recensioni_voucher_apri(text) to anon,authenticated" in SQL


def test_condivisione_cliente_contiene_un_solo_accesso():
    blocco = HTML[HTML.index("async function mostraQR"):HTML.index("/* --- editor camere")]
    assert "Condividi con il cliente" in blocco
    assert 'navigator.share({title:"La tua colazione",text:msg,url:l})' in blocco
    assert "bb_alb_recensioni_link" not in blocco
    assert "recqr" not in blocco
    assert "Scelte privacy e invito recensione:" not in blocco


def test_recensioni_sono_nella_pagina_del_voucher():
    assert 'id="g_rec"' in HTML
    assert 'rpc("bb_recensioni_voucher_apri",{vid:G.d.id})' in HTML
    assert "Apri recensioni e consensi" in HTML
    assert "r.google_url" in HTML
    assert "r.tripadvisor_url" in HTML

