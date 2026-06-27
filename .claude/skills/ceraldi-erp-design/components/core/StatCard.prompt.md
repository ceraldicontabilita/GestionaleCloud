Riquadro KPI del Ceraldi ERP — icona Lucide, etichetta uppercase e valore grande. Il bordo sinistro accentato segnala la categoria.

```jsx
<StatCard icon={<Receipt size={18} />} label="Totale Corrispettivi" value="€ 184.920" accent="primary" />
<StatCard icon={<Banknote size={18} />} label="Pagato Cassa" value="€ 96.400" subtext="52% del totale" accent="success" />
```

`accent`: `primary` `success` `warning` `danger` `info` `accent` `none`. Disporli in griglia da 4 (`repeat(auto-fit, minmax(200px,1fr))`). Valori monetari formattati `€ 1.234`.
