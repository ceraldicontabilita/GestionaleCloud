import { useState, useEffect } from "react";
import axios from "axios";
import { API } from "../../utils/constants";
import {
  Upload, Building2, Boxes, ChefHat, Users, ClipboardCheck,
  BookOpen, CheckCircle2, Circle, ArrowRight, RotateCcw, Landmark,
} from "lucide-react";

// Configurazione guidata (onboarding): porta l'utente, in ordine, alle pagine reali
// dell'app per impostare un nuovo punto vendita. I passi completati restano segnati
// (localStorage) cosi' la checklist sopravvive ai cambi pagina e ai riavvii.
const STEPS = [
  {
    id: "fatture",
    tab: "fatture",
    icon: Upload,
    titolo: "Importa le fatture XML",
    perche:
      "E' il primo passo: dalle fatture elettroniche l'app crea prodotti, prezzi, lotti e giacenze. Senza import il resto resta vuoto.",
    azione: "Vai a Importa fatture",
  },
  {
    id: "azienda",
    tab: "personale",
    icon: Landmark,
    titolo: "Inserisci i dati dell'azienda",
    perche:
      "Ragione sociale, P.IVA, indirizzo, codice destinatario SDI e responsabile HACCP: compaiono su registri, schede, etichette e tutti i PDF. Si compilano nella pagina Personale.",
    azione: "Vai a Dati azienda",
  },
  {
    id: "fornitori",
    tab: "fornitori",
    icon: Building2,
    titolo: "Classifica i fornitori",
    perche:
      "Per ogni fornitore scegli se gestirlo completo (materie prime + magazzino), solo magazzino, oppure escluderlo. Determina cosa entra nelle ricette e nell'HACCP.",
    azione: "Vai a Fornitori",
  },
  {
    id: "materie",
    tab: "materie",
    icon: Boxes,
    titolo: "Controlla materie prime e schede",
    perche:
      "Verifica i prodotti reali per fornitore e, dove serve, aggiungi la scheda tecnica (sito produttore, foto etichetta o testo): composizione e allergeni finiscono in automatico nelle schede ricetta.",
    azione: "Vai a Materie Prime",
  },
  {
    id: "ricette",
    tab: "ricette",
    icon: ChefHat,
    titolo: "Verifica ricette e costi",
    perche:
      "Controlla ingredienti, dosi e food-cost. Gli allergeni dei prodotti composti vengono ereditati a cascata nella scheda della ricetta.",
    azione: "Vai a Ricette",
  },
  {
    id: "personale",
    tab: "personale",
    icon: Users,
    titolo: "Configura il personale HACCP",
    perche:
      "Inserisci gli operatori: servono per firmare registri, produzioni e controlli HACCP.",
    azione: "Vai a Personale",
  },
  {
    id: "registro_haccp",
    tab: "registro_haccp",
    icon: ClipboardCheck,
    titolo: "Apri i registri HACCP",
    perche:
      "Temperature, sanificazioni, olio frittura, ricezione merce: i registri sono pronti, basta iniziare a compilarli.",
    azione: "Vai a Registro HACCP",
  },
  {
    id: "guida",
    tab: "guida",
    icon: BookOpen,
    titolo: "Leggi la Guida",
    perche:
      "Spiegazione passo-passo di ogni pagina. Utile come ripasso e per formare il personale.",
    azione: "Apri la Guida",
  },
];

const LS_KEY = "lotti_onboarding_fatti";

function leggiFatti() {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) || "{}") || {};
  } catch {
    return {};
  }
}

