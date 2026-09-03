/**
 * CataloghiEsterniView.jsx — "Cataloghi fornitori (web)" (richiesta Enzo
 * 03/07/2026: "in admin... una pagina dove io inserendo il link tu capisci
 * che devi fare come stai facendo per Acquaviva/Saima, così posso
 * aggiungere i cataloghi dei miei fornitori ogni volta che inserisco
 * l'indirizzo"). Pagina admin: Enzo incolla nome+URL di un sito fornitore,
 * il backend (fonti_catalogo.py) prova a scaricarne il catalogo prodotti
 * (sitemap + dati Schema.org/Open Graph delle pagine prodotto — nessuno
 * scraper scritto a mano per ogni sito, come per SAIMA, perché qui il sito
 * non è ancora stato ispezionato dal vivo).
 *
 * LIMITE ONESTO mostrato in pagina: questo è un tentativo automatico
 * generico, non garantito per ogni sito — l'esito reale si vede solo dopo
 * "Sincronizza ora" (che gira sul backend live, con accesso a internet).
 */
import { useState, useEffect, useCallback } from "react";
import { conferma } from "../../utils/conferma";
import axios from "axios";
import { toast } from "sonner";
import { apiError } from "../../utils/apiError";
import { API } from "../../utils/constants";
import { Globe, Plus, RefreshCw, Trash2, CheckCircle2, AlertCircle, Clock, ExternalLink } from "lucide-react";

const STATO_UI = {
  nuova:     { label: "Non ancora sincronizzata", colore: "bg-gray-100 text-gray-500", icon: Clock },
  in_corso:  { label: "Sincronizzazione in corso…", colore: "bg-amber-50 text-amber-700", icon: RefreshCw },
  attivo:    { label: "Sincronizzata", colore: "bg-green-50 text-green-700", icon: CheckCircle2 },
  errore:    { label: "Errore / nessun dato trovato", colore: "bg-red-50 text-red-700", icon: AlertCircle },
};

