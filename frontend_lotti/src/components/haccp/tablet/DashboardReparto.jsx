/**
 * Cruscotto operativo di un reparto (Pasticceria, Rosticceria).
 *
 * Si vede dopo il PIN dell'operatore: chi lavora, cosa si e' prodotto oggi e
 * cosa resta da fare. Mostra SOLO dati che il backend espone gia':
 *  - produzioni di oggi            GET /produzioni/per-oggi (filtrate per reparto)
 *  - lotti scaduti o in scadenza   GET /supervisor/lotti-in-scadenza
 *  - temperature ancora da rilevare GET /haccp-auto/turno-oggi
 *  - sanificazioni in ritardo       GET /sanificazione/scadute
 *  - richieste merce aperte         GET /magazzino-bar/richieste?stato=aperta
 *  - anomalie aperte                GET /anomalie/lista?stato=…
 * Una lettura fallita si dice «non disponibile», mai zero: uno zero finto
 * sembrerebbe un reparto in regola.
 *
 * Il colore del reparto sta solo sulla fascia e sulle azioni; rosso, arancio
 * e verde (semantici) dicono lo stato, e ogni stato ha anche il testo.
 */
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import {
  AlertTriangle, BookOpen, CakeSlice, ChefHat, ClipboardCheck, Coffee,
  PackagePlus, RefreshCw, Sparkles, Thermometer, TimerReset, UserRound,
  ArrowLeft, WheatOff,
} from "lucide-react";
import { API } from "../../../utils/constants";
import { isAdmin } from "../../../auth";

const INK = "#2a3329";
const MUTED = "#6b6358";
const CARD = "#fffefb";
const LINE = "#e6e0d4";

const STATI = {
  pericolo: { colore: "#d35f4e", sfondo: "#fbe6e2", testo: "#8f3829" },
  avviso: { colore: "#c4894a", sfondo: "#f7ecdc", testo: "#7d5526" },
  ok: { colore: "#3d8168", sfondo: "#e2efe8", testo: "#234d3d" },
  info: { colore: "#8a6f47", sfondo: "#f3ede2", testo: "#5c4a2f" },
  ignoto: { colore: "#8a8478", sfondo: "#f3f0e8", testo: "#5c574e" },
};

const STATI_ANOMALIA_APERTI = ["Aperta", "In corso"];
const GIORNI_SCADENZA = 2;

async function leggi(url) {
  const risposta = await axios.get(`${API}${url}`, { timeout: 20000 });
  return risposta.data;
}

/** Carica ogni blocco per conto suo: un endpoint lento non spegne gli altri. */
export async function caricaCruscotto(reparto) {
  const [produzioni, scadenze, turno, sanificazioni, richieste, aperte, inCorso] = await Promise.allSettled([
    leggi("/produzioni/per-oggi"),
    leggi(`/supervisor/lotti-in-scadenza?giorni=${GIORNI_SCADENZA}&limit=5`),
    leggi("/haccp-auto/turno-oggi"),
    leggi("/sanificazione/scadute"),
    leggi("/magazzino-bar/richieste?stato=aperta&limit=100"),
    ...STATI_ANOMALIA_APERTI.map((stato) => leggi(`/anomalie/lista?stato=${encodeURIComponent(stato)}`)),
  ]);
  const ok = (r) => r.status === "fulfilled";
  const anomalie = ok(aperte) && ok(inCorso)
    ? [...(aperte.value || []), ...(inCorso.value || [])]
    : null;
  return {
    produzioni: ok(produzioni) && Array.isArray(produzioni.value)
      ? produzioni.value.filter((p) => p.reparto === reparto)
      : null,
    scadenze: ok(scadenze) ? { lotti: scadenze.value?.lotti || [], totale: scadenze.value?.totale ?? 0 } : null,
    turno: ok(turno) ? { lista: turno.value?.da_rilevare || [], quante: turno.value?.quante_da_rilevare ?? 0 } : null,
    sanificazioni: ok(sanificazioni)
      ? { ritardo: sanificazioni.value?.in_ritardo || [], senzaPiano: sanificazioni.value?.senza_piano || [] }
      : null,
    richieste: ok(richieste) ? { lista: richieste.value?.richieste || [], totale: richieste.value?.totale ?? 0 } : null,
    anomalie: anomalie ? { lista: anomalie, alta: anomalie.filter((a) => a.priorita === "Alta") } : null,
  };
}

