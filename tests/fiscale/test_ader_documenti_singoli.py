"""Documenti Agenzia delle entrate-Riscossione fuori dall'archivio ZIP.

Caso reale 07/10/2026: la lettera di accoglimento della rateizzazione 904285
(tre documenti, sei rate dal 13/10/2025) e tre stampe «Dettaglio tributi»
dell'area riservata erano in ERRORI «tipo di documento non riconosciuto».
I testi qui sotto ricalcano la struttura di quei PDF con numeri di prova.
"""
import asyncio

import pytest

from app.routers import documenti
from app.services import ader_snapshot_import as ader
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

SOCIETA = "04523831214"


# I font di base di fitz non hanno il simbolo «€» che le lettere AdeR
# stampano: il PDF sintetico esiste per l'archivio (impronta, pagine), il
# testo che il lettore vede e' quello dichiarato qui, parola per parola.
_TESTI: dict[bytes, str] = {}


def _pdf(text: str) -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page(width=842, height=595)
    page.insert_textbox(fitz.Rect(24, 24, 818, 571), text, fontsize=7)
    result = document.tobytes()
    document.close()
    _TESTI[result] = text
    return result


@pytest.fixture(autouse=True)
def _testo_dal_pdf_sintetico(monkeypatch):
    originale = ader._pdf_text
    monkeypatch.setattr(ader, "_pdf_text", lambda content: _TESTI.get(content) or originale(content))


def _dettaglio(numero="07120250137550929000", tipo="Cartella", ente="CAMERA DI COMMERCIO UFFICIO DIRITTO ANNU",
               notifica="25/08/2025", iniziale="38,08", da_pagare="5,40", sgravio="NO", righe=None):
    righe = righe if righe is not None else [
        ("0961", "Diritto annuale..... Diritto annuale Camera di commercio PROVA S.R.L. REA NA 1",
         "CAMERA DI COMMERCIO UFFICIO DIRITTO ANNUALE DI NAPOLI", "2021", "SI", "28,00", "0,00", "0,00", "0,00", "4,71"),
        ("0962", "Diritto annuale..... Diritto annuale Camera di commercio - sanzione pec PROVA S.R.L. REA NA 1",
         "CAMERA DI COMMERCIO UFFICIO DIRITTO ANNUALE DI NAPOLI", "2021", "SI", "1,43", "0,00", "0,00", "0,00", "0,23"),
        ("0992", "Diritto annuale..... Diritto annuale Camera di commercio - interessi PROVA S.R.L. REA NA 1",
         "CAMERA DI COMMERCIO UFFICIO DIRITTO ANNUALE DI NAPOLI", "2021", "SI", "2,77", "0,00", "0,00", "0,00", "0,46"),
    ]
    corpo = "\n".join(" ".join(r) for r in righe)
    return (
        "- Ministero dell'Economia e delle Finanze Agenzia delle Entrate\n"
        "Area riservata - Cittadini e Imprese\nSituazione debitoria - consulta e paga\nDettaglio tributi\n"
        f"Dati anagrafici\nCodice Fiscale/Partita IVA: {SOCIETA}\nDenominazione : PROVA S.R.L.\n"
        "<- Torna alla lista completa dei documenti\n"
        f"Dati documento {numero}\nN° documento Descrizione Ente Creditore Data notifica Iniziale ? Da pagare ? "
        "Sospensione Sgravio Rateizzazione Dettagli\n"
        f"{numero} {tipo} {ente} {notifica} {iniziale} {da_pagare} Sospensione NO Sgravio {sgravio} Rateizzazione SI "
        "Nessuna Procedura Attiva\n"
        "Gli importi indicati nel prospetto \"Lista tributi\", riportato in basso, non sono comprensivi di eventuali oneri accessori.\n"
        "Lista tributi\nDescrizione Importi a ruolo\nCodice tributo Descrizione tributo/Ente Ente impositore Anno Rateizzato "
        "Iniziale Interessi dovuti a maggior rateizzazione Sgravato Importi sospesi Importo residuo\n"
        f"{corpo}\n"
        "25/02/26, 10:49 Agenzia delle entrate-Riscossione - Area riservata Cittadini e Imprese\n"
        f"https://servizi.agenziaentrateriscossione.gov.it/sac-web/sac2/ec_ruolo.do?identificativoDocumento={numero} 1/1\n"
    )


