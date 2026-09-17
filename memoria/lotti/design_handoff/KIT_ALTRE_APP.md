# Kit "grafica e semplicità Ceraldi" — da portare su ALTRE app del gruppo

Scritto il 25/07/2026 per applicare a un'altra app (es. impresasemplice.online)
lo stesso aspetto e la stessa facilità d'uso di Lotti, senza rifare il lavoro
da zero e senza toccare le logiche di quell'app.

**Regola numero uno: cambia la grafica, NON il comportamento.** Ogni pagina
resta dov'è, con i suoi dati e le sue chiamate. Si sostituiscono colori,
caratteri, spaziature e componenti visivi. Le uniche aggiunte ammesse sono
quelle di usabilità elencate nella parte 2, e vanno concordate prima.

---

## 1. COSA COPIARE FISICAMENTE

Dal repository Lotti, nella nuova app:

| Cosa | Da dove | Perché |
|---|---|---|
| `design_handoff/tokens/*.css` | qui | colori, caratteri, raggi, ombre, spaziature già pronti |
| `design_handoff/ui_kit/` | qui | prototipo navigabile: si apre `index.html` e si vede come deve venire |
| `.claude/skills/bonifica-design/` | qui | procedura automatica che trova e corregge le pagine fuori palette |
| `.claude/skills/audit-codice/` | qui | audit degli errori reali (non di stile) |
| `.claude/skills/guida-operativa/` | qui | genera la guida PDF leggendo il codice vero |
| `.claude/skills/collaudo-funzionale/` | qui | collaudo end-to-end di un flusso con dati di prova |

I quattro "skill" sono cartelle di istruzioni riusabili: copiate nella nuova
app, un assistente le può eseguire lì con gli stessi criteri usati su Lotti.

---

## 2. LE REGOLE VISIVE (non negoziabili)

### Colori
```css
:root {
  --primary:       #5b7a6b;   /* salvia: il colore dell'app */
  --primary-soft:  #e8efe9;
  --primary-grad:  linear-gradient(135deg, #5b7a6b 0%, #6f9180 100%);
  --sidebar:       #3f5a4e;   /* salvia scuro: header e barre */
  --bg:            #faf7f0;   /* crema: sfondo pagina */
  --card:          #fffefb;   /* bianco caldo: le card */
  --border:        #e6e0d4;
  --border-subtle: #f0ebe0;

  --danger:  #d35f4e;  --danger-soft:  #fbe6e2;  --danger-text:  #8f3829;
  --warning: #c4894a;  --warning-soft: #f7ecdc;  --warning-text: #7d5526;
  --success: #3d8168;  --success-soft: #e2efe8;  --success-text: #234d3d;
  --info:    #8a6f47;  --info-soft:    #f3ead9;  --info-text:    #56442d;

  --text:   #2a3329;   /* testo principale */
  --text-2: #6b7669;   /* testo secondario */
  --text-3: #9aa593;   /* testo tenue */
}
```

**MAI colori freddi**: blu, indaco, viola, ciano, azzurro, e nemmeno i grigi
freddi tipo `slate`. Vanno tutti rimappati su salvia o su sabbia (`#8a6f47`,
scuro `#6f583a`). Vale sia per le classi Tailwind (`bg-blue-*`, `text-slate-*`)
sia per i codici colore scritti a mano negli stili.

**Le ombre non sono grigie**, sono tinte di salvia:
```css
--shadow-card: 0 2px 10px rgba(63,90,78,.06);
--shadow-md:   0 4px 20px rgba(63,90,78,.10);
--shadow-lg:   0 8px 32px rgba(63,90,78,.14);
```

### Caratteri
- Titoli (h1, h2, h3, numeri grandi): **Fraunces**, peso 500-700.
- Tutto il resto: **Plus Jakarta Sans**, peso 400-800.
- Testo base 15px, interlinea 1.5. Etichette in maiuscolo 10-11px, peso 700-800.

### Forme e spazi
- Raggi: 12px bottoni e campi, 16px card, 20px finestre, 999px per le pillole.
- **Ogni cosa da toccare è almeno 44×44 px.** Si lavora con le mani sporche.
- Quando si preme: `transform: scale(.97)`, niente altro.

### Icone
Solo **Lucide** (`lucide-react`). **Mai emoji nelle interfacce**: su Android
vengono colorate dal sistema e diventano blu, fuori palette. (Le emoji nelle
etichette stampate o nei testi sono un altro discorso.)

### Mobile
- Nessuno scroll orizzontale su smartphone, mai. Se una tabella è stretta,
  diventa una lista di card.
- Ogni pagina centrata da un contenitore unico, con larghezza massima.
- Se una barra è fissa in basso, il contenuto sopra deve avere spazio: nessun
  bottone deve finire coperto.

---

## 3. LE REGOLE DI SEMPLICITÀ (è questa la parte che conta davvero)

