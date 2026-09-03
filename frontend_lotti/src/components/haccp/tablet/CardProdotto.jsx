/**
 * tablet/CardProdotto.jsx — Card prodotto nella vista tablet
 */
import { BookOpen, Trash2 } from "lucide-react";
import { fotoSrc } from "../../../utils/constants";

const COLORI_REPARTO = {
  pasticceria: ["#fdf2e9","#fde8d8","#fef9c3","#fff0f6","#f5e6ff","#e8f5e9"],
  rosticceria: ["#e8f4fd","#e3f2fd","#f0fdf4","var(--warning-soft)","#fff7ed","#fef2f2"],
  bar: ["#efe9e1","#f3ece3","#f5efe6","#efe7db","#f1eadf","#ece3d6"],
};

export function getColoreProdotto(nome, reparto) {
  const colori = COLORI_REPARTO[reparto] || COLORI_REPARTO.rosticceria;
  let hash = 0;
  for (let i = 0; i < nome.length; i++) hash = nome.charCodeAt(i) + ((hash << 5) - hash);
  return colori[Math.abs(hash) % colori.length];
}

function GiacenzaBadge({ giacenza, style }) {
  if (!giacenza) return null;
  return (
    <div style={{
      position: "absolute", background: "#7c2d12", color: "#fff", borderRadius: 20,
      padding: "3px 9px", fontSize: 12, fontWeight: 900, zIndex: 2,
      boxShadow: "0 2px 6px rgba(0,0,0,0.35)", whiteSpace: "nowrap", ...style,
    }} title="Già pronti in frigo/abbattitore, non ancora al banco">
      🧊 {giacenza} pronti
    </div>
  );
}

export function usaCardTestuale(prodotto, reparto) {
  return reparto === "pasticceria" && !(prodotto?.foto_url || prodotto?.foto_fallback_url);
}

function PulsanteElimina({ prodotto, onElimina, eliminando }) {
  if (!onElimina) return null;
  return (
    <button
      type="button"
      disabled={eliminando}
      onClick={(e) => {
        e.stopPropagation();
        onElimina(prodotto);
      }}
      title={`Elimina ${prodotto.nome}`}
      style={{
        width: "100%", minHeight: 36, border: "none", borderTop: "1px solid #fecaca",
        background: eliminando ? "#f3f4f6" : "#fff1f2", color: eliminando ? "#9ca3af" : "#b91c1c",
        cursor: eliminando ? "wait" : "pointer", display: "flex", alignItems: "center",
        justifyContent: "center", gap: 6, fontSize: 11, fontWeight: 800, fontFamily: "inherit",
      }}
    >
      <Trash2 size={14} /> {eliminando ? "Eliminazione…" : "Elimina"}
    </button>
  );
}

