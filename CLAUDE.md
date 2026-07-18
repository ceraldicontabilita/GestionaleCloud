# Istruzioni per Claude

- Rispondi sempre in italiano, in ogni sessione su questo repo.
- REGOLA PARAMETRI (voluta dall'utente): ogni volta che nel codice o nelle
  specifiche trovi un valore parametrico/configurabile — frequenze di
  scansione (es. "scarica ogni ora"), mittenti attendibili (es. "riceve
  cedolini da questo mittente"), tolleranze e soglie (euro, giorni),
  cartelle Drive, canali accesi/spenti — NON modificarlo di tua iniziativa:
  proponi all'utente una domanda con piu' opzioni di risposta (fino a 5,
  es. via AskUserQuestion) oppure descrivi cosa fa oggi il codice piu'
  fino a 5 possibili correzioni, e aspetta la sua scelta prima di agire.
- Il file LOGICA_FUNZIONAMENTO.md descrive il comportamento reale del
  sistema per gli utenti: tienilo aggiornato quando cambi la logica.
- PIANO DEI CONTI (regola vincolante utente): il piano dei conti e' SOLO CEE,
  quello ufficiale del bilancio del commercialista, memorizzato in
  app/services/piano_conti_ufficiale.py (dettaglio in
  memoria/PIANO_CONTI_UFFICIALE_CERALDI.md). Quando incontri un altro schema
  di conti (es. l'operativo interno 05.01.01 di piano_conti o il numerico
  400100 di contabilita_italiana) convertilo SEMPRE ai codici ufficiali con
  app/services/mapping_piano_conti.py (OPERATIVO_A_UFFICIALE). NON chiedere
  piu' quale schema usare: e' il CEE ufficiale.
- REGOLA CANONICA POS (utente 18/07/2026, definitiva — dettaglio in
  memoria/AUDIT_ESTERNO_18_07_2026.md e LOGICA_FUNZIONAMENTO.md §4):
  cassa DARE = corrispettivo totale XML; cassa AVERE "POS Verso Banca" =
  POS REALE della chiusura manuale serale (fallback XML, fonte tracciata);
  banca DARE = stessa cifra come puro TRASFERIMENTO (source
  trasferimento_pos, stesso trasferimento_id) — una sola operazione su
  due registri, mai duplicazioni; l'accredito dell'estratto conto NON
  crea entrate ma riconcilia il trasferimento del giorno di vendita
  (causale NUMIA); XML = dato fiscale: differenza col reale = "non
  battuto" (saldo progressivo in Coerenza POS) e controllo di
  trascrizione del corrispettivo manuale (manuale ≠ XML → anomalia).
  Ogni scrittura di Prima Nota passa dal motore unico
  app/services/scritture_contabili.py: MAI insert diretti nuovi
  (test-guardia in tests/test_motore_unico_scritture.py).
- SPECIFICA VINCOLANTE F24/cedolini/IRES/IRAP/Chat: il documento
  memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md e' fonte di verita'
  per tutto il motore paghe/fisco (riassunto operativo in memoria/INDEX.md,
  implementazione in app/engines/tributi_engine.py e fiscale_engine.py).
  Regole cardine: il saldo F24 non e' mai automaticamente costo deducibile;
  RC01 = regolarizzazione di periodo precedente, mai imputata al mese
  corrente; associazione F24-cedolini solo a periodo/causale/posizione/
  soggetto coerenti; quietanza senza F24 = alert bloccante "F24 mancante",
  mai ricostruire il modello in automatico.
