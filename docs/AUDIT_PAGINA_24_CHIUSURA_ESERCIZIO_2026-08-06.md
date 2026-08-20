# Audit pagina 24 — Chiusura esercizio

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Data: 2026-08-06
Pagina: `/contabilita/chiusura`
API: `/api/chiusura-esercizio/*`

## Esito

La pagina precedente non era utilizzabile per una chiusura contabile reale. Il bilancino
ricostruiva ricavi e costi direttamente da corrispettivi e fatture, ignorava la completezza
del registro in partita doppia e poteva quindi mostrare un utile non dimostrato. La scrittura
generata era inoltre priva di righe Dare/Avere.

La pagina usa ora come unica fonte il registro definitivo `movimenti_contabili`. Se il registro
è vuoto, incompleto, non valido o non quadrato, il risultato non viene sostituito con zero e non
viene stimato: viene mostrato come **non disponibile** e la chiusura resta bloccata.

## Evidenza read-only prima della correzione

- Esercizio 2025: 0 scritture valide nel registro; 1.176 fatture e 347 corrispettivi ancora da
  registrare. Il vecchio bilancino mostrava comunque un utile di `EUR 467.421,59`.
- Esercizio 2026: 1 scrittura valida; 272 fatture e 171 corrispettivi ancora da registrare.
  Il vecchio bilancino mostrava comunque un utile di `EUR 363.802,59`.
- Storico chiusure reale: 0 record. Non risultano quindi chiusure già eseguite con la vecchia
  scrittura non quadrata.
- Nessun dato di produzione è stato modificato durante il collaudo.

## Correzioni

1. La verifica usa i flag canonici `registrata_contabilita` e `registrato_contabilita` tramite
   il motore unico del bilancio di verifica.
2. Sono bloccanti: esercizio corrente o futuro, registro vuoto/incompleto/non quadrato, mesi RT
   mancanti, TFR mancante in presenza di salari, ammortamenti mancanti e movimenti bancari non
   riconciliati.
3. Il bilancino somma esclusivamente i saldi dei conti `04.*` (ricavi) e `05.*` (costi) presenti
   nel registro valido.
4. La chiusura richiede entrambe le conferme logiche e la frase esatta `CHIUDI <anno>`.
5. La scrittura chiude ogni conto economico e rileva utile/perdita sul conto `03.03.01`; il
   motore comune verifica l'uguaglianza Dare/Avere ed evita duplicazioni per anno.
6. L'apertura richiede `APRI <anno>`, impedisce una seconda apertura e salva solo uno snapshot
   di audit. Non crea movimenti di riporto duplicati in Prima Nota.
7. I saldi Cassa/Banca d'apertura provengono dall'aggregatore canonico, comprese esclusioni e
   saldo iniziale manuale. I debiti fornitori rispettano data di chiusura, soft-delete e residuo
   delle fatture parzialmente pagate.
8. La UI mostra fonte, numero di scritture, backlog e quadratura; non visualizza più importi
   mancanti come `EUR 0,00`.

## Test eseguiti

- Backend mirato: 21 test superati.
- Frontend mirato: 2 test superati.
- Backend completo: 1.166 superati, 2 saltati.
- Frontend completo: 23 file, 106 test superati.
- Build produzione: 3.077 moduli trasformati, completata.

## Limite operativo corretto

La pagina non può sostituire l'attività del commercialista. Consente la chiusura solo dopo che
il registro definitivo è completo e quadrato; l'operazione reale resta volontaria, esplicita e
tracciata.

## Pubblicazione e collaudo live

- PR `#125`, merge `20fa8279226ce6b5bd99799758f037beebede21a`.
- Deploy Render `dep-d9q4ccp42hec73c3fdu0` in stato `live`; health `healthy`, database
  `connected`, commit pubblicato `20fa8279`.
- Collaudo autenticato eseguito con ruolo `sola_lettura` e sole richieste GET. Nessuna chiusura,
  apertura o altra scrittura è stata eseguita.
- 2025: chiusura bloccata per registro vuoto, 1.176 fatture e 347 corrispettivi da registrare,
  16 cespiti senza ammortamento e 2.359 movimenti bancari non riconciliati.
- 2026: chiusura bloccata perché l'esercizio è ancora in corso, oltre a 272 fatture, 171
  corrispettivi e 1.668 movimenti bancari non riconciliati.
- Per entrambi gli esercizi l'API restituisce `disponibile: false` e `bilancino: null`, evitando
  risultati stimati o zeri fittizi.
- Il bundle pubblicato `ChiusuraEsercizio-CgUQWVlm.js` contiene lo stato `Bilancino non
  disponibile` e le conferme forti `CHIUDI` e `APRI`.
