"""Guardia: il non riscosso e' la terza gamba del DARE, non un ammanco.

Una chiusura giornaliera puo' documentare un corrispettivo che non e' entrato
ne' in cassa ne' sul POS: sospesi, buoni, corrispettivo con emissione di
fattura. Non e' denaro, e' un credito — ma e' ricavo del giorno, e l'AVERE
(ricavi + IVA a debito) vale il totale.

Il motore leggeva solo cassa e POS. Il DARE valeva quindi `cassa + pos`
mentre l'AVERE valeva `totale`: la scrittura non quadrava, e il motore
rifiutava **l'intera giornata** con «ripartizione contanti/POS non quadrata
con il totale».

Misurato sull'archivio vero il 20/09/2026: **21 giornate dal 31/03 al 30/07
fuori dal libro giornale, 67.856,00 EUR di ricavi e 6.168,74 EUR di IVA a
debito** — per **204,10 EUR** complessivi di non riscosso. Una manciata di
euro di sospesi buttava fuori dal giornale giornate intere da migliaia.

I valori qui sotto sono quelli veri di quelle giornate. Le chiusure
d'origine le davano gia' per quadrate: il loro campo `differenza` vale zero,
perche' cassa + POS + non riscosso = totale al centesimo.

Il rifiuto resta dov'e' giusto: il non riscosso entra come **prova
dichiarata dal documento**, mai come differenza calcolata per far tornare i
conti. Un totale che non quadra nemmeno contandolo e' ancora
`da_verificare`.
"""
import asyncio

import pytest

import app.services.registrazione_contabile as motore


class _Coll:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def find_one(self, query, proj=None, sort=None):
        trovati = [d for d in self.docs
                   if all(d.get(k) == v for k, v in query.items())]
        if sort:
            chiave, verso = sort[0]
            trovati.sort(key=lambda d: d.get(chiave) or 0, reverse=(verso < 0))
        return dict(trovati[0]) if trovati else None

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                d.update(update.get("$set", {}))
                return
        if upsert:
            nuovo = dict(query)
            nuovo.update(update.get("$set", {}))
            self.docs.append(nuovo)


class _Db:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, nome):
        return self.colls.setdefault(nome, _Coll())


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def db(monkeypatch):
    archivio = _Db()
    conti = archivio["piano_conti"]
    for codice, categoria in [
        ("01.01.01", "attivo"),   # Cassa
        ("01.01.02", "attivo"),   # Banca c/c
        ("01.02.01", "attivo"),   # Crediti v/clienti
        ("04.01.02", "ricavi"),   # Ricavi vendite bar
        ("02.03.01", "passivo"),  # IVA a debito
    ]:
        conti.docs.append({"codice": codice, "categoria": categoria, "saldo": 0.0})

    async def _saldo(_db, codice, importo, verso):
        for d in conti.docs:
            if d["codice"] == codice:
                if d["categoria"] in ("attivo", "costi"):
                    d["saldo"] += importo if verso == "dare" else -importo
                else:
                    d["saldo"] += importo if verso == "avere" else -importo

    import app.routers.accounting.piano_conti as pcmod
    monkeypatch.setattr(pcmod, "aggiorna_saldo_conto", _saldo)
    return archivio


# Le quattro giornate vere, come stanno in archivio (fonte: chiusure
# giornaliere legacy). L'ultima e' il controllo in negativo: stessa forma,
# nessun non riscosso, gia' registrata prima di questa correzione.
GIORNATE = [
    # data, totale, cassa, pos, non riscosso, imponibile, iva
    ("2026-03-31", 3054.10, 641.10, 2408.00, 5.00, 2776.45, 277.65),
    ("2026-05-01", 5209.43, 1795.73, 3411.10, 2.60, 4735.85, 473.58),
    ("2026-07-30", 2539.90, 911.80, 1620.30, 7.80, 2309.00, 230.90),
    ("2026-03-30", 3212.50, 1101.10, 2111.40, 0.00, 2920.45, 292.05),
]


def _corrispettivo(giorno, totale, cassa, pos, non_riscosso, imponibile, iva):
    doc = {
        "id": f"corr-{giorno}", "data": giorno, "totale": totale,
        "pagato_contanti": cassa, "pagato_elettronico": pos,
        "totale_imponibile": imponibile, "totale_iva": iva,
    }
    if non_riscosso:
        doc["non_riscosso"] = non_riscosso
    return doc


