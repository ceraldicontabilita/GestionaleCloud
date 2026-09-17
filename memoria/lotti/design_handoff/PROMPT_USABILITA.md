# Prompt di USABILITÀ (solo interfaccia) — da incollare su un'altra app

Nessuna regola di funzionamento, nessuna funzione da implementare: solo come
deve apparire e come si deve toccare. Le misure sono quelle vere dell'app
Lotti (`frontend/src/index.css`, `TabletHome.jsx`, `TabletView.jsx`,
`tablet/ModalRegistraLotto.jsx`), non valori inventati.

---

```text
INCARICO — Uniformare l'interfaccia di questa app allo standard d'uso del
gruppo Ceraldi. Non cambiare funzioni, dati, pagine o chiamate al server:
si interviene SOLO su aspetto, misure e modo di toccare.

═══ 1. CONTENITORE E ZERO SCROLL ORIZZONTALE ═══
- Contenitore unico di pagina: larghezza 100%, massimo 480px, centrato
  (margini auto), padding laterale 14px. Tutto il contenuto sta lì dentro.
- Regola assoluta: su schermo da 360px di larghezza la pagina NON deve mai
  scorrere in orizzontale. Si verifica così: scrollWidth della pagina <=
  clientWidth. Se sfora, la colpa è quasi sempre una di queste quattro:
  a) una colonna di griglia o un elemento flex senza `min-width: 0`
     (i campi select e input impongono una larghezza minima e sfondano);
  b) un contenitore in riga senza `flex-wrap: wrap`;
  c) un elemento con larghezza fissa in pixel maggiore dello schermo, o senza
     `box-sizing: border-box` con padding aggiunto al 100%;
  d) una tabella larga: va messa dentro un contenitore con
     `overflow-x: auto`, oppure trasformata in elenco di card sotto i 640px.
- Le immagini: `max-width: 100%`.
- Se in fondo c'è una barra fissa, il contenuto deve avere spazio sotto pari
  alla sua altezza, altrimenti l'ultimo bottone resta coperto.

═══ 2. CARD ═══
- Griglia dei prodotti/voci: `grid-template-columns: repeat(auto-fill,
  minmax(150px, 1fr))`, distanza 12px. Su 360px vengono 2 colonne, su tablet
  4-5, senza scrivere alcuna soglia a mano.
- Card di scelta principale (le "porte" dell'app, tipo i reparti): 220px di
  larghezza per 200px di altezza, angoli 24px, distanza 20px, dentro un
  contenitore che va a capo (`flex-wrap: wrap`) largo al massimo 760px e
  centrato. Contenuto: icona grande sopra (56px), etichetta sotto 20px
  peso 900, testo bianco su fondo pieno.
- Card normale: fondo #fffefb, bordo 1px #e6e0d4, angoli 16px, ombra
  `0 2px 10px rgba(63,90,78,.06)`, padding interno 16px.
- Nella card, il titolo non deve mai troncare male: usare
  `overflow: hidden` con clamp a 2-3 righe, non un taglio a metà parola.

═══ 3. TASTIERINO PIN ═══
- Sfondo dietro: `rgba(42,51,41,0.55)` con sfocatura 3px; toccando fuori si
  chiude.
- Pannello: larghezza 100% con massimo 340px, angoli 26px, padding 30px sopra
  e sotto / 24px ai lati, fondo #fffefb, ombra `0 24px 70px rgba(42,51,41,.35)`.
- In testa: icona, titolo 21px peso 700, sottotitolo 13px colore #6b7669.
- Pallini del codice: uno per cifra prevista, 15px di diametro, distanza 12px;
  quello riempito prende il colore del reparto, si ingrandisce del 10% e ha un
  alone `0 0 0 4px <colore>22`.
- Tasti: griglia di 3 colonne, distanza 10px, **altezza tasto 62px**, angoli
  14px, cifra 25px peso 700, fondo #f7f4ec (il tasto cancella #f0ebe0, simbolo
  22px). Ordine 1-9, poi vuoto, 0, cancella.
- In fondo due bottoni sulla stessa riga: "Annulla" che occupa 1 parte
  (bordo 1.5px #e6e0d4, fondo bianco) e "Conferma" che ne occupa 2 (fondo del
  colore del reparto, testo bianco peso 800); entrambi padding 13px, angoli
  14px, testo 14px.
- Comportamento: a 6 cifre conferma da solo dopo 80 millisecondi; a 4 cifre
  serve premere Conferma (Conferma resta spento sotto le 4 cifre). Sotto,
  in 11px, la scritta che lo spiega.
- Errore: riquadro rosso chiaro (fondo #fbe6e2, bordo #f3cfc8, testo #8f3829),
  angoli 10px, padding 10/14, testo 13px peso 700 — mai un avviso di sistema.
- Vibrazione breve a ogni cifra (8ms), più lunga sull'errore.

═══ 4. FINESTRE (MODALI) ═══
- Su telefono: larghezza 100% con massimo 360px; nel gestionale da scrivania
  massimo 512px. Angoli 20px. Padding interno 16px.
- Intestazione con titolo al centro, ritorno a sinistra e chiusura a destra;
  se il contenuto è lungo, l'intestazione resta attaccata in alto
  (`position: sticky; top: 0`) e non scorre via.
- Altezza massima 80% dello schermo, con scorrimento interno: la finestra non
  deve mai uscire dallo schermo.

═══ 5. TOCCO ═══
- Qualsiasi cosa si tocchi: almeno 44×44 pixel. Nessuna eccezione.
- Alla pressione: `transform: scale(.97)`, nient'altro (niente animazioni).
- Distanza minima fra due bersagli diversi: 8px.
- Si sceglie da un menu a tendina vero (`select`), che su telefono si apre a
  tutto schermo. MAI un campo di testo con lista di suggerimenti nascosta
  (`datalist`): su Android quel menu non si apre e l'utente resta bloccato sul
  valore precompilato.
- Per i numeri: campo grande al centro (20px peso 800) con i tasti − e + ai
  lati (36×36px), più una riga di valori pronti come bottoni (5 per riga,
  altezza minima 44px).

═══ 6. TESTO ═══
- Corpo 15px, interlinea 1.5. Testo secondario 13px. Etichette in maiuscolo
  10-11px peso 700-800.
- Titolo di pagina 20-24px. Numeri grandi (statistiche) 24-32px peso 700+.
- Contrasto: testo principale #2a3329 su fondo chiaro; su fondo colorato
  sempre bianco pieno. Mai testo tenue su gradiente: se serve, si mette dietro
  un velo scuro traslucido.

═══ 7. MESSAGGI ═══
- Mai `alert`, `confirm`, `prompt` del browser. Avvisi discreti in basso che
  spariscono da soli; conferme in una finestra dell'app che dice cosa
  succederà ("Elimino 3 righe?") e non "sei sicuro?".
- Errori in italiano semplice, mai codici: "Il server non risponde, riprova
  tra poco" al posto di "Error 500".
- Attesa oltre i 2 secondi: scritta "Carico…"; oltre i 10, spiegare che il
  server sta partendo.
- Un dato che manca si scrive "N/D" con la spiegazione al passaggio del dito,
  mai una casella vuota che sembra uno zero.

═══ 8. COLORI (solo per coerenza visiva) ═══
Salvia #5b7a6b (scuro #3f5a4e), fondo crema #faf7f0, card #fffefb, bordi
#e6e0d4, testo #2a3329 / secondario #6b7669. Semantici: rosso terracotta
#d35f4e, ocra #c4894a, verde #3d8168, sabbia #8a6f47.
MAI blu, indaco, viola, ciano e nemmeno i grigi freddi: vanno rimappati su
salvia o sabbia. Le ombre non sono grigie ma tinte di salvia.
Icone: libreria Lucide. MAI emoji nelle schermate (su Android le colora il
sistema e diventano blu).

═══ 9. COME VERIFICARE (obbligatorio) ═══
Dopo ogni pagina modificata, screenshot a 360×800, 390×844, 768×1024 e
1024×768. Per ognuno controllare: nessuno scroll orizzontale, nessun testo
tagliato o sovrapposto, nessun bottone sotto i 44px, nessun elemento fisso che
copre contenuto. Allegare gli screenshot prima/dopo nel report.

═══ 10. UNICA NOTA NON GRAFICA ═══
Se questa app ha bisogno di un dato che vive nel gestionale Lotti (per esempio
un lotto), NON va riscritta la logica: si chiama l'indirizzo che ti verrà
indicato e si mostra il dato ricevuto.

Vincoli: rispondere in italiano, risultati prima delle spiegazioni; non
cambiare funzioni né chiamate esistenti; niente pubblicazione se la build
fallisce.

Da dove partire: [scrivi qui la pagina]
```
