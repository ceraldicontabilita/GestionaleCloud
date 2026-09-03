/*
 * TourInterattivo.jsx — Tour guidato in-app, passo-passo, SENZA dipendenze esterne.
 * Per ogni passo: naviga al tab reale (onNavigate) e, se il pulsante di navigazione è
 * visibile, ci disegna sopra uno SPOTLIGHT + un tooltip ancorato; altrimenti mostra un
 * tooltip centrato che spiega la pagina su cui ci si trova. Avanzamento persistito in
 * localStorage (lotti_tour_fatto) così non si ripropone da solo dopo il primo giro.
 * Adatto a un'app vendibile: nessun file/CDN da hostare.
 */
import { useState, useEffect, useCallback, useLayoutEffect } from "react";

const LS_KEY = "lotti_tour_fatto";

// Passi nell'ordine del flusso reale. `tab` = id del tab (onNavigate); se esiste un
// pulsante [data-tour="<tab>"] visibile, viene evidenziato.
const PASSI = [
  { tab: "dashboard",          titolo: "Dashboard",        testo: "Il quadro generale: scadenze, avvisi e numeri chiave. È la tua schermata di partenza." },
  { tab: "fatture",            titolo: "Importa Fatture",  testo: "Carica gli XML delle fatture. Da qui nascono prodotti, lotti e giacenze. La barra in basso mostra l'avanzamento anche se cambi pagina." },
  { tab: "fornitori",          titolo: "Fornitori",        testo: "Classifica ogni fornitore: completo, solo magazzino, oppure escluso. Determina cosa entra in Materie Prime e ricette." },
  { tab: "materie",            titolo: "Materie Prime",    testo: "I prodotti reali per fornitore. Apri la scheda (icona documento) e indica sito o foto etichetta: il sistema estrae composizione e allergeni." },
  { tab: "ricette",            titolo: "Ricette",          testo: "Dosi, costi e allergeni. Ogni ingrediente mostra la provenienza FIFO e, se disponibile, la composizione del prodotto composto." },
  { tab: "lotti",              titolo: "Lotti / HACCP",    testo: "I lotti in produzione con tracciabilità e scadenze. La produzione scarica gli ingredienti in FIFO dalla fattura più vecchia." },
  { tab: "ordini",             titolo: "Ordini",           testo: "Flusso bozza → confermato → inviato. Le proposte dell'operatore restano bozze finché non le confermi e invii tu." },
  { tab: "magazzino_prodotti", titolo: "Magazzino",        testo: "Giacenze e riordino dei prodotti. Tieni sotto controllo cosa manca." },
  { tab: "registro_haccp",     titolo: "Registro HACCP",   testo: "Temperature, sanificazioni e controlli: tutto pronto per l'autocontrollo e le verifiche." },
  { tab: "guida",              titolo: "Guida",            testo: "Il manuale d'uso passo-passo, sempre disponibile. Da qui puoi anche rilanciare questo tour." },
];

