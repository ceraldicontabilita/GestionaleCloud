import { useEffect, useMemo, useState } from "react";
import { conferma } from "../../utils/conferma";
import axios from "axios";
import { toast } from "sonner";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Database,
  ExternalLink,
  ListChecks,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { API, formatDate, withToken } from "../../utils/constants";

const statusMeta = {
  ok: {
    label: "OK",
    icon: CheckCircle2,
    bg: "bg-emerald-50",
    fg: "text-emerald-700",
    border: "border-emerald-200",
  },
  attenzione: {
    label: "Attenzione",
    icon: AlertTriangle,
    bg: "bg-amber-50",
    fg: "text-amber-700",
    border: "border-amber-200",
  },
  critico: {
    label: "Critico",
    icon: XCircle,
    bg: "bg-rose-50",
    fg: "text-rose-700",
    border: "border-rose-200",
  },
};

function asNumber(value) {
  const n = Number(value || 0);
  return Number.isFinite(n) ? n : 0;
}

function sampleLabel(sample) {
  if (!sample) return "";
  return (
    sample.nome_canonico ||
    sample.descrizione ||
    sample.ingrediente ||
    sample.ricetta ||
    sample.prodotto ||
    sample.prodotto_nome ||
    sample.numero_fattura ||
    sample.job ||
    sample.nome ||
    sample.id ||
    "Record"
  );
}

function formatSample(sample) {
  const parts = [];
  if (sample.fornitore) parts.push(sample.fornitore);
  if (sample.piva) parts.push(`P.IVA ${sample.piva}`);
  if (sample.data_fattura || sample.data || sample.timestamp) {
    parts.push(formatDate(sample.data_fattura || sample.data || sample.timestamp, true));
  }
  if (sample.quantita) parts.push(`Qta ${sample.quantita}`);
  return parts.join(" - ");
}

function SummaryTile({ label, value, tone = "slate" }) {
  const tones = {
    slate: "border-slate-200 bg-white text-slate-900",
    green: "border-emerald-200 bg-emerald-50 text-emerald-800",
    amber: "border-amber-200 bg-amber-50 text-amber-800",
    red: "border-rose-200 bg-rose-50 text-rose-800",
    indigo: "border-[#cfdfd5] bg-[#f2f6f3] text-[#3f5a4e]",
  };
  return (
    <div className={`rounded-lg border px-4 py-3 ${tones[tone]}`}>
      <div className="text-2xl font-bold leading-none">{value}</div>
      <div className="mt-1 text-xs font-semibold uppercase tracking-normal opacity-70">{label}</div>
    </div>
  );
}

// Ogni campione porta ALLA COSA segnalata, non alla pagina generica
// (segnalato da Enzo 04/07/2026: "ovunque clicco si apre la pagina generica").
function apriCampione(issue, sample, navigate) {
  // fatture: apre direttamente la fattura nel visualizzatore
  if ((issue.id === "righe_fattura_senza_link" || issue.id === "fatture_non_riconciliate") && sample.id) {
    window.open(withToken(`${API}/fatture/${sample.id}/visualizza`), "_blank");
    return;
  }
  // ricette: apre la scheda della ricetta (stesso meccanismo del Supervisore)
  if (issue.id === "ricette_ingredienti_senza_link" && sample.id) {
    try { sessionStorage.setItem("apri_ricetta_id", sample.id); } catch { /* no-op */ }
    navigate("ricette");
    return;
  }
  // lotti: apre Lotti con la ricerca già compilata sul lotto segnalato
  if (issue.id === "lotti_senza_tracciabilita" && (sample.numero_lotto || sample.prodotto || sample.prodotto_nome)) {
    try { sessionStorage.setItem("lotti_search", String(sample.numero_lotto || sample.prodotto || sample.prodotto_nome)); } catch { /* no-op */ }
    navigate("lotti");
    return;
  }
  // fallback: l'area del controllo
  navigate(issue.route);
}

