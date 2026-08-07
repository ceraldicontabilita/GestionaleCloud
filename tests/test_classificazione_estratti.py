"""Riconoscimento della fonte nell'inbox unico degli estratti conto.

I nomi usati qui sono quelli reali della cartella Drive "Estratti conto/Da
elaborare": l'utente ha messo tutto insieme, e la cartella non dice piu' da
dove arriva un documento.

L'errore che questi test impediscono e' preciso: l'estratto della carta di
credito Nexi — quello con le spese Amazon del titolare — importato come
movimento del conto corrente. Creerebbe uscite bancarie mai avvenute.
"""
import pytest

from app.services import classificazione_estratti as cls
from app.services.drive_estratti_conto_ingest import _route_for_path, _supported_file


# --- Nomi inequivocabili ---------------------------------------------------

@pytest.mark.parametrize(("nome", "atteso"), [
    ("Export_Mensile_Luglio_2026.csv", cls.POS),
    ("Export_Transazioni_gennaio 2026.xlsx", cls.POS),
    ("Export_Transazioni_aprile_2026.xlsx", cls.POS),
    ("Commissioni_Marzo_2026.xlsx", cls.POS),
    ("84B9EHMDDE6B4-MSR-20250301000000-20250331235959.PDF", cls.PAYPAL),
    ("84B9EHMDDE6B4-CSR-20250901000000-20250930235959-20251014082217.PDF", cls.PAYPAL),
    ("Estratto mutuo_31-12-2025.pdf", cls.MUTUO),
    ("nexi dicembre 2025.pdf", cls.NEXI),
    ("Estratto_Conto gennaio nexi.pdf", cls.NEXI),
    ("Movimenti carta_12-06-2025_08-45.pdf", cls.NEXI),
    ("ElencoEntrateUsciteAndamento_18-07-2026_10.35.03 anno 2026.csv", cls.BANCA),
    ("Movimenti_BNL_BPM_unificati.xlsx", cls.BANCA),
    ("2019-Q4 Estratto BNL 4-2019 (ott-dic) - cc 3192.pdf", cls.BANCA),
    ("Estratto conto corrente_31-03-2026.pdf", cls.BANCA),
])
def test_il_nome_basta_quando_e_inequivocabile(nome, atteso):
    assert cls.route_da_nome(nome) == atteso


@pytest.mark.parametrize("nome", [
    "Estratto_Conto (7).pdf",
    "Estratto conto agosto.pdf",
    "Estratto_conto_2024-11-30.pdf",
    "Documento.pdf",
])
def test_estratto_conto_da_solo_non_dice_niente(nome):
    """Lo scrivono tutti: banca, carta di credito e PayPal. Serve il contenuto."""
    assert cls.route_da_nome(nome) is None


def test_bnl_e_bpm_valgono_solo_come_parola_intera():
    """Evita che una sigla dentro un'altra parola faccia scattare la banca."""
    assert cls.route_da_nome("riepilogo bpmedia 2026.pdf") is None


# --- Contenuto -------------------------------------------------------------

_NEXI = ("Nexi Payments SpA - Corso Sempione 55, Milano. Gentile Cliente, di "
         "seguito il suo estratto conto Nexi. DETTAGLIO DEI SUOI MOVIMENTI "
         "03/12/25 Amznbusiness Milano 721,65")

_PAYPAL = ("Estratto conto bancario per marzo 2025 - ceraldi group srl. "
           "Codice conto commerciante: 84B9EHMDDE6B4 ID PayPal: "
           "acquisticeraldi@gmail.com")

_BPM = ("Ragione Sociale;Data contabile;Data valuta;Banca;Rapporto;Importo\r\n"
        "CERALDI GROUP S.R.L.;17/07/2026;17/07/2026;05034 - BANCO BPM S.P.A.")


def test_la_carta_nexi_si_riconosce_dall_intestazione():
    assert cls.route_da_testo(_NEXI) == cls.NEXI


def test_il_report_paypal_non_viene_preso_per_un_estratto_bancario():
    """Si intitola "Estratto conto bancario": e' proprio la trappola."""
    assert cls.route_da_testo(_PAYPAL) == cls.PAYPAL


def test_l_export_della_banca_si_riconosce_dalle_colonne():
    assert cls.route_da_testo(_BPM) == cls.BANCA


def test_un_documento_muto_resta_ignoto():
    assert cls.route_da_testo("Ricevuta di pagamento numero 12") is None


def test_il_csv_si_classifica_leggendo_la_prima_riga():
    fonte, motivo = cls.classifica("ESTRATTO 2026.csv", _BPM.encode("utf-8"))
    assert fonte == cls.BANCA
    assert "intestazione" in motivo


