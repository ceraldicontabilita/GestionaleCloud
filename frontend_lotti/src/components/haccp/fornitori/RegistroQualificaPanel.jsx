import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  ShieldCheck, ShieldAlert, Clock, ChevronDown, ChevronRight,
  AlertTriangle, Check, X,
} from "lucide-react";
import { API } from "../../../utils/constants";
import { Card } from "../shared/Card";

// Registro Qualifica Fornitori HACCP (Reg. CE 178/2002 art. 18).
// Estratto da FornitoriList.jsx (refactor 25/07/2026): stato e chiamate
// identici, solo spostati qui. Ricarica le schede quando cambia `fornitori`.
export default function RegistroQualificaPanel({ fornitori }) {
  const [schedeQualifica, setSchedeQualifica] = useState([]);
  const [showQualifica, setShowQualifica]     = useState(false);
  const [approvandoQ, setApprovandoQ]         = useState(null);

  useEffect(() => {
    axios.get(`${API}/haccp-auto-manuale/schede-qualifica`)
      .then(r => setSchedeQualifica(r.data || []))
      .catch(() => {});
  }, [fornitori]);

  const approvaQualifica = async (nome, approva) => {
    setApprovandoQ(nome);
    try {
      await axios.post(`${API}/haccp-auto-manuale/qualifica-fornitore?nome=${encodeURIComponent(nome)}&approva=${approva}`);
      toast.success(approva ? `${nome} — qualificato nel registro HACCP` : `${nome} — sospeso`);
      const res = await axios.get(`${API}/haccp-auto-manuale/schede-qualifica`);
      setSchedeQualifica(res.data || []);
    } catch { toast.error("Errore aggiornamento qualifica"); }
    finally { setApprovandoQ(null); }
  };

  return (
    <Card>
      <button
        onClick={() => setShowQualifica(v => !v)}
        className="w-full p-4 flex items-center justify-between hover:bg-gray-50 rounded-xl transition-colors"
      >
        <div className="flex items-center gap-3">
          <ShieldCheck size={20} className="text-green-600" />
          <div className="text-left">
            <p className="font-semibold text-gray-800">Registro Qualifica Fornitori — HACCP</p>
            <p className="text-xs text-gray-500 mt-0.5">
              Reg. CE 178/2002 art. 18 ·{" "}
              {schedeQualifica.filter(s => s.stato === "approvato").length} approvati ·{" "}
              {schedeQualifica.filter(s => s.stato === "in_attesa_verifica").length} in attesa ·{" "}
              {schedeQualifica.filter(s => s.stato === "sospeso").length} sospesi
            </p>
          </div>
        </div>
        {showQualifica ? <ChevronDown size={18} className="text-gray-400" /> : <ChevronRight size={18} className="text-gray-400" />}
      </button>

      {showQualifica && (
        <div className="border-t">
          <div className="p-3 bg-amber-50 border-b text-xs text-amber-800 flex gap-2">
            <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
            <span>
              <strong>Obbligo HACCP:</strong> Ogni fornitore deve essere qualificato prima di accettarne le forniture.
              Clicca <Check size={10} className="inline" /> per approvare o <X size={10} className="inline" /> per sospendere.
            </span>
          </div>
          <div className="divide-y max-h-[500px] overflow-y-auto">
            {schedeQualifica.map(s => (
              <div key={s.id || s.nome_fornitore} className="p-3 flex items-start gap-3 hover:bg-gray-50">
                <div className="flex-shrink-0 mt-0.5">
                  {s.stato === "approvato"           && <ShieldCheck size={18} className="text-green-500" />}
                  {s.stato === "in_attesa_verifica"  && <Clock size={18} className="text-amber-500" />}
                  {s.stato === "sospeso"             && <ShieldAlert size={18} className="text-red-500" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">{s.nome_fornitore}</p>
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5">
                    <span className="text-xs text-gray-500">{s.categoria_merceologica}</span>
                    <span className="text-xs text-gray-400">T°: {s.temperatura_stoccaggio_richiesta}</span>
                    <span className="text-xs text-gray-400">{s.num_fatture} fatture · {s.ultima_fornitura}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {(s.criteri_qualifica?.certificazioni_richieste || []).map(c => (
                      <span key={c} className="text-[10px] bg-[#f2f6f3] text-[#5b7a6b] px-1.5 py-0.5 rounded">{c}</span>
                    ))}
                  </div>
                </div>
                <div className="flex gap-1.5 flex-shrink-0">
                  {s.stato !== "approvato" && (
                    <button
                      onClick={() => approvaQualifica(s.nome_fornitore, true)}
                      disabled={approvandoQ === s.nome_fornitore}
                      className="p-1.5 bg-green-100 text-green-700 hover:bg-green-200 rounded-lg transition-colors disabled:opacity-40"
                      title="Approva"
                    ><Check size={14} /></button>
                  )}
                  {s.stato !== "sospeso" && (
                    <button
                      onClick={() => approvaQualifica(s.nome_fornitore, false)}
                      disabled={approvandoQ === s.nome_fornitore}
                      className="p-1.5 bg-red-100 text-red-700 hover:bg-red-200 rounded-lg transition-colors disabled:opacity-40"
                      title="Sospendi"
                    ><X size={14} /></button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