function IssueCard({ issue, onNavigate }) {
  const meta = statusMeta[issue.stato] || statusMeta.attenzione;
  const Icon = meta.icon;
  const count = asNumber(issue.conteggio);

  return (
    <div className={`rounded-lg border bg-white p-4 shadow-sm ${meta.border}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-bold ${meta.bg} ${meta.fg}`}>
              <Icon size={13} />
              {meta.label}
            </span>
            <span className="text-xs font-semibold text-slate-500">{issue.area}</span>
          </div>
          <h3 className="mt-2 text-base font-bold text-slate-900">{issue.titolo}</h3>
          <p className="mt-1 text-sm text-slate-600">{issue.descrizione}</p>
        </div>
        <div className="text-right">
          <div className={`text-2xl font-bold ${meta.fg}`}>{count}</div>
          <div className="text-xs font-semibold text-slate-500">
            {issue.totale ? `su ${issue.totale}` : "rilevati"}
          </div>
        </div>
      </div>

      <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
        {issue.azione_consigliata}
      </div>

      {issue.campioni?.length > 0 && (
        <div className="mt-3 space-y-2">
          {issue.campioni.slice(0, 3).map((sample, idx) => (
            <button
              type="button"
              key={`${issue.id}-${idx}`}
              onClick={() => apriCampione(issue, sample, onNavigate)}
              className="flex min-h-10 w-full items-center justify-between gap-3 rounded-md border border-slate-200 px-3 py-2 text-left hover:border-[#b8d0c2] hover:bg-[#f2f6f3] active:scale-[.99]"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-slate-800">{sampleLabel(sample)}</div>
                <div className="truncate text-xs text-slate-500">{formatSample(sample)}</div>
              </div>
              <ChevronRight size={15} className="shrink-0 text-[#5b7a6b]" />
            </button>
          ))}
        </div>
      )}

      {issue.route && (
        <button
          type="button"
          onClick={() => onNavigate(issue.route)}
          className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          Apri area
          <ExternalLink size={13} />
        </button>
      )}
    </div>
  );
}

function PuliziaDbPanel() {
  const [proposta, setProposta] = useState(null);
  const [busy, setBusy] = useState("");
  const [esito, setEsito] = useState(null);

  const analizza = async () => {
    setBusy("analisi"); setEsito(null);
    try {
      const r = await axios.get(`${API}/diagnostic/pulizia-collezioni-proposta`, { timeout: 60000 });
      setProposta(r.data);
      if (!r.data.drop_vuote?.length && !r.data.rinomina_cestino?.length) {
        toast.success("Database già pulito: niente da fare");
      }
    } catch { toast.error("Analisi non riuscita"); }
    finally { setBusy(""); }
  };

  const esegui = async () => {
    if (!proposta) return;
    setBusy("esegui");
    try {
      const r = await axios.post(`${API}/diagnostic/pulizia-collezioni`, {
        drop_vuote: proposta.drop_vuote || [],
        rinomina_cestino: (proposta.rinomina_cestino || []).map((c) => c.collezione),
        conferma: true,
      }, { timeout: 120000 });
      setEsito(r.data);
      setProposta(null);
      toast.success(`Pulizia fatta: ${r.data.drop?.length || 0} eliminate, ${r.data.rinomina?.length || 0} nel cestino`);
    } catch { toast.error("Pulizia non riuscita"); }
    finally { setBusy(""); }
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <Database size={18} className="text-slate-700" />
        <h3 className="text-base font-bold text-slate-900">Pulizia collezioni database</h3>
      </div>
      <p className="mb-3 text-sm text-slate-500">
        Elimina le collezioni vuote e sposta nel cestino (reversibile) i resti delle
        vecchie versioni. Le collezioni usate da Lotti sono protette e non si toccano.
      </p>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={analizza} disabled={!!busy}
          className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60">
          <RefreshCw size={15} className={busy === "analisi" ? "animate-spin" : ""} />
          Analizza
        </button>
        <button type="button" disabled={!!busy}
          onClick={async () => {
            setBusy("rebuild");
            try {
              const r = await axios.post(`${API}/prodotti-master/rebuild`, {}, { timeout: 120000 });
              toast.success(`Catalogo ricostruito: ${r.data?.totale ?? r.data?.prodotti ?? "ok"}`);
            } catch { toast.error("Rebuild non riuscito"); }
            finally { setBusy(""); }
          }}
          className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60">
          <RefreshCw size={15} className={busy === "rebuild" ? "animate-spin" : ""} />
          Rebuild catalogo prodotti
        </button>
        <button type="button" disabled={!!busy}
          onClick={async () => {
            setBusy("bozze");
            try {
              const prev = await axios.post(`${API}/ordini-fornitori/pulisci-e-rigenera-riordini`, {}, { timeout: 60000 });
              const n = prev.data?.bozze_da_eliminare ?? 0;
              if (!n) { toast.success("Nessuna bozza automatica vecchia da pulire"); return; }
              if (!await conferma(`Eliminare ${n} bozze automatiche vecchie e rigenerare i riordini con le scorte di oggi? (le bozze manuali non si toccano)`)) return;
              const r = await axios.post(`${API}/ordini-fornitori/pulisci-e-rigenera-riordini?conferma=true`, {}, { timeout: 120000 });
              toast.success(`Pulite ${r.data?.eliminate} bozze — rigenerate ${r.data?.rigenerate?.length || 0} bozze fresche (${r.data?.prodotti_riordinati || 0} prodotti)`);
            } catch { toast.error("Pulizia bozze non riuscita"); }
            finally { setBusy(""); }
          }}
          className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60">
          <RefreshCw size={15} className={busy === "bozze" ? "animate-spin" : ""} />
          Pulisci e rigenera riordini
        </button>
        {proposta && (proposta.drop_vuote?.length > 0 || proposta.rinomina_cestino?.length > 0) && (
          <button type="button" onClick={esegui} disabled={!!busy}
            className="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: "#5b7a6b" }}>
            <CheckCircle2 size={15} className={busy === "esegui" ? "animate-spin" : ""} />
            Conferma pulizia ({proposta.drop_vuote?.length || 0} vuote + {proposta.rinomina_cestino?.length || 0} nel cestino)
          </button>
        )}
      </div>
      {proposta && (
        <div className="mt-3 grid gap-2 text-xs text-slate-600 md:grid-cols-2">
          <div>
            <div className="mb-1 font-semibold text-slate-800">Vuote da eliminare ({proposta.drop_vuote?.length || 0})</div>
            {(proposta.drop_vuote || []).map((c) => <div key={c} className="truncate">• {c}</div>)}
            {!proposta.drop_vuote?.length && <div className="italic">nessuna</div>}
          </div>
          <div>
            <div className="mb-1 font-semibold text-slate-800">Da spostare nel cestino ({proposta.rinomina_cestino?.length || 0})</div>
            {(proposta.rinomina_cestino || []).map((c) => (
              <div key={c.collezione} className="truncate">• {c.collezione} ({c.documenti} doc)</div>
            ))}
            {!proposta.rinomina_cestino?.length && <div className="italic">nessuna</div>}
          </div>
        </div>
      )}
      {esito && (
        <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-2 text-xs text-emerald-800">
          Fatto: {esito.drop?.length || 0} collezioni vuote eliminate, {esito.rinomina?.length || 0} spostate nel cestino
          {esito.saltate?.length ? ` — ${esito.saltate.length} saltate (protette o non vuote)` : ""}.
        </div>
      )}
    </div>
  );
}

