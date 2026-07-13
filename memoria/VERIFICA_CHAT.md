# Verifica di conformità — Chat Intelligente

_Loop /goal, 13/07/2026. Sola lettura, contro
`SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md` (parte Chat), `CLAUDE.md`,
`LOGICA_FUNZIONAMENTO.md`. Nessuna modifica al codice._

**Esito**: impianto sostanzialmente conforme (tracciabilità, anti-allucinazione,
spiegazione del "perché", download/vai-a). 2 P1 (temi muti per collection
sbagliata), alcuni P2 (copertura parziale).

## Architettura
Due motori dietro `POST /api/chat/ask`:
1. **Motore AI** (`chat_ai_engine.rispondi`, `:747`) — default con `ANTHROPIC_API_KEY`.
   Agent loop, 17 tool tipizzati + `componi_risposta`, proiezioni limitate, tetti
   risultati, log in `chat_tool_calls`.
2. **Motore keyword** (fallback, `chat_router.py:301-427`) — 8 intenti hardcoded.

## Copertura temi

| Tema | Coperto? | Tool (file:linea) |
|---|---|---|
| IVA | Sì (singola fattura; manca aggregato) | `spiega_iva_fattura:481` |
| F24 | Sì | `cerca_f24:204`, `spiega_f24:449`, `doppi_pagamenti_f24:474` |
| **Quietanze** | **NO / rotto** | `cerca_quietanze:220` → legge `db["quietanze"]` invece di `quietanze_f24` |
| Cedolini | Sì | `cerca_cedolini:247`, `cerca_dipendenti:272` |
| Bilancio | Parziale (solo fallback keyword) | `_risposta_bilancio` `chat_router.py:156` |
| Prima Nota | Sì | `cerca_movimenti_prima_nota:415` |
| Corrispettivi | Sì | `cerca_corrispettivi:407` |
| Riconciliazioni | Parziale (nessun tool dedicato) | `cerca_movimenti_bancari:229` |
| **Documenti fiscali** | **NO / rotto** | `cerca_documenti:435` → legge `db["documenti_scaricati"]` (inesistente) |

## Conformi (nessuna azione)
- **Spiegazione del perché**: system prompt impone dati reali + regola decisionale
  (`chat_ai_engine.py:135`); `spiega_f24`/`spiega_iva_fattura` riportano la regola
  applicata. ✔
- **Anti-allucinazione / tracciabilità**: il modello non accede a Mongo, solo tool
  con proiezioni e tetti (`MAX_RISULTATI_TETTO=100`); PDF/raw esclusi dal contesto;
  `documenti_consultati` popolato dai tool usati; log in `chat_tool_calls`. ✔
- **Download / vai-a**: `_documenti_citati_da_tool:576` genera download_url + page_url
  per cedolini/fatture/F24/documenti; endpoint verificati esistenti. ✔
- **Integrazione motori reali**: `spiega_f24`→`tributi_engine`, `doppi_pagamenti_f24`
  →`f24_analisi`, `spiega_iva_fattura`→`iva_fatture`. ✔

## P1 — temi muti per collection sbagliata
1. **Quietanze**: `cerca_quietanze` interroga `db["quietanze"]`; canonica è
   `quietanze_f24` (303 doc) → tool sempre vuoto. (`chat_ai_engine.py:226`)
2. **Documenti fiscali**: `cerca_documenti` interroga `db["documenti_scaricati"]`
   (inesistente); canoniche `documents_inbox`/`documenti_classificati` →
   tool sempre vuoto. (`chat_ai_engine.py:446`)

> Nota CLAUDE.md: per Quietanze la collezione giusta è univoca (`quietanze_f24`);
> per Documenti c'è una scelta tra `documents_inbox` e `documenti_classificati` →
> da confermare con l'utente prima di applicare.

## P2 — copertura parziale / robustezza
3. Bilancio assente come tool del motore AI (solo fallback keyword); "bilanci" non
   mappato in `_DOMINI_KEYWORDS`.
4. Riconciliazioni senza tool dedicato (no accesso a `riconciliazioni_match`).
5. IVA aggregata/liquidazioni senza tool (solo spiegazione per singola fattura).
6. `componi_risposta` non espone `motivazione`/`entita_principali`/`collegamenti`
   dello schema KB (la motivazione finisce in `risposta_testuale`).
7. Nessun `timeout`/retry esplicito sulla chiamata LLM; `temperature` non impostata.
8. Etichetta documento citato per F24 usa `data_versamento` non proiettato → vuota (cosmetico).

## Valori parametrici (riportati, non giudicati)
- Provider Anthropic; modello chat da env `ANTHROPIC_MODEL`, default `claude-sonnet-5`
  (`chat_ai_engine.py:44`); `max_tokens=2000`; temperature non impostata.
- Client ausiliario `anthropic_llm_client.py` (parsing documenti, NON usato dalla
  chat): default `claude-opus-4-5` — divergente dal default chat, da lasciare
  alla decisione dell'utente.

## Coerenza documentale
- `chat_kb.json:793-798` dichiara la chat "non_implementata / pagina_vuota":
  **obsoleto** (il backend AI è implementato e registrato). Incoerenza documentale.
