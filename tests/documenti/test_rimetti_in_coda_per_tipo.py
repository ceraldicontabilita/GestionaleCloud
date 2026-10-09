"""Il ripasso rimette in DA ELABORARE solo i tipi che il gestionale ricostruisce."""
import asyncio

from app.services import drive_cartella_unica as dcu
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def test_dry_run_conta_solo_elaborate_dei_tipi_da_ripassare():
    async def scenario():
        db = ClientArchivioMemoria()["ripasso"]
        for i, (cartella, tipo) in enumerate([
            (dcu.ARCHIVIO, "fattura"), (dcu.ARCHIVIO, "fattura"), (dcu.ARCHIVIO, "corrispettivo"),
            (dcu.ARCHIVIO, "quietanza_f24"), (dcu.ERRORI, "fattura"), (dcu.ARCHIVIO, "cedolino"),
        ]):
            await db[dcu.REGISTRO].insert_one({"id": f"f{i}", "drive_file_id": f"f{i}", "nome": f"n{i}",
                                               "cartella": cartella, "tipo": tipo})
        esito = await dcu.rimetti_in_coda_per_tipo(db, dry_run=True)
        assert esito["dry_run"] is True and esito["da_rimettere"] == 3
        assert esito["per_tipo"] == {"fattura": 2, "corrispettivo": 1}
        # La simulazione non sposta niente.
        assert (await db[dcu.REGISTRO].find_one({"id": "f0"}))["cartella"] == dcu.ARCHIVIO

    asyncio.run(scenario())
