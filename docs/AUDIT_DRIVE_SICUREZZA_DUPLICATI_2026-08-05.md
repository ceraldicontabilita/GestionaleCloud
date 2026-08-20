# Audit Drive: sicurezza e duplicati

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

Data controllo: 5 agosto 2026
Perimetro: 26 cartelle Drive indicate dal titolare

## Esito sintetico

- 477 cartelle e 13.697 file controllati in sola lettura prima delle modifiche.
- Tutti i 13.697 file dispongono di checksum Drive verificabile.
- Individuati 3.346 gruppi di contenuti byte-per-byte identici, per 5.306 copie eccedenti potenziali.
- Isolate 2.976 copie sicuramente ridondanti, pari a 443.215.573 byte (422,68 MiB), e successivamente spostate nel Cestino recuperabile dopo la quadratura finale.
- Tre ulteriori file previsti dal piano sono stati spostati automaticamente dal gestionale in `Elaborate` durante l'audit e sono stati correttamente conservati.
- Conservate 2.327 copie identiche collocate in percorsi organizzativi distinti, perché la posizione può avere valore documentale o operativo.
- Conservati tutti i file collegati tramite ID al database e tutte le cartelle operative `Da elaborare`, `Elaborate` ed `Errori`.

## Criterio di quarantena

Sono state spostate soltanto copie con hash e dimensione identici quando ricorreva almeno una di queste condizioni:

- duplicato nella stessa posizione;
- copia ridondante nella radice dell'area;
- copia già presente in un percorso più affidabile rispetto a `Da elaborare` o `Errori`;
- copia multipla nella medesima cartella di archivio.

Le quarantene sono denominate `QUARANTENA DUPLICATI ESATTI - VERIFICA 2026-08-05`. Dopo la verifica puntuale di nome, posizione, permessi e contenuto, le 11 cartelle di quarantena sono state spostate nel Cestino di Drive. I 2.976 file risultano ancora presenti e recuperabili; il Cestino non è stato svuotato.

## Avviso Google relativo a malware

- Nell'interfaccia del proprietario è stato identificato il file effettivamente segnalato da Google: `07120220159367366000 quietanza.pdf`, PDF di 31 kB, collocato in `Il mio Drive > Da elaborare` e indicato come `Segnalato per comportamento illecito`.
- Il documento contabile è stato conservato. La segnalazione ne impedisce l'accesso tramite API al service account, quindi non è stato possibile eseguire una verifica locale del contenuto del PDF e non viene formulata alcuna conclusione tecnica sulla causa della segnalazione.
- È stato rimosso l'accesso pubblico ereditato dalla cartella principale `GESTIONALE`, riducendo immediatamente l'esposizione del file e di tutte le cartelle figlie.
- L'archivio `Cedolini_riorganizzati.zip`, creato il 3 agosto 2026, è stato controllato separatamente: contiene 1.539 PDF, nessun elemento cifrato, collegamento simbolico, percorso anomalo o estensione eseguibile; Microsoft Defender non ha rilevato minacce.
- 1.517 PDF dell'archivio sono già presenti su Drive con hash identico; 22 risultano unici. L'archivio è stato conservato perché non è eliminabile con certezza.
- Degli elementi unici, 14 sono anteriori al 2018 e non sono stati importati o riproposti; 8 sono dal 2018 in poi.

## Condivisioni e rischio residuo

Il proprietario ha impostato la cartella principale `GESTIONALE` su `Con limitazioni` e ha rimosso l'accesso ereditato `Chiunque abbia il link`. La verifica API successiva conferma zero permessi pubblici sulla cartella principale e su tutte le 26 cartelle indicate.

Il service account del gestionale è rimasto editor nominativo in tutte le 26 cartelle e conserva i permessi di aggiunta e modifica. Le sei cartelle configurate nell'ambiente applicativo risultano accessibili e contengono ciascuna `Da elaborare`, `Elaborate` ed `Errori`.

Resta aperta soltanto la segnalazione Google sul PDF identificato: la restrizione della condivisione non annulla automaticamente lo stato di abuso. Un'eventuale richiesta di revisione deve essere presentata dal proprietario dopo la verifica documentale del PDF.

## Controlli finali

- Quadratura Cestino: 11 cartelle attese, 11 spostate; 2.976 file attesi, 2.976 ancora presenti e recuperabili.
- Tutte le 26 cartelle indicate risultano private, non cestinate e modificabili dal service account.
- Le cartelle operative `Da elaborare`, `Elaborate` ed `Errori` sono presenti in tutte le sei aree configurate nell'applicazione.
- File unici e riferimenti del database non rimossi.
- Nessuna eliminazione permanente eseguita.
- Copia locale temporanea dello ZIP e piani contenenti nomi/ID cancellati al termine dell'attività.
