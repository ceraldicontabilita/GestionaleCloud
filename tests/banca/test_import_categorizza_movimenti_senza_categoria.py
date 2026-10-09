"""L'import valorizza `categoria` sui movimenti che il CSV bancario lascia
vuoti, SOLO quando il riconoscimento e' certo (motore unico in
`app.services.categorizzazione_movimenti`). Verificato il 18/09/2026: 1.764
dei 1.920 movimenti bancari 2026 (92%) arrivavano senza categoria dal CSV
della banca, perche' quella colonna non e' sempre valorizzata dall'export."""
import asyncio

from app.routers.bank import estratto_conto as modulo

INTESTAZIONE = ("Ragione Sociale;Data contabile;Data valuta;Banca;Rapporto;"
                "Importo;Divisa;Descrizione;Categoria/sottocategoria;Hashtag")

BANCA = "05034 - BANCO BPM S.P.A."
RAPPORTO = "5462 - 03406 - 178800005462"


def _riga(descrizione, importo, categoria="", data="17/07/2026"):
    return (f"CERALDI GROUP S.R.L.;{data};{data};{BANCA};{RAPPORTO};"
            f"{importo};EUR;{descrizione};{categoria};")


def _csv(*righe):
    return ("\r\n".join([INTESTAZIONE, *righe]) + "\r\n").encode("utf-8")


class _File:
    skip_duplicate_repairs = True

    def __init__(self, contenuto, filename="ESTRATTO 2026.csv"):
        self.filename = filename
        self._contenuto = contenuto

    async def read(self):
        return self._contenuto


def _db(monkeypatch, nome):
    from app.services.archivio_documenti_memoria import ClientArchivioMemoria
    finto = ClientArchivioMemoria()[nome]
    monkeypatch.setattr(modulo.Database, "get_db", staticmethod(lambda: finto))
    return finto


def _importa(*righe):
    return asyncio.run(modulo.import_estratto_conto(_File(_csv(*righe))))


def _movimenti(db):
    return asyncio.run(db["estratto_conto_movimenti"].find({}).to_list(100))


def test_f24_senza_categoria_dal_csv_viene_categorizzato(monkeypatch):
    db = _db(monkeypatch, "import_f24")
    _importa(_riga("ADDEBITO F24 IVA E RITENUTE", "-780,00"))

    movimenti = _movimenti(db)
    assert len(movimenti) == 1
    assert movimenti[0]["categoria"] == "F24"
    assert movimenti[0]["categoria_auto"] is True
    assert "F24" in movimenti[0]["categoria_auto_motivo"]


def test_descrizione_non_riconosciuta_resta_senza_categoria(monkeypatch):
    db = _db(monkeypatch, "import_sconosciuto")
    _importa(_riga("BONIFICO A FAVORE MARIO ROSSI", "-250,00"))

    movimenti = _movimenti(db)
    assert len(movimenti) == 1
    assert movimenti[0]["categoria"] == ""
    assert not movimenti[0].get("categoria_auto")


def test_categoria_gia_data_dal_csv_bancario_non_viene_toccata(monkeypatch):
    db = _db(monkeypatch, "import_gia_categorizzato")
    _importa(_riga("QUALSIASI CAUSALE", "-99,00", categoria="Fornitori - Beni"))

    movimenti = _movimenti(db)
    assert len(movimenti) == 1
    assert movimenti[0]["categoria"] == "Fornitori - Beni"
    assert not movimenti[0].get("categoria_auto")


def test_regola_imparata_vince_sul_motore_generico_in_import(monkeypatch):
    """Il titolare ha insegnato "questo e' di Nexi" (`regole_riconoscimento_
    banca`, 19/09/2026): all'import questa regola vince sulla parola chiave
    generica "COMMISSIONI" (che da sola darebbe solo "Commissioni bancarie")."""
    db = _db(monkeypatch, "import_regola_appresa")
    asyncio.run(db["regole_riconoscimento_banca"].insert_one({
        "id": "r-nexi", "pattern": "COMMISSIONI NEXI PAYMENTS", "entita_tipo": "fornitore",
        "entita_id": "forn-nexi", "entita_nome": "Nexi Payments S.p.A.", "categoria": "Fatture",
    }))

    _importa(_riga("ADDEBITO COMMISSIONI NEXI PAYMENTS SPA", "-45,90"))

    movimenti = _movimenti(db)
    assert len(movimenti) == 1
    assert movimenti[0]["categoria"] == "Fatture"
    assert movimenti[0]["fornitore_id"] == "forn-nexi"
    assert movimenti[0]["fornitore"] == "Nexi Payments S.p.A."
    assert movimenti[0]["categoria_auto"] is True
