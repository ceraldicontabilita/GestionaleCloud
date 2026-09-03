"""Idempotenza TRA PROCESSI di registra_corrispettivo (audit 03/09/2026 §2, PR 5).

La guardia di ``_scrivi_se_assente`` lavora sulla cache in memoria di un solo
processo. Qui due istanze di ``SupabaseRuntimeDatabase`` (= due processi con
cache diverse) condividono lo stesso "Postgres" finto, che applica la regola
della migrazione ``supabase/migrations/20260903_idempotency_key.sql``: una
riga ATTIVA la cui ``(collection, idempotency_key)`` esiste gia' con id
diverso viene rifiutata e restituita nell'elenco ``rejected`` con il
documento esistente. Atteso: una sola riga per chiave in Postgres e nessuna
copia divergente nelle cache.
"""
import asyncio
import logging

import pytest

from app.services import scritture_contabili as sc
from app.services.supabase_runtime_database import (
    DocumentoDuplicatoRemoto,
    SupabaseRuntimeDatabase,
)


def _attivo(doc):
    return (
        (doc.get("entity_status") or "") != "deleted"
        and (doc.get("status") or "") not in ("deleted", "archived")
    )


class PostgresFinto:
    """Tabella gestionale.documents + RPC gc_upsert_documents con la regola di unicita'."""

    def __init__(self):
        self.tabelle = {}  # collection -> {id: data (senza _id)}
        self.chiamate_upsert = 0

    def semina(self, collection, documents):
        target = self.tabelle.setdefault(collection, {})
        for doc in documents:
            doc = dict(doc)
            target[str(doc.pop("_id"))] = doc

    def manifest(self):
        return [
            {"collection": c, "row_count": len(d), "digest_sha256": "-"}
            for c, d in sorted(self.tabelle.items()) if d
        ]

    def fetch(self, collection, offset, limit):
        righe = [
            {**data, "_id": doc_id}
            for doc_id, data in sorted(self.tabelle.get(collection, {}).items())
        ]
        return righe[offset:offset + limit]

    def upsert(self, collection, documents):
        self.chiamate_upsert += 1
        target = self.tabelle.setdefault(collection, {})
        rejected = []
        scritti_nel_batch = {}
        for doc in documents:
            doc = dict(doc)
            doc_id = str(doc.pop("_id"))
            chiave = doc.get("idempotency_key")
            if chiave and _attivo(doc):
                esistente = next(
                    ((eid, edata) for eid, edata in list(target.items()) + list(scritti_nel_batch.items())
                     if eid != doc_id and edata.get("idempotency_key") == chiave and _attivo(edata)),
                    None,
                )
                if esistente:
                    rejected.append({
                        "id_rifiutato": doc_id,
                        "id_esistente": esistente[0],
                        "idempotency_key": chiave,
                        "documento_esistente": {**esistente[1], "_id": esistente[0]},
                    })
                    continue
            target[doc_id] = doc
            scritti_nel_batch[doc_id] = doc
        return {"upserted": len(documents) - len(rejected), "rejected": rejected}

    def delete(self, collection, ids):
        target = self.tabelle.setdefault(collection, {})
        return sum(int(target.pop(str(i), None) is not None) for i in ids)

    def righe(self, collection):
        return [{**d, "_id": i} for i, d in self.tabelle.get(collection, {}).items()]

    def attive(self, collection):
        return [r for r in self.righe(collection) if _attivo(r)]


