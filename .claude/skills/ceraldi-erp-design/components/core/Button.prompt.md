Bottone d'azione del Ceraldi ERP — navy pieno per l'azione primaria, neutro/ghost per le secondarie, colori di stato per conferme ed eliminazioni.

```jsx
<Button variant="primary" iconLeft={<Plus size={16} />}>Nuova fattura</Button>
<Button variant="secondary">Annulla</Button>
<Button variant="danger" size="sm">Elimina</Button>
```

Varianti: `primary` (default, navy), `secondary`, `ghost`, `outline`, `success`, `danger`, `info`, `warning`. Dimensioni: `sm` `md` `lg`. Passa icone Lucide via `iconLeft` / `iconRight`. Le azioni distruttive usano sempre `danger`.