ACCOGLIMENTO = (
    "Agenzia delle entrate-Riscossione\nVia R. Bracco, 20 80133 NAPOLI (NA)\nSpett.le PROVA S.R.L.\n"
    "Oggetto: Accoglimento dell'istanza di rateizzazione ex art. 19 del D.P.R. n. 602/1973, con identificativo 904285 "
    f"del 01/10/2025 presentata dal C.F. {SOCIETA}\n"
    "Con riferimento all'istanza di rateizzazione di somme iscritte a ruolo con identificativo 904285 da Lei presentata "
    "il 01/10/2025, relativa ai seguenti documenti:\nDocumento n. Importo\n"
    "37120250002792001 € 6,90\n07120250137550929 € 32,20\n07120250145650421 € 3'720,19\n"
    "Le comunichiamo di averLe accordato la suddivisione del pagamento in n. 6 rate mensili.\n"
    "Il pagamento delle singole rate deve avvenire, a decorrere dal 13/10/2025, alle scadenze indicate nel piano allegato.\n"
    "Prospetto del piano di ammortamento\nIdentificativo istanza 904285 del 01/10/2025\n"
    f"C.F.: {SOCIETA}\nN. Documenti: 1 37120250002792001 2 07120250137550929 3 07120250145650421\n"
    "Numero rate accordato: 6\nImporto complessivo rateizzato: € 3'759,29\ndi cui iscritto a ruolo: € 3'759,29\n"
    "di cui mora: € 0,00\ndi cui oneri di riscossione3: € 0,00\n"
    "Prima scadenza di pagamento\nImporto Prima Rata Scadenza Prima Rata Prima Rata\n"
    "Quota capitale € 632,35\nQuota interessi di mora € 0,00\nQuota interessi di rateizzazione € 0,00\n"
    "Quota oneri di riscossione3 € 0,00\nSpese esecutive € 0,00\nDiritti di notifica dei documenti € 11,76\n"
    "€ 644,11 13/10/2025\n"
    "Successive scadenze di pagamento\nN. rata Data scadenza Quota capitale Quota interessi di mora "
    "Quota interessi di rateizzazione Quota oneri di riscossione3 Importo rata\n"
    "2 13/11/2025 € 625,37 € 0,00 € 0,09 € 0,00 € 625,46\n"
    "3 13/12/2025 € 624,43 € 0,00 € 2,58 € 0,00 € 627,01\n"
    "4 13/01/2026 € 625,07 € 0,00 € 1,95 € 0,00 € 627,02\n"
    "5 13/02/2026 € 625,71 € 0,00 € 1,31 € 0,00 € 627,02\n"
    "6 13/03/2026 € 626,36 € 0,00 € 0,66 € 0,00 € 627,02\n"
    "Totale piano € 3'759,29 € 0,00 € 6,59 € 0,00 € 3'777,64\n"
    "3 Per i carichi affidati fino al 31 dicembre 2021 restano fermi l'aggio e gli oneri di riscossione.\n"
)

CARTELLA_VERA = "AGENZIA DELLE ENTRATE-RISCOSSIONE CARTELLA DI PAGAMENTO N. 071 2025 00137550 92 /000 RUOLO N. 2025/1"


def test_il_tipo_si_riconosce_dal_contenuto_non_dal_nome():
    assert ader.riconosci(_dettaglio().replace("\n", " ").upper()) == ader.TIPO_DETTAGLIO
    assert ader.riconosci(ACCOGLIMENTO.replace("\n", " ").upper()) == ader.TIPO_PIANO
    assert ader.riconosci(CARTELLA_VERA) is None


