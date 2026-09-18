from app.services import drive_document_index as index
from app.services.personal_family_registry import family_search_terms, match_family_person


def test_anagrafica_riconosce_alias_cf_e_codice_contribuente():
    assert match_family_person("utenza intestata a LIUZZA MARINA")["person_id"] == "marina-liuzza"
    assert match_family_person("CF CRLVCN74L15F839W")["display_name"] == "Ceraldi Vincenzo"
    assert match_family_person("codice contribuente 1804135")["person_id"] == "ceraldi-antonietta"
    assert "crlvlr88h14f839o" in family_search_terms("Valerio Ceraldi")


def test_documento_lavoro_del_familiare_resta_aziendale():
    record = {
        "Dominio": "documenti dipendenti", "Categoria": "DIMISSIONI TELEMATICHE",
        "Nome file": "CRLVCN74L15F839W_Dimissione.pdf",
        "Percorso Drive": "documenti dipendenti/DIMISSIONI TELEMATICHE/2024/file.pdf",
        "SHA-256": "not-personal-override",
    }
    assert index._administrative_area(record) == "personale"


def test_avviso_personale_del_familiare_va_in_famiglia():
    record = {
        "Dominio": "CARTELLE ESATTORIALI", "Categoria": "AGENZIA RISCOSSIONE",
        "Nome file": "cartella_CRLVCN74L15F839W.pdf",
        "Percorso Drive": "CARTELLE ESATTORIALI/2026/cartella_CRLVCN74L15F839W.pdf",
        "SHA-256": "personal-vincenzo",
    }
    assert index._administrative_area(record) == "famiglia"


def test_nome_familiare_non_trasforma_documento_intestato_alla_societa():
    record = {
        "Dominio": "DOCUMENTI AZIENDALI", "Categoria": "FATTURA",
        "Nome file": "Pane Giuseppina Ceraldi Group.pdf",
        "Percorso Drive": "CERALDI GROUP/04523831214/fattura.pdf",
        "SHA-256": "company-document",
    }
    assert index._administrative_area(record) is None


def test_cf_legale_rappresentante_in_ader_indicizzato_non_basta_per_famiglia():
    record = {
        "Dominio": "CARTELLE ESATTORIALI", "Categoria": "AGENZIA RISCOSSIONE",
        "Nome file": "PNAGPP58D48F839K_MODELLO_DEFINIZIONE_AGEVOLATA.pdf",
        "Percorso Drive": "CARTELLE ESATTORIALI/2023/modello.pdf",
        "SHA-256": "ambiguous-legal-representative",
    }
    assert index._administrative_area(record) == "riscossione"
