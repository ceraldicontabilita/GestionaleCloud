import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import {
  CheckCircle2, AlertCircle, RefreshCw, Activity, FileText, Tag, Eraser,
  BarChart3, ClipboardCheck, Thermometer, Database,
} from "lucide-react";
import { API } from "../../utils/constants";

const SAGE = "#5b7a6b";
const NAVY = "#3f5a4e";
const CARD = "#fffefb";
const LINE = "#e6e0d4";


// Ogni voce porta alla sezione che svolge quella funzione.
const _AZIONE_JOB = {
  "Sincronizzazione fatture": "fatture",
  "Normalizzazione nomi prodotti": "magazzino_prodotti",
  "Pulizia lotti scaduti": "lotti",
  "Controllo scorte minime": "tablet/magazzino",
  "Registri HACCP giornalieri": "registro_haccp",
  "Controlli olio/temperature/reclami": "controllo_olio",
  "Backup dati": "controllo_dati",
};
function _vaiAzione(label) {
  const dest = _AZIONE_JOB[label];
  if (dest) window.location.hash = dest;
}

// Icona Lucide per job (il backend manda un'emoji, ma le emoji nelle UI
// rendono con colori di sistema non controllabili — es. 💾/📊 blu su Android).
const _ICONA_JOB = {
  "Sincronizzazione fatture": FileText,
  "Normalizzazione nomi prodotti": Tag,
  "Pulizia lotti scaduti": Eraser,
  "Controllo scorte minime": BarChart3,
  "Registri HACCP giornalieri": ClipboardCheck,
  "Controlli olio/temperature/reclami": Thermometer,
  "Backup dati": Database,
};

function tempoFa(iso) {
  if (!iso) return "mai";
  try {
    const d = new Date(iso);
    const min = Math.floor((Date.now() - d.getTime()) / 60000);
    if (min < 1) return "ora";
    if (min < 60) return `${min} min fa`;
    const ore = Math.floor(min / 60);
    if (ore < 24) return `${ore} h fa`;
    return `${Math.floor(ore / 24)} g fa`;
  } catch {
    return "—";
  }
}

/**
 * Widget "Stato sistema": mostra con semafori cosa gira in automatico.
 * Rassicura l'utente che fatture, normalizzazione, scorte ecc. funzionano da soli.
 */
export default function StatoSistemaWidget() {
  const [dati, setDati] = useState(null);
  const [loading, setLoading] = useState(true);

  const carica = useCallback(async (tentativo = 1) => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/diagnostic/salute-sistema`, { timeout: 60000 });
      setDati(r.data);
      setLoading(false);
    } catch (e) {
      // Render cold start → riprova qualche volta prima di arrendersi
      if (tentativo < 4) {
        setTimeout(() => carica(tentativo + 1), 2500);
      } else {
        console.error(e);
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  return (
    <div style={{ background: CARD, border: `1px solid ${LINE}`, borderRadius: 16, padding: 18, fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
        <Activity size={18} color={SAGE} />
        <span style={{ fontSize: 16, fontWeight: 600, color: NAVY, fontFamily: "'Fraunces', Georgia, serif", flex: 1 }}>
          Stato sistema
        </span>
        {dati && (
          <span style={{ fontSize: 12, fontWeight: 700, padding: "3px 10px", borderRadius: 20, background: dati.tutto_ok ? "#e2efe8" : "#f7ecdc", color: dati.tutto_ok ? "#3d8168" : "#9c6a32" }}>
            {dati.tutto_ok ? "Tutto regolare" : "Da controllare"}
          </span>
        )}
        <button onClick={() => carica()} style={{ background: "none", border: "none", cursor: "pointer", color: "#9aa593", display: "flex" }}>
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {loading && !dati && <div style={{ textAlign: "center", color: "#9aa593", padding: 20, fontSize: 13 }}>Verifica in corso...</div>}

      {dati && (
        <>
          {/* Semafori job */}
          <div style={{ display: "grid", gap: 7, marginBottom: 14 }}>
            {dati.job.map((j, i) => (
              <div key={i} onClick={() => _vaiAzione(j.label)} title="Apri"
                style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: "#faf7f0", borderRadius: 10, cursor: _AZIONE_JOB[j.label] ? "pointer" : "default" }}
                onMouseEnter={(e) => { if (_AZIONE_JOB[j.label]) e.currentTarget.style.background = "#f0ebe0"; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = "#faf7f0"; }}>
                {(() => { const Icona = _ICONA_JOB[j.label] || Activity; return <Icona size={18} color={SAGE} />; })()}
                <span style={{ flex: 1, fontSize: 13, fontWeight: 500, color: NAVY }}>{j.label}</span>
                <span style={{ fontSize: 11, color: "#9aa593" }}>{tempoFa(j.ultima_esecuzione)}</span>
                {j.ok ? (
                  <CheckCircle2 size={17} color="#3d8168" />
                ) : (
                  <AlertCircle size={17} color="#c4894a" />
                )}
                {_AZIONE_JOB[j.label] && <span style={{ fontSize: 15, color: "#c3cbbd", fontWeight: 700, marginLeft: 2 }}>›</span>}
              </div>
            ))}
          </div>

          {/* Conteggi */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8 }}>
            {[
              { l: "Fatture", v: dati.conteggi.fatture, dest: "fatture" },
              { l: "Lotti attivi", v: dati.conteggi.lotti_attivi, dest: "lotti" },
              { l: "Ordini bozza", v: dati.conteggi.ordini_bozza, dest: "ordini" },
              { l: "Prodotti", v: dati.conteggi.prodotti, dest: "magazzino_prodotti" },
            ].map((c, i) => (
              <div key={i} onClick={() => { if (c.dest) window.location.hash = c.dest; }} style={{ textAlign: "center", padding: "10px 6px", background: "#f0ebe0", borderRadius: 10, cursor: "pointer" }}>
                <div style={{ fontSize: 20, fontWeight: 800, color: SAGE }}>{c.v}</div>
                <div style={{ fontSize: 10, color: "#6b7669", fontWeight: 600 }}>{c.l}</div>
              </div>
            ))}
          </div>

          <p style={{ margin: "12px 0 0", fontSize: 11, color: "#9aa593", textAlign: "center" }}>
            Girano in automatico ogni notte. Tocca una voce per aprire la sezione collegata.
          </p>
        </>
      )}
    </div>
  );
}