class ProcessoFinto(SupabaseRuntimeDatabase):
    """Un processo del server: cache propria, stesso Postgres."""

    def __init__(self, postgres: PostgresFinto, nome: str):
        super().__init__(nome, {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            "SUPABASE_RUNTIME_SECRET": "runtime-secret-test",
        })
        self.postgres = postgres

    async def _rpc(self, function_name, payload):
        if function_name == "gc_collection_manifest":
            return self.postgres.manifest()
        if function_name == "gc_fetch_collection":
            return self.postgres.fetch(
                payload["p_collection"], payload["p_offset"], payload["p_limit"])
        if function_name == "gc_upsert_documents":
            return self.postgres.upsert(payload["p_collection"], payload["p_documents"])
        if function_name == "gc_delete_documents":
            return self.postgres.delete(payload["p_collection"], payload["p_ids"])
        raise AssertionError(function_name)

    def ids_in_cache(self, collection):
        return {str(d.get("_id")) for d in self[collection]._documents}


CORR_ID = "8eb80d64-12ab-4e34-b848-8935ea1114d4"


def _corrispettivo():
    return {
        "_id": "corr-riga", "id": CORR_ID, "data": "2026-03-22",
        "matricola_rt": "99MEY026532", "totale": 4629.20,
        "totale_imponibile": 4208.36, "totale_iva": 420.84,
        "pagato_contanti": 1666.90, "pagato_elettronico": 2962.30,
        "entity_status": "active",
    }


def _chiusura_pos():
    return {
        "_id": "chiusura-riga", "id": "chiusura-1", "data": "2026-03-22",
        "importo": 2962.30, "totale": 2962.30, "gestore": "numia",
        "source": "inserimento_manuale_terminale",
    }


def _postgres_con_dati():
    postgres = PostgresFinto()
    postgres.semina("corrispettivi", [_corrispettivo()])
    postgres.semina("chiusure_pos_manuali", [_chiusura_pos()])
    return postgres


def _chiavi(righe):
    return sorted(r.get("idempotency_key") for r in righe)


def test_due_processi_stesso_corrispettivo_una_sola_riga_per_chiave(caplog):
    postgres = _postgres_con_dati()
    processo_a = ProcessoFinto(postgres, "web")
    processo_b = ProcessoFinto(postgres, "scheduler")

    async def scenario():
        # Entrambi idratano PRIMA che qualcuno scriva: cache identiche e vuote
        # per la Prima Nota, come due container avviati da un deploy sovrapposto.
        await processo_a.hydrate()
        await processo_b.hydrate()
        esito_a = await sc.registra_corrispettivo(processo_a, _corrispettivo())
        with caplog.at_level(logging.ERROR):
            esito_b = await sc.registra_corrispettivo(processo_b, _corrispettivo())
        return esito_a, esito_b

    esito_a, esito_b = asyncio.run(scenario())

    cassa = postgres.attive("prima_nota_cassa")
    banca = postgres.attive("prima_nota_banca")
    assert _chiavi(cassa) == [
        f"corr:{CORR_ID}:cassa_entrata",
        f"corr:{CORR_ID}:cassa_uscita:numia",
    ]
    assert _chiavi(banca) == [f"corr:{CORR_ID}:banca_credito:numia"]
    assert len(postgres.righe("prima_nota_cassa")) == 2
    assert len(postgres.righe("prima_nota_banca")) == 1

    # Il secondo processo riceve gli id gia' esistenti, non quelli mai scritti.
    assert esito_b["prima_nota_cassa_id"] == esito_a["prima_nota_cassa_id"]
    assert esito_b["prima_nota_cassa_uscita_pos_id"] == esito_a["prima_nota_cassa_uscita_pos_id"]
    assert esito_b["prima_nota_banca_id"] == esito_a["prima_nota_banca_id"]
    assert esito_b.get("gia_esistente") is True

    # Nessuna copia divergente: la cache di B contiene solo righe che
    # Postgres ha davvero accettato.
    for collection in ("prima_nota_cassa", "prima_nota_banca"):
        remoti = {r["_id"] for r in postgres.righe(collection)}
        assert processo_b.ids_in_cache(collection) == remoti
        assert processo_a.ids_in_cache(collection) == remoti
    assert "rifiutato" in caplog.text


