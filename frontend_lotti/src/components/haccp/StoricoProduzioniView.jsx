import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { format, subDays } from "date-fns";
import { it } from "date-fns/locale";
import { Trash2, User } from "lucide-react";

import { API } from "../../utils/constants";

function StatCard({ label, value, sub, color = "blue" }) {
  const colors = {
    blue:   { bg: "bg-[#f2f6f3]",   border: "border-[#cfdfd5]",   text: "text-[#5b7a6b]",   val: "text-[#3f5a4e]" },
    green:  { bg: "bg-green-50",  border: "border-green-200",  text: "text-green-700",  val: "text-green-800" },
    amber:  { bg: "bg-amber-50",  border: "border-amber-200",  text: "text-amber-700",  val: "text-amber-800" },
    purple: { bg: "bg-[#faf5ec]", border: "border-[#e6d3ab]", text: "text-[#6f583a]", val: "text-[#5c4830]" },
  };
  const c = colors[color];
  return (
    <div className={`${c.bg} border ${c.border} rounded-xl p-4`}>
      <p className={`text-xs font-semibold uppercase tracking-wide ${c.text} mb-1`}>{label}</p>
      <p className={`text-2xl font-bold ${c.val}`}>{value}</p>
      {sub && <p className={`text-xs ${c.text} mt-0.5`}>{sub}</p>}
    </div>
  );
}

