from pathlib import Path

import json

import pytest

from app.lotti.scripts.associa_immagini_ricettario import (
    Immagine,
    applica_mappature_esplicite,
    normalizza_nome,
    scegli_immagine,
    token_significativi,
)


def image(name):
    stem = name.rsplit(".", 1)[0]
    return Immagine(
        path=Path(name),
        nome_norm=normalizza_nome(stem),
        tokens=frozenset(token_significativi(stem)),
        sha256=name,
    )


def test_nome_esatto_associa_la_foto():
    selected, _ = scegli_immagine("Spritz", [image("spritz.webp")])
    assert selected.path.name == "spritz.webp"


def test_rhum_e_rum_sono_lo_stesso_nome_per_una_foto_esatta():
    selected, reason = scegli_immagine(
        "Babà Napoletano al Rum",
        [image("baba-napoletano-al-rhum.webp")],
    )
    assert selected.path.name == "baba-napoletano-al-rhum.webp"
    assert reason == "nome esatto"


def test_annotazione_base_non_impedisce_il_match_esatto():
    selected, reason = scegli_immagine(
        "Pasta Frolla (base)",
        [image("pasta-frolla.jpg")],
    )
    assert selected.path.name == "pasta-frolla.jpg"
    assert reason == "nome esatto"


def test_variante_usa_il_proprio_nome_e_non_quello_della_base():
    selected, reason = scegli_immagine(
        "Sfogliatella riccia (variante di: sfogliatella frolla)",
        [image("sfogliatella-riccia.webp"), image("sfogliatella-frolla.webp")],
    )
    assert selected.path.name == "sfogliatella-riccia.webp"
    assert reason == "nome esatto"


def test_foto_generica_base_non_viene_associata_alla_variante():
    selected, reason = scegli_immagine(
        "Coda di aragosta al cioccolato",
        [image("coda-di-aragosta.webp")],
    )
    assert selected is None
    assert "nessuna" in reason


def test_mappatura_esplicita_associa_solo_un_file_indicizzato(tmp_path):
    image_path = tmp_path / "ischitano.webp"
    image_path.write_bytes(b"image")
    indexed = Immagine(
        path=image_path,
        nome_norm="ischitano",
        tokens=frozenset({"ischitano"}),
        sha256="digest",
    )
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        json.dumps([{"id": "r1", "file": str(image_path)}]), encoding="utf-8"
    )
    plan = {"associazioni": [], "gia_con_foto": [], "non_associate": [{"id": "r1"}]}

    result = applica_mappature_esplicite(
        plan, [{"id": "r1", "nome": "Cornetto ischitano"}], [indexed], mapping_path
    )

    assert result["associazioni"][0]["file"] == str(image_path)
    assert result["non_associate"] == []


def test_mappatura_esplicita_non_sovrascrive_una_foto_esistente(tmp_path):
    image_path = tmp_path / "foto.webp"
    image_path.write_bytes(b"image")
    indexed = Immagine(image_path, "foto", frozenset({"foto"}), "digest")
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        json.dumps([{"id": "r1", "file": str(image_path)}]), encoding="utf-8"
    )
    plan = {"associazioni": [], "gia_con_foto": [], "non_associate": []}

    result = applica_mappature_esplicite(
        plan,
        [{"id": "r1", "nome": "Ricetta", "foto_url": "/api/foto/esistente"}],
        [indexed],
        mapping_path,
    )

    assert result["associazioni"] == []


def test_mappatura_rifiuta_file_fuori_indice(tmp_path):
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        json.dumps([{"id": "r1", "file": str(tmp_path / "altro.webp")}]), encoding="utf-8"
    )
    plan = {"associazioni": [], "gia_con_foto": [], "non_associate": [{"id": "r1"}]}

    with pytest.raises(ValueError, match="non presente"):
        applica_mappature_esplicite(
            plan, [{"id": "r1", "nome": "Ricetta"}], [], mapping_path
        )
