/**
 * Legenda delle regole (MINI-08): che cosa vuol dire ogni parola che compare
 * nelle viste fiscali e del personale, in italiano semplice. Una fonte sola:
 * la legenda in pagina e le etichette dei badge leggono da qui, cosi' la
 * parola scritta nella tabella e quella spiegata sotto non possono divergere.
 */

export const LIVELLI_RISCONTRO = {
  CERTO: 'Certo',
  PROBABILE: 'Probabile',
  PARZIALE: 'Parziale',
  NESSUN_MATCH: 'Nessun riscontro',
  MOVIMENTO_ORFANO: 'Addebito senza F24',
};

export const STATI_INCROCIO = {
  OK: 'Torna',
  MANCANTE: 'Manca il versamento',
  PARZIALE: 'Versato in parte',
  ECCEDENTE: 'Versato in più',
  NON_DETERMINABILE: 'Non determinabile',
};

export const CANALI = {
  posta: 'Posta',
  drive: 'Drive',
  caricato: 'Caricato a mano',
  altro: 'Altro',
};

export const NETTO_FONTE = {
  cella: 'Letto dalla cella del netto',
  non_letto_da_lul: 'Pagina del Libro Unico senza cella del netto',
};

export const LEGENDA = {
  f24: {
    titolo: 'Come si legge un F24',
    voci: [
      ['Modello', "È la delega preparata dal commercialista. Da sola non prova che sia stata pagata."],
      ['Quietanza', "È la ricevuta dell'Agenzia delle Entrate: documenta il pagamento ma non sostituisce l'addebito in banca."],
      ['Certo', "Importo uguale al centesimo, addebito entro due giorni lavorativi dalla data di incasso e causale di delega."],
      ['Probabile', "Importo e giorni tornano ma manca la data di incasso, oppure ci sono più addebiti possibili: si mostrano tutti, nessuno è applicato."],
      ['Parziale', "Differenza sotto 5 euro: si vede quanto."],
      ['Nessun riscontro', "Nessun addebito trovato. Se manca l'estratto conto del periodo lo si dice: non vuol dire che non sia stato pagato."],
      ['Addebito senza F24', "In banca c'è un addebito di delega ma nessun F24 corrispondente: serve la quietanza."],
      ['Saldo zero', "Tutto pagato in compensazione con crediti: nessun addebito in banca da cercare."],
      ['Periodo', "Il mese o l'anno a cui si riferisce il tributo, scritto sulla riga. Non è la data del pagamento. «0101» è la rata unica, non gennaio."],
      ['Canale', "Da dove è arrivato il documento: Posta, Drive, Caricato a mano. La prima copia arrivata fissa il canale."],
    ],
  },
  tributi: {
    titolo: 'Come si legge un tributo',
    voci: [
      ['Pagato con quietanza', "Somma delle righe di quel codice e periodo nelle quietanze ricevute."],
      ['Con ravvedimento', "Pagato in ritardo con sanzioni e interessi."],
      ['A credito / compensato', "Credito usato per pagare altri tributi nella stessa delega."],
      ['Resta da pagare', "Il più alto fra quanto ha inviato il commercialista e quanto è atteso, meno quanto è già stato pagato."],
      ['Torna', "Il versato coincide con il dovuto entro 1,00 euro."],
      ['Manca il versamento', "Il dovuto c'è, il versamento no."],
      ['Versato in parte', "Il versamento c'è ma è più basso del dovuto."],
      ['Versato in più', "Hai versato più del dovuto: da verificare con il commercialista."],
      ['Non determinabile', "Un dato di partenza non si è potuto leggere: non è uno scostamento, è un «non lo so»."],
      ['Codici IVA', "Da 6001 a 6012 sono i mesi da gennaio a dicembre; 6099 è il saldo annuale."],
    ],
  },
  cedolini: {
    titolo: 'Come si legge una busta paga',
    voci: [
      ['Netto', "Letto solo dalla cella del netto nel PDF. Se la cella è vuota si scrive «Dato non disponibile», mai zero."],
      ['Pagina senza cella', "Certe pagine del Libro Unico non hanno la cella del netto: restano senza netto finché non si legge il modulo intero."],
      ['Stampa di controllo', "Bozza del consulente. La busta definitiva vale più di lei."],
      ['Variante', "Se il consulente rifà la busta, la variante con il numero più alto vale più delle precedenti."],
      ['Sostituita', "Un'altra versione della stessa busta vale al suo posto: questa resta in archivio ma non conta per costi, Prima Nota o pagamenti."],
      ['Rettificata', "Il netto è cambiato fra due versioni: il valore precedente resta nello storico."],
      ['Da decidere', "Due versioni con netti diversi e nessun segno per scegliere: decide il titolare."],
      ['Canale', "Da dove è arrivata la busta: Posta, Drive, Caricato a mano."],
    ],
  },
  protocollo: {
    titolo: 'Come si legge il protocollo',
    voci: [
      ['Protocollo personale', "Documenti di famiglia e personali (TARI, COSAP, verbali, cartelle). Sono conservati per ricerca e non entrano mai nei conti dell'azienda."],
      ['Numero di protocollo', "Anno e progressivo (per esempio 2023/000123): è unico e non cambia mai."],
      ['Documenti collegati', "Documenti dell'azienda che hanno lo stesso file (stessa impronta). Si consultano nella loro sezione: il collegamento non crea scritture né pagamenti."],
      ['Rimosso', "Il documento è stato tolto dall'archivio con un motivo. La riga resta: un protocollo non dimentica."],
    ],
  },
};