def test_un_csv_illeggibile_non_fa_saltare_la_classificazione():
    fonte, _ = cls.classifica("qualcosa.csv", b"\xff\xfe\x00\x01 dati binari")
    assert fonte is None


# --- Esito complessivo -----------------------------------------------------

def test_una_estensione_estranea_non_viene_presa_in_carico():
    fonte, motivo = cls.classifica("Nuova cartella compressa.zip")
    assert fonte is None
    assert "estensione" in motivo


def test_senza_contenuto_un_nome_ambiguo_resta_ignoto():
    fonte, motivo = cls.classifica("Estratto_Conto (7).pdf")
    assert fonte is None
    assert motivo


def test_il_nome_ha_la_precedenza_sul_contenuto():
    """Un export POS resta POS anche se dentro cita la banca."""
    fonte, motivo = cls.classifica("Export_Mensile_Luglio_2026.csv",
                                   _BPM.encode("utf-8"))
    assert fonte == cls.POS
    assert "nome" in motivo


# --- Integrazione con l'instradamento Drive --------------------------------

def test_nell_inbox_unico_i_file_pos_vengono_presi_in_carico():
    """Era il bug: senza una cartella "POS BPM" il file non veniva letto, e i
    mesi restavano senza POS reale."""
    for nome in ("Export_Mensile_Luglio_2026.csv",
                 "Export_Transazioni_gennaio 2026.xlsx",
                 "Commissioni_Marzo_2026.xlsx"):
        route = _route_for_path("", nome)
        assert route == "pos"
        assert _supported_file(route, nome) is True


def test_la_carta_di_credito_non_finisce_piu_nei_movimenti_bancari():
    """Prima qualunque nome con "estratto" diventava un movimento di banca."""
    assert _route_for_path("", "Estratto_Conto (7).pdf") != "bank"


def test_un_file_di_fonte_ignota_resta_in_carico_per_la_verifica_finale():
    """Non viene scartato in silenzio: si scarica e si guarda dentro."""
    assert _supported_file(None, "Estratto_Conto (7).pdf") is True
    assert _supported_file(None, "Nuova cartella compressa.zip") is False


def test_la_cartella_della_fonte_continua_a_comandare():
    """Chi ha ancora la struttura per fonte non deve accorgersi di nulla."""
    assert _route_for_path("POS BPM/2026") == "pos"
    assert _route_for_path("Carta Nexi") == "nexi"
    assert _route_for_path("BPM/2026") == "bank"


# --- Arretrato tenuto fermo ------------------------------------------------

@pytest.mark.parametrize(("nome", "atteso"), [
    ("Export_Mensile_Luglio_2026.csv", 2026),
    ("EC-38949004-agosto 2024.pdf", 2024),
    ("Paypal Maggio 2024.PDF", 2024),
    # Piu' anni nel nome: vale il periodo del documento, non il riferimento.
    ("2019-Q4 Estratto BNL 4-2019 (ott-dic) - cc 3192.pdf", 2019),
    ("Estratto_Conto (7).pdf", None),
    ("Gennaio.pdf", None),
])
def test_l_anno_si_legge_dal_nome_quando_c_e(nome, atteso):
    assert cls.anno_del_nome(nome) == atteso


def test_un_numero_lungo_non_viene_scambiato_per_un_anno():
    assert cls.anno_del_nome("84B9EHMDDE6B4-MSR-20250301000000-20250331235959.PDF") is None


def test_l_arretrato_resta_fermo_e_l_anno_in_corso_passa(monkeypatch):
    from app.services import drive_estratti_conto_ingest as ingest

    monkeypatch.setattr(ingest.settings, "DRIVE_ESTRATTI_ANNO_MINIMO", 2026,
                        raising=False)
    assert ingest._troppo_vecchio("Export_Mensile_Luglio_2026.csv") is False
    assert ingest._troppo_vecchio("EC-38949004-agosto 2024.pdf") is True
    # Senza anno leggibile si sta fermi: importare a caso meta' dello storico
    # sarebbe peggio che aspettare.
    assert ingest._troppo_vecchio("Estratto_Conto (7).pdf") is True


def test_azzerare_l_anno_minimo_sblocca_tutto(monkeypatch):
    from app.services import drive_estratti_conto_ingest as ingest

    monkeypatch.setattr(ingest.settings, "DRIVE_ESTRATTI_ANNO_MINIMO", 0,
                        raising=False)
    assert ingest._troppo_vecchio("EC-38949004-agosto 2024.pdf") is False
    assert ingest._troppo_vecchio("Estratto_Conto (7).pdf") is False