def test_il_dettaglio_tributi_e_una_fotografia_con_le_righe_a_ruolo():
    riga = ader.parse_dettaglio_tributi(content=_pdf(_dettaglio()), filename="stampa.pdf", dataset_sha256="a" * 64)
    assert riga["company_id"] == SOCIETA and riga["document_number"] == "07120250137550929000"
    assert riga["document_type"] == "CARTELLA_ESATTORIALE" and riga["notification_date"] == "2025-08-25"
    # l'ente intero viene dalle righe, in testata il portale lo tronca
    assert riga["creditor"] == "CAMERA DI COMMERCIO UFFICIO DIRITTO ANNUALE DI NAPOLI"
    assert riga["snapshot_date"] == "2026-02-25" and riga["source_layout"] == ader.LAYOUT_DETTAGLIO
    assert (riga["initial_amount"], riga["net_payable_amount"]) == (38.08, 5.4)
    assert [(r["codice_tributo"], r["anno"], r["iniziale_cents"], r["residuo_cents"]) for r in riga["lines"]] == [
        ("0961", 2021, 2800, 471), ("0962", 2021, 143, 23), ("0992", 2021, 277, 46)]
    assert riga["lines_quadrano"] and riga["calculated_business_status"] == "PAYABLE"
    assert riga["payment_evidence"] is False and riga["active_procedure"] is False


def test_lo_zero_da_pagare_per_sgravio_non_e_un_pagamento():
    righe = [("8050", "Modello DM 10 C..... Modello DM 10 CONTRIBUTI DA 11/2024 A 11/2024", "INPS SEDE DI NAPOLI",
              "2024", "NO", "3.921,00", "0,00", "3.921,00", "0,00", "0,00"),
             ("8340", "Spese di notifi..... Spese di notifica forfettarie", "INPS SEDE DI NAPOLI",
              "2025", "SI", "6,90", "0,00", "0,00", "0,00", "0,00")]
    testo = _dettaglio(numero="37120250002792001000", tipo="Avviso di addebito", ente="INPS SEDE DI NAPOLI",
                       notifica="02/08/2025", iniziale="3.927,90", da_pagare="0,00", sgravio="SI", righe=righe)
    riga = ader.parse_dettaglio_tributi(content=_pdf(testo), filename="stampa.pdf", dataset_sha256="b" * 64)
    assert riga["document_type"] == "AVVISO_ADDEBITO" and riga["relief"] is True
    assert riga["calculated_business_status"] == "RELIEVED" and riga["closure_reason"] == "PORTAL_RELIEF"
    assert riga["relief_amount"] == 3921.0 and riga["net_payable_amount"] == 0.0
    # la descrizione con «DA 11/2024 A 11/2024» non si confonde con l'anno della riga
    assert riga["lines"][0]["anno"] == 2024 and riga["lines"][0]["descrizione"].endswith("A 11/2024")


def test_il_piano_porta_tutte_le_rate_e_quadra_con_i_totali_della_lettera():
    piano = ader.parse_rate_plan(content=_pdf(ACCOGLIMENTO), filename="Accoglimento_AR071904285.pdf",
                                 company_id=SOCIETA, document_numbers=["37120250002792001000"], dataset_sha256="c" * 64)
    assert piano["plan_reference"] == "AR071904285" and piano["installment_count"] == 6
    assert [(r["number"], r["due_date"], r["amount_cents"]) for r in piano["installments"]] == [
        (1, "2025-10-13", 64411), (2, "2025-11-13", 62546), (3, "2025-12-13", 62701),
        (4, "2026-01-13", 62702), (5, "2026-02-13", 62702), (6, "2026-03-13", 62702)]
    assert piano["installments"][0]["notification_fees_cents"] == 1176 and piano["installments"][2]["plan_interest_cents"] == 258
    assert [d["amount_cents"] for d in piano["documents"]] == [690, 3220, 372019]
    assert piano["quadratura"] == {"rate_vs_totale_piano": True, "documenti_vs_rateizzato": True, "numero_rate": True,
                                   "somma_rate_cents": 377764, "somma_documenti_cents": 375929}
    assert piano["unresolved_references"] == ["07120250137550929", "07120250145650421"] and piano["requires_review"]


def test_lo_smistatore_li_riconosce_prima_della_cartella(monkeypatch):
    monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda *_a, **_k: ACCOGLIMENTO.upper())
    assert documenti.detect_document_type("file qualunque.pdf", b"%PDF-1.4 finto") == ader.TIPO_PIANO
    monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda *_a, **_k: _dettaglio().upper())
    assert documenti.detect_document_type("stampa.pdf", b"%PDF-1.4 finto") == ader.TIPO_DETTAGLIO


