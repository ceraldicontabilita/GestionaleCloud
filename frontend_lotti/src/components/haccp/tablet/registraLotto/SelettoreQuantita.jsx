// Blocco QUANTITÀ del modale Registra lotto — estratto 1:1 da
// ModalRegistraLotto.jsx (refactor 25/07/2026). Solo presentazione: lo stato
// (unita, pezzi) resta nel modale, qui arrivano valore e callback.
export default function SelettoreQuantita({ unita, setUnita, pezzi, setPezzi }) {
  return (
<div style={{ marginBottom: 8 }}>
  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
    <span style={{ fontSize: 11, fontWeight: 700, color: "#374151" }}>Quantità</span>
    <div style={{ display: "flex", background: "#f0ebe0", borderRadius: 6, padding: 2, gap: 2 }}>
      {["pz","kg"].map(u => (
        <button key={u} onClick={() => { setUnita(u); setPezzi(1); }}
          style={{
            padding: "2px 10px", borderRadius: 4, border: "none", fontWeight: 700, fontSize: 11,
            background: unita === u ? "#fff" : "transparent",
            color: unita === u ? "#2a3329" : "#a39a87",
            boxShadow: unita === u ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
            cursor: "pointer"
          }}>{u}</button>
      ))}
    </div>
  </div>
  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
    <button onClick={() => setPezzi(v => unita === "kg" ? Math.max(0.5, parseFloat((v-0.5).toFixed(1))) : Math.max(1, v-1))}
      style={{ width: 36, height: 36, borderRadius: 8, border: "2px solid #e6e0d4",
        background: "#faf7f0", fontWeight: 700, fontSize: 18, cursor: "pointer", flexShrink: 0 }}>−</button>
    <input type="number"
      min={unita === "kg" ? "0.5" : "1"} step={unita === "kg" ? "0.5" : "1"}
      value={pezzi}
      onChange={e => setPezzi(unita === "kg" ? parseFloat(e.target.value)||0.5 : parseInt(e.target.value)||1)}
      style={{
        flex: 1, padding: "6px 0", fontSize: 20, fontWeight: 800,
        border: "2px solid #cfc6b4", borderRadius: 8, textAlign: "center",
        color: "#2a3329", outline: "none", minWidth: 0
      }} />
    <button onClick={() => setPezzi(v => unita === "kg" ? parseFloat((v+0.5).toFixed(1)) : v+1)}
      style={{ width: 36, height: 36, borderRadius: 8, border: "2px solid #e6e0d4",
        background: "#faf7f0", fontWeight: 700, fontSize: 18, cursor: "pointer", flexShrink: 0 }}>+</button>
  </div>
  <div style={{ display: "grid", gap: 3,
    gridTemplateColumns: unita === "kg" ? "repeat(5,1fr)" : "repeat(5,1fr)" }}>
    {(unita === "kg" ? [0.5,1,1.5,2,3,5,10,15,20] : [1,2,3,5,6,8,10,12,20,30]).map(v => (
      <button key={v} onClick={() => setPezzi(v)}
        style={{
          padding: "4px 2px", borderRadius: 5, fontSize: 10, fontWeight: 700, cursor: "pointer",
          textAlign: "center",
          border: `2px solid ${pezzi === v ? "var(--info)" : "#e6e0d4"}`,
          background: pezzi === v ? "var(--info-soft)" : "#faf7f0",
          color: pezzi === v ? "var(--info-dark)" : "#7a7266"
        }}>{v}{unita}</button>
    ))}
  </div>
</div>
  );
}