export default function ConfiguraWizard({ onNavigate }) {
  const [fatti, setFatti] = useState(leggiFatti);
  const [autoDone, setAutoDone] = useState({});

  // Auto-verifica dallo stato reale del backend (non solo spunte manuali):
  // un passo risulta fatto se l'app rileva che è stato completato davvero.
  useEffect(() => {
    let vivo = true;
    (async () => {
      const next = {};
      try {
        const r = await axios.get(`${API}/diagnostic/salute-sistema`);
        if ((r.data?.conteggi?.fatture || 0) > 0) next.fatture = true;
      } catch { /* offline: resta la spunta manuale */ }
      try {
        const r = await axios.get(`${API}/azienda`);
        if (r.data?.salvata) next.azienda = true;
      } catch { /* idem */ }
      try {
        const r = await axios.get(`${API}/tablet-operatori`);
        if (Array.isArray(r.data) && r.data.length > 0) next.personale = true;
      } catch { /* idem */ }
      if (vivo) setAutoDone(next);
    })();
    return () => { vivo = false; };
  }, []);

  const isDone = (id) => !!fatti[id] || !!autoDone[id];

  useEffect(() => {
    try {
      localStorage.setItem(LS_KEY, JSON.stringify(fatti));
    } catch { /* storage non disponibile: la checklist resta solo in sessione */ }
  }, [fatti]);

  const toggle = (id) => setFatti((f) => ({ ...f, [id]: !f[id] }));
  const reset = () => setFatti({});

  const completati = STEPS.filter((s) => isDone(s.id)).length;
  const perc = Math.round((completati / STEPS.length) * 100);

  return (
    <div className="max-w-3xl mx-auto p-4">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-gray-800">Configurazione guidata</h1>
        <p className="text-gray-500 mt-1">
          Segui i passi in ordine per impostare l'attivita'. Alcuni passi si segnano da soli quando l'app rileva che sono fatti; gli altri puoi spuntarli a mano.
        </p>
      </div>

      {/* avanzamento */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 mb-5">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-600">
            {completati} di {STEPS.length} completati
          </span>
          <div className="flex items-center gap-3">
            <span className="text-sm font-bold text-emerald-700">{perc}%</span>
            {completati > 0 && (
              <button
                onClick={reset}
                className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1"
              >
                <RotateCcw size={13} /> azzera
              </button>
            )}
          </div>
        </div>
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-emerald-500 transition-all duration-300"
            style={{ width: `${perc}%` }}
          />
        </div>
      </div>

      {/* passi */}
      <div className="space-y-3">
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          const done = isDone(s.id);
          return (
            <div
              key={s.id}
              className={`bg-white rounded-xl border p-4 transition-colors ${
                done ? "border-emerald-200 bg-emerald-50/40" : "border-gray-100"
              }`}
            >
              <div className="flex items-start gap-3">
                <button
                  onClick={() => { if (!autoDone[s.id]) toggle(s.id); }}
                  className="mt-0.5 shrink-0"
                  title={autoDone[s.id] ? "Rilevato automaticamente dall'app" : (done ? "Segna come da fare" : "Segna come completato")}
                  style={autoDone[s.id] ? { cursor: "default" } : undefined}
                >
                  {done ? (
                    <CheckCircle2 size={22} className="text-emerald-600" />
                  ) : (
                    <Circle size={22} className="text-gray-300" />
                  )}
                </button>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-gray-400">
                      Passo {i + 1}
                    </span>
                    <Icon size={15} className="text-gray-400" />
                    <h3
                      className={`font-semibold ${
                        done ? "text-emerald-800 line-through decoration-emerald-300" : "text-gray-800"
                      }`}
                    >
                      {s.titolo}
                    </h3>
                    {autoDone[s.id] && (
                      <span className="text-[10px] font-bold text-emerald-700 bg-emerald-100 rounded-full px-2 py-0.5">rilevato</span>
                    )}
                  </div>
                  <p className="text-sm text-gray-500 mt-1 leading-relaxed">{s.perche}</p>

                  <button
                    onClick={() => onNavigate && onNavigate(s.tab)}
                    className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-emerald-700 hover:text-emerald-800"
                  >
                    {s.azione} <ArrowRight size={15} />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {completati === STEPS.length && (
        <div className="mt-5 bg-emerald-600 text-white rounded-xl p-4 text-center">
          <p className="font-semibold">Configurazione completata.</p>
          <p className="text-sm text-emerald-50 mt-1">
            L'attivita' e' pronta. Puoi tornare qui in qualsiasi momento dal menu.
          </p>
        </div>
      )}
    </div>
  );
}
