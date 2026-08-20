---
name: pagina-erp
description: "Use when: analizzare, spiegare, validare, mappare, documentare, approfondire o fare una scheda di una singola pagina del gestionale, pagina ERP, page catalog, dashboard, fatture, banca, flotta, dichiarazioni, documenti, contabilità, noleggio, prima nota."
---
# Skill: pagina-erp

Analizza una pagina del GestionaleCloud come entità di business con dati, origine, relazioni e impatto operativo.

## Obiettivo
Spiegare in modo concreto:
- cosa fa la pagina
- da dove prendono i dati
- dove nascono i dati
- a cosa servono nel processo
- con quali altre pagine interagisce
- quali verifiche o rischi ci sono

## Regole
- Usa page_catalog.json e il codice attivo come fonte di verità.
- Non usare report storici come autorità quando discordano dal codice attivo.
- Non supporre: se un flusso è ambiguo, lo dici chiaramente.
- Mantieni il linguaggio orientato al business e alla verità operativa.

## Output atteso
Rispondi con:
1. Titolo pagina
2. Funzione
3. Dati in entrata
4. Dove nasce
5. Cosa alimenta
6. Relazioni
7. Rischi/Verifiche
8. Fonti usate

## Esempi di prompt
- "spiegami la pagina di fatture"
- "mappa la pagina di prima nota"
- "dove nasce la pagina di banca"
- "cosa alimenta la dashboard"
- "valida la pagina di flotta"