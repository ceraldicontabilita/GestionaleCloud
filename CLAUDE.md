# Istruzioni per Claude — GestionaleCloud (Ceraldi ERP)

Riscritto il 07/08/2026 su richiesta dell'utente: solo regole IN VIGORE.
La storia sta in git, non qui.

- Rispondi sempre in italiano, in ogni sessione su questo repo.
- `LOGICA_FUNZIONAMENTO.md` descrive il comportamento reale del sistema per
  gli utenti: tienilo aggiornato quando cambi la logica.
- Scheda rapida (stack, collezioni canoniche, mappa dei documenti):
  `memoria/INDEX.md`.

## Metodo di lavoro

- **UNA COSA ALLA VOLTA** (utente, 07/08/2026): non aprire un lavoro nuovo
  finché quello in corso non è finito, testato e verificato. Una pagina
  chiusa vale più di cinque iniziate.
- REGOLA PARAMETRI: ogni valore parametrico/configurabile — frequenze di
  scansione, mittenti attendibili, tolleranze e soglie (euro, giorni),
  cartelle Drive, canali accesi/spenti — NON si modifica di propria
  iniziativa: proponi all'utente una domanda con più opzioni (fino a 5,
  es. AskUserQuestion) oppure descrivi cosa fa oggi il codice più fino a 5
  possibili correzioni, e aspetta la sua scelta.
- Porta in produzione (merge in `main`, autoDeploy Render) solo su richiesta
  esplicita dell'utente. Quando la chiede, CI verde prima del merge.

## Contabilità (regole vincolanti)

- **PIANO DEI CONTI**: SOLO il CEE ufficiale del commercialista,
  `app/services/piano_conti_ufficiale.py` (dettaglio in
  `memoria/PIANO_CONTI_UFFICIALE_CERALDI.md`). Ogni altro schema (operativo
  05.01.01, numerico 400100) si converte SEMPRE con
  `app/services/mapping_piano_conti.py` (OPERATIVO_A_UFFICIALE). Non chiedere
  quale schema usare: è il CEE.
- **REGOLA CANONICA POS** (18/07/2026, estesa 07/08/2026): cassa DARE =
  corrispettivo totale XML; cassa AVERE "POS … Verso Banca" = POS REALE della
  chiusura serale (mai ricavato dall'XML); dal 07/08 il POS reale è la SOMMA
  dei gestori (Numia + SumUp), campo `gestore` sulle chiusure, righe storiche
  senza campo = Numia; banca DARE = stessa cifra come puro TRASFERIMENTO
  (source `trasferimento_pos`, un trasferimento per circuito, mai fusioni);
  l'accredito dell'estratto conto NON crea entrate — riconcilia il
  trasferimento del giorno di vendita (causale NUMIA, righe accorpate per
  `DEL gg/mm/aa`, vale anche dal CSV); XML = dato fiscale: differenza col
  reale = "non battuto". SumUp accredita il NETTO sulla Mastercard SumUp
  (19.01.05), mai su BPM; Numia accredita il LORDO su BPM e le commissioni
  arrivano fatturate a parte. Conti e circuiti in
  `app/services/conti_pos.py`; NUMIA è il gestore POS, NEXI è la carta di
  credito aziendale.
- **PRIMA NOTA BANCA** (07/08/2026): non è una copia dell'estratto conto.
  Un pagamento entra quando si sa A COSA si riferisce — fattura, cedolino,
  F24, assegno, trasferimento POS. Ciò che non si aggancia resta nella coda
  da riconciliare (`in_attesa_documento`). Uniche eccezioni: le operazioni
  della banca stessa (`CATEGORIE_SENZA_DOCUMENTO` in
  `prima_nota_module/common.py` — commissioni e prelievi), perché quel
  denaro è uscito davvero e senza di loro il saldo sarebbe sbagliato.
- **MOTORE UNICO**: ogni scrittura di Prima Nota passa da
  `app/services/scritture_contabili.py`. MAI insert diretti nuovi
  (test-guardia in `tests/test_motore_unico_scritture.py`).
- **AGGANCIO DOCUMENTI**: numero fattura + importo al centesimo è la regola
  primaria. L'importo da solo non produce mai un'associazione certa;
  l'ambiguità diventa proposta da confermare, mai registrazione definitiva.
  L'associazione manuale confermata da una persona vale come prova.
- **F24/cedolini/IRES/IRAP**: fonte di verità
  `memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md` (motori in
  `app/engines/tributi_engine.py` e `fiscale_engine.py`). Cardini: il saldo
  F24 non è mai automaticamente costo deducibile; RC01 = regolarizzazione di
  periodo precedente, mai imputata al mese corrente; associazione
  F24-cedolini solo a periodo/causale/posizione/soggetto coerenti; quietanza
  senza F24 = alert bloccante, mai ricostruire il modello in automatico.
- **IVA**: `memoria/SPECIFICA_IVA.md`.
- **Fornitori**: `memoria/FORNITORI_REGOLA_CANONICA.md`.
- Date SEMPRE in formato italiano (gg/mm/aaaa) in tutto ciò che l'utente
  legge: descrizioni, pagine, export.

## Documenti e Drive

- Le fatture arrivano SOLO da Drive, mai da Gmail né PEC. Una fattura via
  email genera un'anomalia, non un import.
- Estratti conto: UNA sola cartella `Estratti conto/Da elaborare` per tutte
  le fonti (banca, carta Nexi, PayPal, mutuo, export POS). La fonte si
  riconosce dal nome o dal contenuto (`classificazione_estratti.py`); un
  documento non riconosciuto va in `Errori` col motivo, mai indovinato.
  Arretrato fermo sotto `DRIVE_ESTRATTI_ANNO_MINIMO`. Dettaglio:
  `memoria/DRIVE_ESTRATTI_CONTO.md`.
- Nessuna cancellazione di documenti o dati reali. Nessuna modifica
  automatica se il collegamento non è certo. Conservare sempre fonte, hash,
  data d'importazione e log di audit. I doppioni si marcano, non si
  cancellano.

## Sicurezza e git

- Segreti SOLO nelle variabili d'ambiente (Render → Environment): mai in
  chat, mai in un file, mai nel repo, mai stampati. Un segreto passato per
  un canale sbagliato è bruciato: va ruotato.
- Mai `git add -A`: sempre file espliciti. Mai perdere o sovrascrivere
  modifiche locali.
- Repo di lavoro: SOLO `GestionaleCloud`. `GestionaleCloud-Private` è
  storico e non si usa.
- File da non aggiungere mai in automatico: `README.md`,
  `docs/AUDIT_DRIVE_SICUREZZA_DUPLICATI_2026-08-05.md`,
  `download_emergent_bundle.py`, `tmp/`.
- Le mappe in `memoria/` (MAPPA_ROUTER, MAPPA_ENDPOINT_COMPLETA,
  ENDPOINT_CLASSIFICAZIONE_FINALE, AUDIT_FRONTEND_DEAD_CODE,
  AUDIT_STATIC_REPORT) sono GENERATE dagli script in `scripts/` e verificate
  dalla CI: si rigenerano, non si modificano a mano. Endpoint nuovi →
  rilanciare gli script e committare il risultato.