function CardProdotto({ prodotto, reparto, onTap, onCambiaFoto, hasVarianti, onVediRicetta, onElimina, eliminando = false }) {
  const colore = getColoreProdotto(prodotto.nome || "", reparto);
  // Una ricetta base con varianti puo avere una foto valida: in quel caso va
  // mostrata come tutte le altre. Il badge continua a segnalare che il tocco
  // apre la scelta della variante.
  const isTestuale = usaCardTestuale(prodotto, reparto);
  const giacenza = prodotto.giacenza_frigo || 0;

  if (isTestuale) {
    return (
      <div style={{ position: "relative" }}>
        <div
          onClick={() => onTap(prodotto)}
          style={{
            borderRadius: 16, overflow: "hidden", cursor: "pointer",
            boxShadow: "0 2px 10px rgba(0,0,0,0.08)",
            transition: "transform 0.12s, box-shadow 0.12s",
            background: "#fff", border: `2px solid ${giacenza ? "#7c2d12" : hasVarianti ? "var(--warning-soft)" : "#f3f4f6"}`,
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
              {hasVarianti && <div style={{ fontSize: 9, color: "var(--warning-text)", fontWeight: 800, letterSpacing: "0.5px", marginBottom: 3 }}>BASE + VARIANTI</div>}
              <p style={{
                margin: 0, fontWeight: 800, fontSize: 14, textTransform: "capitalize",
                color: "#2a3329", lineHeight: 1.25,
                display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden"
              }}>{prodotto.nome}</p>
            </div>
          </div>
          <div style={{ background: giacenza ? "#fff1e6" : hasVarianti ? "#fffbeb" : "#f9fafb", borderTop: `1px solid ${giacenza ? "#7c2d12" : hasVarianti ? "var(--warning-soft)" : "#f3f4f6"}`, padding: "5px 8px", display: "flex", alignItems: "center", gap: 6 }}>
            <p style={{ margin: 0, flex: 1, minWidth: 0, fontSize: 10, color: giacenza ? "#7c2d12" : hasVarianti ? "var(--warning-text)" : "#9ca3af", fontWeight: 600, textAlign: onVediRicetta ? "left" : "center" }}>
              {giacenza ? `🧊 ${giacenza} già in frigo/abbattitore` : "tocca → stampa etichetta"}
            </p>
            {onVediRicetta && (
              <button onClick={e => { e.stopPropagation(); onVediRicetta(prodotto); }}
                title="Vedi la ricetta"
                style={{ flexShrink: 0, background: "#f2f6f3", border: "1px solid #cfdfd5", borderRadius: 8, padding: "4px 8px", color: "#3f5a4e", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, fontWeight: 800, fontFamily: "inherit" }}>
                <BookOpen size={12} /> Ricetta
              </button>
            )}
          </div>
          <PulsanteElimina prodotto={prodotto} onElimina={onElimina} eliminando={eliminando} />
        </div>
        <GiacenzaBadge giacenza={giacenza} style={{ top: -8, left: 8 }} />
        {hasVarianti && onCambiaFoto && (
          <button
            onClick={e => { e.stopPropagation(); onCambiaFoto(prodotto); }}
            style={{ position: "absolute", top: 6, right: 6, background: "rgba(0,0,0,0.5)", border: "none", borderRadius: 8, padding: "3px 6px", color: "#fff", fontSize: 11, cursor: "pointer", zIndex: 1 }}
            title="Carica foto">📷</button>
        )}
      </div>
    );
  }

  const fotoUrl = fotoSrc(prodotto.foto_url || prodotto.foto_fallback_url);
  const usaFotoBase = !prodotto.foto_url && Boolean(prodotto.foto_fallback_url);
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
            {reparto === "pasticceria" ? "🍰" : reparto === "bar" ? "☕" : "🥙"}
          </div>
        )}
        <div style={{ position: "absolute", top: 8, right: 8, background: reparto === "pasticceria" ? "#ea580c" : reparto === "bar" ? "#78350f" : "#22c55e", color: "#fff", borderRadius: 20, padding: "2px 8px", fontSize: 10, fontWeight: 700 }}>
          {reparto === "pasticceria" ? "PAST" : reparto === "bar" ? "BAR" : "ROST"}
        </div>
        <GiacenzaBadge giacenza={giacenza} style={{ top: 8, left: 8 }} />
        {hasVarianti && !giacenza && (
          <div style={{ position: "absolute", top: 8, left: 8, background: "rgba(255,251,235,0.94)", color: "var(--warning-text)", border: "1px solid var(--warning-soft)", borderRadius: 20, padding: "2px 8px", fontSize: 9, fontWeight: 900, letterSpacing: "0.4px", zIndex: 2 }}>
            BASE + VARIANTI
          </div>
        )}
        {usaFotoBase && (
          <div
            title={`Immagine provvisoria della ricetta base${prodotto.foto_fallback_nome ? `: ${prodotto.foto_fallback_nome}` : ""}`}
            style={{ position: "absolute", top: giacenza ? 38 : 8, left: 8, background: "rgba(255,255,255,0.94)", color: "#3f5a4e", border: "1px solid #cfdfd5", borderRadius: 20, padding: "2px 8px", fontSize: 9, fontWeight: 900, letterSpacing: "0.4px", zIndex: 2 }}
          >
            FOTO BASE
          </div>
        )}
        {onCambiaFoto && (
          <button onClick={(e) => { e.stopPropagation(); onCambiaFoto(prodotto); }}
            style={{ position: "absolute", bottom: 6, right: 6, background: "rgba(0,0,0,0.55)", border: "none", borderRadius: 8, padding: "4px 7px", color: "#fff", fontSize: 11, cursor: "pointer" }}
            title="Cambia foto">📷</button>
        )}
        {/* Prima questa portava a #ricette, cioè al Backoffice: da quando il
            gestionale è riservato al titolare, per un dipendente finiva
            contro il tastierino. Ora apre la ricetta in sola lettura. */}
        <button onClick={(e) => { e.stopPropagation(); onVediRicetta?.(prodotto); }}
          style={{ position: "absolute", bottom: 6, left: 6, background: "rgba(0,0,0,0.55)", border: "none", borderRadius: 8, padding: "5px 8px", color: "#fff", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4, fontSize: 11, fontWeight: 700, fontFamily: "inherit" }}
          title="Vedi la ricetta"><BookOpen size={13} /> Ricetta</button>
      </div>
      <div onClick={() => onTap(prodotto)} style={{ padding: "10px 12px" }}>
        <p style={{ margin: 0, fontWeight: 700, fontSize: 13, textTransform: "capitalize", color: "#2a3329", lineHeight: 1.3, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{prodotto.nome}</p>
        <p style={{ margin: "4px 0 0", fontSize: 11, color: giacenza ? "#7c2d12" : "#a39a87", fontWeight: giacenza ? 700 : 400 }}>
          {giacenza ? `🧊 ${giacenza} già in frigo/abbattitore` : "Tocca → registra lotto"}
        </p>
      </div>
      <PulsanteElimina prodotto={prodotto} onElimina={onElimina} eliminando={eliminando} />
    </div>
  );
}

export default CardProdotto;
