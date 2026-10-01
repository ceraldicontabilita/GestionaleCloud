from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "frontend_colazioni" / "index.html").read_text(encoding="utf-8")
SQL = (ROOT / "frontend_colazioni" / "sql" / "supabase-23.sql").read_text(
    encoding="utf-8"
)


def test_consensi_sono_separati_espliciti_e_non_preselezionati():
    assert r"recScelta(\'geolocalizzazione\',true)" in HTML
    assert r"recScelta(\'geolocalizzazione\',false)" in HTML
    assert r"recScelta(\'whatsapp\',true)" in HTML
    assert r"recScelta(\'whatsapp\',false)" in HTML
    assert "Nessuna opzione è preselezionata" in HTML
    assert 'type="checkbox"' not in HTML[HTML.index("function recPagina"):HTML.index("function recPosizione")]


def test_posizione_viene_richiesta_solo_dopo_consenso():
    scelta = HTML.index('if(finalita==="geolocalizzazione"&&si)recPosizione()')
    richiesta = HTML.index("navigator.geolocation.getCurrentPosition")
    assert scelta < richiesta


def test_link_struttura_distinguono_le_tre_fonti():
    assert '["qr","nfc","wifi"]' in HTML
    assert '"#/recensioni/"+REVT.token+"/"+fonte' in HTML
    assert '"qr","nfc","wifi","link","whatsapp"' in HTML


def test_albergatore_invia_al_cliente_con_whatsapp_o_nfc():
    assert "Invia al cliente con WhatsApp" in HTML
    assert "Copia link per NFC" in HTML
    assert 'run("bb_alb_recensioni_link"' in HTML
    assert 'rec("whatsapp")' in HTML
    assert 'rec("nfc")' in HTML


def test_revoca_elimina_i_dati_collegati():
    assert "update bb_recensioni_visite set telefono=null" in SQL
    assert "delete from bb_recensioni_posizioni where visita_id=v.id" in SQL


def test_vecchio_blocco_hardcoded_non_esiste_piu():
    assert "RECENSIONE_GOOGLE" not in HTML
    assert "RECENSIONE_TRIPADVISOR" not in HTML


def test_tabelle_sensibili_hanno_rls_e_solo_rpc():
    tabelle = (
        "bb_recensioni_link",
        "bb_recensioni_visite",
        "bb_recensioni_consensi",
        "bb_recensioni_posizioni",
        "bb_recensioni_inviti",
        "bb_recensioni_click",
    )
    for tabella in tabelle:
        assert f"alter table {tabella} enable row level security" in SQL
    assert "revoke all on bb_recensioni_link" in SQL


def test_coda_richiede_segreto_runtime_e_consenso_attivo():
    assert "perform public.gc_assert_runtime_secret();" in SQL
    assert "bb_recensioni_consenso_attivo(v.id,'whatsapp')" in SQL
    assert "for update of i skip locked" in SQL
