/**
 * ImpostazioniPersonaleView.jsx — personale HACCP, stampanti e dati azienda.
 *
 * 14/09/2026 (titolare, regole R1-R6): l'anagrafica HR comanda, Lotti legge.
 *  - gli operatori sono i dipendenti in forza nell'anagrafica HR (con la spunta
 *    «operatore Lotti»): nome, ruolo, stato e data di fine rapporto vivono in HR,
 *    qui sono in sola lettura con il link alla scheda;
 *  - il PIN si imposta nella scheda HR (uno per persona, portale + tablet):
 *    il blocco «PIN operatori» e la sezione «Nuovi dipendenti dal gestionale»
 *    non esistono più;
 *  - qui restano solo i dati HACCP: postazione (proposta dal ruolo HR) e
 *    scadenza del libretto sanitario; chi non è più in carico sta in una
 *    sezione chiusa in fondo, con data e motivo letti da HR.
 */
import React, { useState, useEffect, useCallback, useMemo } from "react";
import { apiError } from "../../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import { IdCard, Save, Users, Printer, ExternalLink, RefreshCw, ChevronDown, ChevronUp, AlertTriangle, KeyRound, LockKeyhole, Delete, X } from "lucide-react";
import { API } from "../../utils/constants";
import StampantiConfigView from "./StampantiConfigView";
import { createPinModal } from "../../../../frontend_shared/PinModal";

// Tastierino condiviso: il PIN si digita, non si mostra e non si salva qui.
const PinModal = createPinModal(React, { LockKeyhole, Delete, X });

const SAGE = "#5b7a6b";
const SALVIA = "#3f5a4e";
const CARD = "#fffefb";
const LINE = "#e6e0d4";
const DANGER = "#d35f4e";
const WARN = "#9c6a32";
const OK = "#3d8168";
const MUTED = "#9aa593";

const POSTAZIONI = ["laboratorio", "pasticceria", "sala", "bar"];
const HR_ANAGRAFICA = "/hr/dipendenti/anagrafica";

const inp = { padding: "9px 10px", borderRadius: 8, border: `1px solid ${LINE}`, fontSize: 14, fontFamily: "inherit", boxSizing: "border-box", minHeight: 44 };
const btn = (bg) => ({ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, padding: "10px 14px", minHeight: 44, borderRadius: 9, border: "none", background: bg, color: "#fff", fontWeight: 700, fontSize: 13, cursor: "pointer" });
const sezione = { background: CARD, border: `1px solid ${LINE}`, borderRadius: 16, padding: "16px 18px", marginBottom: 18 };
const titoloSez = { display: "flex", alignItems: "center", gap: 9, margin: "0 0 4px", fontSize: 17, fontWeight: 700, color: SALVIA, fontFamily: "\'Plus Jakarta Sans\', -apple-system, BlinkMacSystemFont, \'Segoe UI\', system-ui, sans-serif", flexWrap: "wrap" };
const pill = (bg, fg) => ({ fontSize: 11, fontWeight: 700, background: bg, color: fg, borderRadius: 6, padding: "3px 9px", whiteSpace: "nowrap" });

const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : "");
const dataIt = (iso) => {
  if (!iso) return "";
  const [y, m, d] = String(iso).slice(0, 10).split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
};
const oraIt = (iso) => {
  try { return new Date(iso).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }); } catch { return ""; }
};

// Campi azienda che finiscono nei PDF (listino, report HACCP, manuale, etichette, ordini)
const CAMPI_AZIENDA = [
  ["ragione_sociale", "Ragione sociale", true],
  ["indirizzo", "Indirizzo", true],
  ["partita_iva", "P.IVA", true],
  ["codice_fiscale", "Codice fiscale (= P.IVA per la S.r.l.)", true],
  ["email", "Email", true],
  ["telefono", "Telefono", true],
  ["attivita", "Attività", false],
  ["responsabile_haccp", "Responsabile HACCP", true],
  ["studio_consulenza", "Studio consulenza", true],
];

