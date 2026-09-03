/**
 * RegistroHACCPView.jsx — cruscotto del registro HACCP.
 * Mostra a colpo d'occhio lo stato di tutte le registrazioni obbligatorie per legge:
 * temperature, lotti, anomalie, sanificazione, controllo olio, reclami,
 * libretti sanitari e l'organico per postazione (laboratorio/pasticceria/sala/bar).
 */
import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Thermometer, Package, AlertTriangle, Droplet, SprayCan,
  FileWarning, IdCard, Users, RefreshCw, Printer, X,
} from "lucide-react";
import { API, withToken } from "../../utils/constants";

const SAGE = "#5b7a6b";
const NAVY = "#3f5a4e";
const CARD = "#fffefb";
const LINE = "#e6e0d4";

// Etichette e icone per le postazioni
const POSTAZIONI = {
  laboratorio: { label: "Laboratorio", emoji: "👨‍🍳" },
  pasticceria: { label: "Pasticceria", emoji: "🧁" },
  sala: { label: "Sala", emoji: "🍽️" },
  bar: { label: "Bar", emoji: "☕" },
  "Non assegnata": { label: "Non assegnata", emoji: "❓" },
};

function StatCard({ icon: Icon, label, valore, sotto, colore = SAGE, allarme }) {
  return (
    <div style={{
      background: CARD, border: `1px solid ${allarme ? "#e7b6ab" : LINE}`,
      borderRadius: 14, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 6,
      borderLeft: `4px solid ${allarme ? "#d35f4e" : colore}`,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#6b7669" }}>
        <Icon size={16} color={allarme ? "#d35f4e" : colore} />
        <span style={{ fontSize: 12, fontWeight: 600 }}>{label}</span>
      </div>
      <div style={{ fontSize: 26, fontWeight: 800, color: allarme ? "#d35f4e" : NAVY, lineHeight: 1 }}>{valore}</div>
      {sotto && <div style={{ fontSize: 11, color: "#9aa593" }}>{sotto}</div>}
    </div>
  );
}

export default function RegistroHACCPView() {
  const [dati, setDati] = useState(null);
  const [loading, setLoading] = useState(true);
  const [mostraStampa, setMostraStampa] = useState(false);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/diagnostic/registro-haccp`);
      setDati(r.data);
    } catch {
      toast.error("Errore caricamento registro HACCP");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  if (loading) return <div style={{ textAlign: "center", padding: 60, color: "#9aa593" }}>Caricamento registro…</div>;
  if (!dati) return <div style={{ textAlign: "center", padding: 60, color: "#9aa593" }}>Nessun dato disponibile</div>;

  const t = dati.temperature || {};
  const lib = dati.libretti || {};
  const organico = dati.organico || {};
  const allarmeLibretti = (lib.scaduti || 0) > 0;

  const statoLibrettoBadge = (stato, giorni) => {
    const mappa = {
      valido: { txt: "valido", bg: "#e7f0ea", fg: "#3d8168" },
      in_scadenza: { txt: `scade tra ${giorni}gg`, bg: "#fbf0dd", fg: "#9c6a32" },
      scaduto: { txt: "SCADUTO", bg: "#f7e0db", fg: "#d35f4e" },
      non_registrato: { txt: "da registrare", bg: "#f0ebe0", fg: "#9aa593" },
    };
    const s = mappa[stato] || mappa.non_registrato;
    return <span style={{ fontSize: 10, fontWeight: 700, background: s.bg, color: s.fg, borderRadius: 5, padding: "2px 7px" }}>{s.txt}</span>;
  };

  return (
    <div style={{ padding: "16px", maxWidth: 1000, margin: "0 auto", fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif" }}>
      {/* Azioni (il titolo della pagina è nell'intestazione uniforme) */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", marginBottom: 18, flexWrap: "wrap", gap: 10 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => setMostraStampa(true)} style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: 10, border: "none", background: SAGE, color: "#fff", fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
            <Printer size={15} /> Stampa registro
          </button>
          <button onClick={carica} style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 14px", borderRadius: 10, border: `1px solid ${LINE}`, background: CARD, color: SAGE, fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
            <RefreshCw size={15} /> Aggiorna
          </button>
        </div>
      </div>

      {/* Banner allarme libretti scaduti */}
      {allarmeLibretti && (
        <div style={{ background: "linear-gradient(135deg,#d35f4e,#b04a3a)", borderRadius: 14, padding: "14px 16px", marginBottom: 16, display: "flex", alignItems: "center", gap: 12 }}>
          <IdCard size={24} color="#fff" />
          <div>
            <div style={{ fontWeight: 800, fontSize: 15, color: "#fff" }}>{lib.scaduti} libretto/i sanitario/i SCADUTO/I</div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,.9)" }}>Da rinnovare con urgenza — obbligo di legge</div>
          </div>
        </div>
      )}

      {/* Registrazioni del giorno/mese */}
      <h3 style={{ fontSize: 13, fontWeight: 700, color: "#9aa593", textTransform: "uppercase", letterSpacing: "0.5px", margin: "0 0 10px" }}>Registrazioni</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 12, marginBottom: 22 }}>
        <StatCard icon={Thermometer} label="Temp. positive oggi" valore={t.positive_oggi ?? 0} sotto="frigoriferi / banchi" />
        <StatCard icon={Thermometer} label="Temp. negative oggi" valore={t.negative_oggi ?? 0} sotto="congelatori" colore="#3f5a4e" />
        <StatCard icon={Thermometer} label="Temp. cottura (mese)" valore={t.cottura_mese ?? 0} sotto="≥ 75°C al cuore" colore="#c4894a" />
        <StatCard icon={Droplet} label="Controllo olio (mese)" valore={dati.controllo_olio_mese ?? 0} sotto="friggitrici" colore="#c4a35a" />
        <StatCard icon={Package} label="Lotti attivi" valore={dati.lotti_attivi ?? 0} sotto="tracciabilità" />
        <StatCard icon={SprayCan} label="Sanificazione oggi" valore={dati.sanificazione_oggi ?? 0} colore="#3d8168" />
        <StatCard icon={AlertTriangle} label="Anomalie aperte" valore={dati.anomalie_aperte ?? 0} allarme={(dati.anomalie_aperte ?? 0) > 0} />
        <StatCard icon={FileWarning} label="Reclami fornitori aperti" valore={dati.reclami_aperti ?? 0} colore="#c77b56" />
      </div>

      {/* Libretti sanitari — sintesi */}
      <h3 style={{ fontSize: 13, fontWeight: 700, color: "#9aa593", textTransform: "uppercase", letterSpacing: "0.5px", margin: "0 0 10px" }}>Libretti sanitari</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 12, marginBottom: 22 }}>
        <StatCard icon={IdCard} label="Scaduti" valore={lib.scaduti ?? 0} allarme={(lib.scaduti ?? 0) > 0} />
        <StatCard icon={IdCard} label="In scadenza (30gg)" valore={lib.in_scadenza ?? 0} colore="#c4894a" />
        <StatCard icon={IdCard} label="Da registrare" valore={lib.non_registrati ?? 0} colore="#9aa593" />
      </div>

      {/* Organico per postazione */}
      <h3 style={{ fontSize: 13, fontWeight: 700, color: "#9aa593", textTransform: "uppercase", letterSpacing: "0.5px", margin: "0 0 10px" }}>
        <Users size={14} style={{ verticalAlign: "middle", marginRight: 5 }} />
        Organico per postazione ({dati.totale_dipendenti ?? 0} dipendenti)
      </h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 14 }}>
        {Object.entries(organico).map(([post, persone]) => {
          const info = POSTAZIONI[post] || { label: post, emoji: "📍" };
          return (
            <div key={post} style={{ background: CARD, border: `1px solid ${LINE}`, borderRadius: 14, padding: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, paddingBottom: 10, borderBottom: `1px solid ${LINE}` }}>
                <span style={{ fontSize: 22 }}>{info.emoji}</span>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: NAVY }}>{info.label}</div>
                  <div style={{ fontSize: 11, color: "#9aa593" }}>{persone.length} {persone.length === 1 ? "persona" : "persone"}</div>
                </div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {persone.map((p, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: NAVY }}>{p.nome} {p.cognome}</div>
                      <div style={{ fontSize: 11, color: "#9aa593" }}>{p.mansione || "mansione non assegnata"}</div>
                    </div>
                    {statoLibrettoBadge(p.stato_libretto, p.giorni_alla_scadenza)}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {mostraStampa && <ModalStampaRegistro onClose={() => setMostraStampa(false)} />}
    </div>
  );
}

// ── Modale: scegli periodo e sezioni da stampare ──────────────────────────────
const SEZIONI_STAMPA = [
  { id: "lotti", label: "Lotti di produzione", emoji: "📦", periodico: true },
  { id: "temperature", label: "Temperature frigo/congelatori", emoji: "🌡️", periodico: true },
  { id: "controllo_olio", label: "Controllo olio frittura", emoji: "🛢️", periodico: true },
  { id: "sanificazione", label: "Sanificazione", emoji: "🧴", periodico: false },
  { id: "anomalie", label: "Gestione non conformità", emoji: "⚠️", periodico: false },
  { id: "allergeni", label: "Allergeni", emoji: "🥜", periodico: false },
  { id: "fornitori_qualificati", label: "Fornitori qualificati", emoji: "🚚", periodico: false },
  { id: "ricevimento_merci", label: "Ricevimento merci", emoji: "📥", periodico: false },
  { id: "personale", label: "Personale e igiene", emoji: "👥", periodico: false },
  { id: "principi_haccp", label: "Principi HACCP e CCP", emoji: "📋", periodico: false },
];

function ModalStampaRegistro({ onClose }) {
  // Default: dal 1° gennaio dell'anno corrente a oggi
  const oggi = new Date();
  const inizioAnno = `${oggi.getFullYear()}-01-01`;
  const oggiStr = oggi.toISOString().slice(0, 10);

  const [dataDa, setDataDa] = useState(inizioAnno);
  const [dataA, setDataA] = useState(oggiStr);
  // Di default spunto lotti + temperature (il caso tipico del vigile)
  const [selez, setSelez] = useState(() => new Set(["lotti", "temperature"]));

  const toggle = (id) => setSelez((s) => {
    const n = new Set(s);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });

  const stampa = () => {
    if (selez.size === 0) { toast.error("Seleziona almeno una sezione"); return; }
    const sezioni = Array.from(selez).join(",");
    const anno = new Date(dataDa).getFullYear();
    const url = `${API}/manuale-haccp/genera-manuale?anno=${anno}&data_da=${dataDa}&data_a=${dataA}&sezioni=${sezioni}`;
    // Apre il documento stampabile in una nuova scheda
    window.open(withToken(url), "_blank");
    onClose();
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(42,51,41,0.55)", backdropFilter: "blur(3px)", zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }} onClick={onClose}>
      <div style={{ background: CARD, borderRadius: 18, maxWidth: 520, width: "100%", maxHeight: "90vh", overflowY: "auto", padding: 24 }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
          <h3 style={{ margin: 0, fontSize: 19, fontWeight: 700, color: NAVY, fontFamily: "'Fraunces', Georgia, serif" }}>Stampa registro HACCP</h3>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#9aa593" }}><X size={22} /></button>
        </div>

        {/* Periodo */}
        <div style={{ marginBottom: 18 }}>
          <label style={{ fontSize: 12, fontWeight: 700, color: "#6b7669", textTransform: "uppercase", letterSpacing: "0.5px" }}>Periodo di riferimento</label>
          <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
            <div style={{ flex: 1 }}>
              <span style={{ fontSize: 11, color: "#9aa593" }}>Dal</span>
              <input type="date" value={dataDa} onChange={(e) => setDataDa(e.target.value)} style={{ width: "100%", padding: "9px 10px", borderRadius: 9, border: `1px solid ${LINE}`, fontSize: 14, fontFamily: "inherit" }} />
            </div>
            <div style={{ flex: 1 }}>
              <span style={{ fontSize: 11, color: "#9aa593" }}>Al</span>
              <input type="date" value={dataA} onChange={(e) => setDataA(e.target.value)} style={{ width: "100%", padding: "9px 10px", borderRadius: 9, border: `1px solid ${LINE}`, fontSize: 14, fontFamily: "inherit" }} />
            </div>
          </div>
        </div>

        {/* Sezioni */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 12, fontWeight: 700, color: "#6b7669", textTransform: "uppercase", letterSpacing: "0.5px" }}>Sezioni da includere</label>
          <p style={{ fontSize: 11, color: "#9aa593", margin: "4px 0 10px" }}>Le sezioni con 📅 sono filtrate per il periodo scelto; le altre sono le pagine del manuale.</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {SEZIONI_STAMPA.map((s) => {
              const on = selez.has(s.id);
              return (
                <button key={s.id} onClick={() => toggle(s.id)} style={{
                  display: "flex", alignItems: "center", gap: 10, padding: "11px 14px", borderRadius: 10, cursor: "pointer",
                  border: on ? `2px solid ${SAGE}` : `1px solid ${LINE}`, background: on ? "#eef3ef" : CARD,
                  textAlign: "left", fontFamily: "inherit",
                }}>
                  <span style={{ fontSize: 18 }}>{s.emoji}</span>
                  <span style={{ flex: 1, fontSize: 14, fontWeight: on ? 700 : 500, color: NAVY }}>{s.label}</span>
                  {s.periodico && <span style={{ fontSize: 11 }}>📅</span>}
                  <span style={{ width: 20, height: 20, borderRadius: 6, border: on ? "none" : `1.5px solid ${LINE}`, background: on ? SAGE : "transparent", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 13, fontWeight: 800 }}>{on ? "✓" : ""}</span>
                </button>
              );
            })}
          </div>
        </div>

        <button onClick={stampa} style={{ width: "100%", padding: "15px", border: "none", borderRadius: 12, background: SAGE, color: "#fff", fontSize: 16, fontWeight: 800, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 10, fontFamily: "inherit" }}>
          <Printer size={20} /> Genera e stampa
        </button>
        <p style={{ fontSize: 11, color: "#9aa593", textAlign: "center", margin: "10px 0 0" }}>
          Si apre il documento stampabile: usa Stampa del browser (Ctrl/Cmd+P) per carta o PDF.
        </p>
      </div>
    </div>
  );
}
