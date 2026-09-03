"""Motore CCNL: livelli, minimi retributivi e conversioni.

A cosa serve
------------
La generazione dei contratti sapeva gia' riempire i template .docx, ma i valori
economici andavano scritti a mano: nessuna tabella diceva quanto vale un livello.
Qui stanno le tabelle ufficiali e le due domande che l'anagrafica deve poter fare:

    livello  -> quanto gli spetta      (retribuzione_per_livello)
    importo  -> che livello e'         (suggerisci_livello)

Da dove vengono i numeri
------------------------
CCNL Terziario, Distribuzione e Servizi (CNEL H011), Confcommercio / Filcams
Cgil / Fisascat Cisl / Uiltucs Uil: tabelle prese dall'informativa D.Lgs.
152/1997 fornita dall'azienda (accordo di rinnovo 22 marzo 2024, scadenza
31 marzo 2027). Ogni riga e' verificata: contingenza + minimo = retribuzione.

ATTENZIONE — nessun numero e' inventato. I CCNL di cui non abbiamo il testo
ufficiale sono dichiarati con `tabelle_caricate = False` e le funzioni si
rifiutano di calcolare: meglio un errore esplicito che una busta paga sbagliata.
"""
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------
# Tabelle
# --------------------------------------------------------------------------
# Per ogni livello: (contingenza+EDR, minimo contrattuale, retribuzione mensile)
_TERZIARIO_LIVELLI = {
    "Q":  (540.37, 2070.25, 2610.62),
    "1":  (537.52, 1864.88, 2402.40),
    "2":  (532.54, 1613.11, 2145.65),
    "3":  (527.90, 1378.78, 1906.68),
    "4":  (524.22, 1192.46, 1716.68),
    "5":  (521.94, 1077.35, 1599.29),
    "6":  (519.76,  967.22, 1486.98),
    "7":  (517.51,  828.08, 1345.59),
}

_TERZIARIO_DESCRIZIONI = {
    "Q": "Quadri: funzioni direttive con poteri di discrezionalita' decisionale.",
    "1": "Impiegati con funzioni ad alto contenuto professionale e direzione esecutiva.",
    "2": "Impiegati di concetto con compiti autonomi, coordinamento e controllo.",
    "3": "Impiegati di concetto; operai specializzati provetti.",
    "4": "Impiegati con compiti operativi anche di vendita; operai con conoscenze tecniche.",
    "5": "Impiegati e operai che eseguono lavori qualificati.",
    "6": "Operai con semplici conoscenze pratiche.",
    "7": "Operai adibiti a mansioni di pulizia o equivalenti.",
}

# Scatti di anzianita': importo mensile per scatto (massimo 10, cadenza triennale)
_TERZIARIO_SCATTI = {
    "Q": 25.46, "1": 24.84, "2": 22.83, "3": 21.95,
    "4": 20.66, "5": 20.30, "6": 19.73, "7": 19.47,
}

# Periodo di prova per livello
_TERZIARIO_PROVA = {
    "Q": "6 mesi di calendario", "1": "6 mesi di calendario",
    "2": "60 giorni di lavoro effettivo", "3": "60 giorni di lavoro effettivo",
    "4": "60 giorni di lavoro effettivo", "5": "60 giorni di lavoro effettivo",
    "6": "45 giorni di lavoro effettivo", "7": "45 giorni di lavoro effettivo",
}

# --------------------------------------------------------------------------
# CCNL Pubblici Esercizi / Turismo (H05Y) — e' il contratto del bar e della
# pasticceria. Stessa struttura: (paga base + contingenza = totale mensile).
# I valori erano gia' nel frontend (CCNL_LIVELLI_2026): qui diventano l'unica
# fonte, cosi' non esistono due tabelle da tenere allineate a mano.
# --------------------------------------------------------------------------
_TURISMO_LIVELLI = {
    "QA": (542.70, 1920.26, 2462.96),
    "QB": (537.59, 1734.02, 2271.61),
    "1":  (536.71, 1570.97, 2107.68),
    "2":  (531.59, 1384.76, 1916.35),
    "3":  (528.26, 1272.47, 1800.73),
    "4":  (524.94, 1167.75, 1692.69),
    "5":  (522.37, 1057.72, 1580.09),
    "6S": (520.64,  994.19, 1514.83),
    "6":  (520.51,  971.06, 1491.57),
    "7":  (518.45,  871.75, 1390.20),
}

