# Specifica definitiva — Gestione IVA mensile, fatture ricevute entro il 15, controllo annuale e Chat intelligente

<!-- gestionalecloud-doc
status: reference
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

> [!IMPORTANT]
> Documento di riferimento del dominio. Per persistenza e cutover vale l'architettura Drive-only descritta nei documenti correnti; eventuali nomi Mongo/collection restano compatibilità o contesto storico.

## 1. Obiettivo

Realizzare nel gestionale contabile un motore IVA capace di:

- acquisire le fatture di acquisto elettroniche;
- distinguere data documento, data operazione, data ricezione SDI e data registrazione;
- attribuire ogni fattura al corretto periodo IVA;
- gestire le fatture ricevute entro il giorno 15 del mese successivo;
- evitare che la stessa IVA venga detratta due volte;
- gestire correttamente il passaggio dicembre-gennaio;
- conservare la cronologia delle liquidazioni;
- individuare l'IVA ancora disponibile e non utilizzata;
- alimentare il riepilogo annuale;
- consentire alla Chat intelligente di spiegare ogni scelta.

## 2. Principio fondamentale

La data in cui una fattura viene ricevuta non coincide necessariamente con il periodo IVA nel quale viene utilizzata.

Esempio:

- fattura relativa a gennaio;
- ricevuta l'8 febbraio;
- registrata entro il 15 febbraio;
- IVA attribuita alla liquidazione di gennaio.

Quella fattura compare documentalmente tra le fatture ricevute a febbraio, ma deve risultare fiscalmente utilizzata nella liquidazione IVA di gennaio e non deve essere conteggiata di nuovo nella liquidazione IVA di febbraio.

Il gestionale deve quindi separare sempre:

1. mese di ricezione;
2. periodo IVA attribuito;
3. liquidazione nella quale l'IVA è stata effettivamente utilizzata.

## 3. Regola dei 12 giorni

Il termine dei 12 giorni riguarda l'emissione della fattura immediata da parte del fornitore dopo l'effettuazione dell'operazione.

Non è una tolleranza concessa al cliente per la detrazione IVA.

Il gestionale deve usare questa regola come controllo documentale sul fornitore:

- data operazione;
- data documento;
- data trasmissione allo SDI;
- giorni trascorsi;
- anomalia se la trasmissione supera il termine previsto.

Questo controllo non determina automaticamente il periodo IVA dell'acquirente.

## 4. Regola del giorno 15

Per le fatture relative a operazioni effettuate nel mese precedente, l'IVA può essere attribuita alla liquidazione del mese precedente quando:

- la fattura è ricevuta entro il giorno 15 del mese successivo;
- la fattura è annotata entro il giorno 15 del mese successivo;
- l'operazione appartiene allo stesso anno solare.

Esempio:

- operazione: 31 gennaio 2026;
- ricezione SDI: 8 febbraio 2026;
- registrazione: 10 febbraio 2026;
- IVA: €220.

Risultato:

- mese ricezione: febbraio 2026;
- periodo IVA attribuito: gennaio 2026;
- liquidazione utilizzata: gennaio 2026;
- IVA utilizzata: sì;
- disponibilità per febbraio: no.

## 5. Fattura ricevuta dopo il giorno 15

Esempio:

- operazione: 31 gennaio;
- ricezione: 18 febbraio;
- registrazione: 18 febbraio.

La fattura non deve essere retroattribuita a gennaio.

Risultato:

- mese ricezione: febbraio;
- periodo IVA attribuito: febbraio;
- IVA disponibile per la liquidazione di febbraio o successiva;
- motivo: ricevuta dopo il termine del giorno 15.

## 6. Eccezione dicembre-gennaio

La regola del giorno 15 non deve essere applicata alle operazioni dell'anno precedente.

Esempio:

- operazione: 31 dicembre 2025;
- ricezione: 8 gennaio 2026;
- registrazione: 8 gennaio 2026.

Risultato:

- mese ricezione: gennaio 2026;
- periodo IVA attribuito: gennaio 2026;
- divieto di retroattribuzione a dicembre 2025;
- motivo: operazione appartenente all'anno precedente.

