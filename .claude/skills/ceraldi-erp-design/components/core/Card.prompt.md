Contenitore base del Ceraldi ERP: superficie bianca, bordo 1px, ombra leggera. Niente card annidate in card.

```jsx
<Card title="Elenco Corrispettivi" icon={<Receipt size={16} />} actions={<Button size="sm" variant="secondary">Esporta</Button>}>
  <table>…</table>
</Card>
```

Passa `bodyStyle={{ padding: 0 }}` quando il contenuto è una tabella a tutta larghezza.
