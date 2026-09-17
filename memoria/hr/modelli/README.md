# Modelli documenti — CCNL Pubblici Esercizi/Turismo (H05Y)

<!-- gestionalecloud-doc
status: historical
reviewed_at: 2026-09-17
storage_architecture: supabase
-->

> [!NOTE]
> Snapshot storico: non descrive lo stato operativo corrente. Per l'architettura Drive-only usare `README.md`, `PRODUCT.md`, `CLAUDE.md` e `LOGICA_FUNZIONAMENTO.md`.

## Informativa D.Lgs. 152/1997

`INFORMATIVA_152_1997_Turismo.docx` è l'informativa adattata al CCNL
**Pubblici Esercizi, Ristorazione Collettiva e Commerciale e Turismo**
(Confcommercio-FIPE, codice CNEL **H05Y**, rinnovo 5/6/2024) — sostituisce la
versione Terziario.

Rigenerala con:

```bash
python modelli/genera_informativa_152.py
```

### Come usarla nel sistema
1. Apri **Assunzione & Contratti → Modelli contratto**.
2. Su «Informativa D.Lgs. 152/1997» clicca **Sostituisci** e carica il `.docx`.
3. Genera l'informativa per un dipendente: i segnaposto `{{...}}` vengono
   compilati con i suoi dati (nome, CF, livello, paga, ore, ferie, ecc.).

### Da validare col consulente del lavoro (NON inventare)
Le voci marcate in arancione nel documento richiedono le **tabelle ufficiali
del CCNL H05Y** per il livello di inquadramento:
- minimi tabellari (paga base, contingenza, scatti di anzianità);
- termini di preavviso per recesso.

### Segnaposto disponibili
`{{nome_completo}}` · `{{codice_fiscale}}` · `{{luogo_nascita}}` ·
`{{data_nascita}}` · `{{indirizzo}}` · `{{livello}}` · `{{qualifica}}` ·
`{{mansione}}` · `{{periodo_prova}}` · `{{stipendio_orario}}` ·
`{{ore_settimanali}}` · `{{stipendio_mensile}}` · `{{ferie_giorni}}` ·
`{{mensilita}}` · `{{ticket}}` · `{{data_inizio}}` · `{{data_fine}}`
