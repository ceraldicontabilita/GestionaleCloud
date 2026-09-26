import React, { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw, ShieldCheck } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import { API } from "../../utils/constants";
import { apiError } from "../../utils/apiError";
import { conferma } from "../../utils/conferma";
import { LEGENDA_NA } from "../../utils/attendibilita";

// GC-02h (decisione del titolare, strada A): le registrazioni HACCP in archivio
// senza firma verificata si SEGNANO «n.a.», non si cancellano. Qui il titolare
// vede l'anteprima e preme lui il bottone, entrato dal login del Gestionale:
// nessun token passa di mano. Backend: routers/haccp_attendibilita.py.

const CATEGORIE = {
  temperatura_valore_semplice: "Temperature scritte come numero, senza firma",
  temperatura_senza_firma: "Temperature con nome ma senza firma verificata",
  manutenzione_o_non_usato: "Fermi «manutenzione» / «non usato» del vecchio calendario",
  sanificazione_in_temperature: "Sanificazioni annotate nelle schede temperature",
  sanificazione_x_senza_firma: "«X» delle schede sanificazione senza firma",
  sanificazione_apparecchio_senza_firma: "Sanificazioni frigo/congelatori senza firma",
};
const NON_TOCCATI = {
  giorno_chiuso: "Giorni di chiusura dichiarati",
  non_rilevato: "Giorni dichiarati «non rilevato»",
  casella_aperta: "Caselle aperte dal turno delle 07:00",
  n_d: "Caselle «N/D»",
  firmato: "Registrazioni firmate (restano valide)",
};
const COLLEZIONI = {
  temperature_positive: "Frigoriferi",
  temperature_negative: "Congelatori",
  sanificazione_schede: "Schede sanificazione",
  sanificazione_apparecchi: "Sanificazione apparecchi",
};

const n = (v) => Number(v || 0).toLocaleString("it-IT");

const Card = ({ children, className = "" }) => (
  <div className={`rounded-2xl border border-[#e6e0d4] bg-[#fffefb] p-4 shadow-sm ${className}`}>{children}</div>
);

