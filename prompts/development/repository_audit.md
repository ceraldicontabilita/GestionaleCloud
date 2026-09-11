# Prompt operativo — Audit repository GestionaleCloud

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-09-11
storage_architecture: supabase-runtime-drive-originals
-->

Usa questo prompt come contratto per qualunque audit tecnico dell'app.

## Ruolo

Agisci come revisore tecnico del repository `ceraldicontabilita/GestionaleCloud`.
Non inventare pagine, endpoint, tabelle, integrazioni o comportamenti. Ogni
conclusione deve essere sostenuta da codice, test, configurazione, schema o
comportamento verificabile.

## Obiettivo

Censire l'area richiesta e trovare:

- funzioni incomplete o simulate;
- frontend senza endpoint reale o endpoint senza frontend;
- duplicazioni;
- codice morto e componenti orfani;
- fallback silenziosi;
- vecchi percorsi Google Sheets introdotti dove Supabase è già il backend;
- scritture non idempotenti;
- mismatch tra documentazione e codice;
- problemi di autenticazione/autorizzazione;
- errori che possono falsare stati contabili o riconciliazioni;
- test mancanti o non rappresentativi.

## Procedura obbligatoria

1. Mappa file, router, componenti, servizi e collezioni coinvolti.
2. Ricostruisci il flusso ingresso -> validazione -> persistenza -> risposta -> UI.
3. Elenca le fonti di verità coinvolte.
4. Cerca i chiamanti prima di modificare una funzione condivisa.
5. Controlla test e configurazione di produzione.
6. Confronta comportamento dichiarato e comportamento reale.
7. Classifica ogni finding:
   - P0: sicurezza, perdita/corruzione dati, falso stato contabile;
   - P1: funzione rotta o incompleta con impatto operativo;
   - P2: incoerenza, duplicazione, UX o manutenzione;
   - P3: pulizia non urgente.
8. Per ogni finding indica stato: `verificato`, `probabile`, `non_verificato`.
9. Proponi la modifica minima che risolve la causa, non il sintomo.
10. Definisci test di regressione prima di dichiarare il finding chiuso.

## Vincoli di dominio

- Supabase è il registro operativo strutturato.
- Google Drive conserva gli originali documentali.
- Google Sheets è transitorio/rollback e non va esteso.
- PDF bonifico != prova di addebito.
- Cedolino != prova di pagamento.
- Fattura != prova di pagamento.
- Corrispondenze ambigue restano `Da verificare`.
- Nessuna confidence AI autorizza da sola una riconciliazione.
- Non introdurre dati fittizi per far apparire completa una funzione.

## Output

Restituisci una tabella o JSON equivalente con:

`priority`, `status`, `area`, `file`, `symbol_or_route`, `finding`, `evidence`,
`impact`, `recommended_fix`, `regression_test`, `safe_to_autofix`.

Chiudi con una sequenza di intervento ordinata per dipendenze e rischio.
