"""Stati e vocabolari dell'associazione bonifico <-> dipendente: punto unico.

CLAUDE.md, «Personale» e «Identita', prove e attese»: nessuna entita' si
associa per solo importo, un candidato non si applica mai, e quello che il
titolare ha confermato a mano non lo riassegna piu' nessun motore automatico.

Tre famiglie di costanti, tutte usate da piu' moduli:

* la **conferma manuale** (``confermato_manuale`` sul bonifico);
* i **candidati** della coda «Bonifici da associare» (prove, avvisi);
* il **riscontro** di una busta (stato, confidenza, fonte), con la mappa verso
  ``stato_bonifico`` / ``stato_pagamento`` dell'archivio.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

# ── stato del mese (``paghe_mensili.stato_pagamento``) ──────────────────────
#: Nessuna busta e nessun pagamento.
STATO_PAGA_VUOTO = "vuoto"
#: La busta c'e', il pagamento no.
STATO_PAGA_IN_ATTESA_PAGAMENTO = "in_attesa_pagamento"
#: Il bonifico c'e', la busta non e' ancora arrivata (titolare, 02/10/2026):
#: ``importo_busta`` resta assente, mai 0; all'arrivo della busta
#: (``sincronizza_paghe_mensili``) il pagamento si aggancia da solo.
STATO_PAGA_IN_ATTESA_BUSTA = "in_attesa_busta"
STATO_PAGA_PARZIALE = "parziale"
STATO_PAGA_PAGATO = "pagato"
#: Stati con un residuo da pagare (pannelli «buste in attesa»).
STATI_PAGA_APERTI = (STATO_PAGA_IN_ATTESA_PAGAMENTO, STATO_PAGA_PARZIALE)


def stato_paga_mese(busta: Optional[Decimal], erogato: Decimal) -> str:
    """Lo stato di un mese dal confronto busta ↔ erogato, **al centesimo**:
    nessuna tolleranza (titolare, 02/10/2026; prima 0,50 € di comodo).
    ``busta`` ``None`` = busta non ancora in archivio (non e' uno zero)."""
    if busta is None:
        return STATO_PAGA_IN_ATTESA_BUSTA if erogato > 0 else STATO_PAGA_VUOTO
    if busta <= 0 and erogato <= 0:
        return STATO_PAGA_VUOTO
    if erogato <= 0:
        return STATO_PAGA_IN_ATTESA_PAGAMENTO
    if erogato >= busta:
        return STATO_PAGA_PAGATO
    return STATO_PAGA_PARZIALE


# ── conferma manuale ─────────────────────────────────────────────────────────
#: Il titolare ha associato questo bonifico a mano: nessun motore lo riassegna,
#: e per gli altri dipendenti e' gia' consumato.
CAMPO_CONFERMATO = "confermato_manuale"
CAMPO_CONFERMATO_DA = "confermato_da"
CAMPO_CONFERMATO_IL = "confermato_il"

#: Campi con cui un bonifico si riconosce fra collezioni diverse (riga in coda,
#: esito HR, movimento d'estratto, ricevuta): il riferimento banca «MB…», il CRO
#: e l'impronta del PDF, poi gli id dei documenti del gestionale da cui nasce.
CHIAVI_IDENTITA_BONIFICO = (
    "rif_banca", "cro", "hash", "gestionale_movimento_id", "gestionale_transfer_id",
)


def e_confermato_manuale(riga) -> bool:
    """Vero solo per ``True`` esplicito: un campo assente non e' una conferma."""
    return bool(riga) and riga.get(CAMPO_CONFERMATO) is True


# ── candidati della coda ─────────────────────────────────────────────────────
MAX_CANDIDATI = 10
#: Cambia quando cambia il modo di calcolarli: le righe salvate con un'altra
#: versione si ricalcolano alla lettura.
VERSIONE_CANDIDATI = 1
#: Oltre questa eta' (secondi) i candidati salvati si ricalcolano (buste e
#: residui cambiano quando arriva un altro pagamento).
ETA_MASSIMA_CANDIDATI_SECONDI = 300

PROVA_CF = "cf"
PROVA_NOME_COMPLETO = "nome_completo"
PROVA_COGNOME_IMPORTO = "cognome_importo_residuo"
PROVA_COGNOME_UNIVOCO = "cognome_univoco"
PROVA_COGNOME_CONDIVISO = "cognome_condiviso"
PROVA_IMPORTO_PERIODO = "importo_periodo_causale"

#: Forza della prova (0-100): identita' scritta > cognome + importo al
#: centesimo sul residuo > importo con periodo dichiarato in causale. L'importo
#: da solo non e' mai una prova: senza periodo in causale non produce candidati.
PUNTEGGI_PROVA = {
    PROVA_CF: 100,
    PROVA_NOME_COMPLETO: 90,
    PROVA_COGNOME_IMPORTO: 70,
    PROVA_IMPORTO_PERIODO: 50,
    PROVA_COGNOME_UNIVOCO: 40,
    PROVA_COGNOME_CONDIVISO: 30,
}
PROVE_TESTO = {
    PROVA_CF: "codice fiscale nella causale",
    PROVA_NOME_COMPLETO: "nome e cognome nella causale",
    PROVA_COGNOME_IMPORTO: "cognome nella causale e importo uguale al residuo della busta",
    PROVA_IMPORTO_PERIODO: "importo uguale al residuo della busta del periodo scritto in causale",
    PROVA_COGNOME_UNIVOCO: "cognome nella causale, senza importo uguale al residuo",
    PROVA_COGNOME_CONDIVISO: "cognome condiviso da piu' dipendenti: scegli tu",
}
#: Le prove abbastanza forti da diventare la ``proposta`` unica.
PROVE_DA_PROPOSTA = (PROVA_CF, PROVA_NOME_COMPLETO, PROVA_COGNOME_IMPORTO)

# ── avviso multi-dipendente ──────────────────────────────────────────────────
AVVISO_COGNOME_CONDIVISO = "cognome_condiviso"
AVVISO_STESSO_IMPORTO_PIU_BUSTE = "stesso_importo_piu_buste"
AVVISO_BENEFICIARI_VARI = "beneficiari_vari"
AVVISO_NOTA_DI_TERZI = "nota_di_terzi"
#: In ordine di priorita': il primo che vale e' quello mostrato.
AVVISI_MULTI_DIPENDENTE = (
    AVVISO_NOTA_DI_TERZI,
    AVVISO_BENEFICIARI_VARI,
    AVVISO_COGNOME_CONDIVISO,
    AVVISO_STESSO_IMPORTO_PIU_BUSTE,
)
AVVISI_TESTO = {
    AVVISO_NOTA_DI_TERZI: "La nota nomina una persona ma la distinta puo' pagare piu' dipendenti",
    AVVISO_BENEFICIARI_VARI: "Bonifico cumulativo «beneficiari vari»: puo' pagare piu' dipendenti",
    AVVISO_COGNOME_CONDIVISO: "Cognome condiviso da piu' dipendenti",
    AVVISO_STESSO_IMPORTO_PIU_BUSTE: "Lo stesso importo compare in piu' buste",
}

# ── riscontro di una busta ───────────────────────────────────────────────────
RISCONTRO_CONFERMATO = "confermato"
RISCONTRO_DA_VERIFICARE = "da_verificare"
RISCONTRO_DIFFERENZA = "differenza"
RISCONTRO_NESSUN_BONIFICO = "nessun_bonifico_trovato"
RISCONTRO_NON_RISCONTRABILE = "non_riscontrabile"
STATI_RISCONTRO = (
    RISCONTRO_CONFERMATO, RISCONTRO_DA_VERIFICARE, RISCONTRO_DIFFERENZA,
    RISCONTRO_NESSUN_BONIFICO, RISCONTRO_NON_RISCONTRABILE,
)

CONFIDENZA_ALTA_CAUSALE = "alta_causale_esplicita"
CONFIDENZA_MEDIA_IMPORTO = "media_importo_su_singolo_bonifico"

FONTE_MANUALE = "manuale"
FONTE_RICEVUTA = "ricevuta"
FONTE_ESTRATTO = "estratto"
#: Priorita' delle fonti: la conferma del titolare vince sulla ricevuta del
#: singolo bonifico, che vince sull'estratto conto.
PRIORITA_FONTI = (FONTE_MANUALE, FONTE_RICEVUTA, FONTE_ESTRATTO)

#: Prima di questa data non c'e' ne' l'estratto ufficiale ne' il CSV: la busta
#: non e' riscontrabile (non e' «senza bonifico»). Fonte: indicazione del titolare
#: per il minisito (``riscontro.stato = non_riscontrabile`` in
#: ``cedolini_canonici.json``): i dati bancari cominciano il 26/07/2024. La data
#: non e' scritta nel file d'oro: da verificare se l'archivio bancario cambia.
INIZIO_DATI_BANCARI = "2024-07-26"

