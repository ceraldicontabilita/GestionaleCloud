/**
 * ManualeView — Guida d'uso in-app, pagina per pagina e BOTTONE per bottone.
 * Riscritta nello stile discorsivo di Enzo (04/07/2026): per ogni sezione,
 * cosa fa la pagina e come si usa, senza dettagli tecnici destinati agli sviluppatori.
 * FONTE UNICA: frontend/src/data/guidaContenuti.json — la stessa che genera il
 * PDF stampabile (frontend/public/guida/). Per aggiornare la guida si aggiorna
 * il JSON (mai inventare: si legge dal codice reale) e si rigenera il PDF.
 */
import { useState } from "react";
import { ChevronDown, ChevronRight, BookOpen, HelpCircle } from "lucide-react";
import GUIDA from "../../data/guidaContenuti.json";

const SALVIA = "#5b7a6b";

export default function ManualeView() {
  const [aperta, setAperta] = useState("come-si-entra");

  // Raggruppa per "gruppo" mantenendo l'ordine del file
  const gruppi = [];
  GUIDA.sezioni.forEach((s) => {
    const g = gruppi.find((x) => x.nome === s.gruppo);
    if (g) g.sezioni.push(s);
    else gruppi.push({ nome: s.gruppo, sezioni: [s] });
  });

  return (
    <div className="max-w-3xl mx-auto p-4">
      <div className="flex items-center gap-2 mb-1">
        <BookOpen size={22} style={{ color: SALVIA }} />
        <h2 className="text-xl font-bold text-gray-900">Guida dell'applicazione</h2>
      </div>
      <p className="text-sm text-gray-500 mb-3 flex items-center gap-1.5">
        <HelpCircle size={14} /> Pagina per pagina, bottone per bottone — aggiornata al {GUIDA.aggiornata_il}.
      </p>

      <a href={`${process.env.PUBLIC_URL || ""}/guida/Guida_Operativa_Lotti.pdf`} target="_blank" rel="noreferrer"
        className="mb-4 flex items-center gap-2 rounded-lg px-4 py-3 text-sm font-black text-white"
        style={{ background: SALVIA, textDecoration: "none", width: "fit-content" }}>
        <BookOpen size={16} /> Scarica la Guida operativa completa (PDF stampabile)
      </a>

      {gruppi.map((gruppo) => (
        <div key={gruppo.nome} className="mb-5">
          <h3 className="text-xs font-bold uppercase tracking-wide mb-2" style={{ color: SALVIA }}>
            {gruppo.nome}
          </h3>
          <div className="space-y-2">
            {gruppo.sezioni.map((sez) => {
              const open = aperta === sez.id;
              return (
                <div key={sez.id} className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                  <button
                    onClick={() => setAperta(open ? "" : sez.id)}
                    className="w-full px-4 py-3 flex items-center justify-between gap-2 text-left hover:bg-gray-50">
                    <span className="min-w-0">
                      <span className="block font-semibold text-gray-800 text-sm">{sez.titolo}</span>
                    </span>
                    {open ? <ChevronDown size={16} className="text-gray-400 shrink-0" /> : <ChevronRight size={16} className="text-gray-400 shrink-0" />}
                  </button>
                  {open && (
                    <div className="px-4 pb-4">
                      <p className="text-sm text-gray-700 leading-relaxed mb-3">{sez.scopo}</p>
                      {sez.passi?.length > 0 && (
                        <ul className="space-y-1.5 mb-3">
                          {sez.passi.map((p, i) => (
                            <li key={i} className="text-sm text-gray-600 leading-snug pl-3 border-l-2"
                              style={{ borderColor: "#cfdfd5" }}>{p}</li>
                          ))}
                        </ul>
                      )}
                      {sez.bottoni?.length > 0 && (
                        <div className="overflow-x-auto rounded-lg border border-gray-100">
                          <table className="w-full text-left" style={{ fontSize: 12.5 }}>
                            <thead>
                              <tr style={{ background: "#f2f6f3", color: "#3f5a4e" }}>
                                <th className="px-3 py-2 font-bold">Bottone / elemento</th>
                                <th className="px-3 py-2 font-bold">Cosa fa</th>
                              </tr>
                            </thead>
                            <tbody>
                              {sez.bottoni.map((b, i) => (
                                <tr key={i} className="border-t border-gray-100 align-top">
                                  <td className="px-3 py-2 font-semibold text-gray-800">{b[0]}</td>
                                  <td className="px-3 py-2 text-gray-600">{b[1]}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <p className="text-[11px] text-gray-400 mt-4">
        Per segnalare un problema indica il nome della pagina, il bottone usato e cosa è comparso sullo schermo.
      </p>
    </div>
  );
}