export default function ControlloDatiView() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/controllo-dati/overview`, {
        params: { limit_campioni: 5 },
      });
      setData(res.data);
    } catch (error) {
      toast.error("Errore caricamento controllo dati");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const orderedIssues = useMemo(() => {
    const rank = { critico: 0, attenzione: 1, ok: 2 };
    return [...(data?.controlli || [])].sort((a, b) => {
      const byStatus = (rank[a.stato] ?? 3) - (rank[b.stato] ?? 3);
      if (byStatus !== 0) return byStatus;
      return asNumber(b.conteggio) - asNumber(a.conteggio);
    });
  }, [data]);

  const summary = data?.riepilogo || {};
  const score = asNumber(summary.score_interconnessione);

  const navigate = (route) => {
    if (!route) return;
    window.location.hash = route.replace(/^#/, "");
  };

  return (
    <div className="space-y-4" data-testid="controllo-dati-view">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-lg bg-slate-900 text-white">
            <Database size={19} />
          </div>
          <div className="min-w-0">
            <h2 className="text-lg font-bold text-slate-900">Centro controllo dati</h2>
            <p className="text-sm text-slate-500">
              Ultimo aggiornamento: {data?.aggiornato_il ? formatDate(data.aggiornato_il, true) : "in corso"}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
        >
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          Aggiorna
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <SummaryTile label="Score" value={`${score}%`} tone={score >= 80 ? "green" : score >= 50 ? "amber" : "red"} />
        <SummaryTile label="OK" value={summary.ok || 0} tone="green" />
        <SummaryTile label="Attenzione" value={summary.attenzione || 0} tone="amber" />
        <SummaryTile label="Critici" value={summary.critici || 0} tone="red" />
        <SummaryTile label="Controlli" value={summary.totale_controlli || 0} tone="indigo" />
      </div>

      {loading && !data ? (
        <div className="rounded-lg border border-slate-200 bg-white p-10 text-center text-slate-500">
          <RefreshCw size={24} className="mx-auto mb-3 animate-spin" />
          Caricamento controlli...
        </div>
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {orderedIssues.map((issue) => (
            <IssueCard key={issue.id} issue={issue} onNavigate={navigate} />
          ))}
        </div>
      )}

      <PuliziaDbPanel />

      {data?.prossime_azioni?.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center gap-2">
            <ListChecks size={18} className="text-[#5b7a6b]" />
            <h3 className="text-base font-bold text-slate-900">Prossime azioni</h3>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            {data.prossime_azioni.map((action) => (
              <div key={action} className="rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-700">
                {action}
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && orderedIssues.length === 0 && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-emerald-800">
          <CircleAlert size={18} className="mb-2" />
          Nessun controllo disponibile.
        </div>
      )}
    </div>
  );
}