export default function CataloghiEsterniView() {
  const [fonti, setFonti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [nome, setNome] = useState("");
  const [url, setUrl] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [sincronizzando, setSincronizzando] = useState(null);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/fonti-catalogo`);
      setFonti(Array.isArray(data) ? data : []);
    } catch (e) {
      toast.error("Errore caricamento: " + apiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  // Mentre una fonte è "in_corso" ricontrolla ogni 4s finché non si conclude.
  useEffect(() => {
    if (!fonti.some(f => f.stato === "in_corso")) return;
    const t = setInterval(carica, 4000);
    return () => clearInterval(t);
  }, [fonti, carica]);

  const aggiungi = async () => {
    if (!nome.trim() || !url.trim()) { toast.error("Scrivi nome e indirizzo del sito"); return; }
    setSalvando(true);
    try {
      await axios.post(`${API}/fonti-catalogo`, { nome: nome.trim(), url: url.trim() });
      toast.success("Fonte aggiunta — premi Sincronizza per scaricare il catalogo");
      setNome(""); setUrl("");
      await carica();
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    } finally {
      setSalvando(false);
    }
  };

  const sincronizza = async (f) => {
    setSincronizzando(f.id);
    try {
      await axios.post(`${API}/fonti-catalogo/${f.id}/sincronizza`);
      toast.success(`Sincronizzazione di ${f.nome} avviata — la pagina si aggiorna da sola`);
      await carica();
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    } finally {
      setSincronizzando(null);
    }
  };

  const elimina = async (f) => {
    if (!await conferma(`Eliminare la fonte "${f.nome}"? I prodotti già scaricati restano, a meno che tu non lo chieda esplicitamente qui.`)) return;
    const eliminaProdotti = await conferma("Vuoi eliminare anche i prodotti già scaricati di questa fonte?");
    try {
      await axios.delete(`${API}/fonti-catalogo/${f.id}`, { params: { elimina_prodotti: eliminaProdotti } });
      toast.success("Fonte eliminata");
      await carica();
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    }
  };

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-3 mb-1">
        <Globe size={22} className="text-[#5b7a6b]" />
        <h1 className="text-xl font-bold text-gray-800">Cataloghi fornitori (web)</h1>
      </div>
      <p className="text-sm text-gray-500 mb-4">
        Incolla il sito di un fornitore: il sistema prova a scaricarne da solo foto,
        nomi, prezzi e descrizioni dei prodotti (come già succede per Acquaviva/SAIMA),
        senza bisogno di uno sviluppo dedicato per ogni sito nuovo.
      </p>

      <div className="bg-[#f2f6f3] border border-[#cfdfd5] rounded-xl px-4 py-3 mb-5 text-sm text-[#3f5a4e]">
        <strong>Come funziona davvero:</strong> è un tentativo automatico, non una garanzia —
        funziona bene sui siti che pubblicano dati prodotto in formato standard (la maggior
        parte dei negozi online moderni lo fa). Se un sito non lo prevede, la fonte resta
        "in errore" con il motivo scritto: niente prodotti inventati. In quel caso serve un
        listino/PDF caricato a mano, come già fatto altrove.
      </div>

      {/* Form nuova fonte */}
      <div className="bg-white rounded-xl border border-gray-100 p-4 mb-6 flex flex-wrap gap-3 items-end">
        <div className="flex-1 min-w-[160px]">
          <label className="block text-xs font-semibold text-gray-500 mb-1">Nome fornitore</label>
          <input value={nome} onChange={e => setNome(e.target.value)} placeholder="es. Il Pasticcere"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div className="flex-[2] min-w-[240px]">
          <label className="block text-xs font-semibold text-gray-500 mb-1">Indirizzo del sito</label>
          <input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://www.ilpasticcere.it/"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm" />
        </div>
        <button onClick={aggiungi} disabled={salvando}
          className="flex items-center gap-2 px-4 py-2 bg-[#5b7a6b] text-white rounded-lg text-sm font-medium hover:bg-[#4d6a5c] disabled:opacity-50">
          <Plus size={14} /> Aggiungi
        </button>
      </div>

      {/* Elenco fonti */}
      {loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Caricamento...</div>
      ) : fonti.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <Globe size={32} className="mx-auto mb-2 opacity-30" />
          <p className="text-sm">Nessuna fonte aggiunta ancora.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {fonti.map(f => {
            const st = STATO_UI[f.stato] || STATO_UI.nuova;
            const Icon = st.icon;
            return (
              <div key={f.id} className="bg-white rounded-xl border border-gray-100 p-4 flex items-center gap-4 flex-wrap">
                <div className="flex-1 min-w-[200px]">
                  <div className="flex items-center gap-2">
                    <p className="font-semibold text-gray-800">{f.nome}</p>
                    <a href={f.url} target="_blank" rel="noreferrer" className="text-gray-400 hover:text-[#5b7a6b]">
                      <ExternalLink size={13} />
                    </a>
                  </div>
                  <p className="text-xs text-gray-400 truncate">{f.url}</p>
                </div>
                <span className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${st.colore}`}>
                  <Icon size={12} className={f.stato === "in_corso" ? "animate-spin" : ""} /> {st.label}
                </span>
                {f.stato === "attivo" && (
                  <span className="text-xs text-gray-500">{f.prodotti_trovati} prodotti</span>
                )}
                {f.stato === "errore" && f.ultimo_errore && (
                  <span className="text-xs text-red-500 max-w-[220px] truncate" title={f.ultimo_errore}>{f.ultimo_errore}</span>
                )}
                <div className="flex items-center gap-2 ml-auto">
                  <button onClick={() => sincronizza(f)} disabled={sincronizzando === f.id || f.stato === "in_corso"}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-[#f2f6f3] border border-[#cfdfd5] text-[#5b7a6b] rounded-lg text-xs font-medium hover:bg-[#dce8e0] disabled:opacity-50">
                    <RefreshCw size={12} className={sincronizzando === f.id ? "animate-spin" : ""} /> Sincronizza
                  </button>
                  <button onClick={() => elimina(f)}
                    className="p-1.5 text-gray-400 hover:text-red-600 rounded-lg hover:bg-red-50">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
