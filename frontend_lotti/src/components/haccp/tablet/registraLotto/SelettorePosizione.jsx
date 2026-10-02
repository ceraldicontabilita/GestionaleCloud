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
  // Banco = un solo tocco (e' la scelta piu' frequente); gli apparecchi stanno in un
  // menu a scomparsa raggruppato, non in 24 card una sotto l'altra.
  const opzioni = opzioniDestinazione(reparto, opzioniFrigo, opzioniCongelatori);
  const banco = opzioni.find((o) => o.id === "banco");
  const apparecchio = destinazione === "frigo" || destinazione === "abbattitore"
    ? `${destinazione}:${frigo}` : "";
  const scegli = (valore) => {
    if (!valore) return;
    const opt = opzioni.find((o) => o.key === valore);
    if (opt) { setDestinazione(opt.id); setFrigo(opt.nome); }
  };
  return (
    <div style={{ marginBottom: 8 }}>
      <span style={{ fontSize: 11, fontWeight: 800, color: "#495247", display: "block", marginBottom: 2 }}>
        Destinazione del lotto
      </span>
      <span style={{ fontSize: 10, color: "#7a7266", display: "block", marginBottom: 5 }}>
        Indica solo dove conservi il prodotto. La stampa si sceglie sotto.
      </span>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "stretch" }}>
        {banco && (
          <button type="button" onClick={() => { setDestinazione("banco"); setFrigo(""); }}
            aria-pressed={destinazione === "banco"}
            style={{
              minHeight: 44, padding: "0 16px", borderRadius: 8, cursor: "pointer", fontWeight: 800, fontSize: 13,
              border: `2px solid ${destinazione === "banco" ? banco.color : "#e6e0d4"}`,
              background: destinazione === "banco" ? `${banco.color}18` : "#faf7f0",
              color: destinazione === "banco" ? banco.color : "#495247",
            }}>
            {destinazione === "banco" ? "✓ " : ""}Subito al banco
          </button>
        )}
        <select aria-label="Frigorifero o congelatore" value={apparecchio} onChange={(e) => scegli(e.target.value)}
          style={{
            flex: "1 1 200px", minHeight: 44, padding: "0 10px", borderRadius: 8, fontWeight: 700, fontSize: 13,
            border: `2px solid ${apparecchio ? "#5b7a6b" : "#e6e0d4"}`, background: "#faf7f0", color: "#2a3329",
          }}>
          <option value="">Conserva in frigorifero o congelatore…</option>
          {opzioniFrigo.length > 0 && (
            <optgroup label="Frigoriferi">
              {opzioniFrigo.map((nome) => <option key={`frigo:${nome}`} value={`frigo:${nome}`}>{nome}</option>)}
            </optgroup>
          )}
          {opzioniCongelatori.length > 0 && (
            <optgroup label="Congelatori">
              {opzioniCongelatori.map((nome) => <option key={`abbattitore:${nome}`} value={`abbattitore:${nome}`}>{nome}</option>)}
            </optgroup>
          )}
        </select>
      </div>
      {posizioneMancante && (
        <p style={{ fontSize: 11, fontWeight: 700, color: "#7c2d12", margin: "6px 0 0" }}>
          {banco
            ? "Scegli “Subito al banco” oppure l'apparecchio in cui conserverai il lotto."
            : "Scegli l'apparecchio in cui conserverai il lotto."}
        </p>
      )}
    </div>
  );
}
