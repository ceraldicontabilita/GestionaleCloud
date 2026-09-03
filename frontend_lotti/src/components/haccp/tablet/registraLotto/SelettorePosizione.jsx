// Blocchi DESTINAZIONE (frigo/banco/abbattitore) e POSIZIONE (in quale
// frigorifero/congelatore) del modale Registra lotto — estratti 1:1 da
// ModalRegistraLotto.jsx (refactor 25/07/2026). Solo presentazione.
export default function SelettorePosizione({
  reparto, destinazione, setDestinazione,
  frigo, setFrigo, opzioniFrigo, opzioniCongelatori,
  posizioneAMano, setPosizioneAMano,
  posizioneMancante, confermaSenzaPosizione, setConfermaSenzaPosizione,
}) {
  return (
    <>
<div style={{ marginBottom: 8 }}>
  <span style={{ fontSize: 11, fontWeight: 700, color: "#374151", display: "block", marginBottom: 4 }}>Destinazione</span>
  <div style={{ display: "grid", gridTemplateColumns: reparto === "bar" ? "1fr 1fr" : "1fr 1fr 1fr", gap: 5 }}>
    {[
      { id: "frigo",       emoji: "🧊", label: "Frigo",       color: "var(--info)" },
      // Il bar NON va al banco vendite (i caffè non si contano la sera):
      // destinazione Banco solo per pasticceria/rosticceria.
      ...(reparto !== "bar" ? [{ id: "banco", emoji: "🛒", label: "Banco", color: "#f97316" }] : []),
      { id: "abbattitore", emoji: "❄️", label: "Abbattitore", color: "#5b7a6b" },
    ].map(opt => (
      <button key={opt.id} onClick={() => { setDestinazione(opt.id); setFrigo(""); }}
        style={{
          padding: "7px 4px", borderRadius: 8, cursor: "pointer",
          border: `2px solid ${destinazione === opt.id ? opt.color : "#e6e0d4"}`,
          background: destinazione === opt.id ? `${opt.color}18` : "#faf7f0",
          textAlign: "center"
        }}>
        <span style={{ fontSize: 14 }}>{opt.emoji}</span>
        <div style={{ fontSize: 10, fontWeight: 800, color: destinazione === opt.id ? opt.color : "#374151", marginTop: 1 }}>
          {opt.label}
        </div>
      </button>
    ))}
  </div>
</div>

{(destinazione === "frigo" || destinazione === "abbattitore") && (() => {
  // FIX 25/07/2026: qui c'era un <input> con <datalist>. Su Android
  // il menu della datalist di fatto non si apre: l'operatore vedeva
  // SOLO il valore pre-compilato e non poteva scegliere tra tutti i
  // frigoriferi/congelatori censiti. Ora è un <select> vero (su
  // telefono si apre a tutto schermo), con l'opzione "Altro" che
  // riporta al campo libero per un apparecchio non ancora in elenco.
  const elenco = destinazione === "abbattitore" ? opzioniCongelatori : opzioniFrigo;
  const bordo = destinazione === "abbattitore" ? "#cfdfd5" : "var(--info-border)";
  const sfondo = destinazione === "abbattitore" ? "#f2f6f3" : "var(--info-soft)";
  const stileCampo = {
    width: "100%", padding: "10px", fontSize: 14, fontWeight: 700,
    border: `2px solid ${bordo}`, borderRadius: 8, color: "#2a3329",
    outline: "none", boxSizing: "border-box", background: sfondo,
  };
  return (
  <div style={{ marginBottom: 8 }}>
    <div style={{ fontSize: 11, fontWeight: 800, color: "#5c564a", marginBottom: 4 }}>
      {destinazione === "abbattitore" ? "In quale congelatore/abbattitore?" : "In quale frigorifero?"}
    </div>
    {!posizioneAMano ? (
      <select
        value={elenco.includes(frigo) ? frigo : ""}
        onChange={e => {
          if (e.target.value === "__altro__") { setPosizioneAMano(true); setFrigo(""); }
          else setFrigo(e.target.value);
        }}
        style={stileCampo}
      >
        <option value="">— scegli —</option>
        {elenco.map(v => <option key={v} value={v}>{v}</option>)}
        <option value="__altro__">Altro (scrivi a mano)…</option>
      </select>
    ) : (
      <>
        <input type="text" value={frigo} onChange={e => setFrigo(e.target.value)}
          placeholder={`${destinazione === "abbattitore" ? "❄️ Congelatore" : "🧊 Frigorifero"} (es. ${destinazione === "abbattitore" ? "Congelatore 1" : "Frigo 1"})`}
          style={stileCampo} />
        <button type="button" onClick={() => { setPosizioneAMano(false); setFrigo(elenco[0] || ""); }}
          style={{ marginTop: 5, background: "none", border: "none", padding: 0,
            fontSize: 11, fontWeight: 800, color: "#5b7a6b", textDecoration: "underline", cursor: "pointer" }}>
          ← torna all'elenco
        </button>
      </>
    )}
    {posizioneMancante && (
      <label style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6, cursor: "pointer" }}>
        <input type="checkbox" checked={confermaSenzaPosizione}
          onChange={e => setConfermaSenzaPosizione(e.target.checked)} />
        <span style={{ fontSize: 11, fontWeight: 700, color: "#7c2d12" }}>
          Indica dove va messo il lotto, o conferma che vuoi registrarlo senza posizione
        </span>
      </label>
    )}
  </div>
  );
})()}
    </>
  );
}
