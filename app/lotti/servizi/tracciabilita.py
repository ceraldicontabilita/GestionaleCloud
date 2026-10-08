"""Da un ingrediente ai prodotti finiti, e viceversa.

Per un richiamo non basta sapere «quali dolci contengono farina»: serve sapere
**quale** farina — quella di quel fornitore, di quella fattura — e in quanti
prodotti diversi e' finita. E al contrario, da un dolce, da dove veniva ogni
suo ingrediente.

L'origine di un lotto di produzione oggi sta in due posti, e questo modulo li
legge tutti e due:

1. `lotti_fornitori.lotti_scalati[]` — il collegamento **esatto**, scritto
   dallo scarico FIFO: id del lotto fornitore, fornitore, fattura, quantita'
   consumata. E' la fonte buona, e vale da quando lo scarico gira.

2. `ingredienti_dettaglio[]` — righe di testo costruite per la stampa
   dell'etichetta, nella forma
   `«PRODOTTO  allergeni - FORNITORE n° fatt NUMERO - DATA»`.
   Sono l'unica traccia che hanno i lotti piu' vecchi. Si leggono, perche'
   buttarle significherebbe non poter rispondere su quei lotti, ma restano
   marcate come `origine: "testo"`: sono una ricostruzione, non una prova.

Una riga senza « n° fatt » non ha origine: l'ingrediente c'e', il fornitore no.
Non si indovina e non si nasconde — esce in `senza_origine`, perche' davanti a
un'ispezione quello e' il buco da conoscere prima di essere interrogati.
"""
import re
import unicodedata

SEPARATORE_FATTURA = " n° fatt "

# Coda che `ingredienti_dettaglio` aggiunge al nome: non fa parte dell'ingrediente.
_CODA_ALLERGENI = re.compile(r"\s*(non\s+)?contiene\s+allergeni\s*$", re.IGNORECASE)


def normalizza(testo: str) -> str:
    """Minuscolo, senza accenti e senza spazi doppi: per confrontare i nomi.

    I nomi arrivano dalle fatture dei fornitori, quindi con a capo, doppi spazi
    e maiuscole a caso: «FARINA 00 MANITOBA KG 25» e «farina 00 manitoba» sono
    lo stesso ingrediente e devono incontrarsi.
    """
    senza_accenti = unicodedata.normalize("NFKD", str(testo or ""))
    senza_accenti = "".join(c for c in senza_accenti if not unicodedata.combining(c))
    return " ".join(senza_accenti.lower().split())


def scompone_riga_ingrediente(riga: str) -> dict:
    """Ingrediente, fornitore, fattura e data da una riga di `ingredienti_dettaglio`.

    Il formato e' `«PRODOTTO  allergeni - FORNITORE n° fatt NUMERO - DATA»`, e
    il punto fermo e' « n° fatt »: il nome del prodotto contiene spesso dei
    « - » (per esempio «Ricotta di Pecora x 6 - Ricocrem-»), quindi tagliare
    sul trattino da sinistra spezzerebbe il nome a meta'.
    """
    testo = str(riga or "").strip()
    if not testo:
        return {}
    if SEPARATORE_FATTURA not in testo:
        # Nessuna origine: l'ingrediente e' noto, il fornitore no.
        return {"ingrediente": _pulisci_nome(testo), "testo": testo, "senza_origine": True}

    sinistra, destra = testo.split(SEPARATORE_FATTURA, 1)
    # A destra del separatore: «NUMERO - DATA». La data e' l'ultimo pezzo.
    if " - " in destra:
        fattura, data = destra.rsplit(" - ", 1)
    else:
        fattura, data = destra, ""
    # A sinistra: «PRODOTTO  allergeni - FORNITORE». Il fornitore e' l'ultimo
    # pezzo, e si taglia da destra per non spezzare il nome del prodotto.
    if " - " in sinistra:
        nome, fornitore = sinistra.rsplit(" - ", 1)
    else:
        nome, fornitore = sinistra, ""
    return {
        "ingrediente": _pulisci_nome(nome),
        "fornitore": fornitore.strip().strip('"'),
        "fattura": fattura.strip(),
        "data_fattura": data.strip(),
        "testo": testo,
        "senza_origine": False,
    }


def _pulisci_nome(nome: str) -> str:
    """Il nome dell'ingrediente senza la coda degli allergeni e senza a capo."""
    pulito = " ".join(str(nome or "").split())
    return _CODA_ALLERGENI.sub("", pulito).strip()


def origini_del_lotto(lotto: dict) -> list:
    """Da dove viene ogni ingrediente di un lotto di produzione.

    Preferisce sempre il collegamento esatto dello scarico. Le righe di testo
    si leggono solo per gli ingredienti che quel collegamento non copre, cosi'
    un lotto a meta' strada non perde ne' la parte certa ne' quella vecchia.
    """
    origini, viste = [], set()

    scalati = ((lotto.get("lotti_fornitori") or {}).get("lotti_scalati")) or []
    for voce in scalati:
        nome = voce.get("ingrediente") or voce.get("prodotto") or ""
        if not nome:
            continue
        viste.add(normalizza(nome))
        origini.append({
            "ingrediente": _pulisci_nome(nome),
            "prodotto_fornitore": voce.get("prodotto", ""),
            "fornitore": voce.get("fornitore", ""),
            "fattura": voce.get("fattura_ref", ""),
            "data_fattura": voce.get("data_fattura", ""),
            "lotto_fornitore": voce.get("lotto_id_fornitore", ""),
            "lotto_fornitore_id": voce.get("lotto_id", ""),
            "quantita_consumata": voce.get("quantita_consumata"),
            "unita": voce.get("unita", ""),
            "origine": "scarico",     # collegamento esatto
            "senza_origine": False,
        })

    for riga in (lotto.get("ingredienti_dettaglio") or []):
        if not isinstance(riga, str):
            continue
        voce = scompone_riga_ingrediente(riga)
        if not voce:
            continue
        if normalizza(voce["ingrediente"]) in viste:
            continue        # gia' coperto, e meglio, dallo scarico
        voce.setdefault("fornitore", "")
        voce.setdefault("fattura", "")
        voce.setdefault("data_fattura", "")
        voce["origine"] = "testo"   # ricostruzione dall'etichetta
        origini.append(voce)

    return origini


def corrisponde(origine: dict, *, ingrediente="", fornitore="", fattura="") -> bool:
    """Se questa origine risponde alla domanda posta.

    L'ingrediente si cerca per sottostringa normalizzata: «farina» deve
    trovare «FARINA 00 MANITOBA KG 25». Fornitore uguale. La fattura invece
    e' un identificativo: si confronta intera, o «1/196084» verrebbe trovata
    anche cercando «6084».
    """
    if ingrediente:
        if normalizza(ingrediente) not in normalizza(origine.get("ingrediente", "")):
            return False
    if fornitore:
        if normalizza(fornitore) not in normalizza(origine.get("fornitore", "")):
            return False
    if fattura:
        if normalizza(fattura) != normalizza(origine.get("fattura", "")):
            return False
    return True