Il sistema deve bloccare ogni tentativo di includere in dicembre una fattura ricevuta nel nuovo anno.


## 7. Campi obbligatori per ogni fattura

### Date

- `data_documento`
- `data_operazione`
- `data_trasmissione_sdi`
- `data_ricezione_sdi`
- `data_registrazione`
- `data_importazione_gestionale`

### Periodi

- `mese_documento`
- `mese_operazione`
- `mese_ricezione`
- `periodo_iva_teorico`
- `periodo_iva_attribuito`
- `periodo_iva_utilizzato`

### Stato IVA

- `iva_detraibile`
- `iva_utilizzata`
- `importo_iva_utilizzato`
- `liquidazione_id`
- `data_utilizzo_iva`
- `regola_applicata`
- `motivo_esclusione`
- `disponibile_per_nuovo_calcolo`
- `versione_calcolo`

## 8. Stati della detrazione IVA

Il campo `stato_detrazione_iva` deve ammettere almeno:

- `NON_VALUTATA`
- `DA_INSERIRE`
- `INSERITA_IN_LIQUIDAZIONE`
- `ESCLUSA`
- `RINVIATA`
- `RETTIFICATA`
- `RECUPERATA_IN_DICHIARAZIONE_ANNUALE`
- `INDETRAIBILE`
- `DA_VERIFICARE`

Significato:

- `NON_VALUTATA`: fattura importata ma non ancora analizzata.
- `DA_INSERIRE`: IVA disponibile e non ancora utilizzata.
- `INSERITA_IN_LIQUIDAZIONE`: IVA già utilizzata in una liquidazione specifica.
- `ESCLUSA`: IVA non utilizzata per scelta manuale o motivo fiscale.
- `RINVIATA`: IVA rinviata a un periodo successivo.
- `RETTIFICATA`: fattura o liquidazione modificata dopo una precedente attribuzione.
- `RECUPERATA_IN_DICHIARAZIONE_ANNUALE`: IVA non utilizzata mensilmente ma recuperata nella dichiarazione annuale.
- `INDETRAIBILE`: IVA non detraibile per natura o limitazione fiscale.
- `DA_VERIFICARE`: dati incompleti o incoerenti.

## 9. Regole di attribuzione automatica

### Regola A — stesso mese

Se mese operazione e mese ricezione coincidono, la registrazione è valida e l'IVA è detraibile:

- periodo IVA attribuito = mese ricezione.

### Regola B — entro il 15 del mese successivo

Se:

- il mese di ricezione è quello successivo all'operazione;
- la ricezione avviene entro il giorno 15;
- la registrazione avviene entro il giorno 15;
- l'anno è lo stesso;

allora:

- periodo IVA attribuito = mese operazione;
- regola applicata = `ENTRO_15_MESE_SUCCESSIVO`.

### Regola C — dopo il 15

Se la ricezione avviene oltre il giorno 15:

- periodo IVA attribuito = mese ricezione;
- regola applicata = `RICEVUTA_DOPO_IL_15`.

### Regola D — cambio anno

Se l'anno di ricezione è successivo all'anno dell'operazione:

- il periodo IVA attribuito non può essere l'anno precedente;
- regola applicata = `OPERAZIONE_ANNO_PRECEDENTE`.

### Regola E — fattura già utilizzata

Se `iva_utilizzata = true`:

- la fattura deve essere esclusa da ogni nuovo calcolo;
- il sistema deve mostrare la liquidazione in cui è stata già utilizzata.


## 10. Calcolo mensile IVA

Per calcolare la liquidazione del mese `M`, il sistema deve selezionare solo le fatture che rispettano tutte le condizioni:

```text
periodo_iva_attribuito = M
iva_utilizzata = false
iva_detraibile > 0
stato_documento = valido
fattura_non_duplicata = true
stato_detrazione_iva in [DA_INSERIRE, NON_VALUTATA, RINVIATA]
```

Formula:

```text
IVA a credito del mese =
somma dell'IVA detraibile
delle fatture attribuite al periodo M
e non ancora utilizzate
```

Dopo la conferma:

```text
iva_utilizzata = true
periodo_iva_utilizzato = M
liquidazione_id = identificativo liquidazione
data_utilizzo_iva = data conferma
stato_detrazione_iva = INSERITA_IN_LIQUIDAZIONE
disponibile_per_nuovo_calcolo = false
```

## 11. Divieto di duplicazione

Il sistema deve impedire:

- la stessa fattura in due liquidazioni;
- lo stesso importo IVA detratto due volte;
- una fattura ricevuta a febbraio ma già usata a gennaio conteggiata ancora a febbraio;
- una fattura di dicembre ricevuta a gennaio attribuita a dicembre;
- una fattura con `iva_utilizzata = true` inserita in un nuovo calcolo;
- una liquidazione confermata modificata senza rettifica.

Messaggio obbligatorio:

> Fattura ricevuta nel mese corrente ma già utilizzata nella liquidazione precedente. Non verrà conteggiata nuovamente.

## 12. Liquidazione provvisoria e definitiva

Ogni liquidazione IVA deve avere uno stato:

- `BOZZA`
- `CALCOLATA`
- `DA_VERIFICARE`
- `CONFERMATA`
- `TRASMESSA`
- `RIAPERTA`
- `RETTIFICATA`

Una liquidazione confermata non deve essere sovrascritta.

## 13. Versionamento delle liquidazioni

Ogni ricalcolo deve creare una nuova versione.

Campi:

- `liquidazione_id`
- `versione`
- `data_creazione`
- `data_conferma`
- `utente`
- `motivo_modifica`
- `totale_iva_vendite`
- `totale_iva_acquisti`
- `credito_precedente`
- `debito_periodo`
- `credito_periodo`
- `saldo`
- `fatture_incluse`
- `fatture_escluse`


## 14. Pagina "IVA disponibile non ancora utilizzata"

Creare una pagina dedicata con:

- fornitore;
- numero fattura;
- data documento;
- data operazione;
- data ricezione;
- data registrazione;
- imponibile;
- IVA;
- periodo IVA teorico;
- primo periodo utile;
- ultimo periodo utile;
- stato;
- motivo mancata detrazione;
- anomalia;
- azione manuale.

Filtri:

- Non utilizzata
- Esclusa manualmente
- Ricevuta dopo il 15
- A cavallo d'anno
- IVA indetraibile
- Documento duplicato
- Dati incompleti
- Da recuperare annualmente
- Da verificare

## 15. Colonne della pagina fatture

| Colonna | Esempio |
|---|---|
| Numero fattura | 123/2026 |
| Fornitore | Alfa S.r.l. |
| Data documento | 31/01/2026 |
| Data operazione | 31/01/2026 |
| Data ricezione SDI | 08/02/2026 |
| Data registrazione | 10/02/2026 |
| Mese ricezione | Febbraio 2026 |
| Periodo IVA attribuito | Gennaio 2026 |
| IVA utilizzata | Sì |
| Liquidazione utilizzata | Gennaio 2026 |
| Regola applicata | Entro il 15 |
| Disponibile per nuovo calcolo | No |
| Motivo esclusione dal mese corrente | Già utilizzata a gennaio |
| Stato | Inserita in liquidazione |

## 16. Riepilogo annuale

Il sistema deve distinguere:

| Categoria | Contenuto |
|---|---|
| IVA disponibile | IVA potenzialmente detraibile |
| IVA utilizzata | IVA già detratta nelle liquidazioni |
| IVA non utilizzata | Fatture rimaste fuori |
| IVA indetraibile | IVA esclusa per natura |
| IVA rettificata | Correzioni |
| IVA recuperata annualmente | IVA recuperata nella dichiarazione |
| IVA da verificare | Documenti incompleti |
| IVA rinviata | Fatture attribuite a periodi successivi |

Per ogni fattura deve essere disponibile una cronologia completa:

```text
ricevuta a febbraio
attribuita a gennaio
utilizzata nella liquidazione di gennaio
esclusa automaticamente dalla liquidazione di febbraio
confermata nel riepilogo annuale
```

## 17. Calcolo annuale

Il calcolo annuale non deve ricostruire l'IVA soltanto dalla data di ricezione.

Deve partire da:

1. liquidazioni mensili confermate;
2. fatture con IVA utilizzata;
3. fatture non utilizzate;
4. rettifiche;
5. IVA indetraibile;
6. IVA recuperata annualmente;
7. crediti e debiti riportati.

Formula logica:

```text
IVA annuale detraibile =
IVA già utilizzata nelle liquidazioni
+ IVA recuperabile non ancora utilizzata
- IVA rettificata o resa indetraibile
```

Il sistema deve evitare che una fattura già usata mensilmente venga recuperata nuovamente nella dichiarazione annuale.


## 18. Controlli automatici

### Controlli bloccanti

- fattura duplicata;
- stessa IVA in due liquidazioni;
- periodo IVA incoerente;
- fattura dicembre-gennaio retroattribuita;
- fattura ricevuta dopo il 15 attribuita al mese precedente;
- fattura già utilizzata reinserita;
- liquidazione confermata modificata senza riapertura;
- importo IVA negativo o incoerente;
- documento annullato incluso nel calcolo.

### Controlli di avviso

- data operazione mancante;
- data ricezione SDI mancante;
- data registrazione mancante;
- fattura emessa oltre 12 giorni;
- IVA parzialmente detraibile;
- fattura non utilizzata da molti mesi;
- fattura disponibile per il recupero annuale;
- differenza tra XML e registrazione contabile.

## 19. Azioni manuali consentite

L'utente amministratore può:

- includere una fattura;
- escludere una fattura;
- rinviare una fattura;
- correggere il periodo IVA;
- riaprire una liquidazione;
- creare una rettifica;
- indicare IVA indetraibile;
- segnare IVA recuperata annualmente.

Ogni azione deve richiedere:

- motivazione;
- data;
- utente;
- documento di supporto;
- vecchio valore;
- nuovo valore.

## 20. Chat intelligente

La Chat intelligente deve poter rispondere con tracciabilità.

Esempio:

> La fattura è stata ricevuta l'8 febbraio 2026, ma riguarda gennaio ed è stata registrata entro il 15 febbraio. L'IVA è stata attribuita alla liquidazione di gennaio. A febbraio la fattura resta visibile come documento ricevuto, ma non viene conteggiata di nuovo.

Esempio:

> Ho trovato €1.350 di IVA nelle fatture ricevute a febbraio. Di queste, €800 erano già state attribuite e utilizzate nella liquidazione di gennaio. Nella liquidazione di febbraio considero quindi soltanto €550.

Esempio:

> La fattura riguarda dicembre 2025 ma è stata ricevuta a gennaio 2026. Non può essere attribuita a dicembre. L'IVA è stata assegnata a gennaio 2026.

Esempio:

> Questa fattura non risulta utilizzata in alcuna liquidazione. È disponibile per il ricalcolo o per la verifica annuale.


## 21. Dashboard IVA

La dashboard mensile deve mostrare:

- IVA vendite;
- IVA acquisti del mese;
- IVA acquisti ricevuta nel mese ma attribuita al mese precedente;
- IVA già utilizzata;
- IVA non utilizzata;
- IVA rinviata;
- IVA indetraibile;
- credito precedente;
- saldo del mese;
- anomalie;
- liquidazione in bozza o confermata.

La dashboard annuale deve mostrare:

- totale IVA vendite;
- totale IVA acquisti utilizzata;
- totale IVA non utilizzata;
- totale IVA recuperata annualmente;
- totale IVA indetraibile;
- rettifiche;
- credito finale;
- debito finale;
- fatture ancora da verificare.

## 22. Modello dati suggerito

### Collection `fatture_acquisto`