def test_dettaglio_e_piano_entrano_nelle_entita_canoniche_una_volta_sola(monkeypatch):
    from app.config import settings
    from app.db_collections import (COLL_ADER_POSITION_SNAPSHOTS, COLL_TAX_COLLECTION_CLAIMS,
                                    COLL_TAX_RATE_INSTALLMENTS, COLL_TAX_RATE_PLANS)

    monkeypatch.setattr(settings, "FISCAL_COMPANY_ID", SOCIETA)
    db = ClientArchivioMemoria()["ader_singoli"]
    pdf_dettaglio = _pdf(_dettaglio())
    pdf_piano = _pdf(ACCOGLIMENTO)

    async def scenario():
        primo = await ader.archivia_documento_ader(db, filename="stampa.pdf", content=pdf_dettaglio,
                                                   testo=_dettaglio(), source_context={"channel": "test"})
        piano = await ader.archivia_documento_ader(db, filename="Accoglimento_AR071904285.pdf", content=pdf_piano,
                                                   testo=ACCOGLIMENTO)
        # stessa lettera in una seconda copia PDF con byte diversi: stesso piano, nessun doppione
        secondo_piano = await ader.archivia_documento_ader(db, filename="Accoglimento_AR071904285 (1).pdf",
                                                           content=_pdf(ACCOGLIMENTO + "\n"), testo=ACCOGLIMENTO)
        altro = _dettaglio(numero="07120250145650421000", ente="AMMINISTRAZIONE FINANZIARIA DIR PROV LE",
                           notifica="19/09/2025", iniziale="7.496,28", da_pagare="1.255,14",
                           righe=[("380A", "IRAP ..... IRAP", "AMMINISTRAZIONE FINANZIARIA DIR PROV LE II NAPOLI",
                                   "2022", "SI", "4.040,64", "0,00", "0,00", "0,00", "1.255,14")])
        terzo = await ader.archivia_documento_ader(db, filename="stampa2.pdf", content=_pdf(altro), testo=altro)
        return primo, piano, secondo_piano, terzo

    primo, piano, secondo_piano, terzo = asyncio.run(scenario())
    assert primo["success"] and primo["tipo"] == ader.TIPO_DETTAGLIO and not primo["duplicate"]
    assert "07120250137550929000" in primo["message"] and primo["fiscal_document_id"]
    claims = asyncio.run(db[COLL_TAX_COLLECTION_CLAIMS].find({}, {"_id": 0}).to_list(10))
    assert sorted(c["collection_number"] for c in claims) == ["07120250137550929000", "07120250145650421000"]
    assert next(c for c in claims if c["collection_number"] == "07120250137550929000")["residual_cents"] == 540
    assert asyncio.run(db[COLL_ADER_POSITION_SNAPSHOTS].count_documents({})) == 2

    assert piano["tipo"] == ader.TIPO_PIANO and not piano["duplicate"] and secondo_piano["duplicate"]
    piani = asyncio.run(db[COLL_TAX_RATE_PLANS].find({}, {"_id": 0}).to_list(10))
    assert len(piani) == 1 and piani[0]["plan_reference"] == "AR071904285" and len(piani[0]["installments"]) == 6
    rate = asyncio.run(db[COLL_TAX_RATE_INSTALLMENTS].find({}, {"_id": 0}).to_list(20))
    assert len(rate) == 6 and {r["status"] for r in rate} == {"EXPECTED"} and all(r["rate_plan_id"] == piani[0]["id"] for r in rate)
    assert sum(r["amount_cents"] for r in rate) == 377764
    # il piano citava 07120250145650421 con 17 cifre: il dettaglio arrivato dopo lo risolve, senza inventare il suffisso
    assert terzo["piani_collegati"] == 1
    piano_db = asyncio.run(db[COLL_TAX_RATE_PLANS].find_one({}, {"_id": 0}))
    risolti = {r["printed_reference"]: r["document_number"] for r in piano_db["document_references"]}
    assert risolti["07120250137550929"] == "07120250137550929000" and risolti["07120250145650421"] == "07120250145650421000"
    assert piano_db["unresolved_references"] == ["37120250002792001"] and piano_db["requires_review"] is True


def test_un_dettaglio_di_un_altro_contribuente_si_rifiuta(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "FISCAL_COMPANY_ID", "00000000000")
    db = ClientArchivioMemoria()["ader_altro"]
    with pytest.raises(ValueError, match="altro contribuente"):
        asyncio.run(ader.archivia_documento_ader(db, filename="s.pdf", content=_pdf(_dettaglio()), testo=_dettaglio()))