export default function TourInterattivo({ onNavigate, onClose, passi = PASSI }) {
  const [i, setI] = useState(0);
  const [rect, setRect] = useState(null); // posizione del bersaglio (o null = centrato)
  const passo = passi[i];

  const fine = useCallback(() => {
    try { localStorage.setItem(LS_KEY, "1"); } catch { /* no-op */ }
    onClose && onClose();
  }, [onClose]);

  // Naviga al tab del passo corrente
  useEffect(() => {
    if (passo && onNavigate) onNavigate(passo.tab);
  }, [i, passo, onNavigate]);

  // Calcola la posizione del bersaglio (dopo che la pagina ha renderizzato)
  const calcola = useCallback(() => {
    const el = document.querySelector(`[data-tour="${passo?.tab}"]`);
    if (!el) { setRect(null); return; }
    const r = el.getBoundingClientRect();
    const visibile = r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight && r.right > 0 && r.left < window.innerWidth;
    setRect(visibile ? { top: r.top, left: r.left, width: r.width, height: r.height } : null);
  }, [passo]);

  useLayoutEffect(() => {
    const t = setTimeout(calcola, 90); // attendi il render del tab
    window.addEventListener("resize", calcola);
    window.addEventListener("scroll", calcola, true);
    return () => { clearTimeout(t); window.removeEventListener("resize", calcola); window.removeEventListener("scroll", calcola, true); };
  }, [calcola]);

  if (!passo) return null;

  const pad = 6;
  const spot = rect ? { top: rect.top - pad, left: rect.left - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 } : null;

  // Posizione tooltip: sotto il bersaglio se c'è spazio, altrimenti sopra; senza bersaglio = centrato
  let tipStyle;
  if (!spot) {
    tipStyle = { left: "50%", top: "50%", transform: "translate(-50%,-50%)" };
  } else {
    const sottoSpazio = window.innerHeight - (spot.top + spot.height);
    const cx = Math.min(Math.max(spot.left + spot.width / 2, 170), window.innerWidth - 170);
    if (sottoSpazio > 200) {
      tipStyle = { left: cx, top: spot.top + spot.height + 12, transform: "translateX(-50%)" };
    } else {
      tipStyle = { left: cx, top: spot.top - 12, transform: "translate(-50%,-100%)" };
    }
  }

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 4000 }}>
      {/* Overlay scuro: se c'è bersaglio uso uno spotlight (buco luminoso), altrimenti velo pieno */}
      {spot ? (
        <div
          onClick={() => {}}
          style={{
            position: "fixed", top: spot.top, left: spot.left, width: spot.width, height: spot.height,
            borderRadius: 10, boxShadow: "0 0 0 9999px rgba(28,38,32,0.66)", border: "2px solid #5b7a6b",
            transition: "all .2s ease", pointerEvents: "none",
          }}
        />
      ) : (
        <div style={{ position: "fixed", inset: 0, background: "rgba(28,38,32,0.66)" }} />
      )}

      {/* Tooltip */}
      <div
        style={{
          position: "fixed", ...tipStyle, width: 320, maxWidth: "92vw",
          background: "#fff", borderRadius: 16, boxShadow: "0 18px 50px rgba(0,0,0,.35)",
          padding: 18, zIndex: 4001,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: "#5b7a6b", letterSpacing: .3 }}>
            PASSO {i + 1} / {passi.length}
          </span>
          <button onClick={fine} style={{ border: "none", background: "transparent", color: "#94a3b8", fontSize: 13, cursor: "pointer", fontWeight: 600 }}>
            Salta
          </button>
        </div>
        <h3 style={{ margin: "2px 0 6px", fontSize: 17, fontWeight: 800, color: "#2a3329" }}>{passo.titolo}</h3>
        <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.5, color: "#475569" }}>{passo.testo}</p>

        {/* Barra avanzamento */}
        <div style={{ height: 4, background: "#ece9f6", borderRadius: 4, marginTop: 14, overflow: "hidden" }}>
          <div style={{ height: "100%", width: `${((i + 1) / passi.length) * 100}%`, background: "#5b7a6b", transition: "width .25s" }} />
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
          <button
            onClick={() => setI((v) => Math.max(0, v - 1))}
            disabled={i === 0}
            style={{ flex: "0 0 auto", padding: "9px 14px", borderRadius: 10, border: "1px solid #e2e8f0", background: "#f8fafc", color: "#475569", fontWeight: 700, fontSize: 13, cursor: i === 0 ? "default" : "pointer", opacity: i === 0 ? .5 : 1 }}
          >
            Indietro
          </button>
          {i < passi.length - 1 ? (
            <button
              onClick={() => setI((v) => Math.min(passi.length - 1, v + 1))}
              style={{ flex: 1, padding: "9px 14px", borderRadius: 10, border: "none", background: "linear-gradient(135deg,#3f5a4e,#5b7a6b)", color: "#fff", fontWeight: 800, fontSize: 13, cursor: "pointer" }}
            >
              Avanti
            </button>
          ) : (
            <button
              onClick={fine}
              style={{ flex: 1, padding: "9px 14px", borderRadius: 10, border: "none", background: "linear-gradient(135deg,#3f5a4e,#5b7a6b)", color: "#fff", fontWeight: 800, fontSize: 13, cursor: "pointer" }}
            >
              Fine
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// Esposto per il flag di completamento.
export { LS_KEY as TOUR_LS_KEY };