function Chip({ stato, children }) {
  const s = STATI[stato] || STATI.ignoto;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, background: s.sfondo, color: s.testo, border: `1px solid ${s.colore}55`, borderRadius: 999, padding: "3px 10px", fontSize: 12, fontWeight: 800 }}>
      <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: 99, background: s.colore }} />
      {children}
    </span>
  );
}

function Blocco({ icona: Icona, titolo, valore, stato, etichetta, children, testId }) {
  const s = STATI[stato] || STATI.ignoto;
  return (
    <section data-testid={testId} style={{ background: CARD, border: `1px solid ${LINE}`, borderLeft: `5px solid ${s.colore}`, borderRadius: 16, padding: "14px 16px", minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, justifyContent: "space-between", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 800, color: INK, display: "flex", alignItems: "center", gap: 8 }}>
          <Icona size={18} color={s.colore} aria-hidden="true" /> {titolo}
        </h2>
        <Chip stato={stato}>{etichetta}</Chip>
      </div>
      {valore !== undefined && (
        <div style={{ fontSize: 30, fontWeight: 800, color: INK, letterSpacing: "-0.02em", marginTop: 6, fontVariantNumeric: "tabular-nums" }}>{valore}</div>
      )}
      {children && <div style={{ marginTop: 6, fontSize: 13, color: MUTED }}>{children}</div>}
    </section>
  );
}

function Elenco({ voci }) {
  if (!voci.length) return null;
  return (
    <ul style={{ margin: "4px 0 0", padding: 0, listStyle: "none", display: "grid", gap: 4 }}>
      {voci.map((v, i) => (
        <li key={i} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{v}</li>
      ))}
    </ul>
  );
}

function Azione({ icona: Icona, label, onClick, colore, testId }) {
  return (
    <button type="button" onClick={onClick} data-testid={testId}
      style={{ minHeight: 76, borderRadius: 16, border: "none", background: colore, color: "#fff", fontFamily: "inherit", fontSize: 16, fontWeight: 800, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 6, cursor: "pointer", boxShadow: "0 4px 14px rgba(42,51,41,.18)", padding: "10px 8px" }}>
      <Icona size={24} aria-hidden="true" />
      {label}
    </button>
  );
}

const NON_DISPONIBILE = "Dato non disponibile: riprova con «Aggiorna»";