// Grafico a barre inline puro CSS/SVG
function TrendChart({ data, tipo = "pezzi" }) {
  if (!data || data.length === 0) return (
    <div className="flex items-center justify-center h-32 text-gray-300 text-sm">Nessun dato nel periodo</div>
  );

  const maxVal = Math.max(...data.map(d => d[tipo]), 1);

  return (
    <div className="w-full overflow-x-auto">
      <div className="flex items-end gap-1 h-28 min-w-0 px-1" style={{ minWidth: `${data.length * 22}px` }}>
        {data.map((d, i) => {
          const h = Math.max(3, Math.round((d[tipo] / maxVal) * 96)); // px: il % collassava su parent ad altezza auto
          return (
            <div key={i} className="flex flex-col items-center flex-1 group relative" style={{ minWidth: 18 }}>
              {/* Tooltip */}
              <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 z-10 hidden group-hover:block bg-gray-900 text-white text-xs rounded px-2 py-1 whitespace-nowrap shadow-lg">
                <div className="font-semibold">{d.data}</div>
                <div>{tipo === "pezzi" ? `${d.pezzi} pz` : `€${d.costo}`}</div>
                <div className="text-gray-400">{d.produzioni} prod.</div>
              </div>
              <div
                className="w-full rounded-t transition-all"
                style={{
                  height: `${h}px`,
                  background: tipo === "pezzi" ? "#3d8168" : "#c4894a",
                  opacity: 0.8
                }}
              />
              {/* Etichetta data solo ogni N */}
              {(i % Math.ceil(data.length / 7) === 0) && (
                <span className="text-gray-400 mt-0.5 truncate w-full text-center" style={{ fontSize: 8 }}>
                  {d.data ? d.data.slice(5) : ""}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export const StoricoProduzioniView = () => {
  const [produzioni, setProduzioni] = useState([]);
  const [trend, setTrend] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingTrend, setLoadingTrend] = useState(false);
  const [search, setSearch] = useState("");
  const [filtroData, setFiltroData] = useState({
    da: format(subDays(new Date(), 30), "yyyy-MM-dd"),
    a:  format(new Date(), "yyyy-MM-dd"),
  });
  const [paginaCorrente, setPaginaCorrente] = useState(1);
  const [vistaGrafico, setVistaGrafico] = useState("pezzi");
  const [periodoTrend, setPeriodoTrend] = useState(30);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const perPagina = 20;

  const caricaTrend = useCallback(async (giorni) => {
    setLoadingTrend(true);
    try {
      const res = await axios.get(`${API}/produzioni/trend`, { params: { giorni } });
      setTrend(res.data || []);
    } catch { /* silenzioso */ }
    finally { setLoadingTrend(false); }
  }, []);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 500 };
      if (search) params.search = search;
      const res = await axios.get(`${API}/produzioni/`, { params });
      let lista = res.data || [];

      // Normalizza la data: può essere "dd/mm/yyyy" o ISO string
      const parseDataProd = (data) => {
        if (!data) return null;
        if (data.includes("/")) {
          const [d, m, y] = data.split("/");
          return new Date(`${y}-${m}-${d}T00:00:00`);
        }
        return new Date(data);
      };

      if (filtroData.da) {
        const daDate = new Date(filtroData.da + "T00:00:00");
        lista = lista.filter(p => { const d = parseDataProd(p.data); return !d || d >= daDate; });
      }
      if (filtroData.a) {
        const aDate = new Date(filtroData.a + "T23:59:59");
        lista = lista.filter(p => { const d = parseDataProd(p.data); return !d || d <= aDate; });
      }
      // Ordina per data decrescente
      lista.sort((a, b) => {
        const da = parseDataProd(a.data) || new Date(0);
        const db = parseDataProd(b.data) || new Date(0);
        return db - da;
      });
      setProduzioni(lista);
      setPaginaCorrente(1);
    } catch { /* silenzioso */ }
    finally { setLoading(false); }
  }, [search, filtroData]);

  useEffect(() => { carica(); }, [carica]);
  useEffect(() => { caricaTrend(periodoTrend); }, [caricaTrend, periodoTrend]);

  const eliminaProduzione = async (id) => {
    try {
      await axios.delete(`${API}/produzioni/${id}`);
      setProduzioni(prev => prev.filter(p => p.id !== id));
      setConfirmDeleteId(null);
    } catch { }
  };

  // Stats aggregate
  const totalePezzi = produzioni.reduce((s, p) => s + (p.pezzi || 0), 0);
  const totaleCosto = produzioni.reduce((s, p) => s + (p.costo_totale || 0), 0);
  const ricetteProdotte = new Set(produzioni.map(p => p.ricetta_nome)).size;

  const topRicette = Object.entries(
    produzioni.reduce((acc, p) => {
      acc[p.ricetta_nome] = (acc[p.ricetta_nome] || 0) + (p.pezzi || 0);
      return acc;
    }, {})
  ).sort((a, b) => b[1] - a[1]).slice(0, 5);

  // Paginazione
  const totalePagine = Math.ceil(produzioni.length / perPagina);
  const paginati = produzioni.slice((paginaCorrente - 1) * perPagina, paginaCorrente * perPagina);

  const esportaCsv = () => {
    const righe = [
      ["Data", "Ricetta", "Pezzi", "Costo (€)", "Numero Lotto", "Frigo", "Lotti Fornitori Scalati"].join(";"),
      ...produzioni.map(p => [
        p.data ? p.data.slice(0, 10) : "",
        p.ricetta_nome || "",
        p.pezzi || 0,
        (p.costo_totale || 0).toFixed(2),
        p.numero_lotto || "",
        p.frigo_numero || "",
        (p.lotti_fornitori_scalati || 0)
      ].join(";"))
    ].join("\n");
    const blob = new Blob([righe], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `storico_produzioni_${format(new Date(), "yyyyMMdd")}.csv`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 500);
  };

  // Statistiche trend
  const trendPezziTotale = trend.reduce((s, d) => s + d.pezzi, 0);
  const trendCostoTotale = trend.reduce((s, d) => s + d.costo, 0);
  const mediaGiornaliera = trend.length > 0 ? Math.round(trendPezziTotale / trend.length) : 0;

  return (
    <div className="space-y-6">
      {/* Azioni (titolo nell'intestazione uniforme di pagina) */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <p className="text-gray-500 text-sm">{produzioni.length} registrazioni nel periodo selezionato</p>
        <button
          onClick={esportaCsv}
          data-testid="esporta-csv-btn"
          className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-xl text-sm font-semibold transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          Esporta CSV
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard label="Produzioni" value={produzioni.length} sub="nel periodo" color="blue" />
        <StatCard label="Totale Pezzi" value={totalePezzi.toLocaleString("it-IT")} sub="unità prodotte" color="green" />
        <StatCard label="Costo Totale" value={`€${totaleCosto.toFixed(2)}`} sub="ingredienti usati" color="amber" />
        <StatCard label="Ricette Diverse" value={ricetteProdotte} sub="tipologie" color="purple" />
      </div>

      {/* SEZIONE GRAFICI TREND */}
      <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <div>
            <h3 className="font-bold text-gray-800 text-sm uppercase tracking-wide">Andamento Produzioni</h3>
            <p className="text-xs text-gray-400 mt-0.5">
              {trendPezziTotale.toLocaleString("it-IT")} pz totali · €{trendCostoTotale.toFixed(2)} costo · {mediaGiornaliera} pz/giorno medio
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Toggle tipo */}
            <div className="flex bg-gray-100 rounded-lg p-0.5 text-xs">
              <button
                onClick={() => setVistaGrafico("pezzi")}
                className={`px-3 py-1.5 rounded-md transition-colors font-medium ${vistaGrafico === "pezzi" ? "bg-[#5b7a6b] text-white shadow-sm" : "text-gray-600 hover:text-gray-800"}`}
              >
                Pezzi
              </button>
              <button
                onClick={() => setVistaGrafico("costo")}
                className={`px-3 py-1.5 rounded-md transition-colors font-medium ${vistaGrafico === "costo" ? "bg-emerald-500 text-white shadow-sm" : "text-gray-600 hover:text-gray-800"}`}
              >
                Costo €
              </button>
            </div>
            {/* Periodo */}
            <div className="flex bg-gray-100 rounded-lg p-0.5 text-xs">
              {[7, 30, 90].map(g => (
                <button
                  key={g}
                  onClick={() => setPeriodoTrend(g)}
                  className={`px-3 py-1.5 rounded-md transition-colors font-medium ${periodoTrend === g ? "bg-white shadow-sm text-gray-800" : "text-gray-500 hover:text-gray-700"}`}
                >
                  {g}gg
                </button>
              ))}
            </div>
          </div>
        </div>
        {loadingTrend ? (
          <div className="h-28 flex items-center justify-center text-gray-300 text-sm">Caricamento...</div>
        ) : (
          <TrendChart data={trend} tipo={vistaGrafico} />
        )}
      </div>

      {/* Top 5 ricette */}
      {topRicette.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
          <h3 className="font-bold text-gray-800 mb-4 text-sm uppercase tracking-wide">Top 5 Prodotti (periodo selezionato)</h3>
          <div className="space-y-2">
            {topRicette.map(([nome, pezzi], i) => {
              const max = topRicette[0][1];
              const pct = Math.round((pezzi / max) * 100);
              const colors = ["bg-[#5b7a6b]", "bg-amber-500", "bg-orange-500", "bg-rose-500", "bg-[#8a6f47]"];
              return (
                <div key={nome} className="flex items-center gap-3">
                  <span className="text-xs font-bold text-gray-400 w-4">{i + 1}</span>
                  <span className="text-sm font-medium text-gray-700 capitalize w-44 truncate">{nome}</span>
                  <div className="flex-1 bg-gray-100 rounded-full h-2.5 overflow-hidden">
                    <div className={`h-full ${colors[i]} rounded-full transition-all`} style={{ width: `${pct}%` }} />
                  </div>
                  <span className="text-xs font-bold text-gray-600 w-16 text-right">{pezzi.toLocaleString("it-IT")} pz</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Filtri */}
      <div className="bg-white rounded-2xl border border-gray-100 p-4 shadow-sm space-y-3">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex-1 relative min-w-[200px]">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
            <input
              type="text"
              placeholder="Cerca ricetta..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              data-testid="search-storico-input"
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-[#5b7a6b]"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-500 whitespace-nowrap">Dal</label>
            <input type="date" value={filtroData.da}
              onChange={(e) => setFiltroData(f => ({ ...f, da: e.target.value }))}
              className="px-2 py-2 border border-gray-200 rounded-lg text-xs" />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-500 whitespace-nowrap">Al</label>
            <input type="date" value={filtroData.a}
              onChange={(e) => setFiltroData(f => ({ ...f, a: e.target.value }))}
              className="px-2 py-2 border border-gray-200 rounded-lg text-xs" />
          </div>
          <div className="flex gap-2">
            {[7, 30, 90].map(giorni => (
              <button key={giorni}
                onClick={() => setFiltroData({ da: format(subDays(new Date(), giorni), "yyyy-MM-dd"), a: format(new Date(), "yyyy-MM-dd") })}
                className="px-3 py-2 border border-gray-200 rounded-lg text-xs hover:bg-[#f2f6f3] hover:border-[#b8d0c2] transition-colors"
              >
                {giorni}gg
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Tabella */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        {loading ? (
          <div className="text-center py-12 text-gray-400">Caricamento...</div>
        ) : paginati.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <p className="text-lg font-medium">Nessuna produzione trovata</p>
            <p className="text-sm mt-1">Prova a cambiare il filtro date</p>
          </div>
        ) : (
          <>
            {/* Modal conferma elimina */}
            {confirmDeleteId && (
              <div className="fixed inset-0 z-50 flex items-center justify-center">
                <div className="absolute inset-0 bg-black/50" onClick={() => setConfirmDeleteId(null)} />
                <div className="relative bg-white rounded-2xl shadow-2xl p-6 max-w-xs w-full mx-4 text-center">
                  <Trash2 size={36} className="mx-auto mb-3 text-red-500" />
                  <h3 className="text-lg font-bold text-gray-800 mb-1">Eliminare questa produzione?</h3>
                  <p className="text-xs text-gray-400 mb-5">Questa azione non può essere annullata. Il lotto collegato rimarrà.</p>
                  <div className="flex gap-3">
                    <button onClick={() => setConfirmDeleteId(null)}
                      className="flex-1 px-4 py-2 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50">Annulla</button>
                    <button onClick={() => eliminaProduzione(confirmDeleteId)}
                      className="flex-1 px-4 py-2 bg-red-600 text-white rounded-xl text-sm font-semibold hover:bg-red-700">Elimina</button>
                  </div>
                </div>
              </div>
            )}

            <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Data</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Ricetta</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Pezzi</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Costo</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">N° Lotto</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Frigo</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Lotti Scalati</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Operatore</th>
                  <th className="px-2 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {paginati.map((p, i) => (
                  <tr key={p.id} className={`border-b border-gray-50 hover:bg-[#f2f6f3]/30 transition-colors ${i % 2 === 0 ? "" : "bg-gray-50/30"}`}>
                    <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                      {(() => {
                        const raw = p.data || "";
                        if (!raw) return "—";
                        if (raw.includes("/")) return raw;
                        try { return format(new Date(raw), "dd/MM/yyyy HH:mm", { locale: it }); }
                        catch { return raw.slice(0,10); }
                      })()}
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-800 capitalize">{p.ricetta_nome}</td>
                    <td className="px-4 py-3 text-center">
                      <span className="font-bold text-[#5b7a6b]">{(p.pezzi || 0).toLocaleString("it-IT")}</span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {p.costo_totale ? (
                        <span className="text-green-700 font-semibold">€{p.costo_totale.toFixed(2)}</span>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-3">
                      {p.numero_lotto ? (
                        <span className="font-mono text-xs bg-[#f2f6f3] text-[#5b7a6b] px-2 py-1 rounded">{p.numero_lotto}</span>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {p.frigo_numero ? (
                        <span className="text-xs bg-[#e8efe9] text-[#5b7a6b] px-2 py-1 rounded font-medium">{p.frigo_numero}</span>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {(p.lotti_fornitori_scalati || 0) > 0 ? (
                        <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded font-bold">
                          {p.lotti_fornitori_scalati}
                        </span>
                      ) : <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {p.operatore_nome ? (
                        <span className="inline-flex items-center gap-1 text-xs bg-[#f2f6f3] text-[#3f5a4e] px-2 py-1 rounded font-medium">
                          <User size={11} /> {p.operatore_nome}
                        </span>
                      ) : <span className="text-gray-300 text-xs">—</span>}
                    </td>
                    <td className="px-2 py-3">
                      <button onClick={() => setConfirmDeleteId(p.id)}
                        className="p-1.5 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                        title="Elimina produzione" data-testid={`btn-elimina-prod-${p.id}`}>
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>

            {/* Paginazione */}
            {totalePagine > 1 && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
                <p className="text-xs text-gray-500">
                  {(paginaCorrente - 1) * perPagina + 1}–{Math.min(paginaCorrente * perPagina, produzioni.length)} di {produzioni.length}
                </p>
                <div className="flex gap-2">
                  <button onClick={() => setPaginaCorrente(p => Math.max(1, p - 1))} disabled={paginaCorrente === 1}
                    className="px-3 py-1.5 border border-gray-200 rounded-lg text-xs disabled:opacity-40 hover:bg-gray-50">
                    ← Prec.
                  </button>
                  <span className="px-3 py-1.5 text-xs text-gray-600">{paginaCorrente}/{totalePagine}</span>
                  <button onClick={() => setPaginaCorrente(p => Math.min(totalePagine, p + 1))} disabled={paginaCorrente === totalePagine}
                    className="px-3 py-1.5 border border-gray-200 rounded-lg text-xs disabled:opacity-40 hover:bg-gray-50">
                    Succ. →
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default StoricoProduzioniView;
