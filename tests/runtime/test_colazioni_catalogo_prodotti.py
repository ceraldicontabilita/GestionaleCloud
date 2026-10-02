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


def test_alias_fattura_esatti_uniscono_lo_stesso_articolo_e_usano_la_scheda_ufficiale():
    fatture = [
        {
            "fornitore": "Vandemoortele",
            "prodotti": [
                {"descrizione": "AQV BABY CRNT CALI STRA 35G 3.15KG", "quantita": 2},
                {"descrizione": "BABY CORNETTO CALISE DRITTO VUOTO", "quantita": 3},
                {"descrizione": "LIQUIDAZ EX DA PFA 3% OBJ 2025", "quantita": 1},
            ],
        }
    ]
    catalogo_acquaviva = [
        {
            "id": "baby-calise",
            "nome_verificato": "Baby Calise dritto",
            "alias_fattura": [
                "AQV BABY CRNT CALI STRA 35G 3.15KG",
                "BABY CORNETTO CALISE DRITTO VUOTO",
            ],
            "immagine_prodotto": "https://dolciariaacquaviva.com/baby.webp",
            "allergeni": ["Glutine", "Latte"],
            "link_prodotto": "https://dolciariaacquaviva.com/prodotto/baby-calise-dritto/",
        }
    ]

    [riga] = costruisci_catalogo_prodotti_hotel(fatture, [], catalogo_acquaviva)

    assert riga["nome"] == "Baby Calise dritto"
    assert riga["descrizione"] == (
        "Cornetto baby vuoto, soffice e friabile, con impasto brioche e sfoglia."
    )
    assert riga["quantita_acquistata"] == Decimal("5")
    assert len(riga["descrizioni_fattura"]) == 2
    assert riga["collegamento_catalogo"] is True
    assert riga["immagine"] == "https://dolciariaacquaviva.com/baby.webp"


def test_alias_non_collegato_ha_presentazione_breve_senza_inventare_allergeni():
    fatture = [
        {
            "fornitore": "Vandemoortele",
            "prodotti": [
                {"descrizione": "AQV CRNT GLUTEN FREE 80G 1.6KG", "quantita": 1}
            ],
        }
    ]

    [riga] = costruisci_catalogo_prodotti_hotel(fatture, [], [])

    assert riga["nome"] == "Croissant senza glutine"
    assert riga["descrizione"] == "Croissant vuoto senza glutine."
    assert riga["allergeni"] == []
    assert riga["collegamento_catalogo"] is False


def test_due_descrizioni_tecniche_della_stessa_ciambella_diventano_una_sola_voce():
    fatture = [
        {
            "fornitore": "Vandemoortele",
            "prodotti": [
                {"descrizione": "AQV CMBLL MAXI SUGARED 100G 3KG", "quantita": 2},
                {"descrizione": "CIAMBELLA MAXI ZUCCHERATA G. 100", "quantita": 3},
            ],
        }
    ]

    [riga] = costruisci_catalogo_prodotti_hotel(fatture, [], [])

    assert riga["nome"] == "Ciambella maxi zuccherata"
    assert riga["descrizione"] == "Ciambella soffice ricoperta di zucchero."
    assert riga["quantita_acquistata"] == Decimal("5")
    assert len(riga["descrizioni_fattura"]) == 2
    assert riga["allergeni"] == []
    assert riga["collegamento_catalogo"] is False


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
        / "20261001113238_convenzioni_catalogo_prodotti_strutture.sql"
    ).read_text(encoding="utf-8")
    sql_tavolo = (
        ROOT
        / "supabase"
        / "migrations"
        / "20261001113247_colazioni_servizio_tavolo_per_camera.sql"
    ).read_text(encoding="utf-8")

    assert '"prodotti","Prodotti hotel"' in html
    assert '"prodotti","Prodotti e ordini"' in html
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
    assert "function ntServ(i,v)" in html
    assert "function crServ(i,v)" in html
    assert "☕ Banco" in html
    assert "🪑 Tavolo +${eur(sup())}" in html
    assert "const crDefaultTavolo=()=>false" in html
    assert "Banco selezionato di default" in html
    assert 'id="in_tav"' not in html
    assert "Foto non disponibile" not in html
    assert "Allergeni non inseriti" not in html
    assert "Allergeni non documentati" not in html
    assert "Prezzo hotel (€)" in html