export function statoLibretto(scad) {
  if (!scad) return { txt: "libretto mancante", bg: "#f7e0db", fg: DANGER, peso: 0 };
  const giorni = Math.ceil((new Date(scad) - new Date()) / 86400000);
  if (giorni < 0) return { txt: "SCADUTO", bg: "#f7e0db", fg: DANGER, peso: 1 };
  if (giorni <= 30) return { txt: `scade tra ${giorni} gg`, bg: "#fbf0dd", fg: WARN, peso: 2 };
  return { txt: `valido fino al ${dataIt(scad)}`, bg: "#e7f0ea", fg: OK, peso: 3 };
}

export default function ImpostazioniPersonaleView() {
  const [operatori, setOperatori] = useState([]);
  const [valori, setValori] = useState({});
  const [loading, setLoading] = useState(true);
  const [salvando, setSalvando] = useState(null);
  const [pinPer, setPinPer] = useState(null); // operatore a cui si sta dando il PIN
  const [salvatoAlle, setSalvatoAlle] = useState({});
  const [sincronizzando, setSincronizzando] = useState(false);
  const [mostraNonInCarico, setMostraNonInCarico] = useState(false);

  const [azienda, setAzienda] = useState(null);
  const [azSaving, setAzSaving] = useState(false);
  const [azSalvatoAlle, setAzSalvatoAlle] = useState("");
  const setAz = (campo, val) => setAzienda((a) => ({ ...(a || {}), [campo]: val }));

  const caricaAzienda = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/azienda`);
      setAzienda(r.data || {});
    } catch (e) {
      apiError(e, "Impossibile caricare i dati azienda");
    }
  }, []);

  const salvaAzienda = async () => {
    setAzSaving(true);
    try {
      const r = await axios.put(`${API}/azienda`, azienda || {});
      setAzienda(r.data || {});
      setAzSalvatoAlle(oraIt(new Date().toISOString()));
      toast.success("Dati azienda salvati: aggiornati su tutti i PDF");
    } catch (e) {
      toast.error(apiError(e, "Errore nel salvataggio dei dati azienda"));
    } finally {
      setAzSaving(false);
    }
  };

  const carica = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/tablet-operatori`, { params: { tutti: 1 } });
      const lista = Array.isArray(r.data) ? r.data : [];
      setOperatori(lista);
      setValori((prev) => {
        const next = {};
        for (const d of lista) {
          if (!d.dipendente_id) continue;
          next[d.dipendente_id] = prev[d.dipendente_id] || {
            postazione: d.postazione || d.postazione_proposta || "",
            libretto_sanitario_scadenza: d.libretto_sanitario_scadenza || "",
          };
        }
        return next;
      });
    } catch (e) {
      toast.error(apiError(e, "Errore caricamento personale"));
    } finally {
      setLoading(false);
    }
  }, []);

  const riallinea = useCallback(async (notifica = true) => {
    setSincronizzando(true);
    try {
      const r = await axios.post(`${API}/tablet-operatori/sincronizza-hr`, {});
      const e = r.data || {};
      if (e.esito === "hr_non_configurato") toast.error("Anagrafica HR non raggiungibile");
      else if (notifica) toast.success(`Allineato all'anagrafica HR: ${e.creati || 0} nuovi, ${e.disattivati || 0} non più in carico`);
    } catch (e) {
      toast.error(apiError(e, "Allineamento non riuscito"));
    } finally {
      await carica();
      setSincronizzando(false);
    }
  }, [carica]);

  useEffect(() => { riallinea(false); caricaAzienda(); }, [riallinea, caricaAzienda]);

  const setCampo = (id, campo, val) =>
    setValori((s) => ({ ...s, [id]: { ...s[id], [campo]: val } }));

  const salva = async (d) => {
    setSalvando(d.dipendente_id);
    try {
      const r = await axios.patch(`${API}/tablet-operatori/${d.dipendente_id}`, valori[d.dipendente_id]);
      const quando = r.data?.salvato_alle || new Date().toISOString();
      setSalvatoAlle((s) => ({ ...s, [d.dipendente_id]: oraIt(quando) }));
      setOperatori((l) => l.map((o) => (o.dipendente_id === d.dipendente_id ? { ...o, ...valori[d.dipendente_id] } : o)));
      toast.success(`${d.cognome || d.nome} salvato`);
    } catch (e) {
      toast.error(apiError(e, "Errore salvataggio"));
    } finally {
      setSalvando(null);
    }
  };

  const inCarico = useMemo(() => operatori.filter((o) => o.in_carico !== false && o.ruolo !== "amministratore"), [operatori]);
  const amministratori = useMemo(() => operatori.filter((o) => o.in_carico !== false && o.ruolo === "amministratore"), [operatori]);
  const nonInCarico = useMemo(() => operatori.filter((o) => o.in_carico === false), [operatori]);

  // Il dato più urgente per primo: libretto mancante, scaduto, in scadenza, poi valido.
  const ordinati = useMemo(() => {
    const peso = (o) => statoLibretto((valori[o.dipendente_id] || {}).libretto_sanitario_scadenza || o.libretto_sanitario_scadenza).peso;
    return [...inCarico].sort((a, b) => peso(a) - peso(b) || String(a.nome).localeCompare(String(b.nome)));
  }, [inCarico, valori]);

  const riepilogo = useMemo(() => {
    let registrati = 0, inScadenza = 0, scaduti = 0, senzaPin = 0;
    for (const o of inCarico) {
      const scad = (valori[o.dipendente_id] || {}).libretto_sanitario_scadenza || o.libretto_sanitario_scadenza;
      if (scad) {
        registrati += 1;
        const st = statoLibretto(scad);
        if (st.peso === 1) scaduti += 1;
        if (st.peso === 2) inScadenza += 1;
      }
      if (!o.pin_impostato) senzaPin += 1;
    }
    return { operatori: inCarico.length, registrati, inScadenza, scaduti, senzaPin };
  }, [inCarico, valori]);

  const campiPdfVuoti = useMemo(
    () => (azienda ? CAMPI_AZIENDA.filter(([c, , inPdf]) => inPdf && !String(azienda[c] || "").trim()).map(([, l]) => l) : []),
    [azienda]
  );

  if (loading) return <div style={{ textAlign: "center", padding: 60, color: MUTED }}>Caricamento…</div>;

  const SchedaOperatore = ({ d }) => {
    const v = valori[d.dipendente_id] || {};
    const badge = statoLibretto(v.libretto_sanitario_scadenza);
    const cognome = d.cognome || d.nome;
    return (
      <div style={{ border: `1px solid ${LINE}`, borderRadius: 14, padding: "14px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: SALVIA }}>{d.nome}</div>
            <div style={{ fontSize: 12, color: MUTED, marginTop: 2 }}>
              {d.mansione ? d.mansione : <span style={{ color: WARN }}>mansione non inserita in HR</span>}
              {d.ruolo === "amministratore" ? " · amministratore" : ""}
            </div>
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            <span style={pill(badge.bg, badge.fg)}>{badge.txt}</span>
            {d.pin_impostato
              ? <span style={pill("#e7f0ea", OK)}><KeyRound size={11} style={{ verticalAlign: "-1px" }} /> PIN impostato</span>
              : <span style={pill("#fbf0dd", WARN)}><KeyRound size={11} style={{ verticalAlign: "-1px" }} /> PIN da impostare</span>}
            {d.dipendente_id && (
              <button type="button" onClick={() => setPinPer(d)}
                style={{ ...pill("#f4f8f3", SALVIA), border: `1px solid ${LINE}`, cursor: "pointer", minHeight: 44, display: "inline-flex", alignItems: "center", gap: 4 }}>
                <KeyRound size={12} /> {d.pin_impostato ? "Cambia PIN" : "Imposta PIN"}
              </button>
            )}
            <a href={HR_ANAGRAFICA + (d.dipendente_id ? `?dip=${encodeURIComponent(d.dipendente_id)}` : "")} style={{ ...pill("#f4f8f3", SALVIA), textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4 }}>
              scheda HR <ExternalLink size={11} />
            </a>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10, alignItems: "end" }}>
          <div>
            <label htmlFor={`postazione-${d.dipendente_id}`} style={{ fontSize: 11, color: MUTED, fontWeight: 600 }}>
              Postazione{!d.postazione && d.postazione_proposta ? <span style={{ color: WARN }}> · proposta dal ruolo HR</span> : null}
            </label>
            <select id={`postazione-${d.dipendente_id}`} value={v.postazione || ""} onChange={(e) => setCampo(d.dipendente_id, "postazione", e.target.value)}
              style={{ ...inp, width: "100%", background: "#fff" }}>
              <option value="">—</option>
              {POSTAZIONI.map((p) => <option key={p} value={p}>{cap(p)}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor={`libretto-${d.dipendente_id}`} style={{ fontSize: 11, color: MUTED, fontWeight: 600 }}>
              <IdCard size={11} style={{ verticalAlign: "middle" }} aria-hidden="true" /> Scadenza libretto sanitario
            </label>
            <input id={`libretto-${d.dipendente_id}`} type="date" value={v.libretto_sanitario_scadenza || ""} onChange={(e) => setCampo(d.dipendente_id, "libretto_sanitario_scadenza", e.target.value)}
              style={{ ...inp, width: "100%" }} />
          </div>
          <div>
            <button onClick={() => salva(d)} disabled={salvando === d.dipendente_id} style={{ ...btn(SAGE), width: "100%", opacity: salvando === d.dipendente_id ? 0.6 : 1 }}>
              <Save size={15} /> {salvando === d.dipendente_id ? "Salvo…" : `Salva ${cognome}`}
            </button>
            {salvatoAlle[d.dipendente_id] && <div style={{ fontSize: 11, color: OK, marginTop: 4, textAlign: "center" }}>Salvato alle {salvatoAlle[d.dipendente_id]}</div>}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div style={{ padding: 16, maxWidth: 900, margin: "0 auto", fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
        <Users size={22} color={SAGE} />
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: SALVIA, fontFamily: "\'Plus Jakarta Sans\', -apple-system, BlinkMacSystemFont, \'Segoe UI\', system-ui, sans-serif" }}>Personale HACCP</h2>
      </div>

      {/* ── 1) Personale e libretti sanitari ───────────── */}
      <section style={sezione}>
        <h3 style={titoloSez}>
          <IdCard size={18} color={SAGE} /> Personale e libretti sanitari
        </h3>
        <p style={{ margin: "0 0 10px", fontSize: 13, color: MUTED }}>
          Gli operatori sono i dipendenti in forza nell'anagrafica HR: nome, ruolo, stato e PIN si modificano lì
          (<a href={HR_ANAGRAFICA} style={{ color: SAGE, fontWeight: 700 }}>apri l'anagrafica HR</a>). Qui solo postazione e libretto sanitario;
          gli avvisi di scadenza compaiono sulla campanella entro 30 giorni.
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 14 }}>
          <span style={pill("#f4f8f3", SALVIA)}>{riepilogo.operatori} operatori</span>
          <span style={pill(riepilogo.registrati === riepilogo.operatori ? "#e7f0ea" : "#fbf0dd", riepilogo.registrati === riepilogo.operatori ? OK : WARN)}>
            {riepilogo.registrati} libretti registrati
          </span>
          <span style={pill(riepilogo.inScadenza ? "#fbf0dd" : "#f4f8f3", riepilogo.inScadenza ? WARN : SALVIA)}>{riepilogo.inScadenza} in scadenza</span>
          <span style={pill(riepilogo.scaduti ? "#f7e0db" : "#f4f8f3", riepilogo.scaduti ? DANGER : SALVIA)}>{riepilogo.scaduti} scaduti</span>
          {riepilogo.senzaPin > 0 && <span style={pill("#fbf0dd", WARN)}>{riepilogo.senzaPin} senza PIN (impostalo nella scheda HR)</span>}
          <button onClick={() => riallinea()} disabled={sincronizzando} title="Rilegge subito l'anagrafica HR (succede comunque da solo ogni 10 minuti)"
            style={{ ...btn("transparent"), color: SALVIA, border: `1px solid ${LINE}`, marginLeft: "auto", padding: "8px 12px", opacity: sincronizzando ? 0.6 : 1 }}>
            <RefreshCw size={14} /> {sincronizzando ? "Allineo…" : "Riallinea con HR"}
          </button>
        </div>
        {ordinati.length === 0 ? (
          <div style={{ color: MUTED, fontSize: 13 }}>Nessun operatore in forza nell'anagrafica HR.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {ordinati.map((d) => <SchedaOperatore key={d.dipendente_id} d={d} />)}
          </div>
        )}
        {amministratori.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: MUTED, marginBottom: 8 }}>AMMINISTRATORI (firmano col proprio PIN personale della scheda HR)</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {amministratori.map((d) => <SchedaOperatore key={d.dipendente_id} d={d} />)}
            </div>
          </div>
        )}
      </section>

      {/* ── 2) Non più in carico (da HR) ─────────────────── */}
      <section style={{ ...sezione, padding: "12px 18px" }}>
        <button onClick={() => setMostraNonInCarico((v) => !v)}
          style={{ ...btn("transparent"), color: SALVIA, justifyContent: "space-between", width: "100%", padding: "6px 0" }}>
          <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 15, fontFamily: "\'Plus Jakarta Sans\', -apple-system, BlinkMacSystemFont, \'Segoe UI\', system-ui, sans-serif" }}>
            Non più in carico <span style={pill("#f4f8f3", SALVIA)}>{nonInCarico.length}</span>
          </span>
          {mostraNonInCarico ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </button>
        {mostraNonInCarico && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
            <p style={{ margin: 0, fontSize: 12.5, color: MUTED }}>
              Cessati nell'anagrafica HR o nomi storici di Lotti senza una persona in HR. Mai cancellati: i lotti, le sanificazioni e le
              temperature già firmate restano a loro nome. Per rimettere qualcuno in carico si riattiva in HR.
            </p>
            {nonInCarico.length === 0 && <div style={{ color: MUTED, fontSize: 13 }}>Nessuno.</div>}
            {nonInCarico.map((o, index) => (
              <div key={o.dipendente_id || `storico-${index}`} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8, padding: "10px 12px", border: `1px solid ${LINE}`, borderRadius: 10 }}>
                <div>
                  <div style={{ fontWeight: 700, color: SALVIA }}>{o.nome}</div>
                  <div style={{ fontSize: 11.5, color: MUTED }}>
                    {o.hr_stato === "non_in_hr"
                      ? "nome storico di Lotti, non presente nell'anagrafica HR"
                      : o.data_fine_rapporto
                        ? `non più in carico dal ${dataIt(o.data_fine_rapporto)}${o.motivo_fine_rapporto_etichetta ? ` · ${o.motivo_fine_rapporto_etichetta}` : ""} (da HR)`
                        : "cessato in HR"}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {o.hr_stato !== "non_in_hr" && !o.data_fine_rapporto && <span style={pill("#fbf0dd", WARN)}>data da inserire in HR</span>}
                  <span style={pill("#f4f8f3", MUTED)}>PIN disattivato</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── 3) Dati azienda · Fatturazione elettronica ──── */}
      <section style={sezione}>
        <h3 style={titoloSez}><IdCard size={18} color={SAGE} /> Dati azienda · Fatturazione elettronica</h3>
        <p style={{ margin: "0 0 12px", fontSize: 12.5, color: MUTED }}>
          Usati in tutti i PDF (listino, report HACCP, manuale, etichette lotto, ordini). Una modifica qui si riflette ovunque.
        </p>

        {azienda === null ? (
          <div style={{ color: MUTED, fontSize: 13 }}>Caricamento…</div>
        ) : (
          <>
            {campiPdfVuoti.length > 0 && (
              <div style={{ display: "flex", gap: 8, alignItems: "flex-start", background: "#f7e0db", color: "#8f3829", borderRadius: 10, padding: "10px 12px", marginBottom: 12, fontSize: 13 }}>
                <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
                <div><b>Campi vuoti che finiscono nei PDF:</b> {campiPdfVuoti.join(", ")}.</div>
              </div>
            )}
            <div style={{ background: "#f4f8f3", border: `1px solid ${LINE}`, borderRadius: 10, padding: "12px 14px", marginBottom: 14 }}>
              <label htmlFor="azienda-codice-destinatario" style={{ display: "block", fontSize: 12, fontWeight: 700, color: SALVIA, marginBottom: 5 }}>
                Codice destinatario SDI
              </label>
              <input
                id="azienda-codice-destinatario"
                value={azienda.codice_destinatario || ""}
                onChange={(e) => setAz("codice_destinatario", e.target.value.toUpperCase())}
                placeholder="USAL8PV"
                maxLength={7}
                style={{ ...inp, width: 180, textTransform: "uppercase", fontWeight: 700, letterSpacing: 1 }}
              />
              <div style={{ fontSize: 11.5, color: MUTED, marginTop: 6 }}>
                Cambialo quando cambi gestore dell'interscambio fatturazione: aggiorna i PDF.
              </div>
            </div>

            {(() => {
              const attivo = ["1", "true", "si", "sì", "x"].includes(String(azienda.controllo_visivo_responsabile || "").trim().toLowerCase());
              return (
                <div style={{ background: "#f4f8f3", border: `1px solid ${LINE}`, borderRadius: 10, padding: "12px 14px", marginBottom: 14 }}>
                  <label style={{ display: "flex", gap: 10, alignItems: "flex-start", cursor: "pointer", minHeight: 44 }}>
                    <input type="checkbox" checked={attivo}
                      onChange={(e) => setAz("controllo_visivo_responsabile", e.target.checked ? "si" : "no")}
                      style={{ width: 22, height: 22, marginTop: 2, accentColor: SAGE }} />
                    <span>
                      <span style={{ display: "block", fontSize: 13, fontWeight: 700, color: SALVIA }}>
                        Il responsabile HACCP fa di persona il controllo visivo di frigoriferi e congelatori
                      </span>
                      <span style={{ display: "block", fontSize: 11.5, color: MUTED, marginTop: 4 }}>
                        Ogni mattina alle 07:00 si aprono le caselle del giorno. Finito il giro, nelle pagine Temperature tocchi
                        «Giro fatto: tutto conforme» col tuo PIN: il registro annota l'esito firmato da te, all'ora vera, senza
                        scrivere numeri. Una temperatura fuori soglia si scrive a mano col valore vero.
                      </span>
                    </span>
                  </label>
                </div>
              );
            })()}

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 12 }}>
              {CAMPI_AZIENDA.map(([campo, etichetta, inPdf]) => {
                const vuoto = inPdf && !String(azienda[campo] || "").trim();
                return (
                  <div key={campo}>
                    <label htmlFor={`azienda-${campo}`} style={{ display: "block", fontSize: 12, fontWeight: 600, color: vuoto ? DANGER : SALVIA, marginBottom: 4 }}>
                      {etichetta}{vuoto ? " · vuoto, entra nei PDF" : ""}
                    </label>
                    <input
                      id={`azienda-${campo}`}
                      value={azienda[campo] || ""}
                      onChange={(e) => setAz(campo, e.target.value)}
                      style={{ ...inp, width: "100%", borderColor: vuoto ? DANGER : LINE }}
                    />
                  </div>
                );
              })}
            </div>

            <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <button onClick={salvaAzienda} disabled={azSaving} style={{ ...btn(SAGE), opacity: azSaving ? 0.6 : 1 }}>
                <Save size={15} /> {azSaving ? "Salvo…" : "Salva dati azienda"}
              </button>
              {azSalvatoAlle && <span style={{ fontSize: 12, color: OK }}>Salvato alle {azSalvatoAlle}</span>}
            </div>
          </>
        )}
      </section>

      {pinPer && (
        <PinModal
          title={`PIN di ${pinPer.nome}`}
          subtitle="4-8 cifre. Vale per il portale HR e per firmare in Lotti."
          color={SAGE}
          onCancel={() => setPinPer(null)}
          onVerify={async (pin) => {
            try {
              await axios.post(`${API}/tablet-operatori/${encodeURIComponent(pinPer.dipendente_id)}/pin`, { pin });
            } catch (e) {
              throw new Error(apiError(e, "PIN non salvato"));
            }
            toast.success(`PIN di ${pinPer.nome} salvato`);
            setOperatori((l) => l.map((o) => (o.dipendente_id === pinPer.dipendente_id ? { ...o, pin_impostato: true } : o)));
            setPinPer(null);
          }}
        />
      )}

      {/* ── 4) Stampanti ───────────── */}
      <section style={sezione}>
        <h3 style={titoloSez}><Printer size={18} color={SAGE} /> Stampanti</h3>
        <p style={{ margin: "0 0 14px", fontSize: 13, color: MUTED }}>
          Configurazione stampanti per reparto (banco, magazzino, etichette).
        </p>
        <StampantiConfigView />
      </section>
    </div>
  );
}
