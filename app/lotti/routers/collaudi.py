"""
collaudi.py — Registro dei collaudi da fare sull'app live (richiesta Enzo
03/07/2026: "una pagina con tutti i test da fare, non mandarli in chat").

Ogni intervento di sviluppo registra qui i suoi test manuali; Enzo li apre
dalla pagina Collaudi (admin), li esegue sul telefono/tablet e li spunta.
Un collaudo spuntato resta in archivio con data e chi l'ha fatto.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from app.lotti.db import database as db

router = APIRouter(prefix="/collaudi", tags=["collaudi"])


class NuovoCollaudo(BaseModel):
    titolo: str                 # es. "Carrello cataloghi -> Ordini"
    gruppo: str = ""            # es. "Ordini", "Colazione", "Cataloghi"
    passi: List[str]            # passi da eseguire, in ordine
    note: Optional[str] = ""


# Collaudi pendenti accumulati durante gli sviluppi del 03/07/2026 (prima
# venivano dettati in chat). Seed una tantum: inserisce solo se il registro
# è vuoto, poi si lavora solo via API/pagina.
_SEED = [
    {"titolo": "Carrello unico: dai cataloghi agli ordini", "gruppo": "Ordini", "passi": [
        "Apri Prodotti → tab Bindi (o Saima) e tocca “+ Aggiungi all'ordine” su un prodotto.",
        "Apri la pagina Ordini → Carrello: il prodotto deve essere lì.",
        "Tocca “Crea bozze”: in “Da inviare” deve comparire la bozza col fornitore giusto.",
    ]},
    {"titolo": "Import cataloghi PDF", "gruppo": "Cataloghi", "passi": [
        "Prodotti → Il Pasticcere → “Importa dal catalogo PDF 2026”: devono comparire ~111 prodotti.",
        "Ripeti per Tre Marie (~112) e Bindi (~89).",
        "Ripremi il bottone: i numeri NON devono raddoppiare (niente doppioni).",
    ]},
    {"titolo": "Prezzo verde = già comprato", "gruppo": "Cataloghi", "passi": [
        "Lancia una volta POST /api/fatture/backfill-codici-articolo (o chiedi a Claude).",
        "Apri un catalogo di un fornitore da cui hai già fatture: i prodotti comprati devono avere prezzo verde + “✓ già comprato”.",
        "Un prodotto mai comprato NON deve avere prezzo.",
    ]},
    {"titolo": "Riordino con consumi reali e festività", "gruppo": "Ordini", "passi": [
        "Nel tab Riordini controlla il banner festività (visibile nei 12 giorni prima di una festa).",
        "Scarica qualche prodotto dal tablet magazzino per creare consumi, poi guarda le proposte del riordino automatico: la nota deve dire “consumo reale X/giorno”.",
        "A ridosso di una festività la quantità proposta deve raddoppiare (nota “quantità raddoppiata”).",
    ]},
    {"titolo": "Giacenza e soglia dalla card", "gruppo": "Ordini", "passi": [
        "Ordini → Catalogo → su una card tocca “✎ correggi giacenza / soglia”.",
        "Scrivi giacenza contata e soglia, Salva: i badge Giac./Min. devono aggiornarsi.",
    ]},
    {"titolo": "Alert: click per silenziare + allergeni automatici", "gruppo": "Supervisore", "passi": [
        "Apri il pannello Supervisore: su ogni alert c'è la ✕ — toccala e l'alert deve sparire per oggi.",
        "L'alert allergeni deve comparire SOLO per ricette senza ingredienti (l'automatismo fa il resto da solo).",
        "Sistema una ricetta segnalata (aggiungi ingredienti): al refresh l'alert deve calare di 1 e NON ricomparire.",
    ]},
    {"titolo": "Migrazione materie prime", "gruppo": "Magazzino", "passi": [
        "POST /api/materie-prime/migra-in-lotti-fornitori (senza flag) e guarda i numeri.",
        "Controlla pagina Materie Prime + una registrazione lotto (ingredienti con fornitore e n° fattura).",
        "Solo se tutto ok: rilancia con ?elimina_dopo=true.",
    ]},
    {"titolo": "Farcitura cornetti", "gruppo": "Tablet", "passi": [
        "Tablet pasticceria → giacenza cornetti vuoti → “🥐 Dividi nei gusti”.",
        "Controlla la divisione proposta (proporzioni della Colazione attiva), modifica un gusto, conferma.",
        "Verifica in Vendita banco i gusti registrati e in magazzino lo scarico delle creme (FIFO).",
    ]},
    {"titolo": "Scheda fornitore estesa + qualità ricette", "gruppo": "Fornitori", "passi": [
        "Apri un fornitore: compila sito web e giorni di chiusura, Salva scheda.",
        "Controlla il pannello “🍰 Qualità dati per le ricette”: contatori e lista “Da sistemare”.",
    ]},
    {"titolo": "Dizionario: battesimo righe XML con proposta", "gruppo": "Qualità dati", "passi": [
        "Menu Altro → Dizionario Ingredienti: filtro «Solo Magazzino+Lotti» attivo di default; le righe mostrano prezzo, quantità e unità come in fattura (le righe vecchie li acquisiscono alla prossima fattura).",
        "Su una riga scoperta: il nome canonico è GIÀ proposto nel campo (scritta «proposta del sistema») — tocca il bottone verde «Conferma proposta» e la riga esce dall'elenco.",
        "Su una riga senza proposta: inizia a scrivere — l'autocomplete suggerisce i nomi già usati (niente refusi tipo Vaniglia/vaniglia).",
        "Pannello Supervisore: c'è l'avviso «N righe fattura da battezzare nel Dizionario» — toccalo e deve aprire questa pagina; battezza una riga e al refresh il numero cala.",
        "Da amministratore: tocca «Completa dati storici» — le righe vecchie si riempiono con prezzo/quantità/unità presi dalle fatture già importate (una tantum).",
    ]},
    {"titolo": "Mani sporche: motivi a tendina, mai tastiera", "gruppo": "Lotti & Economia", "passi": [
        "Ricezione Merce → su un lotto da verificare tocca «Non conforme»: l'azione correttiva è una TENDINA con i motivi pronti (la tastiera compare solo scegliendo «Altro»).",
        "Apri un lotto → «Smaltisci»: anche qui tendina con i motivi HACCP pronti; scegline uno e conferma senza scrivere nulla.",
        "«Sposta» / «Congela» / «Recupera»: motivo a tendina con opzioni sensate per ciascuna azione.",
        "Olio Frittura e Temp. Cottura: registra un controllo FUORI NORMA — l'azione correttiva è a tendina.",
    ]},
    {"titolo": "Ordini semplificati: quantità libera, righe pre-spuntate, cataloghi", "gruppo": "Ordini", "passi": [
        "Ordini → Riordini: su un prodotto sotto soglia regola la quantità con −/+ (es. 3) PRIMA di toccare «+ Aggiungi» — deve entrare nel carrello con la TUA quantità.",
        "Crea le bozze e vai su «Da inviare»: le righe sono GIÀ tutte spuntate — togli una spunta, poi «Conferma e scarica PDF» deve funzionare senza chiederti nulla.",
        "Nel Carrello, un prodotto con più fornitori dice «il migliore è già scelto ✓» e la prima voce del menu ha la ★ MIGLIORE.",
        "Ordini → Catalogo: in fondo ai filtri ci sono i bottoni di TUTTI i cataloghi (Acquaviva, SAIMA, MePA, Il Pasticcere, Tre Marie, Alfa, Sammontana, Bindi + fonti web tipo Sunset Cash): toccane uno e verifica che il carrello resti lo stesso.",
    ]},
    {"titolo": "Confronto prezzi: pagina prodotto semplice + carrello", "gruppo": "Ordini", "passi": [
        "Menu Altro → «Confronto prezzi»: scrivi un prodotto (es. «coca cola» o «farina») nella barra di ricerca.",
        "Per ogni prodotto vedi l'ultimo prezzo di OGNI fornitore, ordinati dal più conveniente; il migliore è evidenziato in verde con «più conveniente».",
        "Tocca il carrello sulla riga migliore: il prodotto entra in Ordini → Carrello (controlla che ci sia).",
        "Se un nome è sbagliato o mancante, tocca «correggi nome»/«dai un nome», scrivi quello giusto e Salva: al refresh resta memorizzato (matching per le prossime fatture).",
    ]},
    {"titolo": "Usa oggi + drill-down dashboard + gemello completo", "gruppo": "Lotti & Economia", "passi": [
        "Cosa usare oggi (menu Altro): su ogni card c'è «Usa oggi» — toccalo e controlla che sul tablet compaia il task «🕐 Usa prima: …» in “Cosa fare oggi”.",
        "Dashboard economica: ORA anche «Valore lotti attivi» e «Costo spreco oggi» si aprono col tocco; nelle liste sotto, tocca una riga: fornitore → scheda fornitore, prodotto → ricetta, variazione prezzi → Confronto già filtrato.",
        "Apri un lotto (Dettaglio): la scheda ora mostra quantità PRODOTTA e residua, l'elenco ingredienti, e i bottoni «Apri ricetta», «Apri recall», «Registro HACCP», «Apri fattura» (sulle righe provenienza) e «Stampa report» (documento A4, diverso dall'etichetta).",
    ]},
    {"titolo": "Sunset Cash: fonte web e scheda catalogo dinamica", "gruppo": "Cataloghi", "passi": [
        "Menu Altro → Cataloghi Fornitori (web): aggiungi Nome “Sunset Cash”, indirizzo https://www.sunsetcash.it, poi «Aggiungi» e «Sincronizza».",
        "Aspetta il badge: «Sincronizzata (N prodotti)» oppure «Errore / nessun dato trovato» — se errore, screenshot a Claude (serve un connettore dedicato).",
        "Se ha trovato prodotti: vai in Listini & Vendita → deve comparire la NUOVA scheda “Sunset Cash” col numero di prodotti; sfogliala e prova «+ Aggiungi all'ordine» → il prodotto deve stare in Ordini → Carrello.",
    ]},
    {"titolo": "Guida completa: in-app e PDF", "gruppo": "Guida", "passi": [
        "Apri la Guida (bottone in alto o menu Altro): deve avere ~31 sezioni raggruppate (Per iniziare, Ufficio, Acquisti, Tablet, Registri HACCP, Amministrazione).",
        "Apri una sezione: testo discorsivo + passi + tabella «Bottone / Cosa fa / Dove porta» con le etichette VERE dell'app.",
        "Tocca «Scarica la Guida operativa completa (PDF stampabile)»: si apre il PDF nuovo (copertina salvia, 17 pagine, data 04/07/2026).",
    ]},
    {"titolo": "Controllo Dati: i campioni aprono la cosa segnalata", "gruppo": "Controllo dati", "passi": [
        "Home → card “Collaudi da fare”: ora è in Home, senza cercare il menu Altro.",
        "Controllo Dati → “Ingredienti ricetta non collegati”: tocca “Panuozzo” — si apre la SCHEDA della ricetta, non la pagina generica.",
        "“Righe fattura senza link prodotto”: tocca una riga — si apre la FATTURA nel visualizzatore; verifica anche che il numero sia calato (i fornitori esclusi non vengono più contati).",
        "“Lotti senza ingredienti tracciati”: tocca un lotto — si apre Lotti con la ricerca già compilata su quel lotto.",
    ]},
    {"titolo": "Confronto leggibile + variazioni prezzo in un solo alert", "gruppo": "Supervisore", "passi": [
        "Ordini → Confronto: i nomi dei prodotti ora si leggono per intero (su due righe), niente più “Pista…”.",
        "Pannello Supervisore: le variazioni di prezzo sono UN solo alert con l'elenco; la sua ✕ le segna viste e NON ricompaiono domani (tornano solo variazioni nuove).",
    ]},
    {"titolo": "Alert critici bloccati + allergeni da confermare", "gruppo": "Supervisore", "passi": [
        "Pannello Supervisore: gli alert ROSSI (critici) non hanno più la ✕ — al suo posto un ! che spiega perché.",
        "Un alert non critico si nasconde ancora con la ✕ come prima.",
        "Chiedi a Claude di lanciare POST /api/food-cost/backfill-allergeni-da-confermare (col tuo PIN admin): comparirà l'alert azzurro “ricette con allergeni auto-rilevati da confermare”.",
        "Apri una ricetta dall'elenco dell'alert, controlla gli allergeni e Salva: al refresh il contatore deve calare di 1.",
    ]},
    {"titolo": "Bonifica bug: allergeni, prezzi recenti, crash", "gruppo": "Qualità dati", "passi": [
        "Apri una ricetta e usa “rileva allergeni”: il risultato deve essere coerente rientrando dalla pagina Registro Allergeni (prima due mappe diverse davano risultati diversi).",
        "Sfoglia un catalogo con prezzo verde: la data del prezzo mostrato deve essere quella dell'ULTIMA fattura del prodotto, non una vecchia.",
        "Backoffice → Prodotti → “Applica soglie dai consumi”: deve mostrare il messaggio di esito (prima crashava in silenzio).",
        "Tablet → registra lotto con sotto-ricette (BOM): lo step di selezione lotti deve aprirsi senza schermo bianco.",
        "Catalogo Saima/Acquaviva → tocca la stella preferiti: deve funzionare (prima crashava).",
        "Fornitori → apri una scheda fornitore grossa: deve caricarsi visibilmente più veloce di prima.",
    ]},
    {"titolo": "Alert: niente doppioni, lotti archiviati esclusi", "gruppo": "Supervisore", "passi": [
        "Smaltisci (o archivia) un lotto scaduto: al “Ricontrolla” del Supervisore il contatore dei lotti scaduti deve calare.",
        "Verifica che ci sia UN solo alert “lotti in scadenza entro 2 giorni” (prima erano due identici) e che toccandolo si apra l'elenco dei lotti.",
        "Verifica che “prodotti che non compri da troppo tempo” e le qualifiche fornitori siano UN alert con elenco, non una sfilza di alert singoli.",
    ]},
    {"titolo": "Food cost: l'ingrediente generico prende il prezzo giusto", "gruppo": "Qualità dati", "passi": [
        "Apri una ricetta che usa un ingrediente generico (es. «farina» o «zucchero») e guarda il food cost calcolato.",
        "Verifica che il costo di quell'ingrediente sia quello della materia prima base (es. farina 00), NON di un omonimo costoso (farina di mandorle, zucchero a velo): prima il sistema sceglieva sempre il più caro.",
        "Se hai correzioni salvate a mano sul Dizionario (scorta minima, nome canonico), lancia una sincronizzazione fatture e verifica che restino: gli id delle righe non devono più cambiare.",
    ]},
    {"titolo": "Sicurezza: le funzioni pericolose solo da amministratore", "gruppo": "Impostazioni", "passi": [
        "Da un accesso DIPENDENTE (PIN operatore) prova ad aprire Backup / gestione Personale / azzeramento dati: le azioni distruttive devono rispondere «riservato all'amministratore», non eseguire.",
        "Da amministratore le stesse azioni devono funzionare normalmente.",
        "Verifica che un dipendente non possa modificare il proprio ruolo o creare un altro amministratore.",
    ]},
    {"titolo": "Documenti HACCP e temperature con la virgola", "gruppo": "HACCP", "passi": [
        "Apri il Manuale HACCP a schermo intero e il report mensile (bottone in alto): devono mostrare il documento, NON un messaggio «Autenticazione richiesta».",
        "Stampa un registro HACCP e apri un ricettario Saima: la scheda nuova deve aprire il PDF, non un errore.",
        "In Ricezione Merce scrivi una temperatura con la virgola (es. «4,5»): deve salvarsi 4,5 e non 0/vuoto. Idem sui valori in Sconti Merce.",
    ]},
    {"titolo": "Frigoriferi e congelatori: i nomi in un posto solo", "gruppo": "HACCP", "passi": [
        "Menu «Altro» → Amministrazione → «Frigoriferi e congelatori»: devono comparire tutti gli apparecchi, frigoriferi e congelatori separati, con il numero accanto.",
        "Cambia il nome di uno (es. «Cella Fresca Nord» → «Cella 1») e premi Salva: il bottone Salva deve comparire SOLO dopo aver toccato il testo.",
        "Riapri Temperature positive: la colonna deve chiamarsi già «Cella 1». Apri anche un controllo registrato il mese scorso: deve mostrare il nome nuovo (è lo stesso apparecchio).",
        "Dal tablet, in Registra lotto, la tendina del posto deve mostrare «Cella 1».",
        "Aggiungi un apparecchio nuovo, poi toglilo: dopo la rimozione non deve più comparire nella scelta del posto, ma i controlli già registrati restano.",
        "Premi «Segnala guasto» su un apparecchio: si apre l'anomalia in rosso e ti porta subito ad Anomalie per spostare i lotti che erano dentro.",
        "In Tracciabilità NON deve più esistere nessuna finestra «Genera Nuovo Lotto»: il lotto si crea solo producendo una ricetta.",
    ]},
    {"titolo": "Buchi nei registri: dichiarati, non nascosti", "gruppo": "HACCP", "passi": [
        "Stampa il report HACCP del mese (Tracciabilità → Report HACCP PDF): i giorni in cui non c'è stata nessuna rilevazione devono comparire come «N/D» e, passandoci sopra col dito/mouse, spiegare il motivo («sistema non attivo quel giorno»). Nessun giorno deve sparire dalla tabella.",
        "Apri Sanificazione: i giorni passati senza nessuna registrazione mostrano «N/D» color sabbia, quelli fatti la «X» verde, il giorno di oggi resta vuoto (è ancora aperto). Toccando una casella «N/D» puoi comunque registrarla ora.",
        "Stampa il registro sanificazione (bottone PDF): in fondo c'è la legenda X / N/D / cella vuota.",
        "Controlla che nessuna temperatura sia stata inventata per i giorni mancanti: la casella N/D non deve mostrare gradi.",
        "Registro tracciabilità fatture-ricette: se i collegamenti sono più di 500, sopra la tabella deve esserci scritto «Mostrate le prime 500 righe di N» col rimando al CSV.",
    ]},
    {"titolo": "Sicurezza: import e sincronizzazioni solo da titolare", "gruppo": "Impostazioni", "passi": [
        "Da amministratore: «Sincronizza listino da fatture», «Importa sconti merce dalle fatture», sincronizzazione Drive e import cataloghi Acquaviva devono funzionare come sempre.",
        "Da dipendente (o senza aver fatto l'accesso): gli stessi comandi devono rispondere «non autorizzato» e NON eseguire.",
        "Pannello Supervisore: la ✕ che nasconde un avviso deve funzionare solo col tuo accesso da amministratore.",
    ]},
    {"titolo": "Tablet: il dipendente produce e legge le ricette, il resto è tuo", "gruppo": "Tablet", "passi": [
        "Dal tablet, con un PIN DIPENDENTE: Pasticceria, Rosticceria, Bar, Produzioni al banco e Dose di oggi devono aprirsi normalmente.",
        "Sempre col PIN dipendente prova Magazzino, Lavagna richieste e Ordini: hanno il lucchetto «Solo titolare» e devono rispondere «PIN non autorizzato».",
        "Con il TUO PIN le stesse tre card devono aprirsi: le usi tu dal tablet.",
        "Su ogni prodotto del reparto c'è il bottone «Ricetta»: si apre la scheda in SOLA LETTURA con ingredienti, dosi, allergeni e note. Non deve esserci nessun modo di modificarla da lì.",
        "Prova a cancellare un lotto da un accesso dipendente: deve rispondere «riservato all'amministratore».",
    ]},
    {"titolo": "Audit end-to-end: le correzioni sul campo", "gruppo": "Qualità dati", "passi": [
        "Apri un lotto (Tracciabilità o «Lotti da usare oggi» → Dettaglio) e tocca «Recupera»: deve funzionare e scalare la quantità. Prima dava SEMPRE errore, il bottone non ha mai funzionato.",
        "Fornitori → apri una fattura in anteprima e chiudila con la ✕ in alto: la pagina non deve svuotarsi.",
        "Fornitori → pannello duplicati, con un fornitore marcato «escluso»: la pagina non deve svuotarsi.",
        "Corrispettivi: anche in un periodo senza dati la pagina deve mostrare quello che c'è (es. le festività in arrivo), non una schermata rossa.",
        "Acquisti → Catalogo: i prodotti devono comparire come sempre (è stato cambiato il filtro interno dei prodotti non ordinabili: cavi, detersivi ecc. devono restare FUORI dal catalogo).",
    ]},
    {"titolo": "PIN: nessuno può più leggerli, si reimpostano", "gruppo": "Impostazioni", "passi": [
        "IMPORTANTE, prima di tutto: entra col TUO PIN dal tablet e dal gestionale. Devono funzionare esattamente come prima (i PIN non sono stati cambiati, è cambiato solo COME vengono conservati).",
        "Fai entrare un dipendente dal tablet col suo PIN: deve entrare come sempre.",
        "Personale → «PIN operatori» → inserisci il tuo PIN e tocca «Gestisci PIN»: NON deve comparire nessun PIN, solo il nome e l'etichetta «PIN impostato». Prima si leggevano tutti in chiaro.",
        "Su un dipendente scrivi un PIN nuovo e tocca «Reimposta PIN». Poi prova dal tablet: il PIN NUOVO entra, il VECCHIO deve essere rifiutato. (Prima il vecchio tornava valido al primo riavvio del server: era il difetto più serio.)",
        "Prova a mettere a un dipendente un PIN già usato da un altro: deve rifiutarlo dicendo di sceglierne un altro.",
        "Se qualcosa non torna, riscrivi il PIN al dipendente da questa stessa pagina: è la via ufficiale, non esiste più nessun posto dove «vedere» i PIN.",
    ]},
]


async def _seed_mancanti():
    """Inserisce i collaudi del _SEED non ancora applicati. Un registro
    separato (collaudi_seed_applicati) ricorda cosa è già stato seminato:
    così le sessioni di sviluppo possono aggiungere collaudi nel codice
    (quando il backend live non è raggiungibile) senza resuscitare quelli
    che Enzo ha già fatto o eliminato."""
    applicati = {
        d["titolo"]
        async for d in db.collaudi_seed_applicati.find({}, {"_id": 0, "titolo": 1})
    }
    esistenti = {
        d["titolo"] async for d in db.collaudi.find({}, {"_id": 0, "titolo": 1})
    }
    now = datetime.now(timezone.utc).isoformat()
    for s in _SEED:
        if s["titolo"] in applicati:
            # i passi possono arricchirsi nel codice dopo il primo seed:
            # aggiorna SOLO i collaudi non ancora eseguiti, mai quelli fatti
            await db.collaudi.update_one(
                {"titolo": s["titolo"], "stato": "da_fare", "passi": {"$ne": s["passi"]}},
                {"$set": {"passi": s["passi"]}},
            )
            continue
        # se già presente (seed vecchio, prima del registro) non lo duplica:
        # lo segna solo come applicato
        if s["titolo"] not in esistenti:
            await db.collaudi.insert_one({
                "id": str(uuid.uuid4()), "titolo": s["titolo"], "gruppo": s["gruppo"],
                "passi": s["passi"], "note": "", "stato": "da_fare",
                "creato_il": now, "eseguito_il": None, "eseguito_da": "",
            })
        await db.collaudi_seed_applicati.insert_one({"titolo": s["titolo"], "applicato_il": now})


@router.get("")
async def lista_collaudi(anche_fatti: bool = True):
    await _seed_mancanti()
    q = {} if anche_fatti else {"stato": "da_fare"}
    docs = await db.collaudi.find(q, {"_id": 0}).sort(
        [("stato", -1), ("creato_il", -1)]
    ).to_list(300)
    return {"collaudi": docs,
            "da_fare": sum(1 for d in docs if d.get("stato") == "da_fare")}


@router.post("")
async def aggiungi_collaudo(payload: NuovoCollaudo = Body(...)):
    """Usato dalle sessioni di sviluppo per registrare i test del proprio
    intervento (invece di dettarli in chat)."""
    doc = {
        "id": str(uuid.uuid4()), "titolo": payload.titolo.strip(),
        "gruppo": (payload.gruppo or "").strip(), "passi": payload.passi,
        "note": payload.note or "", "stato": "da_fare",
        "creato_il": datetime.now(timezone.utc).isoformat(),
        "eseguito_il": None, "eseguito_da": "",
    }
    await db.collaudi.insert_one(dict(doc))
    return {"ok": True, "id": doc["id"]}


@router.post("/{collaudo_id}/stato")
async def cambia_stato(collaudo_id: str, stato: str, operatore: str = ""):
    if stato not in ("da_fare", "fatto", "fallito"):
        raise HTTPException(400, "Stato non valido (da_fare|fatto|fallito)")
    res = await db.collaudi.update_one(
        {"id": collaudo_id},
        {"$set": {"stato": stato,
                  "eseguito_il": datetime.now(timezone.utc).isoformat() if stato != "da_fare" else None,
                  "eseguito_da": operatore or ""}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Collaudo non trovato")
    return {"ok": True}


@router.delete("/{collaudo_id}")
async def elimina_collaudo(collaudo_id: str):
    res = await db.collaudi.delete_one({"id": collaudo_id})
    if not res.deleted_count:
        raise HTTPException(404, "Collaudo non trovato")
    return {"ok": True}
