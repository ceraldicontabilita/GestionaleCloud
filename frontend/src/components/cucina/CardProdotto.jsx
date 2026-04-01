/**
 * tablet/CardProdotto.jsx — Card prodotto nella vista tablet
 */

const COLORI_REPARTO = {
  pasticceria: ["#fdf2e9","#fde8d8","#fef9c3","#fff0f6","#f5e6ff","#e8f5e9"],
  rosticceria: ["#e8f4fd","#e3f2fd","#f0fdf4","#fef3c7","#fff7ed","#fef2f2"],
};

export function getColoreProdotto(nome, reparto) {
  const colori = COLORI_REPARTO[reparto] || COLORI_REPARTO.rosticceria;
  let hash = 0;
  for (let i = 0; i < nome.length; i++) hash = nome.charCodeAt(i) + ((hash << 5) - hash);
  return colori[Math.abs(hash) % colori.length];
}

function CardProdotto({ prodotto, reparto, onTap, onCambiaFoto, hasVarianti }) {
  const colore = getColoreProdotto(prodotto.nome || "", reparto);
  const isTestuale = hasVarianti || (reparto === "pasticceria" && !prodotto.foto_url);

  if (isTestuale) {
    return (
      <div style={{ position: "relative" }}>
        <div
          onClick={() => onTap(prodotto)}
          style={{
            borderRadius: 16, overflow: "hidden", cursor: "pointer",
            boxShadow: "0 2px 10px rgba(0,0,0,0.08)",
            transition: "transform 0.12s, box-shadow 0.12s",
            background: "#fff", border: `2px solid ${hasVarianti ? "#fde68a" : "#f3f4f6"}`,
            userSelect: "none", WebkitTapHighlightColor: "transparent",
            display: "flex", flexDirection: "column", minHeight: 100
          }}
          onMouseDown={e => { e.currentTarget.style.transform = "scale(0.96)"; }}
          onMouseUp={e => { e.currentTarget.style.transform = "scale(1)"; }}
          onTouchStart={e => { e.currentTarget.style.transform = "scale(0.96)"; }}
          onTouchEnd={e => { e.currentTarget.style.transform = "scale(1)"; }}
        >
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "14px 10px 6px", textAlign: "center" }}>
            <div>
              {hasVarianti && <div style={{ fontSize: 9, color: "#92400e", fontWeight: 800, letterSpacing: "0.5px", marginBottom: 3 }}>BASE + VARIANTI</div>}
              <p style={{
                margin: 0, fontWeight: 800, fontSize: 14, textTransform: "capitalize",
                color: "#1e293b", lineHeight: 1.25,
                display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden"
              }}>{prodotto.nome}</p>
            </div>
          </div>
          <div style={{ background: hasVarianti ? "#fffbeb" : "#f9fafb", borderTop: `1px solid ${hasVarianti ? "#fef3c7" : "#f3f4f6"}`, padding: "5px 8px", textAlign: "center" }}>
            <p style={{ margin: 0, fontSize: 10, color: hasVarianti ? "#92400e" : "#9ca3af", fontWeight: 600 }}>
              tocca → stampa etichetta
            </p>
          </div>
        </div>
        {hasVarianti && onCambiaFoto && (
          <button
            onClick={e => { e.stopPropagation(); onCambiaFoto(prodotto); }}
            style={{ position: "absolute", top: 6, right: 6, background: "rgba(0,0,0,0.5)", border: "none", borderRadius: 8, padding: "3px 6px", color: "#fff", fontSize: 11, cursor: "pointer", zIndex: 1 }}
            title="Carica foto">📷</button>
        )}
      </div>
    );
  }

  const fotoUrl = prodotto.foto_url || null;
  return (
    <div
      style={{ borderRadius: 16, overflow: "hidden", cursor: "pointer", boxShadow: "0 4px 16px rgba(0,0,0,0.12)", transition: "transform 0.15s, box-shadow 0.15s", background: "#fff", userSelect: "none", WebkitTapHighlightColor: "transparent", position: "relative" }}
      onMouseDown={(e) => { e.currentTarget.style.transform = "scale(0.97)"; }}
      onMouseUp={(e) => { e.currentTarget.style.transform = "scale(1)"; }}
      onTouchStart={(e) => { e.currentTarget.style.transform = "scale(0.97)"; }}
      onTouchEnd={(e) => { e.currentTarget.style.transform = "scale(1)"; }}
    >
      <div onClick={() => onTap(prodotto)} style={{ height: 130, overflow: "hidden", position: "relative", background: fotoUrl ? "#f0f0f0" : colore }}>
        {fotoUrl ? (
          <img src={fotoUrl} alt={prodotto.nome}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
            onError={(e) => { e.target.style.display = "none"; e.target.parentNode.style.background = colore; }} />
        ) : (
          <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 48 }}>
            {reparto === "pasticceria" ? "🍰" : "🥙"}
          </div>
        )}
        <div style={{ position: "absolute", top: 8, right: 8, background: reparto === "pasticceria" ? "#f59e0b" : "#3b82f6", color: "#fff", borderRadius: 20, padding: "2px 8px", fontSize: 10, fontWeight: 700 }}>
          {reparto === "pasticceria" ? "PAST" : "ROST"}
        </div>
        {onCambiaFoto && (
          <button onClick={(e) => { e.stopPropagation(); onCambiaFoto(prodotto); }}
            style={{ position: "absolute", bottom: 6, right: 6, background: "rgba(0,0,0,0.55)", border: "none", borderRadius: 8, padding: "4px 7px", color: "#fff", fontSize: 11, cursor: "pointer" }}
            title="Cambia foto">📷</button>
        )}
      </div>
      <div onClick={() => onTap(prodotto)} style={{ padding: "10px 12px" }}>
        <p style={{ margin: 0, fontWeight: 700, fontSize: 13, textTransform: "capitalize", color: "#1e293b", lineHeight: 1.3, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{prodotto.nome}</p>
        <p style={{ margin: "4px 0 0", fontSize: 11, color: "#94a3b8" }}>Tocca → registra lotto</p>
      </div>
    </div>
  );
}

export default CardProdotto;
