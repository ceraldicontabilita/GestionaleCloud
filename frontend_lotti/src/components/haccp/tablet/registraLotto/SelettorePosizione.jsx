// Blocchi DESTINAZIONE (frigo/banco/abbattitore) e POSIZIONE (in quale
// frigorifero/congelatore) del modale Registra lotto — estratti 1:1 da
// ModalRegistraLotto.jsx (refactor 25/07/2026). Solo presentazione.
export function opzioniDestinazione(reparto, opzioniFrigo, opzioniCongelatori) {
  return [
    ...(reparto !== "bar" ? [{ key: "banco", id: "banco", nome: "", emoji: "🛒", label: "Banco", color: "#f97316" }] : []),
    ...opzioniFrigo.map((nome) => ({ key: `frigo:${nome}`, id: "frigo", nome, emoji: "🧊", label: nome, color: "var(--info)" })),
    ...opzioniCongelatori.map((nome) => ({ key: `abbattitore:${nome}`, id: "abbattitore", nome, emoji: "❄️", label: nome, color: "#5b7a6b" })),
  ];
}

export default function SelettorePosizione({
  reparto, destinazione, setDestinazione,
  frigo, setFrigo, opzioniFrigo, opzioniCongelatori,
  posizioneMancante,
}) {
  return (
    <>
<div style={{ marginBottom: 8 }}>
  <span style={{ fontSize: 11, fontWeight: 700, color: "#495247", display: "block", marginBottom: 4 }}>Dove va questo lotto?</span>
  <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 5 }}>
    {opzioniDestinazione(reparto, opzioniFrigo, opzioniCongelatori).map(opt => {
      const selezionata = destinazione === opt.id && frigo === opt.nome;
      return (
      <button key={opt.key} type="button" onClick={() => { setDestinazione(opt.id); setFrigo(opt.nome); }}
        style={{
          minHeight: 48, padding: "7px 4px", borderRadius: 8, cursor: "pointer",
          border: `2px solid ${selezionata ? opt.color : "#e6e0d4"}`,
          background: selezionata ? `${opt.color}18` : "#faf7f0",
          textAlign: "center"
        }}>
        <span style={{ fontSize: 14 }}>{opt.emoji}</span>
        <div style={{ fontSize: 10, fontWeight: 800, color: destinazione === opt.id ? opt.color : "#495247", marginTop: 1 }}>
          {selezionata ? "✓ " : ""}{opt.label}
        </div>
      </button>
      );
    })}
  </div>
    {posizioneMancante && (
      <p style={{ fontSize: 11, fontWeight: 700, color: "#7c2d12", margin: "6px 0 0" }}>
        Scegli una destinazione: basta un tocco, nessun ripiano da indicare.
      </p>
    )}
  </div>
    </>
  );
}
