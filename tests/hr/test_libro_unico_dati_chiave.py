"""Il parser vivo del Libro Unico legge anche i dati chiave del cedolino.

Fino al 19/09/2026 esistevano DUE copie di `routers/libro_unico_parser.py`, una
per lato. La copia `app/hr` aveva gli arricchimenti (giorni effettivamente
lavorati, cattura generica delle voci, ratei 13ma/14ma, indennita' L.207/24,
trattamento integrativo L.21) ma non e' mai stata usata: le sue tabelle
(`hr.app_employees`, `hr.app_buste_paga`, `hr.app_presenze_mensili`) non
esistono in Supabase e nessun chiamante puntava alle sue rotte. La copia viva —
`app/services/libro_unico_workflow.py`, invocata da `documenti.upload_auto` quando
riconosce un cedolino — quei campi non li leggeva.

Questi test coprono gli arricchimenti portati sulla copia viva, e il fatto che
finiscano davvero nel documento archiviato: `busta_doc` e `presenze_doc`
elencano i campi uno per uno, quindi un parser piu' ricco da solo non basta.
"""
import re
from pathlib import Path

from app.services.libro_unico_workflow import parse_busta_paga, parse_foglio_presenze

SORGENTE = Path("app/services/libro_unico_workflow.py").read_text(encoding="utf-8")


def test_giorni_lavorati_esclude_i_giorni_con_giustificativo():
    """Un giorno con ore ma con codice di assenza non e' un giorno lavorato."""
    testo = "\n".join([
        "CERALDI GROUP S.R.L.",
        "LU 1 8,00",
        "MA 2 8,00",
        "ME 3 AI 6,40",
        "GI 4 FE 8,00",
        "SA 6",
    ])

    res = parse_foglio_presenze(testo)

    assert res["giorni_lavorati"] == 2, res["presenze"]
    assert res["giorni_con_giustificativo"] == 2


def test_voci_e_dati_chiave_dal_corpo_del_cedolino():
    """Ratei 13ma/14ma e trattamento integrativo letti dalle righe codificate."""
    testo = "\n".join([
        "C00001 Retribuzione 9,54850 79,99992 ORE 763,48",
        "C50000 Rateo 13ma Mensilita 63,62",
        "C50022 Rateo 14ma Mensilita 63,62",
        "F09081 Tratt. integrativo L.21 67,00",
    ])

    res = parse_busta_paga(testo)

    codici = [v["codice"] for v in res["voci"]]
    assert codici == ["C00001", "C50000", "C50022", "F09081"]

    dati = res["dati_chiave"]
    assert dati["rateo_13ma_presente"] is True
    assert dati["rateo_13ma_importo"] == "63,62"
    assert dati["rateo_14ma_presente"] is True
    assert dati["tratt_integrativo_l21"] == "67,00"
    # Voce assente: campo nullo, non zero — CLAUDE.md, «non inventare numeri».
    assert dati["indennita_l207_24"] is None


def test_cedolino_senza_ratei_non_li_dichiara_presenti():
    res = parse_busta_paga("C00001 Retribuzione 9,54850 79,99992 ORE 763,48")

    assert res["dati_chiave"]["rateo_13ma_presente"] is False
    assert res["dati_chiave"]["rateo_13ma_importo"] is None


def _campi_del_dizionario(nome_variabile: str) -> set:
    """Chiavi elencate nel dict `<nome_variabile> = {...}` dentro il router."""
    inizio = SORGENTE.index(f"{nome_variabile} = {{")
    blocco = SORGENTE[inizio:]
    profondita, fine = 0, None
    for i, ch in enumerate(blocco):
        if ch == "{":
            profondita += 1
        elif ch == "}":
            profondita -= 1
            if profondita == 0:
                fine = i
                break
    assert fine is not None, f"dizionario {nome_variabile} non chiuso"
    return set(re.findall(r'^\s{8,}"([a-z_0-9]+)":', blocco[: fine + 1], re.MULTILINE))


def test_i_campi_nuovi_finiscono_nel_documento_archiviato():
    """Il parser piu' ricco non basta: i due dict sono allowlist esplicite."""
    assert {"voci", "dati_chiave", "ore_lavorate", "giorni_retribuiti"} <= (
        _campi_del_dizionario("busta_doc")
    )
    assert {"giorni_lavorati", "giorni_con_giustificativo"} <= (
        _campi_del_dizionario("presenze_doc")
    )


def test_una_sola_copia_del_workflow_libro_unico():
    assert not Path("app/hr/routers/libro_unico_parser.py").exists() and not Path("app/routers/libro_unico_parser.py").exists(), (
        "La copia HR e' tornata: era registrata a /api/paghe ma scriveva su "
        "tabelle inesistenti e le mancavano la validazione PDF "
        "(`verifica_pdf_reale`), il fix P0.3 su Collections.EMPLOYEES e lo "
        "STEP 3b (TFR + Prima Nota Salari)."
    )
