import { Building2, X } from "lucide-react";
import FattureList from "./FattureList";
import TrackerColliOmaggio from "./TrackerColliOmaggio";

// Modale "Scheda Anagrafica Fornitore" — estratto 1:1 da FornitoriList.jsx
// (refactor 25/07/2026). Lo stato resta nel genitore: qui solo presentazione
// e i callback ricevuti via props.

// ── Contatti & condizioni commerciali (form controllato dal genitore) ──────
function ContattiCard({ selectedFornitore, contattoEdit, setContattoEdit, salvandoContatto, onSalvaScheda }) {
  return (
    <div className="rounded-xl border border-[#dce8e0] bg-[#f2f6f3]/50 p-4">
      <p className="text-xs font-bold text-[#3f5a4e] uppercase tracking-wide mb-3">Contatti & Ordini</p>
      <div className="space-y-3">
        <div>
          <label className="text-xs text-gray-500 font-medium block mb-1">Email commerciale</label>
          <input
            type="email"
            placeholder="ordini@fornitore.it"
            value={contattoEdit.email}
            onChange={e => setContattoEdit(c => ({ ...c, email: e.target.value }))}
            className="w-full px-3 py-2 text-sm border rounded-lg outline-none focus:ring-2 focus:ring-[#5b7a6b] border-gray-200"
          />
        </div>
        <div>
          <label className="text-xs text-gray-500 font-medium block mb-1">Cellulare / WhatsApp</label>
          <div className="flex gap-2">
            <input
              type="tel"
              placeholder="+39 333 0000000"
              value={contattoEdit.cellulare}
              onChange={e => setContattoEdit(c => ({ ...c, cellulare: e.target.value }))}
              className="flex-1 px-3 py-2 text-sm border rounded-lg outline-none focus:ring-2 focus:ring-green-300 border-gray-200"
            />
            {contattoEdit.cellulare && (
              <a
                href={`https://wa.me/${contattoEdit.cellulare.replace(/[^\d]/g, "")}?text=${encodeURIComponent(`Ordine fornitore ${selectedFornitore}`)}`}
                target="_blank" rel="noreferrer"
                className="px-3 py-2 bg-green-500 text-white rounded-lg text-xs font-bold hover:bg-green-600 flex items-center gap-1 whitespace-nowrap"
              >
                WhatsApp
              </a>
            )}
          </div>
        </div>
        <label className="flex items-start gap-2 cursor-pointer bg-white border border-[#cfdfd5] rounded-lg px-3 py-2.5">
          <input
            type="checkbox"
            checked={!!contattoEdit.email_verificata}
            onChange={e => setContattoEdit(c => ({ ...c, email_verificata: e.target.checked }))}
            className="mt-0.5 accent-[#5b7a6b]"
          />
          <span>
            <span className="block text-sm font-medium text-gray-800">Email verificata</span>
            <span className="block text-xs text-gray-500">Se attiva, questa email è la fonte di verità e non verrà più sovrascritta dal recupero automatico dalle fatture.</span>
          </span>
        </label>
        {/* ── Scheda estesa: più informazioni = ordini più precisi e
             schede tecniche più facili da recuperare per le ricette ── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
          {[
            { k: "pec",                  l: "PEC",                 ph: "fornitore@pec.it" },
            { k: "sito_web",             l: "Sito web (per schede tecniche prodotti)", ph: "https://www.fornitore.it" },
            { k: "referente",            l: "Referente / agente",  ph: "Nome e cognome" },
            { k: "telefono_fisso",       l: "Telefono fisso",      ph: "081 0000000" },
            { k: "giorni_consegna",      l: "Giorni di consegna",  ph: "es. lunedì e giovedì" },
            { k: "giorni_chiusura",      l: "Giorni/periodi di chiusura", ph: "es. domenica, 10-20 agosto" },
            { k: "ordine_minimo",        l: "Ordine minimo",       ph: "es. 150 € / 10 colli" },
            { k: "condizioni_pagamento", l: "Pagamento",           ph: "es. RiBa 30gg f.m." },
            { k: "metodo_pagamento",     l: "Metodo di pagamento", ph: "es. bonifico, RiBa, contanti" },
            { k: "certificazioni",       l: "Certificazioni",      ph: "es. BIO, IGP, MSC" },
          ].map(f => (
            <div key={f.k}>
              <label className="text-xs text-gray-500 font-medium block mb-1">{f.l}</label>
              <input
                type="text"
                placeholder={f.ph}
                value={contattoEdit[f.k] || ""}
                onChange={e => setContattoEdit(c => ({ ...c, [f.k]: e.target.value }))}
                className="w-full px-3 py-2 text-sm border rounded-lg outline-none focus:ring-2 focus:ring-[#5b7a6b] border-gray-200"
              />
            </div>
          ))}
        </div>
        <div className="rounded-lg border border-[#cfdfd5] bg-white p-3 space-y-3">
          <label className="flex items-start gap-2 cursor-pointer">
            <input type="checkbox" checked={contattoEdit.procedura_ordini_attiva !== false}
              onChange={e => setContattoEdit(c => ({ ...c, procedura_ordini_attiva: e.target.checked }))}
              className="mt-0.5 accent-[#5b7a6b]" />
            <span>
              <span className="block text-sm font-semibold text-gray-800">Procedura ordini attiva</span>
              <span className="block text-xs text-gray-500">Il motore prepara bozze per questo fornitore; l'invio resta sempre manuale.</span>
            </span>
          </label>
          <div>
            <label className="text-xs text-gray-500 font-medium block mb-1">Giorni effettivi di consegna</label>
            <div className="flex flex-wrap gap-1.5">
              {["Lun","Mar","Mer","Gio","Ven","Sab","Dom"].map((label, idx) => {
                const selected = (contattoEdit.giorni_consegna_settimana || []).includes(idx);
                return <button type="button" key={label}
                  onClick={() => setContattoEdit(c => ({...c, giorni_consegna_settimana: selected
                    ? (c.giorni_consegna_settimana || []).filter(x => x !== idx)
                    : [...(c.giorni_consegna_settimana || []), idx].sort()}))}
                  className={`px-2.5 py-1.5 rounded-md text-xs font-bold border ${selected ? "bg-[#5b7a6b] text-white border-[#5b7a6b]" : "bg-white text-gray-600 border-gray-200"}`}>
                  {label}
                </button>;
              })}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500 font-medium block mb-1">Preavviso ordine (giorni)</label>
              <input type="number" min="0" max="30" value={contattoEdit.lead_time_giorni ?? 1}
                onChange={e => setContattoEdit(c => ({...c, lead_time_giorni: Number(e.target.value)}))}
                className="w-full px-3 py-2 text-sm border rounded-lg border-gray-200" />
            </div>
            <div>
              <label className="text-xs text-gray-500 font-medium block mb-1">Ordina entro</label>
              <input type="time" value={contattoEdit.ora_limite_ordine || ""}
                onChange={e => setContattoEdit(c => ({...c, ora_limite_ordine: e.target.value}))}
                className="w-full px-3 py-2 text-sm border rounded-lg border-gray-200" />
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <label className="text-xs text-gray-500 font-medium">Chiusure programmate del fornitore</label>
              <button type="button" onClick={() => setContattoEdit(c => ({
                  ...c, chiusure_programmate: [...(c.chiusure_programmate || []), {dal: "", al: "", motivo: ""}],
                }))}
                className="text-xs font-bold text-[#5b7a6b] hover:underline">+ periodo</button>
            </div>
            <div className="space-y-2">
              {(contattoEdit.chiusure_programmate || []).map((periodo, idx) => (
                <div key={idx} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-center">
                  <input type="date" value={periodo.dal || ""}
                    onChange={e => setContattoEdit(c => ({...c, chiusure_programmate: (c.chiusure_programmate || []).map((p,i) => i === idx ? {...p, dal:e.target.value} : p)}))}
                    className="px-2 py-1.5 text-xs border rounded-lg border-gray-200" />
                  <input type="date" value={periodo.al || ""}
                    onChange={e => setContattoEdit(c => ({...c, chiusure_programmate: (c.chiusure_programmate || []).map((p,i) => i === idx ? {...p, al:e.target.value} : p)}))}
                    className="px-2 py-1.5 text-xs border rounded-lg border-gray-200" />
                  <button type="button" aria-label="Rimuovi periodo"
                    onClick={() => setContattoEdit(c => ({...c, chiusure_programmate: (c.chiusure_programmate || []).filter((_,i) => i !== idx)}))}
                    className="px-2 py-1.5 text-red-500 font-bold">×</button>
                </div>
              ))}
            </div>
          </div>
        </div>
        {contattoEdit.sito_web && (
          <a href={contattoEdit.sito_web.startsWith("http") ? contattoEdit.sito_web : `https://${contattoEdit.sito_web}`}
            target="_blank" rel="noreferrer"
            className="inline-block text-xs font-semibold text-[#5b7a6b] underline">
            Apri il sito del fornitore →
          </a>
        )}
        {/* Rivendita: instrada i prodotti del fornitore nei modali del tablet */}
        <label className="flex items-start gap-2 cursor-pointer bg-white border border-amber-200 rounded-lg px-3 py-2.5">
          <input
            type="checkbox"
            checked={!!contattoEdit.rivendita_colazione}
            onChange={e => setContattoEdit(c => ({ ...c, rivendita_colazione: e.target.checked }))}
            className="mt-0.5 accent-amber-600"
          />
          <span>
            <span className="block text-sm font-medium text-gray-800">☕ Colazione</span>
            <span className="block text-xs text-gray-500">I prodotti acquistati da questo fornitore diventano selezionabili nei preset Colazione del tablet.</span>
          </span>
        </label>
        <label className="flex items-start gap-2 cursor-pointer bg-white border border-green-200 rounded-lg px-3 py-2.5">
          <input
            type="checkbox"
            checked={!!contattoEdit.rivendita_senza_glutine}
            onChange={e => setContattoEdit(c => ({ ...c, rivendita_senza_glutine: e.target.checked }))}
            className="mt-0.5 accent-green-600"
          />
          <span>
            <span className="block text-sm font-medium text-gray-800">🌾 Senza glutine</span>
            <span className="block text-xs text-gray-500">I prodotti di questo fornitore compaiono nel tab Senza Glutine del tablet (invio al banco su richiesta).</span>
          </span>
        </label>
        <button
          disabled={salvandoContatto}
          onClick={onSalvaScheda}
          className="w-full py-2 bg-[#5b7a6b] text-white rounded-lg text-sm font-semibold hover:bg-[#4d6a5c] disabled:opacity-50"
        >
          {salvandoContatto ? "Salvataggio..." : "Salva scheda fornitore"}
        </button>
      </div>
    </div>
  );
}

