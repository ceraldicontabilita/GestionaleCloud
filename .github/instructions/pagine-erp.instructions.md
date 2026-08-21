---
applyTo: ["page_catalog.json", "memoria/**", "frontend/src/pages/**", "frontend/src/main.jsx", "app/**", "docs/**"]
description: "Istruzioni applicate a tutte le pagine ERP, al catalogo e alla documentazione operativa."
---

# Istruzioni pagine ERP

<!-- gestionalecloud-doc
status: current
reviewed_at: 2026-08-20
storage_architecture: drive-only
-->

Usa queste regole quando lavori su una pagina, su un catalogo di schermate o su documentazione a livello pagina.

## Priorità di verità
- Usa il codice attivo e la page catalog come autorità.
- Non affidarti a archive, ZIP storici o report datati se contraddicono la logica reale del repo.
- Il fatto che una pagina risponda HTTP 200 non basta: deve avere logica, flusso di dati e relazioni coerenti.

## Contesto di ogni pagina
Per ogni schermata, identifica sempre:
1. funzione di business
2. dati in ingresso
3. origine dei dati
4. da dove provengono di fatto
5. cosa alimenta a valle
6. quali altre pagine o flussi dipendono da essa
7. ambiguità o rischi di coerenza

## Regole di dominio
- Documento, fattura, quietanza, movimento bancario, assegno, F24, cedolino, rendiconto IVA, POS e pagamento sono entità distinte.
- Un importo da solo non basta a identificare un evento.
- I collegamenti devono conservare origine e provenienza.
- Un risultato ambiguo va lasciato aperto, non inventato.
- La contabilità e i movimenti bancari vanno valutati come prove separate ma collegate.

## Lineage dati
Per ogni pagina, traccia il percorso:
- origine esterna: email, Drive, Sheets, PDFs, XML, $banca$, PayPal, POS, dichiarazioni,
- normalizzazione e deduplicazione,
- registrazione applicativa o ledger,
- elaborazione della pagina,
- output: contabilità, dashboard, alert, stati, report.

Drive/Sheets è l'unico archivio operativo. Ogni pagina usa il registro
condiviso e non introduce archivi alternativi. Gli alert operativi escono
soltanto su Telegram; Obsidian documenta il sistema ma non memorizza dati delle
pagine.

## Output richiesto
Ogni documentazione di pagina deve includere:
- titolo pagina
- funzione
- source data
- dove nasce
- che cosa alimenta
- relazioni
- evidenze tecniche

## Scope utile
Questo set è applicabile a tutte le 65 pagine del catalogo, alle pagine di contabilità, documenti, banca, flotta, IVA, dichiarazioni, dashboard, accesso e operazioni.
