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
- SPECIFICA VINCOLANTE F24/cedolini/IRES/IRAP/Chat: il documento
  memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md e' fonte di verita'
  per tutto il motore paghe/fisco (riassunto operativo in memoria/INDEX.md,
  implementazione in app/engines/tributi_engine.py e fiscale_engine.py).
  Regole cardine: il saldo F24 non e' mai automaticamente costo deducibile;
  RC01 = regolarizzazione di periodo precedente, mai imputata al mese
  corrente; associazione F24-cedolini solo a periodo/causale/posizione/
  soggetto coerenti; quietanza senza F24 = alert bloccante "F24 mancante",
  mai ricostruire il modello in automatico.
