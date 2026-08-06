# Audit pagina 23 - Finanziaria

Data: 2026-08-06
Percorso: `/contabilita/finanziaria`
Endpoint canonico: `GET /api/finanziaria/summary?anno={anno}`
Modalita collaudo dati: sola lettura

## Esito tecnico prima del deploy

La route React e l'endpoint backend sono collegati. La pagina legge Prima Nota
Cassa, Prima Nota Banca, corrispettivi e fatture passive; non esegue scritture
contabili durante il caricamento.

Difetti reali riprodotti sui dati 2026:

- il valore chiamato `Saldo` era la sola variazione dei flussi dell'anno,
  pari a EUR 581.144,68;
- la disponibilita contabile Cassa + Banca era invece EUR 282.586,86;
- la differenza, EUR 298.557,82, corrispondeva al riporto iniziale Banca
  negativo non mostrato nel KPI;
- i crediti clienti venivano mostrati come EUR 0,00 pur non esistendo una
  fonte canonica delle fatture attive;
- la riga Salari interrogava un campo storico non uniforme e si presentava
  come una terza fonte, anche se i pagamenti erano gia compresi nelle uscite
  Banca.

## Correzioni

- separati `flow_balance` (variazione dell'anno) e `available_balance`
  (disponibilita contabile comprensiva dei riporti);
- mantenuto `balance` come alias retrocompatibile della variazione annuale;
- esposti `opening_balance`, fonte e nota del calcolo;
- aggiunta la colonna Riporto iniziale e corretto il totale finale della
  tabella su `saldo_totale`;
- rimossa la riga Salari dal totale della pagina e documentata la grana
  distinta cedolino/acconto/saldo;
- i crediti clienti senza fonte sono ora `Non disponibile`, non zero;
- l'IVA e indicata espressamente come stima documentale, distinta dalla
  liquidazione del commercialista e dal pagamento F24;
- resa deterministica la suite frontend limitando jsdom a due worker.

## Test eseguiti

- backend completo: 1.162 passati, 2 saltati;
- frontend completo: 22 file, 104 test passati;
- regressioni pagina Finanziaria: 2 backend e 3 frontend;
- regressioni saldi/riporti: 11 test passati;
- build produzione: 3.077 moduli trasformati;
- artefatti `frontend/dist` ripuliti dopo la verifica, non inclusi nella PR.

## Chiusura

Lo stato `[x] VERIFICATA` nel registro pagine verra applicato soltanto dopo
merge, deploy e ripetizione del controllo autenticato con dati reali in sola
lettura.
