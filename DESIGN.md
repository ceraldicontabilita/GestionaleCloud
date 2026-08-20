# DESIGN.md — GestionaleCloud / Ceraldi ERP

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

Design system operativo del frontend di `ceraldicontabilita/GestionaleCloud`.
La fonte eseguibile dei token è `frontend/src/lib/utils.js`; questo documento
spiega come usarli senza creare varianti locali.

## Obiettivo

Questo documento è una vista UI sintetica. Regole, divieti e criteri completi
sono definiti una sola volta in `PROMPT_MASTER.md`.

L'interfaccia deve sembrare un gestionale contabile, non una plancia di
comandi. Ogni pagina deve aiutare a capire subito:

1. quale periodo e archivio si stanno consultando;
2. quali dati sono certi, attesi, riconciliati o da verificare;
3. quale documento o movimento è l'origine del dato;
4. quale azione è automatica e quale richiede una scelta umana.

## Token ufficiali

| Uso | Valore |
|---|---|
| Primario navy | `#0f2744` |
| Primario chiaro | `#1e3a5f` |
| Accento oro | `#b8860b` |
| Sfondo pagina | `#f1f5f9` |
| Superficie/card | `#ffffff` |
| Bordo | `#e2e8f0` |
| Testo | `#0f172a` |
| Testo secondario | `#64748b` |
| Successo | `#15803d` |
| Avviso | `#b45309` |
| Errore | `#b91c1c` |
| Informazione | `#1d4ed8` |

- Font: stack di sistema definito in `FONT.family`.
- Numeri, importi e identificativi: `FONT.mono` quando l'allineamento aiuta il
  confronto.
- Spaziature: `4, 8, 12, 16, 20, 24, 32 px` (`SPACING`).
- Raggi: `6–14 px` per controlli e contenitori; pill solo per badge/stati.
- Ombre: usare esclusivamente `SHADOWS`, con tinta navy.

## Struttura delle pagine

- Usare `PageLayout`/`PageHeader` e i componenti condivisi già presenti.
- Mostrare prima riepilogo e anomalie realmente azionabili, poi filtri, poi
  dati.
- Raggruppare i movimenti per giornata quando la sequenza temporale conta.
- Un alert numerico deve aprire sempre l'elenco dei record che lo compongono.
- Evitare pulsanti diagnostici all'utente finale: deduplicazione, import e
  collegamenti certi devono essere idempotenti e automatici.
- La navigazione tra fattura, documento, pagamento e registrazione deve
  mantenere l'ID operazione canonico e offrire link bidirezionali.

## Stati e semantica

| Stato | Colore | Regola |
|---|---|---|
| Riconciliato/pagato verificato | verde | Esiste una prova collegata e identificabile. |
| Atteso | blu | Registrazione prevista, non ancora riscontrata. |
| Da verificare | arancio | Mancano dati o vi sono più candidati. |
| Errore | rosso | Il flusso non può proseguire senza correzione. |
| Informativo | grigio/blu | Non richiede un'azione immediata. |

Non usare il colore come unica informazione: ogni badge deve avere testo
esplicito. `Attesa quietanza` è lo stato documentale corretto per i verbali;
non usare `attesa fattura` come sinonimo.

## Tabelle, importi e date

- Date visibili: `gg-mm-aaaa`; date API: ISO `aaaa-mm-gg`.
- Importi: due decimali, separatori italiani e segno coerente con Dare/Avere.
- Mostrare sempre origine, ID operazione e collegamenti alle prove.
- Non fondere righe diverse solo perché hanno stesso importo.
- Le liste grandi devono avere ricerca, filtri, paginazione e stato vuoto
  esplicito.

## Modali e documenti

- Il visualizzatore deve stare sopra ogni altro dialog, con `z-index` coerente.
- Deve chiudersi con pulsante evidente, `Esc` e ritorno del focus al comando
  che lo ha aperto.
- Il contenuto non deve apparire sotto una finestra precedente né lasciare
  overlay bloccati.
- Per PDF e fatture privilegiare una vista ampia, responsiva e stampabile.

## Responsive e accessibilità

- Desktop: sfruttare la larghezza senza perdere la gerarchia visiva.
- Tablet/mobile: trasformare le tabelle dense in card leggibili e mantenere le
  azioni primarie raggiungibili.
- Tutti i controlli devono avere etichetta, focus visibile e area cliccabile
  adeguata.
- Non introdurre Tailwind o un secondo sistema di token.

## Verifica di una modifica UI

1. test Vitest interessati;
2. build Vite senza errori;
3. prova della pagina con dati, vuoto, errore e caricamento;
4. controllo modali, focus, filtri, anno globale e link bidirezionali;
5. nessuna informazione critica disponibile soltanto tramite colore.
