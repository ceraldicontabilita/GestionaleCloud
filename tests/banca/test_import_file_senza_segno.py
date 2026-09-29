"""Un export senza segno non si registra: non si indovina se e' entrata o uscita.

Caso reale del 29/09/2026: «ElencoEntrateUsciteAndamento_31-07-2026.csv»
(1.873 righe, nessun importo negativo) ha scritto 242 movimenti 2026 come
«entrata», addebiti SDD e prelievi assegno compresi, tutti doppioni.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.routers.bank import estratto_conto as modulo

INTESTAZIONE = ("Ragione Sociale;Data contabile;Data valuta;Banca;Rapporto;"
                "Importo;Divisa;Descrizione;Categoria/sottocategoria;Hashtag")


def _riga(descrizione, importo, giorno):
    data = f"{giorno:02d}/06/2026"
    return f"CERALDI GROUP S.R.L.;{data};{data};BPM;5462;{importo};EUR;{descrizione};;"


class _File:
    skip_duplicate_repairs = True

    def __init__(self, righe):
        self.filename = "ElencoEntrateUsciteAndamento_31-07-2026_07.23.35.csv"
        self._contenuto = ("\r\n".join([INTESTAZIONE, *righe]) + "\r\n").encode("utf-8")

    async def read(self):
        return self._contenuto


def _db(monkeypatch, nome):
    from app.services.archivio_documenti_memoria import ClientArchivioMemoria
    finto = ClientArchivioMemoria()[nome]
    monkeypatch.setattr(modulo.Database, "get_db", staticmethod(lambda: finto))
    return finto


def test_file_con_soli_importi_positivi_viene_rifiutato(monkeypatch):
    db = _db(monkeypatch, "senza_segno")
    righe = [_riga("PRELIEVO ASSEGNO - NUM: 02087693%02d" % g, "1496,96", g) for g in range(1, 8)]
    righe += [_riga("ADDEBITO DIRETTO SDD - SDD CORE: FASTWEB", "30,50", g) for g in range(8, 13)]
    with pytest.raises(HTTPException) as err:
        asyncio.run(modulo.import_estratto_conto(_File(righe)))
    assert err.value.status_code == 422
    assert "senza segno" in err.value.detail
    assert asyncio.run(db["estratto_conto_movimenti"].find({}).to_list(10)) == []


def test_file_con_uscite_negative_si_registra(monkeypatch):
    db = _db(monkeypatch, "con_segno")
    righe = [_riga("PRELIEVO ASSEGNO - NUM: 02087693%02d" % g, "-1496,96", g) for g in range(1, 8)]
    righe += [_riga("BONIF. VS. FAVORE - CLIENTE %d" % g, "300,00", g) for g in range(8, 13)]
    asyncio.run(modulo.import_estratto_conto(_File(righe)))
    movimenti = asyncio.run(db["estratto_conto_movimenti"].find({}).to_list(20))
    assert len(movimenti) == 12
    assert sum(1 for m in movimenti if m["tipo"] == "uscita") == 7


def test_pochi_movimenti_tutti_in_entrata_restano_ammessi():
    assert not modulo.segno_assente([{"importo": 100.0}] * 3)
    assert modulo.segno_assente([{"importo": 100.0}] * 12)
    assert not modulo.segno_assente([{"importo": 100.0}] * 11 + [{"importo": -5.0}])