def test_in_batch_la_cache_viene_riallineata_senza_eccezioni(caplog):
    postgres = _postgres_con_dati()
    processo_a = ProcessoFinto(postgres, "web")
    processo_b = ProcessoFinto(postgres, "rebuild")

    async def scenario():
        await processo_a.hydrate()
        await processo_b.hydrate()
        await sc.registra_corrispettivo(processo_a, _corrispettivo())
        with caplog.at_level(logging.ERROR):
            async with processo_b.batch_writes():
                esito_b = await sc.registra_corrispettivo(processo_b, _corrispettivo())
        return esito_b

    asyncio.run(scenario())

    assert len(postgres.attive("prima_nota_cassa")) == 2
    assert len(postgres.attive("prima_nota_banca")) == 1
    for collection in ("prima_nota_cassa", "prima_nota_banca"):
        assert processo_b.ids_in_cache(collection) == {
            r["_id"] for r in postgres.righe(collection)
        }
    assert "cache riallineata" in caplog.text


def test_rifiuto_senza_documento_esistente_marca_la_copia_in_memoria():
    postgres = _postgres_con_dati()
    processo = ProcessoFinto(postgres, "web")
    originale = postgres.upsert

    def upsert_senza_documento(collection, documents):
        esito = originale(collection, documents)
        for r in esito["rejected"]:
            r.pop("documento_esistente", None)
        return esito

    postgres.upsert = upsert_senza_documento
    postgres.semina("prima_nota_cassa", [{
        "_id": "riga-altro-processo", "id": "pn-altro", "data": "2026-03-22",
        "tipo": "entrata", "categoria": "Corrispettivi", "importo": 4629.20,
        "source": "corrispettivo_import", "matricola_rt": "ALTRA",
        "idempotency_key": f"corr:{CORR_ID}:cassa_entrata",
    }])

    async def scenario():
        # Cache vuota per la Prima Nota: il processo non sa della riga altrui.
        await processo.hydrate()
        processo["prima_nota_cassa"]._documents.clear()
        with pytest.raises(DocumentoDuplicatoRemoto):
            await processo["prima_nota_cassa"].insert_one({
                "_id": "riga-mia", "id": "pn-mio", "data": "2026-03-22",
                "tipo": "entrata", "categoria": "Corrispettivi", "importo": 4629.20,
                "source": "corrispettivo_import",
                "idempotency_key": f"corr:{CORR_ID}:cassa_entrata",
            })
        return processo["prima_nota_cassa"]._documents

    cache = asyncio.run(scenario())

    assert len(postgres.righe("prima_nota_cassa")) == 1
    assert len(cache) == 1
    assert cache[0]["entity_status"] == "deleted"
    assert cache[0]["duplicate_of"] == "riga-altro-processo"


def test_la_chiave_vince_sulla_guardia_storica_per_data_e_matricola():
    """Dopo la bonifica una riga storica ha la chiave ma magari non la
    matricola: la guardia per data/matricola non la vedrebbe, la chiave si'."""
    postgres = PostgresFinto()
    postgres.semina("corrispettivi", [_corrispettivo()])
    postgres.semina("prima_nota_cassa", [{
        "_id": "riga-storica", "id": "pn-storica", "data": "2026-03-22",
        "tipo": "entrata", "categoria": "Corrispettivi", "importo": 4629.20,
        "source": "corrispettivo_import", "matricola_rt": None,
        "corrispettivo_id": CORR_ID,
        "idempotency_key": f"corr:{CORR_ID}:cassa_entrata",
    }])
    processo = ProcessoFinto(postgres, "web")

    async def scenario():
        await processo.hydrate()
        return await sc.registra_corrispettivo(processo, _corrispettivo())

    esito = asyncio.run(scenario())

    assert esito["prima_nota_cassa_id"] == "pn-storica"
    assert esito.get("gia_esistente") is True
    assert len(postgres.righe("prima_nota_cassa")) == 1