@pytest.mark.parametrize(
    "giorno,totale,cassa,pos,non_riscosso,imponibile,iva",
    GIORNATE, ids=[g[0] for g in GIORNATE],
)
def test_la_giornata_entra_nel_giornale_e_quadra(
    db, giorno, totale, cassa, pos, non_riscosso, imponibile, iva
):
    esito = _run(motore.registra_corrispettivo(
        db, _corrispettivo(giorno, totale, cassa, pos, non_riscosso, imponibile, iva)))

    assert esito["stato"] == "registrato", (
        f"{giorno}: {esito.get('motivo')}. Una giornata da {totale:.2f} EUR "
        f"resta fuori dal libro giornale per {non_riscosso:.2f} EUR di "
        "sospesi."
    )
    mov = esito["movimento"]
    assert mov["totale_dare"] == pytest.approx(totale, abs=0.01)
    assert mov["totale_avere"] == pytest.approx(totale, abs=0.01)
    assert round(sum(r["dare"] for r in mov["righe"]), 2) == pytest.approx(
        round(sum(r["avere"] for r in mov["righe"]), 2), abs=0.01), (
        "Le righe non quadrano fra loro, anche se i totali dichiarati si'."
    )


def test_il_non_riscosso_va_sui_crediti_non_in_cassa_ne_in_banca(db):
    """Dove finisce conta quanto il fatto che quadri.

    Metterlo in cassa gonfierebbe il contante di un denaro che non c'e', e
    il conto cassa e' quello che si conta a mano la sera.
    """
    esito = _run(motore.registra_corrispettivo(db, _corrispettivo(*GIORNATE[0])))

    righe = {r["conto_codice"]: r["dare"] for r in esito["movimento"]["righe"] if r["dare"]}
    assert righe == {
        "01.01.01": pytest.approx(641.10, abs=0.01),   # Cassa: solo i contanti veri
        "01.01.02": pytest.approx(2408.00, abs=0.01),  # Banca: la quota POS
        "01.02.01": pytest.approx(5.00, abs=0.01),     # Crediti: il non riscosso
    }
    saldi = {d["codice"]: round(d["saldo"], 2) for d in db["piano_conti"].docs}
    assert saldi["01.01.01"] == pytest.approx(641.10, abs=0.01)
    assert saldi["01.02.01"] == pytest.approx(5.00, abs=0.01)


def test_senza_non_riscosso_la_scrittura_resta_com_era(db):
    """Il controllo in negativo: 147 giornate su 187 non hanno quel campo."""
    esito = _run(motore.registra_corrispettivo(db, _corrispettivo(*GIORNATE[3])))

    conti = {r["conto_codice"] for r in esito["movimento"]["righe"]}
    assert "01.02.01" not in conti, (
        "Una giornata senza sospesi non deve aprire una riga di credito a zero."
    )


def test_un_totale_che_non_quadra_nemmeno_col_non_riscosso_resta_da_verificare(db):
    """Il non riscosso e' una prova del documento, non un tappabuchi.

    Se fosse calcolato come `totale - cassa - pos`, qualunque giornata
    quadrerebbe sempre — e uno scarto vero (un incasso non registrato)
    sparirebbe dentro i crediti senza che nessuno lo veda.
    """
    esito = _run(motore.registra_corrispettivo(db, {
        "id": "corr-storto", "data": "2026-04-02", "totale": 100.0,
        "pagato_contanti": 10.0, "pagato_elettronico": 20.0,
        "non_riscosso": 5.0,  # ne mancano 65, non 5
        "totale_imponibile": 90.91, "totale_iva": 9.09,
    }))

    assert esito["stato"] == "da_verificare"
    assert db["movimenti_contabili"].docs == []


def test_un_non_riscosso_negativo_non_diventa_un_avere_mascherato(db):
    """Un DARE negativo e' un AVERE: quadrerebbe togliendo ricavo."""
    esito = _run(motore.registra_corrispettivo(db, {
        "id": "corr-negativo", "data": "2026-04-02", "totale": 100.0,
        "pagato_contanti": 60.0, "pagato_elettronico": 50.0,
        "non_riscosso": -10.0,
        "totale_imponibile": 90.91, "totale_iva": 9.09,
    }))

    assert esito["stato"] == "da_verificare"
    assert db["movimenti_contabili"].docs == []


def test_il_conto_dei_crediti_e_gia_mappato_al_piano_cee():
    """Qui non si apre un conto nuovo: si usa quello che c'era gia'.

    CLAUDE.md: «solo CEE ufficiale... un conto fuori tabella viene rifiutato
    dal motore». Se domani qualcuno togliesse `01.02.01` dalla mappatura, la
    scrittura finirebbe in un conto che il bilancio non sa dove mettere.
    """
    from app.services.mapping_piano_conti import OPERATIVO_A_UFFICIALE
    from app.services.piano_conti_ufficiale import CONTI_UFFICIALI

    codice = motore._C_CREDITI[0]
    assert codice in OPERATIVO_A_UFFICIALE, (
        f"{codice} non e' mappato al piano CEE"
    )
    assert OPERATIVO_A_UFFICIALE[codice] in CONTI_UFFICIALI