// ── Registro ricette PRODOTTE coi prodotti del fornitore (tracciabilità
//    inversa fornitore → ricette, richiesta Enzo 23/07/2026) ────────────────
function RegistroRicetteCard({ registroRicette }) {
  if (!registroRicette || !(registroRicette.totale_ricette > 0)) return null;
  return (
    <div className="rounded-xl border border-[#cfdfd5] bg-[#f2f6f3] p-4">
      <p className="text-xs font-bold text-[#3f5a4e] uppercase tracking-wide mb-1">
        📒 Registro produzioni coi suoi prodotti
      </p>
      <p className="text-xs text-gray-500 mb-3">
        {registroRicette.totale_produzioni} produzioni registrate in {registroRicette.totale_ricette} ricette
        — dal lotto di produzione si risale a questo fornitore e viceversa.
      </p>
      <div className="max-h-56 overflow-y-auto space-y-1.5">
        {registroRicette.ricette.map((r, i) => (
          <div key={i} className="bg-white border border-[#e6e0d4] rounded-lg px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-bold text-gray-800 capitalize truncate">{r.ricetta}</span>
              <span className="text-[11px] font-bold text-[#3f5a4e] whitespace-nowrap">{r.volte}× prodotte</span>
            </div>
            <div className="text-[11px] text-gray-500">
              con: {r.ingredienti.slice(0, 4).join(", ")}{r.ingredienti.length > 4 ? "…" : ""}
            </div>
            {r.ultimo_lotto && (
              <div className="text-[10px] text-gray-400 font-mono">
                ultimo lotto {r.ultimo_lotto} · {r.ultima_data}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Qualità dei dati per le ricette (catena prodotto → dizionario → ricetta) ─
function QualitaRicetteCard({ qualitaRicette }) {
  if (!qualitaRicette || !(qualitaRicette.prodotti_acquistati > 0)) return null;
  return (
    <div className="rounded-xl border border-[#d9cfbb] bg-[#faf7f0] p-4">
      <p className="text-xs font-bold text-[#6f583a] uppercase tracking-wide mb-1">
        🍰 Qualità dati per le ricette
      </p>
      <p className="text-xs text-gray-500 mb-3">
        Quanto i prodotti comprati da questo fornitore sono collegati alle tue
        ricette: più la catena è completa, più food cost, allergeni e
        tracciabilità FIFO sono affidabili.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mb-3">
        {[
          { l: "Prodotti comprati", v: qualitaRicette.prodotti_acquistati, c: "text-gray-700" },
          { l: "Con codice articolo", v: qualitaRicette.con_codice_articolo, c: "text-[#5b7a6b]" },
          { l: "Nel dizionario", v: qualitaRicette.collegati_dizionario, c: "text-[#5b7a6b]" },
          { l: "Con nome canonico", v: qualitaRicette.con_nome_canonico, c: "text-[#8a6f47]" },
          { l: "Usati in ricette", v: qualitaRicette.usati_in_ricette, c: "text-green-700" },
        ].map((s, i) => (
          <div key={i} className="bg-white rounded-lg border border-[#e6e0d4] p-2 text-center">
            <p className={`text-lg font-bold ${s.c}`}>{s.v}</p>
            <p className="text-[10px] text-gray-400 leading-tight">{s.l}</p>
          </div>
        ))}
      </div>
      {qualitaRicette.ricette_coinvolte?.length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-semibold text-gray-600 mb-1.5">
            Ricette che usano i suoi prodotti ({qualitaRicette.ricette_coinvolte.length}):
          </p>
          <div className="flex flex-wrap gap-1.5">
            {qualitaRicette.ricette_coinvolte.map((r, i) => (
              <span key={i} className="text-[10px] bg-white border border-[#cfdfd5] text-[#3f5a4e] px-2 py-0.5 rounded-full">{r}</span>
            ))}
          </div>
        </div>
      )}
      {qualitaRicette.da_sistemare_totale > 0 && (
        <div>
          <p className="text-xs font-semibold text-[#c4894a] mb-1.5">
            ⚠ Da sistemare ({qualitaRicette.da_sistemare_totale} prodotti — dal Dizionario Ingredienti):
          </p>
          <div className="max-h-36 overflow-y-auto space-y-1">
            {qualitaRicette.da_sistemare.map((p, i) => (
              <div key={i} className="flex items-center justify-between gap-2 bg-white border border-[#f0e6d4] rounded px-2 py-1">
                <span className="text-[11px] text-gray-700 truncate">{p.descrizione}</span>
                <span className="text-[10px] text-[#c4894a] whitespace-nowrap">{p.problema}</span>
              </div>
            ))}
            {qualitaRicette.da_sistemare_totale > qualitaRicette.da_sistemare.length && (
              <p className="text-[10px] text-gray-400">
                … e altri {qualitaRicette.da_sistemare_totale - qualitaRicette.da_sistemare.length}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Rimanenze in giacenza dei prodotti del fornitore ───────────────────────
function RimanenzeCard({ anagrafica }) {
  if (!Array.isArray(anagrafica.rimanenze) || anagrafica.rimanenze.length === 0) return null;
  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-bold text-emerald-800 uppercase tracking-wide">
          Rimanenze in giacenza
        </p>
        <span className="text-xs font-semibold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full">
          {anagrafica.num_prodotti_in_giacenza} prodotti
        </span>
      </div>
      <div className="space-y-1.5 max-h-72 overflow-y-auto">
        {anagrafica.rimanenze.map((r, i) => (
          <div key={i} className="flex items-center justify-between bg-white rounded-lg border border-emerald-100 px-3 py-2">
            <div className="min-w-0">
              <p className="text-sm font-medium text-gray-800 truncate">{r.prodotto}</p>
              {r.giorni_alla_scadenza != null && (
                <p className={`text-xs ${r.scaduto || r.giorni_alla_scadenza < 0 ? "text-red-600 font-semibold" : r.giorni_alla_scadenza <= 7 ? "text-amber-600" : "text-gray-400"}`}>
                  {r.scaduto || r.giorni_alla_scadenza < 0 ? "scaduto" : `scade tra ${r.giorni_alla_scadenza} gg`}
                  {r.data_scadenza ? ` · ${r.data_scadenza}` : ""}
                </p>
              )}
            </div>
            <div className="text-right whitespace-nowrap ml-3">
              <span className="text-sm font-bold text-emerald-700">{r.quantita}</span>
              <span className="text-xs text-gray-500 ml-1">{r.unita}</span>
              {r.n_lotti > 1 && <span className="block text-[10px] text-gray-400">{r.n_lotti} lotti</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function SchedaAnagraficaModal({
  selectedFornitore, anagrafica, loadingAnagrafica,
  anniDisponibili, annoFiltro, onCambiaAnno, onClose,
  contattoEdit, setContattoEdit, salvandoContatto, onSalvaScheda,
  qualitaRicette, registroRicette,
  fornitoriEffettivi, onSetTipoFornitura,
}) {
  if (!selectedFornitore) return null;
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-xl max-h-[80vh] flex flex-col">
        <div className="px-4 py-3 border-b flex justify-between items-center">
          <h3 className="font-semibold flex items-center gap-2">
            <Building2 size={18} className="text-[#5b7a6b]" />
            Scheda Anagrafica Fornitore
          </h3>
          {/* ── Selettore anno globale ── */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 font-medium">Anno:</span>
            <div className="flex gap-1">
              {anniDisponibili.map(a => (
                <button
                  key={a}
                  onClick={() => onCambiaAnno(a)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                    annoFiltro === a
                      ? 'bg-[#5b7a6b] text-white shadow-sm'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {a}
                </button>
              ))}
            </div>
            <button onClick={onClose}
              className="text-gray-400 hover:text-gray-600 ml-2">
              <X size={18} />
            </button>
          </div>
        </div>
        <div className="overflow-y-auto flex-1 p-4">
          {loadingAnagrafica ? (
            <div className="text-center py-8 text-gray-400">Caricamento...</div>
          ) : anagrafica ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <p className="text-xs text-gray-500 font-medium">Ragione Sociale</p>
                  <p className="font-semibold text-gray-900">{anagrafica.nome}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-medium">P.IVA / C.F.</p>
                  <p className="text-sm">{anagrafica.piva || "-"}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-medium">Stato</p>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    anagrafica.escluso ? "bg-red-100 text-red-700" :
                    anagrafica.in_attesa ? "bg-amber-100 text-amber-700" :
                    "bg-green-100 text-green-700"
                  }`}>
                    {anagrafica.escluso ? "Escluso" : anagrafica.in_attesa ? "In Attesa" : "Attivo"}
                  </span>
                </div>
                <div className="col-span-2">
                  <p className="text-xs text-gray-500 font-medium mb-1">Cosa popola questo fornitore</p>
                  {(() => {
                    const tipoCorrente = (fornitoriEffettivi.find(x => x.nome === anagrafica.nome)?.tipo_fornitura) || (anagrafica.escluso ? "escluso" : "completo");
                    const opts = [
                      { v: "completo", l: "Magazzino + Lotti", d: "Ingrediente: stock, tracciabilità lotti e ricette" },
                      { v: "solo_magazzino", l: "Solo magazzino", d: "Stock/ordini, ma niente lotti né ricette" },
                      { v: "escluso", l: "Escluso", d: "Le sue fatture non vengono importate" },
                    ];
                    const cls = (v, on) => on
                      ? (v === "escluso" ? "bg-red-600 text-white border-red-600" : v === "solo_magazzino" ? "bg-amber-500 text-white border-amber-500" : "bg-green-600 text-white border-green-600")
                      : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50";
                    return (
                      <div className="flex flex-wrap gap-1.5">
                        {opts.map(o => (
                          <button key={o.v} onClick={() => onSetTipoFornitura(anagrafica.nome, o.v)} title={o.d}
                            className={`rounded-lg px-3 py-1.5 text-xs font-bold border transition ${cls(o.v, tipoCorrente === o.v)}`}>
                            {o.l}
                          </button>
                        ))}
                      </div>
                    );
                  })()}
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-medium">
                    N° Fatture {anagrafica.anno_filtro && `(${anagrafica.anno_filtro})`}
                  </p>
                  <p className="text-sm font-medium">
                    {anagrafica.num_fatture}
                    {anagrafica.num_fatture_totali !== anagrafica.num_fatture && (
                      <span className="text-xs text-gray-400 ml-1">/ {anagrafica.num_fatture_totali} tot.</span>
                    )}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-medium">
                    Totale Acquistato {anagrafica.anno_filtro && `(${anagrafica.anno_filtro})`}
                  </p>
                  <p className="text-sm font-bold text-[#5b7a6b]">€{(anagrafica.totale_acquistato || 0).toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-medium">Prodotti Diversi</p>
                  <p className="text-sm">{anagrafica.num_prodotti_diversi}</p>
                </div>
                {anagrafica.indirizzo && (
                  <div className="col-span-2">
                    <p className="text-xs text-gray-500 font-medium">Indirizzo</p>
                    <p className="text-sm">{anagrafica.indirizzo}</p>
                  </div>
                )}
                {anagrafica.note && (
                  <div className="col-span-2">
                    <p className="text-xs text-gray-500 font-medium">Note</p>
                    <p className="text-sm">{anagrafica.note}</p>
                  </div>
                )}
              </div>

              <ContattiCard
                selectedFornitore={selectedFornitore}
                contattoEdit={contattoEdit}
                setContattoEdit={setContattoEdit}
                salvandoContatto={salvandoContatto}
                onSalvaScheda={onSalvaScheda}
              />

              <RegistroRicetteCard registroRicette={registroRicette} />

              <QualitaRicetteCard qualitaRicette={qualitaRicette} />

              <RimanenzeCard anagrafica={anagrafica} />

              <TrackerColliOmaggio anagrafica={anagrafica} />

              {anagrafica.storico_fatture?.length > 0 && (
                <FattureList fatture={anagrafica.storico_fatture} />
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
