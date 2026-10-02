"""Le note per il consulente (trattenute dei verbali pagati) partono con le presenze.

Fino al 02/10/2026 `note_presenze_consulente` era scritta dal gestionale e letta da nessuno.
"""
from tests.hr.scenari_base import mondo, run  # noqa: F401
from app.hr.services import presenze_consulente as pc


def _nota(mondo, **extra):
    doc = {"id": "nota_trattenuta_verbale_V1", "dipendente_id": "d1", "dipendente_nome": "Rossi Mario",
           "tipo": "trattenuta_verbale", "mese": 10, "anno": 2026, "importo": "95.50",
           "descrizione": "TRATTENUTA VERBALE 111/V/2026 - Targa GX037HJ - Pagato 2026-09-20",
           "verbale_id": "V1", "inviato_consulente": False, **extra}
    run(mondo.gest["note_presenze_consulente"].insert_one(dict(doc)))
    return doc


def test_le_note_del_mese_vanno_nel_testo_e_in_un_csv(mondo):
    _nota(mondo)
    note = run(pc.note_consulente_mese(2026, 10))
    assert [n["id"] for n in note] == ["nota_trattenuta_verbale_V1"]
    testo = pc.testo_note(note)
    assert "Rossi Mario" in testo and "95,50 €" in testo and "111/V/2026" in testo
    allegati = pc.allegato_note(2026, 10, note)
    assert len(allegati) == 1 and allegati[0][3] == "note_presenze_2026_10.csv"
    assert "Rossi Mario;trattenuta_verbale;95,50" in allegati[0][0].decode("utf-8")
    assert run(pc.note_consulente_mese(2026, 9)) == [] and pc.testo_note([]) == "" and pc.allegato_note(2026, 9, []) == []


def test_un_invio_riuscito_segna_le_note_inviate_e_un_errore_no(mondo):
    _nota(mondo)
    rec = run(pc.registra_invio(2026, 10, "studio@example.invalid", n_dipendenti=3, con_pdf=True,
                                origine="hr", esito=pc.ESITO_ERRORE, errore="SMTPError"))
    assert "note_inviate" not in rec
    assert run(mondo.gest["note_presenze_consulente"].find_one({"id": "nota_trattenuta_verbale_V1"}))["inviato_consulente"] is False
    rec = run(pc.registra_invio(2026, 10, "studio@example.invalid", n_dipendenti=3, con_pdf=True, origine="erp"))
    assert rec["note_inviate"] == 1
    nota = run(mondo.gest["note_presenze_consulente"].find_one({"id": "nota_trattenuta_verbale_V1"}))
    assert nota["inviato_consulente"] is True and nota["invio_id"] == rec["id"]
    # secondo invio: la nota resta inviata, non si conta due volte
    assert run(pc.registra_invio(2026, 10, "studio@example.invalid", n_dipendenti=3, con_pdf=True, origine="erp"))["note_inviate"] == 0
