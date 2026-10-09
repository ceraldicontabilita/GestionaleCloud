"""
test_prodotti_master_spazzatura.py
───────────────────────────────────
Regression test per il fix del 01/07/2026 in prodotti_master.py: righe
amministrative/legali venivano promosse a "prodotto" (nome_canonico non
atomico), inquinando il catalogo ordinabile e i controlli-dati
"prodotti_senza_prezzo"/"prodotti_senza_fornitore".

Le stringhe "reali" sono prese dai campioni live di GET /controllo-dati/overview
il 01/07/2026 (nessun valore inventato). Copre anche il bug di normalizzazione:
_RX_NON_ORDINABILI richiedeva spazio letterale tra le parole, quindi varianti con
trattino ("Spese-Gestione-Incasso") sfuggivano al filtro nonostante il pattern
"spese gestione incasso" fosse già presente.
"""
import re

from app.lotti.routers.prodotti_master import _RX_NON_ORDINABILI

_RX = re.compile(_RX_NON_ORDINABILI, re.IGNORECASE)


def test_testo_legale_fattura_escluso():
    # campione live: prodotto senza prezzo, in realtà un rigo di legge (art. 62
    # D.L. 1/2012 su pagamenti filiera agroalimentare), non un ingrediente.
    nome = (
        "Assolve Gli Obblighi Di Cui All'Articolo 62, Comma 1, Del Decreto "
        "Legge 24 Gennaio 2012, N. 1, Convertito Con Modificazi"
    )
    assert _RX.search(nome)


def test_righe_acconto_storno_escluse():
    assert _RX.search("- A Detrarre Ns.Ft.Acconto N.9 Del 21/1/26")
    assert _RX.search("A Detrarre Ft Di Acconto Ft 25 Del 23/12/2025")
    assert _RX.search("Storno Sconti")
    assert _RX.search("Colli Peso")


def test_separatore_flessibile_trattino():
    # stesso pattern "spese gestione incasso" già presente prima del fix, ma
    # con trattini al posto degli spazi: prima del fix NON veniva escluso.
    assert _RX.search("Spese-Gestione-Incasso")
    assert _RX.search("Spese_Gestione_Incasso")
    assert _RX.search("Spese Gestione Incasso")


def test_classificatore_righe_leasing_e_ausiliarie():
    # Pattern aggiunti il 02/07/2026 (richiesta Enzo: mai cercare sul web queste
    # righe): targhe auto compatte del leasing, righe ausiliarie, articolo vario,
    # cauzioni. Verificati su 3.694 righe fattura reali: 38 match, tutti non-food.
    from app.lotti.routers.classificatore_alimenti import e_non_food_certo

    assert e_non_food_certo("GG782PN STELVIO 2.2 Turbo Diesel 190CV Sprint AT")
    assert e_non_food_certo("GW980EP Canone di Locazione")
    assert e_non_food_certo("ARTICOLO VARIO")
    assert e_non_food_certo("Riga ausiliaria contenente informazioni tecniche e aggiuntive del documento")
    assert e_non_food_certo("Cauzioni addebito")
    # ...ma le sigle-confezione con spazi NON devono matchare come targa
    assert not e_non_food_certo("ZUCCHERO A VELO x 5kg")
    assert not e_non_food_certo("RICOTTA TIPO ROMA")
    assert not e_non_food_certo("KIMBO EXTREME 1kg GRANI")


def test_detersivi_riconosciuti_per_scheda_sicurezza():
    # Richiesta Enzo 02/07/2026: i detersivi devono avere la scheda di SICUREZZA
    # (principi attivi, pericoli) per l'HACCP — RX_DETERSIVI li instrada alla
    # ricerca web con prompt dedicato, restando FUORI dai cataloghi alimentari.
    from app.lotti.routers.classificatore_alimenti import RX_DETERSIVI, e_non_food_certo

    for nome in ["ACE CANDEGGINA 3LT CLASSICA", "BIG MATIK DETERG.LAVASTOV.PROF.6KG",
                 "CHANTECLAIR SGRASSATORE", "AMUCHINA SPRAY 750ML SENZA RISCIACQUO IG",
                 "DERMOMED SAPONE 1LT"]:
        assert RX_DETERSIVI.search(nome), nome
        assert e_non_food_certo(nome), nome
    # ...ma l'ammoniaca PER DOLCI (E503) è materia prima di pasticceria
    assert not RX_DETERSIVI.search("AMMONIACA (BICARBONATO DI AMMONIO) E503 KG1")
    for nome in ["Farina 00", "Burro", "DATTERI SIRIA KG1", "ACQUA LETE CL.33"]:
        assert not RX_DETERSIVI.search(nome), nome


def test_nessun_falso_positivo_su_ingredienti_veri():
    # deve restare atomico e ordinabile: nessuna parola spazzatura è substring
    # di questi nomi reali (in particolare "vite "/"viti " non deve matchare
    # parole che iniziano allo stesso modo, es. "Vitello"/"Vitamina").
    for nome in [
        "Farina 00", "Margarina", "Burro", "Panna Fresca", "Uova Fresche Cat.A",
        "Falanghina Sannio Taburno", "Aglianico Taburno Rosso",
        "Vitello Tonnato", "Vitamina C in polvere",
    ]:
        assert not _RX.search(nome), f"falso positivo su ingrediente vero: {nome!r}"
