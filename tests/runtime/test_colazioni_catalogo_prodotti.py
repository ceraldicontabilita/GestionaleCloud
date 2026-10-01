from decimal import Decimal
from pathlib import Path

from app.routers.colazioni import costruisci_catalogo_prodotti_hotel


ROOT = Path(__file__).resolve().parents[2]


def test_catalogo_include_solo_acquisti_vandemoortele_e_tutte_le_ricette_interne():
    fatture = [
        {
            "fornitore": "VANDEMOORTELE EUROPE NV",
            "prodotti": [
                {"descrizione": "CORNETTO CREMA 90G", "quantita": 2, "prezzo": 30},
                {"descrizione": "CORNETTO CREMA 90G", "quantita": 3, "prezzo": 30},
            ],
        },
        {
            "fornitore": "ALTRO FORNITORE",
            "prodotti": [{"descrizione": "NON DEVE ENTRARE", "quantita": 1, "prezzo": 1}],
        },
    ]
    prodotti = [
        {
            "id": "interno-1",
            "nome": "Sfogliatella riccia",
            "ricetta_id": "ricetta-1",
            "attivo": True,
            "allergeni": ["Glutine", "Uova"],
        },
        {"id": "rivendita-1", "nome": "Bibita", "attivo": True},
    ]

    catalogo = costruisci_catalogo_prodotti_hotel(fatture, prodotti)

    assert [(p["origine"], p["nome"]) for p in catalogo] == [
        ("vandemoortele", "CORNETTO CREMA 90G"),
        ("produzione_interna", "Sfogliatella riccia"),
    ]
    assert catalogo[0]["quantita_acquistata"] == Decimal("5")
    assert catalogo[0]["prova"] == "fattura"
    assert catalogo[1]["prova"] == "ricetta"


def test_fattura_si_arricchisce_solo_con_codice_univoco_documentato():
    fatture = [
        {
            "fornitore_ragione_sociale": "Vandemoortele Europe NV",
            "prodotti": [{"descrizione": "AQV 57216 CROISSANT 95G", "quantita": 1}],
        }
    ]
    prodotti = [
        {
            "id": "catalogo-1",
            "nome": "Croissant cannella",
            "codice_aqv_2026": "57216",
            "descrizione": "Con crema alla cannella",
            "allergeni": ["Glutine", "Latte"],
            "immagine_url": "/lotti/foto/57216.webp",
            "prezzo_vendita": "2.50",
            "attivo": True,
        }
    ]

    [riga] = costruisci_catalogo_prodotti_hotel(fatture, prodotti)

    assert riga["nome"] == "Croissant cannella"
    assert riga["collegamento_catalogo"] is True
    assert riga["allergeni"] == ["Glutine", "Latte"]
    assert riga["prezzo"] == Decimal("2.50")


def test_nessun_match_per_somiglianza_e_nessun_prezzo_inventato():
    fatture = [
        {
            "fornitore": "Vandemoortele",
            "prodotti": [{"descrizione": "CORNETTO CALISE DRITTO VUOTO", "quantita": 1}],
        }
    ]
    prodotti = [
        {
            "id": "sbagliato",
            "nome": "Cornetto senza glutine vuoto",
            "descrizione": "Altro prodotto",
            "allergeni": ["Latte"],
            "attivo": True,
        }
    ]

    [riga] = costruisci_catalogo_prodotti_hotel(fatture, prodotti)

    assert riga["nome"] == "CORNETTO CALISE DRITTO VUOTO"
    assert riga["collegamento_catalogo"] is False
    assert riga["allergeni"] == []
    assert riga["prezzo"] is None


def test_tutti_i_lievitati_richiesti_entrano_se_collegati_a_ricetta():
    nomi = [
        "Croissant vuoto",
        "Brioche crema",
        "Sfogliatella riccia",
        "Treccia miele",
        "Cornetto senza glutine",
    ]
    prodotti = [
        {"id": f"prodotto-{indice}", "nome": nome, "ricetta_id": f"ricetta-{indice}"}
        for indice, nome in enumerate(nomi)
    ]

    catalogo = costruisci_catalogo_prodotti_hotel([], prodotti)

    assert {p["nome"] for p in catalogo} == set(nomi)
    assert {p["origine"] for p in catalogo} == {"produzione_interna"}


def test_frontend_e_migrazione_espongono_selezione_per_struttura():
    html = (ROOT / "frontend_colazioni" / "index.html").read_text(encoding="utf-8")
    sql = (
        ROOT
        / "supabase"
        / "migrations"
        / "20261001130000_convenzioni_catalogo_prodotti_strutture.sql"
    ).read_text(encoding="utf-8")
    sql_tavolo = (
        ROOT
        / "supabase"
        / "migrations"
        / "20261001131500_colazioni_servizio_tavolo_per_camera.sql"
    ).read_text(encoding="utf-8")

    assert '"prodotti","Prodotti hotel"' in html
    assert '"prodotti","Prodotti"' in html
    assert "bb_tit_prodotti_salva" in html
    assert "bb_alb_prodotti" in html
    assert "primary key (struttura_id, prodotto_chiave)" in sql
    assert "check (prezzo > 0)" in sql
    assert "enable row level security" in sql
    assert "revoke all on public.bb_struttura_prodotti from public, anon, authenticated" in sql
    assert "security definer set search_path=''" in sql
    assert "add column if not exists servizio_tavolo" in sql_tavolo
    assert "coalesce((r->>'servizio_tavolo')::boolean,false)" in sql_tavolo
    assert "c.prezzo+supp" in sql_tavolo
    assert "'tavolo',v.servizio_tavolo" in sql_tavolo
    assert "servizio_tavolo:!!r.tavolo" in html
    assert "c.prezzo+(r.tavolo?sup():0)" in html


def test_pagina_ospite_qr_offre_recensione_google_e_tripadvisor_senza_incentivi():
    html = (ROOT / "frontend_colazioni" / "index.html").read_text(encoding="utf-8")

    assert "bb_recensioni_invito_pubblico" in html
    assert "i.google_url" in html
    assert "i.tripadvisor_url" in html
    assert "Com’è stata la tua esperienza?" in html
    assert "Nessun premio o incentivo è associato alla recensione." in html
    assert 'if(p[1]==="recensioni")return recensioniOspite' in html
