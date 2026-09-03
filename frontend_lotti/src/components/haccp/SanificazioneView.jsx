import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Sparkles, ChevronLeft, ChevronRight, Save, RefreshCw, Refrigerator, Snowflake, Check, X, Printer } from "lucide-react";
import Button from "../ui/Button";
import { API, MESI_IT, withToken } from "../../utils/constants";
import { formattaDataItaliana, giorniNelMese } from "../../utils/dateUtils";

// Operatore sanificazione apparecchi
const OPERATORE_SANIFICAZIONE = "SANKAPALA ARACHCHILAGE JANANIE AYACHANA DISSANAYAKA";

const SanificazioneView = () => {
  const [mese, setMese] = useState(new Date().getMonth() + 1);
  const [anno, setAnno] = useState(new Date().getFullYear());
  const [scheda, setScheda] = useState(null);
  const [attrezzature, setAttrezzature] = useState([]);
  const [schedaApparecchi, setSchedaApparecchi] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [viewMode, setViewMode] = useState("attrezzature"); // "attrezzature" o "apparecchi"

  const numGiorni = giorniNelMese(mese, anno);

  const fetchScheda = useCallback(async () => {
    setLoading(true);
    try {
      const [schedaRes, attrRes, apparecchiRes] = await Promise.all([
        axios.get(`${API}/sanificazione/scheda/${anno}/${mese}`),
        axios.get(`${API}/sanificazione/attrezzature`),
        axios.get(`${API}/sanificazione/apparecchi/${anno}`)
      ]);
      
      const schedaData = schedaRes.data;
      
      // Verifica se la scheda è vuota e popola automaticamente
      const registrazioni = schedaData?.registrazioni || {};
      const hasData = Object.values(registrazioni).some(attr => Object.keys(attr).length > 0);
      
      if (!hasData) {
        // Scheda vuota - popola automaticamente
        try {
          const popolaRes = await axios.post(`${API}/haccp-auto/popola-sanificazione?anno=${anno}&mese=${mese}`);
          if (popolaRes.data.success) {
            toast.success(`Scheda sanificazione ${mese}/${anno} popolata automaticamente`);
            // Ricarica la scheda dopo il popolamento
            const nuovaScheda = await axios.get(`${API}/sanificazione/scheda/${anno}/${mese}`);
            setScheda(nuovaScheda.data);
          }
        } catch (e) {
          // Popolamento non necessario o già presente
          setScheda(schedaData);
        }
      } else {
        setScheda(schedaData);
      }
      
      setAttrezzature(attrRes.data);
      setSchedaApparecchi(apparecchiRes.data);
    } catch (err) {
      toast.error("Errore caricamento scheda");
    }
    setLoading(false);
  }, [mese, anno]);

  useEffect(() => { fetchScheda(); }, [fetchScheda]);

  const toggleCella = (attr, giorno) => {
    if (!scheda) return;
    
    const nuoveReg = { ...scheda.registrazioni };
    if (!nuoveReg[attr]) nuoveReg[attr] = {};
    
    nuoveReg[attr][giorno] = nuoveReg[attr][giorno] === "X" ? "" : "X";
    setScheda({ ...scheda, registrazioni: nuoveReg });
  };

  const marcaTuttoGiorno = (giorno) => {
    if (!scheda) return;
    const nuoveReg = { ...scheda.registrazioni };
    attrezzature.forEach(attr => {
      if (!nuoveReg[attr]) nuoveReg[attr] = {};
      nuoveReg[attr][giorno] = "X";
    });
    setScheda({ ...scheda, registrazioni: nuoveReg });
  };

  const salvaScheda = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/sanificazione/scheda/${anno}/${mese}`, {
        registrazioni: scheda.registrazioni,
        operatore: scheda.operatore_responsabile
      });
      toast.success("Scheda salvata!");
    } catch (err) {
      toast.error("Errore salvataggio");
    }
    setSaving(false);
  };

  const cambaMese = (delta) => {
    let nuovoMese = mese + delta;
    let nuovoAnno = anno;
    if (nuovoMese < 1) { nuovoMese = 12; nuovoAnno--; }
    if (nuovoMese > 12) { nuovoMese = 1; nuovoAnno++; }
    setMese(nuovoMese);
    setAnno(nuovoAnno);
  };

  // Ottieni sanificazione per un apparecchio in un giorno specifico
  const getSanificazioneGiorno = (tipo, numero, giorno) => {
    if (!schedaApparecchi) return null;
    const chiave = String(numero);
    const registrazioni = tipo === "frigorifero" 
      ? schedaApparecchi.registrazioni_frigoriferi?.[chiave] || []
      : schedaApparecchi.registrazioni_congelatori?.[chiave] || [];
    return registrazioni.find(s => s.mese === mese && s.giorno === giorno);
  };

  // Conta statistiche apparecchi
  const getStatisticheApparecchi = () => {
    if (!schedaApparecchi) return { totale: 0, eseguite: 0, non_eseguite: 0 };
    
    let totale = 0, eseguite = 0;
    
    // Frigoriferi
    for (const sanifs of Object.values(schedaApparecchi.registrazioni_frigoriferi || {})) {
      const meseCorrente = sanifs.filter(s => s.mese === mese);
      totale += meseCorrente.length;
      eseguite += meseCorrente.filter(s => s.eseguita).length;
    }
    
    // Congelatori
    for (const sanifs of Object.values(schedaApparecchi.registrazioni_congelatori || {})) {
      const meseCorrente = sanifs.filter(s => s.mese === mese);
      totale += meseCorrente.length;
      eseguite += meseCorrente.filter(s => s.eseguita).length;
    }
    
    return { totale, eseguite, non_eseguite: totale - eseguite };
  };

  if (loading) return <div className="text-center py-10"><RefreshCw className="animate-spin mx-auto" /></div>;

  const statsApparecchi = getStatisticheApparecchi();

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <p className="text-sm font-semibold text-gray-600">{scheda?.azienda} - {scheda?.area}</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => cambaMese(-1)} className="p-2 hover:bg-gray-100 rounded"><ChevronLeft size={20}/></button>
          <span className="font-semibold min-w-[150px] text-center">{MESI_IT[mese-1]} {anno}</span>
          <button onClick={() => cambaMese(1)} className="p-2 hover:bg-gray-100 rounded"><ChevronRight size={20}/></button>
          <Button onClick={() => window.open(withToken(`${API}/sanificazione/export-pdf/${anno}/${mese}`), '_blank')} variant="secondary" size="sm" data-testid="stampa-sanificazione-btn">
            <Printer size={16}/> PDF
          </Button>
          {viewMode === "attrezzature" && (
            <Button onClick={salvaScheda} disabled={saving}>
              <Save size={16}/> {saving ? "Salvo..." : "Salva"}
            </Button>
          )}
        </div>
      </div>

      {/* Tab Switch */}
      <div className="flex gap-2 border-b pb-2">
        <button
          onClick={() => setViewMode("attrezzature")}
          className={`px-4 py-2 rounded-t-lg font-medium transition-colors ${
            viewMode === "attrezzature" 
              ? "bg-[#5b7a6b] text-white" 
              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          }`}
        >
          <Sparkles size={16} className="inline mr-2" />
          Attrezzature
        </button>
        <button
          onClick={() => setViewMode("apparecchi")}
          className={`px-4 py-2 rounded-t-lg font-medium transition-colors ${
            viewMode === "apparecchi" 
              ? "bg-green-500 text-white" 
              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          }`}
        >
          <Refrigerator size={16} className="inline mr-2" />
          Apparecchi Refrigeranti
        </button>
      </div>

      {viewMode === "attrezzature" ? (
        <>
          {/* Pulsanti rapidi */}
          <div className="flex gap-2 overflow-x-auto pb-2">
            <span className="text-sm text-gray-500 py-1">Marca tutto:</span>
            {Array.from({length: numGiorni}, (_, i) => (
              <button
                key={i+1}
                onClick={() => marcaTuttoGiorno(String(i+1))}
                className="px-2 py-1 text-xs bg-[#f2f6f3] hover:bg-[#dce8e0] text-[#5b7a6b] rounded"
              >
                {i+1}
              </button>
            ))}
          </div>

          {/* Tabella Attrezzature */}
          <div className="bg-white rounded-lg border overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-gray-700 sticky left-0 bg-gray-50 min-w-[200px]">Attrezzatura</th>
                  {Array.from({length: numGiorni}, (_, i) => (
                    <th key={i+1} className="px-1 py-2 text-center font-medium text-gray-600 min-w-[30px]">{i+1}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y">
                {attrezzature.map(attr => (
                  <tr key={attr} className="hover:bg-gray-50">
                    <td className="px-3 py-2 font-medium text-gray-800 sticky left-0 bg-white text-xs">{attr}</td>
                    {Array.from({length: numGiorni}, (_, i) => {
                      const g = String(i + 1);
                      const val = scheda?.registrazioni?.[attr]?.[g] || "";
                      return (
                        <td key={g} className="px-1 py-1 text-center">
                          <button
                            onClick={() => toggleCella(attr, g)}
                            title={val === "N/D"
                              ? "Quel giorno non è stata registrata nessuna sanificazione (sistema non attivo). Tocca per registrarla ora."
                              : undefined}
                            className={`w-6 h-6 rounded text-xs font-bold transition-colors ${
                              val === "X"
                                ? "bg-[#5b7a6b] text-white"
                                : val === "N/D"
                                  ? "bg-[#f4f1ea] text-[#8a6f47] text-[8px] leading-none whitespace-nowrap"
                                  : "bg-gray-100 hover:bg-gray-200 text-gray-400"
                            }`}
                          >
                            {val === "X" ? "X" : val === "N/D" ? "N/D" : ""}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Footer Attrezzature */}
          <div className="flex items-center justify-between text-sm text-gray-500 bg-gray-50 p-3 rounded-lg">
            <span>Responsabile: <strong>{scheda?.operatore_responsabile || "N/D"}</strong></span>
            <span>Ultimo aggiornamento: {formattaDataItaliana(scheda?.updated_at)}</span>
          </div>
        </>
      ) : (
        <>
          {/* Sezione Apparecchi Refrigeranti */}
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <h3 className="font-semibold text-green-800 mb-2">
              👷 Operatore Sanificazione Apparecchi
            </h3>
            <p className="text-sm text-green-700">{OPERATORE_SANIFICAZIONE}</p>
            <p className="text-xs text-green-600 mt-1">
              Pulizia ogni 7-10 giorni per ogni apparecchio • Un solo apparecchio per giorno
            </p>
          </div>

          {/* Statistiche Mese */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-white border rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-gray-800">{statsApparecchi.totale}</div>
              <div className="text-xs text-gray-500">Sanificazioni programmate</div>
            </div>
            <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-green-600">{statsApparecchi.eseguite}</div>
              <div className="text-xs text-green-700">Eseguite</div>
            </div>
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-red-600">{statsApparecchi.non_eseguite}</div>
              <div className="text-xs text-red-700">Non eseguite</div>
            </div>
          </div>

          {/* Tabella Frigoriferi - GIORNI come righe, FRIGO come colonne */}
          <div className="bg-white rounded-lg border overflow-hidden">
            <div className="bg-orange-50 px-4 py-2 flex items-center gap-2">
              <Refrigerator size={18} className="text-orange-600" />
              <h4 className="font-semibold text-orange-800">Frigoriferi (0°C / +4°C)</h4>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium text-gray-700 sticky left-0 bg-gray-50 min-w-[60px]">Giorno</th>
                    {Array.from({length: 12}, (_, i) => (
                      <th key={i+1} className="px-1 py-2 text-center font-medium text-gray-600 min-w-[55px]">
                        <span className="text-xs">Frigo</span><br/>{i+1}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {Array.from({length: numGiorni}, (_, giornoIdx) => {
                    const giorno = giornoIdx + 1;
                    
                    return (
                      <tr key={giorno} className="hover:bg-gray-50">
                        <td className="px-3 py-1 font-medium text-gray-800 sticky left-0 bg-white">
                          {giorno}
                        </td>
                        {Array.from({length: 12}, (_, frigoIdx) => {
                          const numero = frigoIdx + 1;
                          const sanif = getSanificazioneGiorno("frigorifero", numero, giorno);
                          
                          return (
                            <td key={numero} className="px-1 py-1 text-center">
                              {sanif ? (
                                <div className={`w-6 h-6 mx-auto rounded flex items-center justify-center ${
                                  sanif.eseguita 
                                    ? "bg-green-500 text-white" 
                                    : "bg-red-100 text-red-600"
                                }`} title={sanif.eseguita ? "Pulizia eseguita" : "Non eseguita"}>
                                  {sanif.eseguita ? <Check size={14}/> : <X size={14}/>}
                                </div>
                              ) : (
                                <div className="w-6 h-6 mx-auto"></div>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Tabella Congelatori - GIORNI come righe, CONGELATORI come colonne */}
          <div className="bg-white rounded-lg border overflow-hidden">
            <div className="bg-[#f2f6f3] px-4 py-2 flex items-center gap-2">
              <Snowflake size={18} className="text-[#4f6d5f]" />
              <h4 className="font-semibold text-[#34483f]">Congelatori (-22°C / -18°C)</h4>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium text-gray-700 sticky left-0 bg-gray-50 min-w-[60px]">Giorno</th>
                    {Array.from({length: 12}, (_, i) => (
                      <th key={i+1} className="px-1 py-2 text-center font-medium text-gray-600 min-w-[55px]">
                        <span className="text-xs">Cong</span><br/>{i+1}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {Array.from({length: numGiorni}, (_, giornoIdx) => {
                    const giorno = giornoIdx + 1;
                    
                    return (
                      <tr key={giorno} className="hover:bg-gray-50">
                        <td className="px-3 py-1 font-medium text-gray-800 sticky left-0 bg-white">
                          {giorno}
                        </td>
                        {Array.from({length: 12}, (_, congIdx) => {
                          const numero = congIdx + 1;
                          const sanif = getSanificazioneGiorno("congelatore", numero, giorno);
                          
                          return (
                            <td key={numero} className="px-1 py-1 text-center">
                              {sanif ? (
                                <div className={`w-6 h-6 mx-auto rounded flex items-center justify-center ${
                                  sanif.eseguita 
                                    ? "bg-green-500 text-white" 
                                    : "bg-red-100 text-red-600"
                                }`} title={sanif.eseguita ? "Pulizia eseguita" : "Non eseguita"}>
                                  {sanif.eseguita ? <Check size={14}/> : <X size={14}/>}
                                </div>
                              ) : (
                                <div className="w-6 h-6 mx-auto"></div>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Legenda */}
          <div className="flex items-center gap-4 text-xs text-gray-600 bg-gray-50 p-3 rounded-lg flex-wrap">
            <span className="flex items-center gap-1">
              <span className="w-4 h-4 bg-green-500 rounded flex items-center justify-center text-white"><Check size={10}/></span> Pulizia eseguita
            </span>
            <span className="flex items-center gap-1">
              <span className="w-4 h-4 bg-red-100 rounded flex items-center justify-center text-red-600"><X size={10}/></span> Non eseguita
            </span>
            <span className="flex items-center gap-1">
              <span className="w-4 h-4 bg-white border rounded"></span> Nessuna pulizia programmata
            </span>
          </div>
        </>
      )}
    </div>
  );
};

export default SanificazioneView;