_TURISMO_MANSIONI = {
    "QA": "Quadri direttivi.",
    "QB": "Quadri.",
    "1":  "Direttore, capo servizi.",
    "2":  "Capo cuoco, capo barista.",
    "3":  "Cuoco unico, primo pasticciere, barman unico.",
    "4":  "Cuoco tavola calda/capo partita, secondo pasticciere, rosticciere, barman.",
    "5":  "Barista, cameriere (anche tavola calda), banconiere pasticceria/gelateria.",
    "6S": "Operai qualificati super.",
    "6":  "Commis cucina/sala/bar, secondo banconiere pasticceria.",
    "7":  "Personale di fatica / primo ingresso.",
}

# Divisore orario per orario settimanale contrattuale
_DIVISORI_ORARI = {40: 168, 42: 182, 45: 195}
DIVISORE_GIORNALIERO = 26

CCNL = {
    "terziario": {
        "id": "terziario",
        "nome": "Terziario, Distribuzione e Servizi",
        "codice_cnel": "H011",
        "parti": "Confcommercio · Filcams Cgil · Fisascat Cisl · Uiltucs Uil",
        "stipula": "2024-03-22",
        "scadenza": "2027-03-31",
        "fonte": "Informativa D.Lgs. 152/1997 aziendale (accordo di rinnovo 22/03/2024)",
        "tabelle_caricate": True,
        "livelli": _TERZIARIO_LIVELLI,
        "descrizioni": _TERZIARIO_DESCRIZIONI,
        "scatti": _TERZIARIO_SCATTI,
        "periodo_prova": _TERZIARIO_PROVA,
        "ore_settimanali_std": 40,
        "divisore_orario": 168,
        "ferie_giorni": 26,
        "mensilita": 14,
        "terzo_elemento": 11.36,          # mensile, per 14 mensilita', tutti i livelli
        "maggiorazioni": {
            "straordinario_41_48": 0.15,
            "straordinario_oltre_48": 0.20,
            "straordinario_festivo": 0.30,
            "straordinario_notturno": 0.50,
            "supplementare": 0.35,
        },
    },
    # I due CCNL richiesti per bar/pasticceria. Le tabelle NON sono nel materiale
    # fornito: finche' non arrivano, l'anagrafica puo' elencarli ma i calcoli si
    # fermano con un errore esplicito.
    "turismo_pubblici_esercizi": {
        "id": "turismo_pubblici_esercizi",
        "nome": "Pubblici Esercizi, Ristorazione e Turismo",
        "codice_cnel": "H05Y",
        "parti": "Fipe/Confcommercio · Filcams Cgil · Fisascat Cisl · Uiltucs Uil",
        "stipula": "2024-06-05",
        "fonte": "Minimi Confcommercio-FIPE, rinnovo 05/06/2024, terza tranche dal "
                 "01/06/2026 (fonte Confcommercio Milano). Da ricontrollare a ogni rinnovo.",
        "tabelle_caricate": True,
        "livelli": _TURISMO_LIVELLI,
        "descrizioni": _TURISMO_MANSIONI,
        "scatti": {},              # scatti non caricati: restano a zero
        "periodo_prova": {},
        "ore_settimanali_std": 40,
        "divisore_orario": 172,   # ricavato dalle buste, non da manuale
        "ferie_giorni": 26,
        "mensilita": 14,
        "terzo_elemento": 0.0,
    },
    # Tenuto solo come promemoria: in Ceraldi Group la pasticceria e' inquadrata
    # nel Turismo (il pasticciere sta al 3º/4º di quella tabella), quindi questo
    # contratto non serve. Servirebbe se l'attivita' passasse a impresa artigiana
    # iscritta all'albo — e allora andrebbe scelto fra le quattro varianti
    # esistenti (Confartigianato/CNA/Casartigiani/CLAAI, Confsal-Conflavoro,
    # Confsal-Unilavoro, e quella 2024 per le imprese sotto i 15 dipendenti),
    # che hanno minimi diversi fra loro.
    "panificazione_pasticceria": {
        "id": "panificazione_pasticceria",
        "nome": "Panificazione e Pasticceria (artigianato)",
        "codice_cnel": "",
        "parti": "",
        "tabelle_caricate": False,
        "livelli": {},
        "nota": "Non applicato in azienda: la pasticceria e' inquadrata nel CCNL "
                "Turismo. Da caricare solo se il consulente del lavoro indica un "
                "CCNL artigiano, precisando quale delle varianti esistenti.",
    },
}