export default function AttendibilitaHaccpView() {
  const [dati, setDati] = useState(null);
  const [loading, setLoading] = useState(false);
  const [scrivendo, setScrivendo] = useState(false);
  const [esito, setEsito] = useState(null);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/haccp-attendibilita/anteprima`);
      setDati(r.data);
    } catch (e) {
      toast.error(apiError(e, "Anteprima non disponibile"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const segna = async () => {
    if (!dati?.totale_da_segnare) return;
    const ok = await conferma(
      `Segnare «n.a.» ${n(dati.totale_da_segnare)} registrazioni senza firma verificata? ` +
        "I valori restano com'erano: si aggiunge solo il segno. Una seconda esecuzione non cambia niente.",
      { titolo: "Segna le registrazioni non attendibili", ok: "Sì, segna", pericolo: true },
    );
    if (!ok) return;
    setScrivendo(true);
    try {
      const r = await axios.post(`${API}/haccp-attendibilita/segna`, null, {
        params: { dry_run: false, conferma: "SEGNA" },
      });
      setEsito(r.data);
      toast.success(`${n(r.data.caselle_segnate)} registrazioni segnate su ${n(r.data.documenti_modificati)} schede`);
      await carica();
    } catch (e) {
      toast.error(apiError(e, "Scrittura non riuscita"));
    } finally {
      setScrivendo(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-2xl space-y-3">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-extrabold text-[#2a3329]" style={{ letterSpacing: "-0.02em" }}>
          <ShieldCheck size={20} className="text-[#5b7a6b]" aria-hidden="true" /> Attendibilità registri HACCP
        </h2>
        <p className="text-[13px] text-[#6b6358]">
          Le registrazioni in archivio senza firma verificata (PIN o sessione del tablet) non attestano chi ha fatto il
          controllo. Non si cancellano: si segnano «n.a.» e stampe e schede le tengono fuori dai conteggi di conformità.
        </p>
      </div>

      {loading && !dati && <div className="py-8 text-center text-[#8a7f70]">Conto le registrazioni…</div>}

      {dati && (
        <>
          <Card>
            <div className="grid grid-cols-2 gap-3 text-center">
              <div>
                <div className="text-2xl font-extrabold tabular-nums text-[#c4894a]">{n(dati.totale_da_segnare)}</div>
                <div className="text-[12px] text-[#6b6358]">da segnare</div>
              </div>
              <div>
                <div className="text-2xl font-extrabold tabular-nums text-[#3d8168]">{n(dati.totale_gia_segnati)}</div>
                <div className="text-[12px] text-[#6b6358]">già segnate</div>
              </div>
            </div>
          </Card>

          <Card className="space-y-2">
            <h3 className="text-sm font-bold text-[#3f5a4e]">Cosa si segna</h3>
            {Object.entries(CATEGORIE).map(([k, etichetta]) => {
              const c = dati.per_categoria?.[k] || {};
              return (
                <div key={k} className="flex items-start justify-between gap-3 border-t border-[#f0ebe0] pt-2 text-[13px]">
                  <span className="text-[#2a3329]">{etichetta}</span>
                  <span className="whitespace-nowrap text-right tabular-nums">
                    <b>{n(c.da_segnare)}</b>
                    {c.gia_segnati ? <span className="block text-[11px] text-[#8a7f70]">{n(c.gia_segnati)} già segnate</span> : null}
                  </span>
                </div>
              );
            })}
          </Card>

          <Card className="space-y-2">
            <h3 className="text-sm font-bold text-[#3f5a4e]">Per registro e anno</h3>
            {Object.entries(dati.per_collezione || {}).map(([coll, anni]) => (
              <div key={coll} className="border-t border-[#f0ebe0] pt-2 text-[13px]">
                <div className="font-bold text-[#2a3329]">{COLLEZIONI[coll] || coll}</div>
                <div className="mt-1 flex flex-wrap gap-2">
                  {Object.entries(anni).sort().map(([anno, cats]) => {
                    const tot = Object.values(cats).reduce((s, c) => s + (c.da_segnare || 0) + (c.gia_segnati || 0), 0);
                    return (
                      <span key={anno} className="rounded-full border border-[#e6e0d4] bg-[#faf7f0] px-2.5 py-1 text-[12px]">
                        {anno}: <b className="tabular-nums">{n(tot)}</b>
                      </span>
                    );
                  })}
                </div>
              </div>
            ))}
          </Card>

          <Card className="space-y-2">
            <h3 className="text-sm font-bold text-[#3f5a4e]">Cosa resta com'è</h3>
            {Object.entries(NON_TOCCATI).map(([k, etichetta]) => (
              <div key={k} className="flex justify-between gap-3 border-t border-[#f0ebe0] pt-2 text-[13px]">
                <span className="text-[#2a3329]">{etichetta}</span>
                <b className="tabular-nums">{n(dati.non_toccati?.[k])}</b>
              </div>
            ))}
            {dati.anomalie?.length > 0 && (
              <div className="rounded-xl border border-[#e8d3b5] bg-[#fbf3e8] p-3 text-[12px] text-[#7a5a2e]">
                <div className="mb-1 flex items-center gap-1.5 font-bold">
                  <AlertTriangle size={14} aria-hidden="true" /> {dati.anomalie.length} valori di forma inattesa (non toccati)
                </div>
                {dati.anomalie.slice(0, 10).map((a, i) => (
                  <div key={i}>
                    {COLLEZIONI[a.collezione] || a.collezione} {a.anno} · {a.coordinata.join(" / ")}: {a.motivo}
                  </div>
                ))}
              </div>
            )}
          </Card>

          <p className="text-[12px] text-[#8a7f70]">{LEGENDA_NA}</p>

          {esito && (
            <div className="flex items-center gap-2 rounded-xl border border-[#b8d0c2] bg-[#eef3ef] px-3 py-2 text-[13px] text-[#3f5a4e]">
              <CheckCircle2 size={16} aria-hidden="true" />
              Segnate {n(esito.caselle_segnate)} registrazioni su {n(esito.documenti_modificati)} schede.
            </div>
          )}

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <button type="button" onClick={carica} disabled={loading || scrivendo}
              className="flex min-h-[48px] items-center justify-center gap-2 rounded-xl border border-[#e6e0d4] bg-[#fffefb] text-sm font-bold text-[#3f5a4e] disabled:opacity-50">
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} aria-hidden="true" /> Ricalcola anteprima
            </button>
            <button type="button" onClick={segna} disabled={scrivendo || loading || !dati.totale_da_segnare}
              className="flex min-h-[48px] items-center justify-center gap-2 rounded-xl bg-[#5b7a6b] text-sm font-bold text-white disabled:opacity-50">
              <ShieldCheck size={16} aria-hidden="true" />
              {dati.totale_da_segnare ? `Segna ${n(dati.totale_da_segnare)} registrazioni` : "Niente da segnare"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
