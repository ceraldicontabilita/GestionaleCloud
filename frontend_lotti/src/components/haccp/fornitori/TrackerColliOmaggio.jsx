// Tracker colli omaggio del fornitore (KPI, saldo, prossimo omaggio, valore
// economico recuperato, dettaglio per prodotto e per fattura).
// Estratto 1:1 da FornitoriList.jsx (refactor 25/07/2026) — componente puro,
// riceve solo `anagrafica` e non fa chiamate.
export default function TrackerColliOmaggio({ anagrafica }) {
  if (!anagrafica || !(anagrafica.colli_pagati > 0)) return null;
  return (
    <div className="rounded-xl border-2 border-amber-200 bg-amber-50 p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">🎁</span>
        <p className="font-semibold text-amber-800 text-sm">
          Tracker Colli Omaggio {anagrafica.anno_filtro && <span className="text-amber-500">— {anagrafica.anno_filtro}</span>}
        </p>
        <span className="ml-auto text-xs text-amber-600 bg-amber-100 px-2 py-0.5 rounded-full">
          ogni {anagrafica.soglia_omaggio} pagati = 1 omaggio
        </span>
      </div>

      {/* KPI principali: 4 box */}
      <div className="grid grid-cols-4 gap-2 text-center mb-3">
        <div className="bg-white rounded-lg p-2 border border-amber-100">
          <p className="text-xl font-bold text-gray-800">{anagrafica.colli_pagati}</p>
          <p className="text-[10px] text-gray-500 font-medium uppercase">Colli Pagati</p>
        </div>
        <div className="bg-white rounded-lg p-2 border border-green-200">
          <p className="text-xl font-bold text-green-600">{anagrafica.colli_omaggio_maturati}</p>
          <p className="text-[10px] text-gray-500 font-medium uppercase">Maturati</p>
          <p className="text-[9px] text-green-500">(guadagnati)</p>
        </div>
        <div className={`rounded-lg p-2 border ${anagrafica.colli_omaggio_ricevuti > anagrafica.colli_omaggio_maturati ? 'bg-orange-50 border-orange-200' : 'bg-green-50 border-green-200'}`}>
          <p className={`text-xl font-bold ${anagrafica.colli_omaggio_ricevuti > anagrafica.colli_omaggio_maturati ? 'text-orange-600' : 'text-green-600'}`}>
            {anagrafica.colli_omaggio_ricevuti}
          </p>
          <p className="text-[10px] text-gray-500 font-medium uppercase">Ricevuti</p>
          <p className="text-[9px] text-gray-400">(effettivi)</p>
        </div>
        <div className={`rounded-lg p-2 border ${
          anagrafica.colli_credito > 0 ? 'bg-[#f2f6f3] border-[#cfdfd5]'
          : anagrafica.colli_credito < 0 ? 'bg-orange-50 border-orange-200'
          : 'bg-gray-50 border-gray-200'}`}>
          <p className={`text-xl font-bold ${
            anagrafica.colli_credito > 0 ? 'text-[#5b7a6b]'
            : anagrafica.colli_credito < 0 ? 'text-orange-600'
            : 'text-gray-500'}`}>
            {anagrafica.colli_credito > 0 ? `+${anagrafica.colli_credito}` : anagrafica.colli_credito}
          </p>
          <p className="text-[10px] text-gray-500 font-medium uppercase">Saldo</p>
          <p className="text-[9px] text-gray-400">
            {anagrafica.colli_credito > 0 ? 'da ricevere' : anagrafica.colli_credito < 0 ? 'anticipato' : 'in pari'}
          </p>
        </div>
      </div>

      {/* Stato saldo: anticipo vs credito */}
      <div className={`flex items-center gap-2 text-xs font-semibold py-2 px-3 rounded-lg mb-3 ${
        anagrafica.colli_credito > 0 ? 'bg-[#e8efe9] text-[#5b7a6b]'
        : anagrafica.colli_credito < 0 ? 'bg-orange-100 text-orange-700'
        : 'bg-green-100 text-green-700'
      }`}>
        <span>
          {anagrafica.colli_credito > 0
            ? `Hai ${anagrafica.colli_credito} omaggi da ricevere`
            : anagrafica.colli_credito < 0
              ? `Hai ricevuto ${Math.abs(anagrafica.colli_credito)} omaggio in anticipo`
              : 'Sei in pari con gli omaggi'}
        </span>
      </div>

      {/* Prossimo omaggio: quanti colli mancano */}
      <div className="bg-white rounded-lg border border-amber-200 p-3 mb-3">
        <div className="flex justify-between items-start mb-2">
          <div>
            <p className="text-xs font-bold text-amber-800">Prossimo Omaggio</p>
            {anagrafica.colli_al_prossimo_omaggio > 0 && (
              <p className="text-[10px] text-gray-500 mt-0.5">
                {anagrafica.colli_credito < 0
                  ? `Devi prima rientrare dall'anticipo (${Math.abs(anagrafica.colli_credito)}×${anagrafica.soglia_omaggio}) + ciclo corrente`
                  : `Mancano ${anagrafica.soglia_omaggio - (anagrafica.colli_pagati % anagrafica.soglia_omaggio || anagrafica.soglia_omaggio)} colli per completare il ciclo`
                }
              </p>
            )}
          </div>
          <div className="text-right">
            {anagrafica.colli_al_prossimo_omaggio === 0
              ? <span className="text-green-600 font-bold text-sm">Omaggio disponibile!</span>
              : <span className="text-amber-700 font-bold text-lg">{anagrafica.colli_al_prossimo_omaggio} colli</span>
            }
          </div>
        </div>

        {/* Barra progresso visiva */}
        {(() => {
          const soglia = anagrafica.soglia_omaggio || 10;
          const nel_ciclo = anagrafica.colli_pagati % soglia || 0;
          const pct_ciclo = Math.round((nel_ciclo / soglia) * 100);
          const anticipo = anagrafica.colli_credito < 0 ? Math.abs(anagrafica.colli_credito) : 0;
          return (
            <div>
              {anticipo > 0 && (
                <p className="text-[9px] text-orange-600 mb-1">
                  Ciclo attuale: {nel_ciclo}/{soglia} ({pct_ciclo}%) · poi serviranno {anticipo}×{soglia} colli extra per l'anticipo
                </p>
              )}
              <div className="w-full bg-amber-100 rounded-full h-2 overflow-hidden">
                <div className="bg-amber-500 h-2 rounded-full transition-all" style={{ width: `${pct_ciclo}%` }} />
              </div>
              <p className="text-[9px] text-gray-500 mt-1">
                Ciclo corrente: {nel_ciclo} / {soglia} colli
              </p>
            </div>
          );
        })()}
      </div>

      {/* Credito/Debito omaggio */}
      {anagrafica.colli_credito !== 0 && (
        <div className={`text-center text-xs font-semibold py-1.5 rounded-lg mb-3 ${
          anagrafica.colli_credito > 0
            ? 'bg-[#e8efe9] text-[#5b7a6b]'
            : 'bg-orange-100 text-orange-700'
        }`}>
          {anagrafica.colli_credito > 0
            ? `Il fornitore ti deve ancora ${anagrafica.colli_credito} omaggio`
            : `Anticipo: hai ricevuto ${Math.abs(anagrafica.colli_credito)} omaggio non ancora maturato — serve acquistare altri ${anagrafica.colli_al_prossimo_omaggio} colli`}
        </div>
      )}

      {/* ── VALORE ECONOMICO OMAGGI ────────────────────── */}
      {(anagrafica.valore_omaggi_ricevuti > 0 || anagrafica.incasso_omaggi_vendita > 0) && (
        <div className="bg-white rounded-xl border-2 border-emerald-200 p-3">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-sm">💰</span>
              <p className="text-sm font-bold text-emerald-800">Valore Recuperato dagli Omaggi</p>
            </div>
            <div className="text-right">
              <span className="text-2xl font-bold text-emerald-700">€{(anagrafica.incasso_omaggi_vendita || 0).toFixed(2)}</span>
              <p className="text-[9px] text-emerald-600">totale recuperato</p>
            </div>
          </div>

          {/* Due righe: incasso + risparmio + costo acquisto */}
          <div className="grid grid-cols-3 gap-2 text-center mb-3">
            <div className="bg-emerald-50 rounded-lg p-2 border border-emerald-100">
              <p className="text-base font-bold text-emerald-600">
                €{(anagrafica.omaggi_dettaglio || []).filter(o=>o.tipo==='prodotto_finito').reduce((s,o)=>s+(o.valore_economico||0),0).toFixed(2)}
              </p>
              <p className="text-[9px] text-emerald-700 font-semibold">Incasso Vendita</p>
              <p className="text-[8px] text-gray-400">prodotti finiti venduti</p>
            </div>
            <div className="bg-[#f2f6f3] rounded-lg p-2 border border-[#dce8e0]">
              <p className="text-base font-bold text-[#5b7a6b]">
                €{(anagrafica.omaggi_dettaglio || []).filter(o=>o.tipo==='ingrediente_ricetta').reduce((s,o)=>s+(o.valore_economico||0),0).toFixed(2)}
              </p>
              <p className="text-[9px] text-[#5b7a6b] font-semibold">Risparmio Food Cost</p>
              <p className="text-[8px] text-gray-400">ingredienti non pagati</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-2 border border-gray-100">
              <p className="text-base font-bold text-orange-500">
                €{(anagrafica.valore_omaggi_ricevuti || 0).toFixed(2)}
              </p>
              <p className="text-[9px] text-gray-600 font-semibold">Costo Acquisto</p>
              <p className="text-[8px] text-gray-400">quanto valgono all'acquisto</p>
            </div>
          </div>

          {/* Barra recupero */}
          <div className="mb-3">
            <div className="w-full bg-gray-100 rounded-full h-2.5 relative overflow-hidden">
              <div className="bg-emerald-500 h-2.5 rounded-full transition-all" style={{ width: `${Math.min(anagrafica.perc_recupero_su_fatture || 0, 100)}%` }} />
            </div>
            <p className="text-[10px] text-emerald-700 mt-1 font-medium text-center">
              {anagrafica.perc_recupero_su_fatture}% del totale fatture recuperato tramite omaggi
              <span className="text-gray-400 ml-1">(su €{(anagrafica.totale_acquistato || 0).toFixed(2)} acquistati)</span>
            </p>
          </div>

          {/* Dettaglio per prodotto */}
          {anagrafica.omaggi_dettaglio?.length > 0 && (
            <details>
              <summary className="text-xs text-emerald-700 cursor-pointer font-medium hover:text-emerald-900 mb-2">
                Dettaglio per prodotto ({anagrafica.colli_omaggio_ricevuti} KAR · {anagrafica.pezzi_omaggio_totali} pezzi totali)
              </summary>
              <div className="mt-2 space-y-2 max-h-64 overflow-y-auto">
                {/* Legenda */}
                <div className="flex gap-2 flex-wrap">
                  <span className="text-[8px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-full font-bold">Prodotto = incasso vendita</span>
                  <span className="text-[8px] bg-[#e8efe9] text-[#5b7a6b] px-1.5 py-0.5 rounded-full font-bold">Ingrediente = risparmio food cost</span>
                  <span className="text-[8px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full font-bold">? = stima costo acq.</span>
                </div>
                {anagrafica.omaggi_dettaglio.map((od, i) => {
                  const tipo = od.tipo || 'sconosciuto';
                  const badgeClass = tipo === 'prodotto_finito' ? 'bg-emerald-100 text-emerald-700' : tipo === 'ingrediente_ricetta' ? 'bg-[#e8efe9] text-[#5b7a6b]' : 'bg-gray-100 text-gray-500';
                  const badgeLabel = tipo === 'prodotto_finito' ? 'Prodotto' : tipo === 'ingrediente_ricetta' ? 'Ingrediente' : '?';
                  const valore = od.valore_economico || od.valore_totale || 0;
                  const valoreCls = tipo === 'ingrediente_ricetta' ? 'text-[#5b7a6b]' : tipo === 'prodotto_finito' ? 'text-emerald-600' : 'text-orange-500';
                  return (
                    <div key={i} className="bg-gray-50 rounded-lg p-2 border border-gray-100">
                      {/* Riga 1: badge + nome + valore */}
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1 mb-0.5">
                            <span className={`text-[7px] font-bold px-1.5 py-0.5 rounded-full shrink-0 ${badgeClass}`}>{badgeLabel}</span>
                            <span className="text-[10px] text-gray-700 font-semibold truncate" title={od.prodotto}>
                              {od.prodotto.replace(/^AQV\s+/i,'').replace(/\s+\d+G\s+\d+\.?\d*KG.*/i,'').substring(0,35)}
                            </span>
                          </div>
                          {/* Dettaglio calcolo */}
                          {tipo === 'prodotto_finito' && od.prezzo_vendita_pezzo > 0 && (
                            <p className="text-[9px] text-emerald-600 ml-0.5">
                              {od.stima ? '~' : ''}€{od.prezzo_vendita_pezzo.toFixed(2)}/pz × {od.pezzi_totali} pz = <strong>€{valore.toFixed(2)}</strong>
                              {od.stima && <span className="text-gray-400 ml-1">(stima per categoria)</span>}
                            </p>
                          )}
                          {tipo === 'ingrediente_ricetta' && (
                            <div className="ml-0.5">
                              <p className="text-[9px] text-[#5b7a6b]">
                                {od.qty_cartoni} KAR × €{od.prezzo_unitario.toFixed(2)}/KAR = <strong>€{valore.toFixed(2)}</strong> risparmio
                              </p>
                              {od.ricette_collegate?.length > 0 && (
                                <p className="text-[8px] text-[#5b7a6b]">
                                  Usato in: {od.ricette_collegate.map(r=>r.nome_ricetta).join(', ')}
                                </p>
                              )}
                            </div>
                          )}
                          {tipo === 'sconosciuto' && (
                            <p className="text-[9px] text-gray-500 ml-0.5">
                              {od.qty_cartoni} KAR × €{od.prezzo_unitario > 0 ? od.prezzo_unitario.toFixed(2) : '?'}/KAR
                            </p>
                          )}
                        </div>
                        <div className="text-right shrink-0">
                          <span className={`text-sm font-bold ${valore > 0 ? valoreCls : 'text-gray-300'}`}>
                            {valore > 0 ? `€${valore.toFixed(2)}` : 'N/D'}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </details>
          )}
        </div>
      )}

      {/* Dettaglio colli per fattura */}
      {anagrafica.colli_per_fattura?.filter(f => f.pagati > 0 || f.omaggio > 0).length > 0 && (
        <details className="mt-3">
          <summary className="text-xs text-amber-700 cursor-pointer font-medium hover:text-amber-900">
            Dettaglio colli per fattura
          </summary>
          <div className="mt-2 space-y-1 max-h-36 overflow-y-auto">
            {anagrafica.colli_per_fattura.filter(f => f.pagati > 0 || f.omaggio > 0).map((f, i) => (
              <div key={i} className="flex items-center justify-between text-xs py-1 border-b border-amber-100 last:border-0">
                <span className="text-gray-500 w-24 flex-shrink-0">{f.data}</span>
                <span className="font-mono text-gray-600 w-20 flex-shrink-0 truncate">{f.numero}</span>
                <span className="text-gray-700">{f.pagati} pagati</span>
                {f.omaggio > 0 && (
                  <span className="text-green-600 font-semibold">+{f.omaggio} omaggio</span>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