# Il contratto realmente applicato in azienda e' il Turismo/Pubblici Esercizi,
# non il Terziario: nei Libri Unici la voce CONTING. vale 536,71 (1º), 524,94
# (4º) e 520,51 (6º), che sono esattamente i valori della tabella Turismo e non
# corrispondono a nessun livello del Terziario. Verificato su 45 LUL, 85
# occorrenze, zero corrispondenze col Terziario.
CCNL_DEFAULT = "turismo_pubblici_esercizi"


class CCNLNonDisponibile(Exception):
    """Il CCNL esiste in anagrafica ma non abbiamo le sue tabelle retributive."""


# --------------------------------------------------------------------------
# Helper
# --------------------------------------------------------------------------
def _get(ccnl_id: Optional[str]) -> Dict[str, Any]:
    c = CCNL.get((ccnl_id or CCNL_DEFAULT).strip().lower())
    if not c:
        raise CCNLNonDisponibile(f"CCNL sconosciuto: {ccnl_id!r}")
    return c


def _norm_livello(livello: Any) -> str:
    """Riporta alla chiave di tabella le mille grafie dei documenti.

    '3', '3°', 'III' -> '3' · 'Quadro A', 'q a' -> 'QA' · '6° S', 'VI S' -> '6S'
    """
    s = str(livello or "").strip().upper()
    for ch in ("°", "º", "^", "."):
        s = s.replace(ch, "")
    s = " ".join(s.split())
    if s.startswith("QUADRO"):
        coda = s.replace("QUADRO", "").strip()
        return ("Q" + coda) if coda in ("A", "B") else "Q"
    romani = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6", "VII": "7"}
    parti = s.split()
    if len(parti) == 2 and parti[1] == "S":                 # '6 S' / 'VI S'
        return romani.get(parti[0], parti[0]) + "S"
    s = s.replace(" ", "")
    if s.endswith("S") and len(s) > 1:                      # '6S' / 'VIS'
        base = s[:-1]
        return romani.get(base, base) + "S"
    return romani.get(s, s)


def divisore_orario(ore_settimanali: Any, ccnl_id: Optional[str] = None) -> int:
    """Divisore per il calcolo della quota oraria.

    Non e' lo stesso per tutti i contratti: il Terziario usa 168 per le 40 ore,
    il Turismo 172. Il 172 non e' preso da un manuale ma ricavato dalle buste
    Ceraldi: la contingenza mensile di tabella diviso quella oraria stampata sul
    cedolino da' 172 su 115 buste su 115.
    """
    try:
        ore = int(round(float(ore_settimanali)))
    except (TypeError, ValueError):
        ore = 40
    base = (CCNL.get(ccnl_id or CCNL_DEFAULT) or {}).get("divisore_orario", 168)
    if base == 168 and ore in _DIVISORI_ORARI:
        return _DIVISORI_ORARI[ore]
    return base if ore == 40 else max(1, int(round(ore * base / 40)))


def lista_ccnl() -> List[Dict[str, Any]]:
    return [{"id": c["id"], "nome": c["nome"], "codice_cnel": c.get("codice_cnel", ""),
             "tabelle_caricate": c["tabelle_caricate"], "nota": c.get("nota", ""),
             "livelli": sorted(c["livelli"].keys(), key=_ordine_livello)}
            for c in CCNL.values()]


def _ordine_livello(l: str) -> tuple:
    """Dal piu' alto al piu' basso: quadri, poi i numeri, col 'super' prima del
    livello pieno di pari numero (6S viene prima di 6)."""
    if l in ("Q", "QA"):
        return (0, 0, 0)
    if l == "QB":
        return (0, 1, 0)
    base, sup = (l[:-1], 0) if l.endswith("S") else (l, 1)
    return (1, int(base), sup) if base.isdigit() else (2, 0, 0)


