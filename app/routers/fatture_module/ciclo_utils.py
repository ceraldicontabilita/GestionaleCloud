"""
Costanti condivise per lo scadenziario fornitori (usate da pagamento.py).

Le funzioni cerca_match_bancario()/esegui_riconciliazione() che stavano qui
sono state rimosse: erano un ulteriore motore di matching estratto conto
(regola consolidata in PROMPT_MASTER.md, sezioni 6 e 9),
usato solo da POST /api/scadenzario-fornitori/riconcilia-automatica, senza
alcun chiamante frontend. La riconciliazione automatica live è unica, in
app/services/riconciliazione_bancaria.py.
"""
COL_SCADENZIARIO = "scadenziario_fornitori"
COL_BANK_TRANSACTIONS = "bank_transactions"
COL_RICONCILIAZIONI   = "riconciliazioni"
COL_FATTURE      = "invoices"

METODI_PAGAMENTO = {
    "MP01": {"desc": "Contanti",  "tipo": "contanti",  "giorni_default": 0},
    "MP02": {"desc": "Assegno",   "tipo": "assegno",   "giorni_default": 0},
    "MP03": {"desc": "Assegno circolare", "tipo": "assegno", "giorni_default": 0},
    "MP05": {"desc": "Bonifico",  "tipo": "bonifico",  "giorni_default": 30},
    "MP09": {"desc": "RID",       "tipo": "rid",       "giorni_default": 30},
    "MP12": {"desc": "RIBA",      "tipo": "riba",      "giorni_default": 60},
}