Sono le scelte che rendono Lotti usabile da chiunque in negozio. Valgono su
qualsiasi app del gruppo.

1. **Una schermata di card grandi come punto di partenza.** Niente menu a
   tendina nascosti: chi apre l'app vede subito riquadri grandi con scritto
   cosa fanno. I menu servono solo per le cose amministrative.

2. **Chi entra vede solo quello che gli serve.** I dipendenti vedono le card
   operative; il resto compare solo dopo il PIN del titolare. Meno cose a
   schermo = meno errori.

3. **Il caso normale deve essere già pronto.** I campi arrivano precompilati
   con la scelta più probabile (data di oggi, quantità 1, posizione più usata)
   e sopra c'è scritto: "Già pronto: tocca Registra. Cambia solo ciò che serve".

4. **Si sceglie da un elenco, non si scrive.** Menu a tendina veri (che su
   telefono si aprono a tutto schermo), mai campi di testo con suggerimenti
   nascosti. Chi ha le mani sporche non digita.

5. **Numeri col tastierino grande**, con i valori più usati come bottoni
   (1, 2, 3, 5, 10...) e i tasti − e + accanto.

6. **Mai le finestrelle grigie del browser** (`alert`, `confirm`, `prompt`):
   si usano avvisi discreti in basso (toast) e finestre di conferma coerenti
   con l'app. Le conferme importanti dicono cosa succederà, non "sei sicuro?".

7. **Gli errori si spiegano in italiano.** Non "Error 500": "Il server non
   risponde, riprova tra poco". Nessun codice tecnico davanti all'utente.

8. **Un dato che manca si dichiara.** Mai una cella vuota che sembra uno zero:
   si scrive "Dato non disponibile" o "N/D". Vale nelle stampe e nei registri.

9. **Niente doppioni per un doppio tocco.** Ogni operazione che scrive
   qualcosa deve essere ripetibile senza creare due volte la stessa cosa.

10. **Sempre una via d'uscita visibile.** In ogni schermata profonda c'è un
    tasto "← Indietro" fisso in alto, che resta lì anche scorrendo.

11. **Il colore ha un significato:** verde = fatto/conforme, ocra = attenzione,
    terracotta = errore o scaduto, sabbia = informazione. Non si usano a caso.

12. **Le pagine si aprono in fretta o dicono che stanno caricando.** Se
    un'attesa supera i due secondi, ci vuole un messaggio ("Carico…"), e se il
    server è lento va detto che sta partendo, non lasciato in bianco.

---

## 4. PROMPT PRONTO PER L'ALTRA APP

Da incollare a un assistente che lavora sul progetto impresasemplice.online,
dopo aver copiato le cartelle indicate al punto 1.

```text
Devi applicare a questa app la veste grafica e le regole di usabilità del
gruppo Ceraldi, già in uso nell'app Lotti. Trovi tutto in design_handoff/:
KIT_ALTRE_APP.md (regole), tokens/*.css (colori, caratteri, misure) e ui_kit/
(prototipo navigabile di riferimento).

REGOLA NUMERO UNO: cambia la grafica, NON il comportamento. Nessuna pagina
viene spostata, nessuna chiamata al server cambia, nessuna funzione sparisce.

Fai in questo ordine:
1. Inventario: elenca le pagine dell'app e, per ognuna, cosa è fuori dalle
   regole (colori freddi, emoji nelle interfacce, testi tecnici, tabelle che
   sborda­no su smartphone, bottoni piccoli sotto i 44px).
2. Fondamenta: porta i token di colore/tipografia nel foglio di stile globale
   e sostituisci i valori sparsi nel codice, senza toccare la logica.
3. Pagina per pagina: applica le regole, partendo dalle due più usate ogni
   giorno. Dopo ogni pagina fai la build e uno screenshot a 390×844 e a
   1024×768 per verificare che non ci sia scroll orizzontale.
4. Semplicità: applica i punti della sezione 3 del kit dove ha senso in questa
   app (precompilazione del caso normale, scelta da elenco, avvisi in italiano,
   dato mancante dichiarato, tasto indietro sempre visibile).
5. Report finale: cosa hai cambiato, cosa hai lasciato e perché, screenshot
   prima/dopo delle pagine principali.

Vincoli: rispondere in italiano, risultati prima delle spiegazioni; leggere il
codice reale prima di dichiarare una causa; mai scrivere PIN, password o token
nel codice o nei file; niente push se la build fallisce.

Nuovo incarico: [scrivi qui da quale pagina vuoi partire]
```

---

## 5. COSA NON C'È IN QUESTO KIT

Il kit copre l'aspetto e il modo di usare l'app. **Non** copre le regole di
dominio di Lotti (FIFO dei lotti, bevande a cartone, richiami ASL, registri
HACCP): quelle sono di questa attività e non vanno portate altrove a scatola
chiusa. Se l'altra app ha regole sue, vanno scritte nel suo file di progetto.
