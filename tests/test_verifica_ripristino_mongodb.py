"""Test del confronto DR MongoDB, interamente in memoria e senza segreti."""
import mongomock

from scripts.verifica_ripristino_mongodb import (
    _validate_distinct_targets,
    build_manifest,
    compare_manifests,
)


def _database(nome):
    client = mongomock.MongoClient()
    db = client[nome]
    db.invoices.insert_many(
        [
            {"_id": "inv-1", "total_amount": 100.0, "status": "imported"},
            {"_id": "inv-2", "total_amount": 200.0, "status": "paid"},
        ]
    )
    db.invoices.create_index("status")
    db.prima_nota_banca.insert_one({"_id": "mov-1", "importo": 100.0})
    return db


def test_manifest_non_contiene_documenti_o_uri():
    manifest = build_manifest(_database("source"), sample_size=10)
    rendered = str(manifest)

    assert "inv-1" not in rendered
    assert "mongodb" not in rendered.lower()
    assert manifest["collections"]["invoices"]["document_count"] == 2
    assert len(manifest["collections"]["invoices"]["sample_sha256"]) == 64


def test_copia_identica_supera_il_confronto():
    source = build_manifest(_database("source"))
    restored = build_manifest(_database("restored"))

    report = compare_manifests(source, restored)

    assert report["ok"] is True
    assert report["mismatches"] == {}


def test_documento_mancante_viene_rilevato():
    source_db = _database("source")
    restored_db = _database("restored")
    restored_db.invoices.delete_one({"_id": "inv-2"})

    report = compare_manifests(
        build_manifest(source_db), build_manifest(restored_db)
    )

    assert report["ok"] is False
    assert "document_count" in report["mismatches"]["invoices"]
    assert "sample_sha256" in report["mismatches"]["invoices"]


def test_indice_mancante_viene_rilevato():
    source_db = _database("source")
    restored_db = _database("restored")
    restored_db.invoices.drop_index("status_1")

    report = compare_manifests(
        build_manifest(source_db), build_manifest(restored_db)
    )

    assert report["ok"] is False
    assert report["mismatches"]["invoices"] == ["indexes"]


def test_collection_mancante_e_inattesa_vengono_rilevate():
    source_db = _database("source")
    restored_db = _database("restored")
    restored_db.drop_collection("prima_nota_banca")
    restored_db.extra.insert_one({"_id": 1})

    report = compare_manifests(
        build_manifest(source_db), build_manifest(restored_db)
    )

    assert report["ok"] is False
    assert report["missing_collections"] == ["prima_nota_banca"]
    assert report["unexpected_collections"] == ["extra"]


def test_stesso_target_viene_rifiutato_senza_mostrare_uri():
    try:
        _validate_distinct_targets(
            "mongodb+srv://utente:segreto@cluster.example/",
            "mongodb+srv://utente:segreto@cluster.example/",
            "Gestionale",
            "Gestionale",
        )
    except ValueError as exc:
        assert "segreto" not in str(exc)
        assert "coincidono" in str(exc)
    else:
        raise AssertionError("Lo stesso target doveva essere rifiutato")