export default function DashboardReparto({
  reparto, label, colore, operatore,
  onProduci, onRicette, onRichiediMerce, onColazione, onAlpha,
  onCambiaOperatore, onReparti,
}) {
  const [dati, setDati] = useState(null);
  const [carico, setCarico] = useState(true);
  const [haccpAperto, setHaccpAperto] = useState(false);

  const aggiorna = useCallback(async () => {
    setCarico(true);
    try { setDati(await caricaCruscotto(reparto)); } finally { setCarico(false); }
  }, [reparto]);

  useEffect(() => { aggiorna(); }, [aggiorna]);

  const d = dati || {};
  const produzioni = d.produzioni;
  const pezzi = produzioni ? produzioni.reduce((s, p) => s + (Number(p.pezzi) || 0), 0) : 0;
  const scaduti = d.scadenze ? d.scadenze.lotti.filter((l) => (l.giorni_alla_scadenza ?? 0) < 0).length : 0;

  const stato = (valore, seZero, seNonZero) => (valore === null || valore === undefined ? "ignoto" : valore > 0 ? seNonZero : seZero);

  return (
    <div data-testid={`cruscotto-${reparto}`} style={{ padding: "14px 16px 28px", display: "grid", gap: 14, maxWidth: 1100, width: "100%", margin: "0 auto", boxSizing: "border-box" }}>
      {/* Chi sta lavorando: il PIN si chiede una volta per turno, non a ogni reparto. */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", background: CARD, border: `1px solid ${LINE}`, borderRadius: 16, padding: "12px 16px" }}>
        <div style={{ width: 44, height: 44, borderRadius: 99, background: colore, display: "grid", placeItems: "center", flexShrink: 0 }}>
          <UserRound size={22} color="#fff" aria-hidden="true" />
        </div>
        <div style={{ flex: 1, minWidth: 160 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: MUTED }}>Operatore attivo · {label}</div>
          <div data-testid="operatore-attivo" style={{ fontSize: 18, fontWeight: 800, color: INK }}>{operatore?.nome || "—"}</div>
        </div>
        <button type="button" onClick={aggiorna} disabled={carico} aria-label="Aggiorna i dati del reparto"
          style={{ minHeight: 44, padding: "0 14px", borderRadius: 12, border: `1px solid ${LINE}`, background: CARD, color: INK, fontWeight: 700, fontFamily: "inherit", display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
          <RefreshCw size={16} aria-hidden="true" /> {carico ? "Aggiorno…" : "Aggiorna"}
        </button>
        <button type="button" onClick={onCambiaOperatore} data-testid="cambia-operatore"
          style={{ minHeight: 44, padding: "0 14px", borderRadius: 12, border: `1px solid ${LINE}`, background: CARD, color: INK, fontWeight: 700, fontFamily: "inherit", display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
          <TimerReset size={16} aria-hidden="true" /> Cambia operatore
        </button>
      </div>

      {/* Azioni primarie: grandi, per le mani sporche. */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(150px,1fr))", gap: 12 }}>
        <Azione icona={ChefHat} label="Produci e registra lotto" onClick={onProduci} colore={colore} testId="azione-produci" />
        <Azione icona={BookOpen} label="Ricette" onClick={onRicette} colore={colore} testId="azione-ricette" />
        <Azione icona={PackagePlus} label="Richiedi merce" onClick={onRichiediMerce} colore={colore} testId="azione-richiedi-merce" />
        <Azione icona={ClipboardCheck} label="Controlli HACCP" onClick={() => setHaccpAperto((v) => !v)} colore={colore} testId="azione-haccp" />
        {onColazione && <Azione icona={Coffee} label="Colazione" onClick={onColazione} colore={colore} testId="azione-colazione" />}
        {onAlpha && <Azione icona={WheatOff} label="Senza glutine" onClick={onAlpha} colore={colore} testId="azione-alpha" />}
        <Azione icona={ArrowLeft} label="Torna ai reparti" onClick={onReparti} colore="#4a3f33" testId="azione-reparti" />
      </div>

      {haccpAperto && (
        <section data-testid="pannello-haccp" style={{ background: CARD, border: `1px solid ${LINE}`, borderRadius: 16, padding: "14px 16px", display: "grid", gap: 10 }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: INK }}>Controlli HACCP di oggi</h2>
          <div style={{ fontSize: 14, color: INK }}>
            <b>Temperature da rilevare:</b>{" "}
            {d.turno ? (d.turno.lista.length
              ? d.turno.lista.map((t) => `${t.nome || `${t.tipo} ${t.numero}`}${t.operatore_nome ? ` (tocca a ${t.operatore_nome})` : ""}`).join(" · ")
              : "nessuna") : NON_DISPONIBILE}
          </div>
          <div style={{ fontSize: 14, color: INK }}>
            <b>Sanificazioni in ritardo:</b>{" "}
            {d.sanificazioni ? (d.sanificazioni.ritardo.length
              ? d.sanificazioni.ritardo.map((s) => s.area).join(" · ")
              : "nessuna") : NON_DISPONIBILE}
          </div>
          {isAdmin() ? (
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <a href="#temp_positive" style={{ minHeight: 44, display: "inline-flex", alignItems: "center", padding: "0 14px", borderRadius: 12, background: "#5b7a6b", color: "#fff", fontWeight: 800, textDecoration: "none" }}>Registro temperature</a>
              <a href="#sanificazione" style={{ minHeight: 44, display: "inline-flex", alignItems: "center", padding: "0 14px", borderRadius: 12, background: "#5b7a6b", color: "#fff", fontWeight: 800, textDecoration: "none" }}>Registro sanificazione</a>
            </div>
          ) : (
            <p style={{ margin: 0, fontSize: 13, color: MUTED }}>Le rilevazioni si registrano e si firmano dal registro HACCP: qui vedi cosa manca.</p>
          )}
        </section>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(260px,1fr))", gap: 12 }}>
        <Blocco testId="blocco-anomalie" icona={AlertTriangle} titolo="Anomalie aperte"
          valore={d.anomalie ? d.anomalie.lista.length : undefined}
          stato={!d.anomalie ? "ignoto" : d.anomalie.alta.length ? "pericolo" : d.anomalie.lista.length ? "avviso" : "ok"}
          etichetta={!d.anomalie ? (carico ? "Carico…" : "Non disponibile") : d.anomalie.alta.length ? `${d.anomalie.alta.length} priorità alta` : d.anomalie.lista.length ? "Da seguire" : "Nessuna"}>
          {d.anomalie ? <Elenco voci={d.anomalie.alta.concat(d.anomalie.lista.filter((a) => a.priorita !== "Alta")).slice(0, 3).map((a) => `${a.attrezzatura || a.categoria || "Attrezzatura"} — ${a.tipo || ""}`)} /> : (!carico && NON_DISPONIBILE)}
        </Blocco>

        <Blocco testId="blocco-temperature" icona={Thermometer} titolo="Temperature da rilevare oggi"
          valore={d.turno ? d.turno.quante : undefined}
          stato={stato(d.turno ? d.turno.quante : null, "ok", "avviso")}
          etichetta={!d.turno ? (carico ? "Carico…" : "Non disponibile") : d.turno.quante ? "Da rilevare" : "Tutte rilevate"}>
          {d.turno ? <Elenco voci={d.turno.lista.slice(0, 3).map((t) => t.nome || `${t.tipo} ${t.numero}`)} /> : (!carico && NON_DISPONIBILE)}
        </Blocco>

        <Blocco testId="blocco-sanificazioni" icona={Sparkles} titolo="Sanificazioni in ritardo"
          valore={d.sanificazioni ? d.sanificazioni.ritardo.length : undefined}
          stato={stato(d.sanificazioni ? d.sanificazioni.ritardo.length : null, "ok", "avviso")}
          etichetta={!d.sanificazioni ? (carico ? "Carico…" : "Non disponibile") : d.sanificazioni.ritardo.length ? "In ritardo" : "In regola"}>
          {d.sanificazioni ? (
            <>
              <Elenco voci={d.sanificazioni.ritardo.slice(0, 3).map((s) => s.area)} />
              {d.sanificazioni.senzaPiano.length > 0 && <div style={{ marginTop: 4 }}>{d.sanificazioni.senzaPiano.length} aree senza piano</div>}
            </>
          ) : (!carico && NON_DISPONIBILE)}
        </Blocco>

        <Blocco testId="blocco-scadenze" icona={AlertTriangle} titolo={`Lotti in scadenza (entro ${GIORNI_SCADENZA} giorni)`}
          valore={d.scadenze ? d.scadenze.totale : undefined}
          stato={!d.scadenze ? "ignoto" : scaduti ? "pericolo" : d.scadenze.totale ? "avviso" : "ok"}
          etichetta={!d.scadenze ? (carico ? "Carico…" : "Non disponibile") : scaduti ? `${scaduti} già scaduti` : d.scadenze.totale ? "Da usare subito" : "Nessuno"}>
          {d.scadenze ? (
            <>
              <Elenco voci={d.scadenze.lotti.slice(0, 3).map((l) => `${l.prodotto || "Lotto"} · scad. ${l.data_scadenza || "—"}`)} />
              <div style={{ marginTop: 4 }}>Tutto il laboratorio, non solo {label}.</div>
            </>
          ) : (!carico && NON_DISPONIBILE)}
        </Blocco>

        <Blocco testId="blocco-produzioni" icona={CakeSlice} titolo="Produzioni di oggi"
          valore={produzioni ? produzioni.length : undefined}
          stato={produzioni ? "info" : "ignoto"}
          etichetta={!produzioni ? (carico ? "Carico…" : "Non disponibile") : `${pezzi} pezzi`}>
          {produzioni ? <Elenco voci={produzioni.slice(0, 3).map((p) => `${p.ricetta || p.nome || "Produzione"} · ${p.pezzi ?? "?"} pz${p.operatore_nome ? ` · ${p.operatore_nome}` : ""}`)} /> : (!carico && NON_DISPONIBILE)}
        </Blocco>

        <Blocco testId="blocco-richieste" icona={PackagePlus} titolo="Richieste merce aperte"
          valore={d.richieste ? d.richieste.totale : undefined}
          stato={d.richieste ? (d.richieste.totale ? "info" : "ok") : "ignoto"}
          etichetta={!d.richieste ? (carico ? "Carico…" : "Non disponibile") : d.richieste.totale ? "In attesa del magazzino" : "Nessuna"}>
          {d.richieste ? <Elenco voci={d.richieste.lista.slice(0, 3).map((r) => `${r.prodotto_nome} · ${r.quantita} ${r.unita_movimento === "pezzo" ? "pz" : "colli"}${r.richiesto_da ? ` · ${r.richiesto_da}` : ""}`)} /> : (!carico && NON_DISPONIBILE)}
        </Blocco>
      </div>

    </div>
  );
}
