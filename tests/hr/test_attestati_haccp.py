"""Attestati di formazione alimentarista: lettura dal contenuto e abbinamento al dipendente."""
from app.hr.services.attestati_haccp import abbina_dipendente, leggi_attestato

# Testo come lo restituisce l'OCR: parole incollate, trattini bassi dalle sottolineature.
TESTO_II = (
    "NomeAlessandroCognomeCapezzutoNatoil 02/04/1986aNapoliprov.(NA)\n"
    "CONNESSEALL'IGIENE DEGLIALIMENTI,della durata diore 8,conseguendolaidoneitaALLA MANSIONE\n"
    "Luogoe dataNapoli(NA),10/06/2026\n"
)
TESTO_COMPOSTO = "NomeJananie AyachanaCognome Sankapala_Nata il 08/06/1974nello Sri Lanka\nLuogo e data Napoli (NA),10/06/2026\ndurata di ore 8"

DIPENDENTI = [
    {"id": "1", "nome": "Alessandro", "cognome": "Capezzuto", "stato": "attivo"},
    {"id": "2", "nome": "Vincenzo", "cognome": "Ceraldi", "stato": "attivo"},
    {"id": "3", "nome": "Antonella", "cognome": "Ceraldi", "stato": "cessato"},
    {"id": "4", "nome": "Jananie Ayachana Dissanayaka", "cognome": "Sankapala Arachchilage", "stato": "cessato"},
    {"id": "5", "nome": "Antonietta", "cognome": "Ceraldi", "stato": "attivo"},
]


def test_legge_nome_data_e_ore_dal_contenuto():
    letto = leggi_attestato(TESTO_II)
    assert (letto["nome"], letto["cognome"]) == ("alessandro", "capezzuto")
    assert letto["data_attestato"] == "2026-06-10"
    assert letto["ore_corso"] == 8


def test_abbina_un_solo_dipendente():
    assert abbina_dipendente(leggi_attestato(TESTO_II), DIPENDENTI)["dipendente"]["id"] == "1"


def test_nome_composto_e_cognome_doppio_si_abbinano_anche_se_cessato():
    letto = leggi_attestato(TESTO_COMPOSTO)
    abb = abbina_dipendente(letto, DIPENDENTI)
    assert abb["dipendente"]["id"] == "4"


def test_stesso_cognome_non_basta():
    """Tre Ceraldi: il nome decide, e «Antonella» non si confonde con «Antonietta»."""
    letto = {"nome": "antonella", "cognome": "ceraldi"}
    assert abbina_dipendente(letto, DIPENDENTI)["dipendente"]["id"] == "3"
    letto = {"nome": "valerio", "cognome": "ceraldi"}
    abb = abbina_dipendente(letto, DIPENDENTI)
    assert abb["dipendente"] is None and abb["motivo"] == "nessun_dipendente"


def test_nome_illeggibile_resta_da_assegnare():
    abb = abbina_dipendente(leggi_attestato("pagina senza attestato"), DIPENDENTI)
    assert abb["dipendente"] is None and abb["motivo"] == "nome_non_letto"
