"""Detergenti e frequenze: i dati che stavano scritti dentro il manuale.

Il manuale HACCP (`routers/manuale_haccp_testi.py`) portava gia' due tabelle —
i prodotti da usare, con pH, diluizione e tempo di contatto, e ogni quanto si
lava ciascuna area — ma scritte a mano dentro l'HTML. Da li' si potevano
stampare e basta: il piano di sanificazione non poteva leggerle, e chi
compilava il piano riscriveva a memoria quello che il manuale gia' diceva.

Qui quelle tabelle diventano dati. Il manuale continua a stamparle, ma
generandole da qui: una sola copia, e correggere il pH di un prodotto non
lascia piu' il manuale a dire una cosa e il piano un'altra.

**Niente e' stato aggiunto.** I prodotti sono per TIPOLOGIA, come nel manuale
(«detergente sgrassante alcalino», non un nome commerciale): il nome della
marca lo scrive il responsabile nel piano, perche' e' quello che rimanda alla
scheda di sicurezza vera, e non e' una cosa che si indovina.

Le frequenze restano un **suggerimento**: il manuale parla di «frigoriferi» e
«piani di lavoro», il registro di «Attrezzature Laboratorio» e «Montacarichi».
Dove le due cose coincidono senza forzature il piano lo propone; dove il
manuale non dice niente — montacarichi, deposito — non propone niente.
"""

# ── I prodotti, dal capitolo «Detergenti e sanificanti» del manuale ─────────
# Ogni voce: che cos'e', a cosa serve, e le condizioni d'uso quando il manuale
# le dichiara. `diluizione` e `tempo_contatto` vuoti = il manuale non li da'
# per quel prodotto, e il responsabile li prende dall'etichetta.
DETERGENTI = [
    {
        "id": "detergente_neutro",
        "nome": "Detergente neutro",
        "caratteristica": "pH 6-8",
        "utilizzo": "Pulizia quotidiana superfici, pavimenti",
        "diluizione": "",
        "tempo_contatto": "",
        "note": "Non aggredisce le superfici, adatto per uso frequente",
    },
    {
        "id": "sgrassante_alcalino",
        "nome": "Detergente sgrassante alcalino",
        "caratteristica": "pH 9-12",
        "utilizzo": "Rimozione grassi, oli, residui carboniosi",
        "diluizione": "",
        "tempo_contatto": "",
        "note": "Per forni, cappe, friggitrici. Risciacquare bene",
    },
    {
        "id": "detergente_acido",
        "nome": "Detergente acido",
        "caratteristica": "pH 1-5",
        "utilizzo": "Rimozione calcare, incrostazioni minerali",
        "diluizione": "",
        "tempo_contatto": "",
        "note": "Per lavastoviglie, caffettiere. Non miscelare con candeggina",
    },
    {
        "id": "cloro",
        "nome": "Disinfettante a base di cloro",
        "caratteristica": "ipoclorito di sodio",
        "utilizzo": "Sanificazione superfici, stoviglie",
        "diluizione": "1-2%",
        "tempo_contatto": "5-10 minuti",
        "note": "",
    },
    {
        "id": "alcol",
        "nome": "Disinfettante a base di alcol",
        "caratteristica": "≥70%",
        "utilizzo": "Sanificazione rapida superfici",
        "diluizione": "",
        "tempo_contatto": "",
        "note": "Azione immediata, evapora senza risciacquo",
    },
    {
        "id": "quaternari",
        "nome": "Disinfettante quaternari d'ammonio",
        "caratteristica": "",
        "utilizzo": "Sanificazione attrezzature",
        "diluizione": "",
        "tempo_contatto": "",
        "note": "Buona compatibilita' con metalli, bassa corrosivita'",
    },
    {
        "id": "sapone_mani",
        "nome": "Sapone mani neutro",
        "caratteristica": "",
        "utilizzo": "Igiene mani personale",
        "diluizione": "",
        "tempo_contatto": "",
        "note": "Da dispenser, senza profumazione intensa",
    },
    {
        "id": "gel_mani",
        "nome": "Gel igienizzante mani",
        "caratteristica": "alcol ≥60%",
        "utilizzo": "Igienizzazione mani quando acqua non disponibile",
        "diluizione": "",
        "tempo_contatto": "",
        "note": "Non sostituisce il lavaggio con acqua e sapone",
    },
]

REGOLE_UTILIZZO = [
    "Leggere sempre l'etichetta e la scheda di sicurezza",
    "Rispettare le diluizioni indicate dal produttore",
    "Non miscelare MAI prodotti diversi (reazioni pericolose)",
    "Conservare in contenitori originali, separati dagli alimenti",
    "Utilizzare DPI appropriati (guanti, occhiali se necessario)",
    "Risciacquare abbondantemente dopo l'uso",
    "Conservare le schede di sicurezza accessibili",
]

# ── Ogni quanto, dalla tabella «Frequenza sanificazione» del manuale ────────
FREQUENZE_MANUALE = [
    ("Piani di lavoro", "Dopo ogni utilizzo + fine giornata"),
    ("Utensili, taglieri", "Dopo ogni utilizzo"),
    ("Frigoriferi", "Ogni 7-10 giorni"),
    ("Congelatori", "Ogni 7-10 giorni"),
    ("Pavimenti", "Giornaliera"),
    ("Pareti, scaffali", "Settimanale"),
    ("Cappe, filtri", "Settimanale"),
    ("Forni", "Dopo ogni utilizzo intensivo"),
]

# Dove un'area del registro corrisponde senza forzature a una riga del manuale.
# La chiave e' l'area del registro, il valore la frequenza del piano.
# Montacarichi e Deposito NON ci sono: il manuale non ne parla, e una
# frequenza inventata su un manuale HACCP vale meno di una casella vuota.
FREQUENZA_SUGGERITA = {
    "Pavimentazione": ("giornaliera", "Pavimenti — «Giornaliera»"),
    "Tagliere, Coltelli": ("dopo_ogni_uso", "Utensili, taglieri — «Dopo ogni utilizzo»"),
}


def detergente(identificativo: str) -> dict:
    """Il prodotto per id, o None. Serve a validare quello scelto nel piano."""
    for voce in DETERGENTI:
        if voce["id"] == identificativo:
            return voce
    return None
