"""Bug segnalato dall'utente 15/07/2026, trovato analizzando un export reale
dell'estratto conto (file caricato dall'utente, 4287 movimenti): i pagamenti
tramite addebito diretto SDD (CORE o B2B) — utenze, leasing, assicurazioni,
fornitori con mandato ricorrente — non avevano MAI il nome del beneficiario
estratto da estrai_fornitore_pulito(), perché la funzione cercava solo la
parola "FAVORE" (usata nei bonifici). Sul file reale: 240 righe SDD, zero
fornitori estratti — perdendo così il bonus di punteggio "nome fornitore in
causale" nel matching con le fatture in riconciliazione_bancaria.py.

Esempi qui sotto sono sintetici (non i nomi reali del file caricato) ma
riproducono esattamente il formato reale verificato: "SDD CORE: <codice
mandato senza spazi> <nome beneficiario>" / "SDD B2B : <codice> <nome>"."""
from app.routers.bank.estratto_conto import estrai_fornitore_pulito


def test_estrae_fornitore_da_sdd_core():
    desc = "ADDEBITO DIRETTO SDD - SDD CORE: AB12CD34EF56 Fornitore Utenze Srl"
    assert estrai_fornitore_pulito(desc) == "Fornitore Utenze Srl"


def test_estrae_fornitore_da_sdd_b2b():
    desc = "ADDEBITO DIRETTO SDD - SDD B2B : 00000000000000 Grande Fornitore SpA"
    assert estrai_fornitore_pulito(desc) == "Grande Fornitore SpA"


def test_estrae_fornitore_con_codice_mandato_alfanumerico_complesso():
    # Codici mandato reali possono contenere parentesi/virgole senza spazi.
    desc = "ADDEBITO DIRETTO SDD - SDD CORE: XY)1,ABCDE2FGH(99ZZ9 Marketplace EU Sarl, IT Branch"
    assert estrai_fornitore_pulito(desc) == "Marketplace EU Sarl, IT Branch"


def test_non_estrae_da_riga_commissione_sdd_senza_nome():
    # "Comm.sdd:" è la riga di commissione collegata, senza nome beneficiario.
    assert estrai_fornitore_pulito("COMMISSIONI - Comm.sdd: AB12CD34EF56") is None


def test_favore_ha_precedenza_su_sdd():
    # Non dovrebbe capitare nella realtà, ma se entrambi i pattern fossero
    # presenti "FAVORE" resta il ramo prioritario esistente.
    desc = "VOSTRA DISPOSIZIONE - VS.DISP. FAVORE Fornitore Bonifico Srl - ADD.TOT"
    assert estrai_fornitore_pulito(desc) == "Fornitore Bonifico Srl"


def test_prelievo_assegno_resta_senza_fornitore():
    desc = "PRELIEVO ASSEGNO - DM 00000 CRA: 00000000000000 NUM: 0000000000"
    assert estrai_fornitore_pulito(desc) is None