def test_schede_catalogo_sono_compatte_senza_marchi_o_provenienze_visibili():
    html = (ROOT / "frontend_colazioni" / "index.html").read_text(encoding="utf-8")

    assert "catalog-title" in html
    assert "catalog-desc" in html
    assert "catalog-allergens" in html
    assert "catalog-price-row" in html
    assert "cpOrigine" not in html
    assert "Acquaviva acquistati" not in html
    assert ">Produzione interna<" not in html
    assert "Prodotti acquistati" in html
    assert "Preparati dal bar" in html
    assert "immagine:p.immagine||foto||null" in html
    assert "catalogParole(p.descrizione)!==catalogParole(p.nome)" in html


def test_segnalazione_alimentare_albergatore_e_salvata_nel_voucher():
    sql = (
        ROOT
        / "supabase"
        / "migrations"
        / "20261002133000_colazioni_attenzione_alimentare_albergatore.sql"
    ).read_text(encoding="utf-8")

    assert "attenzione_alimentare" in sql
    assert "jsonb_build_object('nota',attenzione)" in sql
    assert "length(attenzione)>500" in sql


def test_pagina_ospite_qr_offre_recensione_google_e_tripadvisor_senza_incentivi():
    html = (ROOT / "frontend_colazioni" / "index.html").read_text(encoding="utf-8")

    assert "bb_recensioni_invito_pubblico" in html
    assert "i.google_url" in html
    assert "i.tripadvisor_url" in html
    assert "Com’è stata la tua esperienza?" in html
    assert "Nessun premio o incentivo è associato alla recensione." in html
    assert 'if(p[1]==="recensioni")return recensioniOspite' in html


def test_guida_napoli_ospite_usa_fonti_ufficiali_e_portami_maps():
    html = (ROOT / "frontend_colazioni" / "index.html").read_text(encoding="utf-8")

    assert "NAP_GUIDE" in html
    assert "🚇 Linee ANM" in html
    assert "🎫 Biglietti" in html
    assert "🏛️ Musei e luoghi" in html
    assert "ℹ️ Infopoint" in html
    assert "https://www.google.com/maps/dir/?api=1&destination=" in html
    assert "📍 Portami" in html
    assert "MappaReteSuFerroPDF" in html
    assert "cartadellamobilita25" in html
    assert "museoarcheologiconapoli.it/orari-e-biglietti" in html
    assert "museosansevero.it/organizza-la-tua-visita/orari-e-tariffe" in html
    assert "capodimonte.cultura.gov.it/biglietti" in html
    assert "static-www.comune.napoli.it" in html
    assert "Dati e collegamenti ufficiali verificati il 01/10/2026" in html


def test_albergatore_puo_ordinare_prodotti_e_il_titolare_riceve_avviso():
    html = (ROOT / "frontend_colazioni" / "index.html").read_text(encoding="utf-8")
    servizio = (ROOT / "app" / "lotti" / "servizi" / "ordini_hotel.py").read_text(encoding="utf-8")
    vista_lotti = (ROOT / "frontend_lotti" / "src" / "components" / "haccp" / "OrdiniHotelView.jsx").read_text(encoding="utf-8")

    assert "🥐 Ordine mattutino dolce e salato" in html
    assert "function apInvia()" in html
    assert "/api/colazioni/ordini-prodotti/albergatore" in html
    assert "Ordini prodotti" in html
    assert "da incassare" in html
    assert "tracciabilita_stato" in servizio
    assert "fatture_origine" in servizio
    assert "produzione_da_registrare" in servizio
    assert "lotto_fornitore_da_associare" in servizio
    assert "Apri ricetta / Produci" in vista_lotti
    assert "Associa lotto" in vista_lotti