# --------------------------------------------------------------------------
# livello -> retribuzione
# --------------------------------------------------------------------------
def retribuzione_per_livello(livello: Any, ccnl_id: Optional[str] = None,
                             ore_settimanali: Any = None, scatti: int = 0) -> Dict[str, Any]:
    """Quanto spetta a un livello: mensile, giornaliera e oraria.

    Il part-time e' riproporzionato sulle ore rispetto all'orario pieno del CCNL.
    `scatti` e' il numero di scatti di anzianita' maturati (il CCNL ne prevede
    al massimo 10, e oltre quel tetto non maturano piu').
    """
    c = _get(ccnl_id)
    if not c["tabelle_caricate"]:
        raise CCNLNonDisponibile(c.get("nota") or f"Tabelle non caricate per {c['nome']}")
    lv = _norm_livello(livello)
    if lv not in c["livelli"]:
        raise CCNLNonDisponibile(f"Livello {livello!r} non previsto dal CCNL {c['nome']}")

    contingenza, minimo, retribuzione = c["livelli"][lv]
    std = c["ore_settimanali_std"]
    ore = float(ore_settimanali) if ore_settimanali else std
    quota = min(1.0, ore / std) if std else 1.0

    n_scatti = max(0, min(int(scatti or 0), 10))
    imp_scatti = round(c["scatti"].get(lv, 0.0) * n_scatti, 2)

    mensile_pieno = retribuzione + imp_scatti + c.get("terzo_elemento", 0.0)
    mensile = round(mensile_pieno * quota, 2)
    div_ore = divisore_orario(ore if ore in _DIVISORI_ORARI else std, c["id"])

    return {
        "ccnl": c["id"], "ccnl_nome": c["nome"], "livello": lv,
        "descrizione": c.get("descrizioni", {}).get(lv, ""),
        "contingenza_edr": contingenza,
        "minimo_contrattuale": minimo,
        "retribuzione_tabellare": retribuzione,
        "scatti_numero": n_scatti,
        "scatti_importo": imp_scatti,
        "terzo_elemento": c.get("terzo_elemento", 0.0),
        "ore_settimanali": ore,
        "part_time": quota < 1.0,
        "percentuale_part_time": round(quota * 100, 1),
        "mensile_lordo": mensile,
        "giornaliera": round(mensile / DIVISORE_GIORNALIERO, 2),
        "oraria": round(mensile_pieno / div_ore, 2),
        "mensilita": c.get("mensilita", 14),
        "annuo_lordo": round(mensile * c.get("mensilita", 14), 2),
        "ferie_giorni": c.get("ferie_giorni"),
        "periodo_prova": c.get("periodo_prova", {}).get(lv, ""),
    }


# --------------------------------------------------------------------------
# importo -> livello
# --------------------------------------------------------------------------
def suggerisci_livello(importo_mensile: Any, ccnl_id: Optional[str] = None,
                       ore_settimanali: Any = None) -> Dict[str, Any]:
    """Dato quanto si vuole pagare, quale livello ci corrisponde.

    Restituisce il livello piu' vicino e la classifica completa per scarto, cosi'
    in anagrafica si vede anche la seconda scelta. `sotto_minimo` segnala quando
    l'importo non raggiunge nemmeno il livello piu' basso: e' il caso che va
    fermato prima di firmare, non dopo.
    """
    c = _get(ccnl_id)
    if not c["tabelle_caricate"]:
        raise CCNLNonDisponibile(c.get("nota") or f"Tabelle non caricate per {c['nome']}")
    try:
        importo = float(str(importo_mensile).replace(",", "."))
    except (TypeError, ValueError):
        raise CCNLNonDisponibile(f"Importo non valido: {importo_mensile!r}")

    candidati = []
    for lv in sorted(c["livelli"], key=_ordine_livello):
        r = retribuzione_per_livello(lv, c["id"], ore_settimanali)
        scarto = importo - r["mensile_lordo"]
        candidati.append({
            "livello": lv,
            "descrizione": r["descrizione"],
            "mensile_lordo": r["mensile_lordo"],
            "giornaliera": r["giornaliera"],
            "oraria": r["oraria"],
            "scarto": round(scarto, 2),
            "scarto_percentuale": round(scarto / r["mensile_lordo"] * 100, 1) if r["mensile_lordo"] else 0.0,
        })

    per_vicinanza = sorted(candidati, key=lambda x: abs(x["scarto"]))
    migliore = per_vicinanza[0]
    piu_basso = min(candidati, key=lambda x: x["mensile_lordo"])

    return {
        "ccnl": c["id"], "ccnl_nome": c["nome"],
        "importo_richiesto": round(importo, 2),
        "ore_settimanali": float(ore_settimanali) if ore_settimanali else c["ore_settimanali_std"],
        "livello_suggerito": migliore["livello"],
        "scarto": migliore["scarto"],
        "copre_il_minimo": migliore["scarto"] >= 0,
        "sotto_minimo": importo < piu_basso["mensile_lordo"],
        "minimo_assoluto": piu_basso["mensile_lordo"],
        "giornaliera": migliore["giornaliera"],
        "oraria": migliore["oraria"],
        "classifica": per_vicinanza,
    }
