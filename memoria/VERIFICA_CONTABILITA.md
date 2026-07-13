# Verifica di conformità — Motori Contabili

_Loop /goal, 13/07/2026. Sola lettura, contro `LOGICA_FUNZIONAMENTO.md`
(§4 Prima Nota, §5 POS, §6 Riconciliazione), `CLAUDE.md`, `memoria/moduli/*`.
Nessuna modifica al codice._

**Esito**: 1 P0 **latente** (condizionato all'attivazione del canale Estratti
Conto, oggi spento), 3 P1 sulla riconciliazione, vari P2. Regola cardine
"F24 mai costo automatico", ricavi=solo corrispettivi, e coerenza POS:
**tutti conformi**.

## Tabella area → stato → evidenza

| # | Area | Stato | Evidenza |
|---|------|-------|----------|
| 1 | Prima Nota — movimenti da azione precisa | CONFORME (sostanza) / dubbio su modello e inserimento libero | `corrispettivi_helpers.py:144-226`; `cassa.py:83-137` |
| 2 | Coerenza POS (calendario/segni/quadratura) | CONFORME | `pos_corrispettivi_check.py:753-808,901-932` |
| 3 | Riconciliazione bancaria (filtri/stati/no doppi match) | NON CONFORME | `riconciliazione_bancaria.py:591-812`; `bank_statement_import.py:912-939`; `operazioni_module/smart.py:210-285` |
| 4 | Bilancio — attivo/passivo, F24 non è costo | CONFORME | `bilancio.py:171-348`; `piano_conti.py:409-428` |
| 5 | Piano dei conti | CONFORME | `piano_conti.py:136-430` |
| 6 | Centri di costo (cucina/516,46/misto) | CONFORME (motore unico) / dubbio soglia; router legacy NON CONFORME | `learning_machine_cdc.py:60-218,705-709`; `accounting/centri_costo.py:563-599` |
| 7 | Corrispettivi = unica fonte ricavi | CONFORME | `bilancio.py:257-278` |
| 8 | Bonifici / Estratti conto | dubbio (doppio conteggio POS latente) | `estratto_conto.py:527-612` |

## P0 (latente)
**P0-1 — Possibile DOPPIO CONTEGGIO del POS in `prima_nota_banca`.** All'import
corrispettivo si crea una entrata sintetica "Corrispettivi POS" in banca
(`corrispettivi_helpers.py:203-224`); all'import estratto conto il "sync generico"
inserisce in `prima_nota_banca` ogni movimento EC non riconciliato, incluso
l'accredito NUMIA reale (`estratto_conto.py:557-604`). Il motore auto per gli
accrediti POS cerca solo in `prima_nota_cassa` categoria "POS"
(`riconciliazione_bancaria.py:894-960`), quindi l'accredito reale non chiude la
entrata sintetica e si somma: il Bilancio conta il POS due volte
(`bilancio.py:132-143`).
**Attenuante**: il canale *Estratti conto da Drive* è SPENTO (LOGICA §13), quindi
oggi non si materializza in automatico; ma l'**upload manuale** dell'estratto
attiva il percorso. Da provare su un estratto reale con accredito NUMIA prima di
riaccendere il canale. L'accredito reale deve *chiudere/sostituire* la entrata
sintetica (match banca↔banca), non aggiungersi.

## P1
- **P1-1 — Filtri duri §6 non implementati; auto-conferma troppo aggressiva.**
  I candidati includono importi 50–200% dell'EC (`riconciliazione_bancaria.py:598-605`),
  nessun filtro duro ±2€/±5gg; auto-riconcilia e marca "pagata" con solo importo
  (score==10) senza verifica data, tolleranza ±0,05€ invece di ±0,01
  (`:787-812`). §6 vuole filtri duri come pre-selezione e "Certo" solo con importo
  esatto E stessa data. (I valori 2€/5gg la stessa §6 li dà come "mai tarati".)
- **P1-2 — Riconciliazione MANUALE senza guard "già riconciliato → 409".**
  `bank_statement_import.py:912-939` setta `riconciliato=True` incondizionatamente
  e aggiorna solo `prima_nota_banca`, non il movimento EC → l'EC resta
  `riconciliato=False` e può essere ri-agganciato dal motore auto (**doppio match**).
  `operazioni_module/smart.py:210-285` non verifica mai lo stato pregresso. §6
  impone rifiuto con conflitto, mai sovrascrittura muta.
- **P1-3 (dubbio) — Soglia 516,46€ classificata per keyword, non sull'importo.**
  Il centro `5.3_PICCOLE_ATTREZZATURE` è assegnato solo per parole chiave
  (`learning_machine_cdc.py:199-218,667-686`) senza confrontare l'importo unitario
  col limite art. 102 TUIR: un bene keyword-matchato ma >516,46€ va comunque a
  costo integrale invece che a cespite. Soglia coerente; manca la verifica su importo.

## P2 — robustezza
- P2-1 modello Prima Nota Cassa corrispettivi (cassa=contanti + banca=elettronico)
  diverge dalla descrizione §4 ("entrata intero + uscita POS"): netto identico,
  allineare LOGICA o annotare.
- P2-2 inserimento manuale libero in Prima Nota Cassa (`cassa.py:83-137`) — varco
  rispetto a "mai liberamente" (§4); da confermare come voluto.
- P2-3 router `accounting/centri_costo.py` legacy incoerente (secondo schema CdC
  TeamSystem; `CHIAVI_RIBALTAMENTO` referenzia `CDC-05/06/07` inesistenti). Da
  deprecare in favore del motore unico.
- P2-4 tre classificatori di costo paralleli (`learning_machine_cdc`,
  `classificazione_costi`, `categorizzazione_contabile`) → consolidare.
- P2-5 valori stima/placeholder presentati come dati (interessi mutui hardcoded 0
  `bilancio.py:774-778`; ricavi per CdC stimati `centri_costo.py:529,678-681`):
  etichettare come stime.

## Conformi (nessuna azione)
F24 mai costo automatico ✔; ricavi=solo corrispettivi, fatture emesse non
ri-sommate ✔; coerenza POS senza bug di segno/quadratura (fix 12/07 confermato) ✔;
motore unico CdC (cucina separata, <516,46, fornitore misto) ✔; anti-duplicato
corrispettivi a 3 livelli ✔; soft-delete filtrati ✔; `sincronizza-prima-nota`
senza il vecchio bug "quota POS in cassa" ✔.

## Valori parametrici (riportati, non giudicati)
Tolleranza match auto ±0,05€ / candidati 50–200% (diverge da ±0,01 / ±2€, P1-1);
nessun filtro date (diverge da ±5gg, P1-1); tolleranza POS 2 fasi 0,50€ default;
soglia beni 516,46€ (coerente, non verificata su importo P1-3); noleggio auto
3.615,20€/anno ded. 20%; accredito POS weekend lun/mar (coerente).