```json
{
  "id": "uuid",
  "fornitore_id": "uuid",
  "numero_fattura": "string",
  "data_documento": "date",
  "data_operazione": "date",
  "data_trasmissione_sdi": "datetime",
  "data_ricezione_sdi": "datetime",
  "data_registrazione": "date",
  "mese_ricezione": "YYYY-MM",
  "periodo_iva_teorico": "YYYY-MM",
  "periodo_iva_attribuito": "YYYY-MM",
  "periodo_iva_utilizzato": "YYYY-MM|null",
  "imponibile": 0,
  "iva_totale": 0,
  "iva_detraibile": 0,
  "iva_utilizzata": false,
  "importo_iva_utilizzato": 0,
  "liquidazione_id": null,
  "stato_detrazione_iva": "NON_VALUTATA",
  "regola_applicata": null,
  "motivo_esclusione": null,
  "disponibile_per_nuovo_calcolo": true,
  "duplicata": false,
  "annullata": false,
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### Collection `liquidazioni_iva`

```json
{
  "id": "uuid",
  "periodo": "YYYY-MM",
  "versione": 1,
  "stato": "BOZZA",
  "iva_vendite": 0,
  "iva_acquisti": 0,
  "credito_precedente": 0,
  "saldo": 0,
  "fatture_incluse": [],
  "fatture_escluse": [],
  "data_calcolo": "datetime",
  "data_conferma": null,
  "motivo_rettifica": null,
  "created_by": "user_id"
}
```

### Collection `movimenti_iva_fattura`

```json
{
  "id": "uuid",
  "fattura_id": "uuid",
  "tipo_movimento": "ATTRIBUZIONE|UTILIZZO|ESCLUSIONE|RETTIFICA|RECUPERO_ANNUALE",
  "periodo": "YYYY-MM",
  "importo_iva": 0,
  "liquidazione_id": "uuid|null",
  "motivazione": "string",
  "created_at": "datetime",
  "created_by": "user_id"
}
```


## 23. Endpoint suggeriti

```text
POST   /api/iva/fatture/importa
GET    /api/iva/fatture
GET    /api/iva/fatture/non-utilizzate
PATCH  /api/iva/fatture/{id}/attribuzione
PATCH  /api/iva/fatture/{id}/escludi
PATCH  /api/iva/fatture/{id}/rinvia
POST   /api/iva/liquidazioni/calcola
POST   /api/iva/liquidazioni/{id}/conferma
POST   /api/iva/liquidazioni/{id}/riapri
POST   /api/iva/liquidazioni/{id}/rettifica
GET    /api/iva/liquidazioni/{periodo}
GET    /api/iva/riepilogo-annuale/{anno}
GET    /api/iva/anomalie
```

## 24. Test obbligatori

### Test 1 — ricevuta entro il 15

- documento gennaio;
- ricezione 8 febbraio;
- registrazione 10 febbraio;
- attribuzione gennaio;
- esclusione automatica da febbraio.

### Test 2 — ricevuta dopo il 15

- documento gennaio;
- ricezione 18 febbraio;
- attribuzione febbraio.

### Test 3 — cambio anno

- documento dicembre;
- ricezione gennaio;
- attribuzione gennaio;
- blocco retroattribuzione a dicembre.

### Test 4 — doppia detrazione

- fattura già usata a gennaio;
- tentativo di inserirla a febbraio;
- blocco.

### Test 5 — ricalcolo

- liquidazione in bozza;
- aggiunta fattura;
- nuovo risultato;
- conferma;
- blocco modifiche senza riapertura.

### Test 6 — riepilogo annuale

- fatture usate;
- fatture non usate;
- IVA indetraibile;
- rettifiche;
- recupero annuale;
- nessuna duplicazione.

## 25. Regola finale vincolante

La data di ricezione stabilisce quando il documento diventa disponibile.

Il campo `periodo_iva_attribuito` stabilisce in quale liquidazione deve essere considerato.

Il flag `iva_utilizzata` impedisce che la stessa IVA venga detratta una seconda volta.

Il calcolo mensile e il controllo annuale devono basarsi sullo stato effettivo di utilizzo dell'IVA e non soltanto sulla data del documento o sulla data di ricezione.
