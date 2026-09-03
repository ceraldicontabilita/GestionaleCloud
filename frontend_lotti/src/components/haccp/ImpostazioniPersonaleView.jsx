/**
 * ImpostazioniPersonaleView.jsx — gestione personale, PIN e onboarding dipendenti.
 *
 * Tre sezioni:
 *  1) PIN operatori — 25/07/2026 i PIN NON sono più leggibili da nessuno,
 *     nemmeno da qui: non esistono più in chiaro nel database. Qui si vede solo
 *     CHI ha un PIN impostato e si può assegnarne uno nuovo («Reimposta PIN»),
 *     che revoca subito il precedente.
 *  2) Nuovi dipendenti dal gestionale — legge i dipendenti registrati su gestionalecloud
 *     non ancora abilitati al tablet e consente di assegnare PIN + postazione (o ignorarli).
 *  3) Personale e libretti sanitari — mansione, postazione, scadenza libretto (con alert).
 */
import { useState, useEffect, useCallback } from "react";
import { apiError } from "../../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import { IdCard, Save, Users, KeyRound, UserPlus, RefreshCw, UserX, Printer } from "lucide-react";
import { API } from "../../utils/constants";
import StampantiConfigView from "./StampantiConfigView";

const SAGE = "#5b7a6b";
const NAVY = "#3f5a4e";
const CARD = "#fffefb";
const LINE = "#e6e0d4";

const POSTAZIONI = ["laboratorio", "pasticceria", "sala", "bar"];
const MANSIONI = [
  "Pasticcere", "Aiuto pasticcere", "Rosticcere", "Fornaio",
  "Banconista", "Barista", "Cameriere", "Cassiere", "Responsabile", "Magazziniere",
];

const inp = { padding: "9px 10px", borderRadius: 8, border: `1px solid ${LINE}`, fontSize: 14, fontFamily: "inherit", boxSizing: "border-box" };
const btn = (bg) => ({ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, padding: "10px 14px", borderRadius: 9, border: "none", background: bg, color: "#fff", fontWeight: 700, fontSize: 13, cursor: "pointer" });
const sezione = { background: CARD, border: `1px solid ${LINE}`, borderRadius: 16, padding: "16px 18px", marginBottom: 18 };
const titoloSez = { display: "flex", alignItems: "center", gap: 9, margin: "0 0 4px", fontSize: 17, fontWeight: 700, color: NAVY, fontFamily: "'Fraunces', Georgia, serif" };

export default function ImpostazioniPersonaleView() {
  const [dipendenti, setDipendenti] = useState([]);
  const [valori, setValori] = useState({});
  const [loading, setLoading] = useState(true);
  const [salvando, setSalvando] = useState(null);

  // Sezione PIN
  const [pinInput, setPinInput] = useState("");
  const [pinSbloccato, setPinSbloccato] = useState(false);
  const [pinList, setPinList] = useState([]);
  const [sbloccando, setSbloccando] = useState(false);
  const [resetVal, setResetVal] = useState({});
  const [resetting, setResetting] = useState(null);

  // Sezione nuovi dipendenti
  const [nuovi, setNuovi] = useState([]);
  const [loadingNuovi, setLoadingNuovi] = useState(true);
  const [abilVal, setAbilVal] = useState({});
  const [abilitando, setAbilitando] = useState(null);

  // Sezione dati azienda / fatturazione elettronica
  const [azienda, setAzienda] = useState(null);
  const [azSaving, setAzSaving] = useState(false);
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
      toast.success("Dati azienda salvati — aggiornati su tutti i PDF");
    } catch (e) {
      apiError(e, "Errore nel salvataggio dei dati azienda");
    } finally {
      setAzSaving(false);
    }
  };

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/tablet-operatori`);
      const lista = (r.data || []).filter((d) => d.ruolo !== "amministratore");
      setDipendenti(lista);
      const init = {};
      for (const d of lista) {
        init[d.id] = {
          mansione: d.mansione || "",
          postazione: d.postazione || "",
          libretto_sanitario_scadenza: d.libretto_sanitario_scadenza || "",
        };
      }
      setValori(init);
    } catch {
      toast.error("Errore caricamento dipendenti");
    } finally {
      setLoading(false);
    }
  }, []);

  const caricaNuovi = useCallback(async () => {
    setLoadingNuovi(true);
    try {
      const r = await axios.get(`${API}/tablet-operatori/nuovi-dipendenti`);
      setNuovi(r.data?.nuovi || []);
    } catch {
      setNuovi([]);
    } finally {
      setLoadingNuovi(false);
    }
  }, []);

  useEffect(() => { carica(); caricaNuovi(); caricaAzienda(); }, [carica, caricaNuovi, caricaAzienda]);

  const setCampo = (id, campo, val) =>
    setValori((s) => ({ ...s, [id]: { ...s[id], [campo]: val } }));

  const salva = async (id) => {
    setSalvando(id);
    try {
      await axios.patch(`${API}/tablet-operatori/${id}`, valori[id]);
      toast.success("Dati salvati");
      carica();
    } catch (e) {
      toast.error(apiError(e, "Errore salvataggio"));
    } finally {
      setSalvando(null);
    }
  };

  // ── PIN ──────────────────────────────────────────────
  const sblocca = async () => {
    const pin = pinInput.trim();
    if (pin.length < 4) { toast.error("Inserisci il PIN amministratore"); return; }
    setSbloccando(true);
    try {
      const r = await axios.post(`${API}/tablet-operatori/pin-operatori`, { pin });
      setPinList(r.data?.operatori || []);
      setPinSbloccato(true);
      setPinInput("");
    } catch (e) {
      toast.error(apiError(e, "PIN amministratore errato"));
    } finally {
      setSbloccando(false);
    }
  };

  const resetPin = async (id) => {
    const np = (resetVal[id] || "").trim();
    if (np.length < 4) { toast.error("PIN minimo 4 cifre"); return; }
    setResetting(id);
    try {
      const r = await axios.post(`${API}/tablet-operatori/${id}/reimposta-pin`, { pin_nuovo: np });
      const aggiornati = new Set(r.data?.operatori_aggiornati || [id]);
      setPinList((l) => l.map((o) => (aggiornati.has(o.id) ? { ...o, pin_impostato: true } : o)));
      setResetVal((s) => ({ ...s, [id]: "" }));
      toast.success(r.data?.messaggio || "PIN aggiornato: da adesso vale solo quello nuovo");
    } catch (e) {
      toast.error(apiError(e, "Errore aggiornamento PIN"));
    } finally {
      setResetting(null);
    }
  };

  // ── Nuovi dipendenti ─────────────────────────────────
  const setAbil = (cf, campo, val) =>
    setAbilVal((s) => ({ ...s, [cf]: { ...s[cf], [campo]: val } }));

  const chiaveDipendente = (dip) => dip.gestionale_dipendente_id || dip.codice_fiscale;

  const abilita = async (dip) => {
    const dipKey = chiaveDipendente(dip);
    const f = abilVal[dipKey] || {};
    const pin = (f.pin || "").trim();
    if (pin.length < 4) { toast.error("Imposta un PIN di almeno 4 cifre"); return; }
    setAbilitando(dipKey);
    try {
      await axios.post(`${API}/tablet-operatori/abilita-dipendente`, {
        gestionale_dipendente_id: dip.gestionale_dipendente_id,
        codice_fiscale: dip.codice_fiscale,
        nome: dip.nome,
        cognome: dip.cognome,
        mansione: dip.mansione || "",
        postazione: f.postazione || "",
        pin,
      });
      toast.success(`${dip.nome} ${dip.cognome} abilitato`);
      caricaNuovi();
      carica();
    } catch (e) {
      toast.error(apiError(e, "Errore abilitazione"));
    } finally {
      setAbilitando(null);
    }
  };

  const collegaEsistente = async (dip) => {
    const candidato = dip.candidato_operatore;
    if (!candidato?.id) return;
    const dipKey = chiaveDipendente(dip);
    setAbilitando(dipKey);
    try {
      await axios.post(`${API}/tablet-operatori/collega-dipendente`, {
        operatore_id: candidato.id,
        gestionale_dipendente_id: dip.gestionale_dipendente_id,
        codice_fiscale: dip.codice_fiscale || "",
      });
      toast.success(`${candidato.nome} collegato al gestionale`);
      await caricaNuovi();
      await carica();
    } catch (e) {
      toast.error(apiError(e, "Collegamento non riuscito"));
    } finally {
      setAbilitando(null);
    }
  };

  const ignora = async (dip) => {
    try {
      await axios.post(`${API}/tablet-operatori/ignora-dipendente`, {
        codice_fiscale: dip.codice_fiscale,
        gestionale_dipendente_id: dip.gestionale_dipendente_id,
      });
      setNuovi((l) => l.filter((x) => x.gestionale_dipendente_id !== dip.gestionale_dipendente_id));
      toast.success("Dipendente ignorato");
    } catch (e) {
      toast.error(apiError(e, "Errore"));
    }
  };

  const statoLibretto = (scad) => {
    if (!scad) return null;
    const giorni = Math.ceil((new Date(scad) - new Date()) / 86400000);
    if (giorni < 0) return { txt: "SCADUTO", bg: "#f7e0db", fg: "#d35f4e" };
    if (giorni <= 30) return { txt: `scade tra ${giorni}gg`, bg: "#fbf0dd", fg: "#9c6a32" };
    return { txt: "valido", bg: "#e7f0ea", fg: "#3d8168" };
  };

  if (loading) return <div style={{ textAlign: "center", padding: 60, color: "#9aa593" }}>Caricamento…</div>;

  return (
    <div style={{ padding: 16, maxWidth: 900, margin: "0 auto", fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
        <Users size={22} color={SAGE} />
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: NAVY, fontFamily: "'Fraunces', Georgia, serif" }}>Operatori e personale</h2>
      </div>

      {/* ── 0) Dati azienda · Fatturazione elettronica ──── */}
      <section style={sezione}>
        <h3 style={titoloSez}><IdCard size={18} color={SAGE} /> Dati azienda · Fatturazione elettronica</h3>
        <p style={{ margin: "0 0 12px", fontSize: 12.5, color: "#9aa593" }}>
          Usati in tutti i PDF (listino, report HACCP, manuale, etichette lotto, ordini). Una modifica qui si riflette ovunque.
        </p>

        {azienda === null ? (
          <div style={{ color: "#9aa593", fontSize: 13 }}>Caricamento…</div>
        ) : (
          <>
            <div style={{ background: "#f4f8f3", border: `1px solid ${LINE}`, borderRadius: 10, padding: "12px 14px", marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: NAVY, marginBottom: 5 }}>
                Codice destinatario SDI
              </label>
              <input
                value={azienda.codice_destinatario || ""}
                onChange={(e) => setAz("codice_destinatario", e.target.value.toUpperCase())}
                placeholder="USAL8PV"
                maxLength={7}
                style={{ ...inp, width: 180, textTransform: "uppercase", fontWeight: 700, letterSpacing: 1 }}
              />
              <div style={{ fontSize: 11.5, color: "#9aa593", marginTop: 6 }}>
                Cambialo quando cambi gestore dell'interscambio fatturazione: aggiorna i PDF.
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 12 }}>
              {[
                ["ragione_sociale", "Ragione sociale"],
                ["indirizzo", "Indirizzo"],
                ["partita_iva", "P.IVA"],
                ["codice_fiscale", "Codice fiscale"],
                ["email", "Email"],
                ["telefono", "Telefono"],
                ["attivita", "Attività"],
                ["responsabile_haccp", "Responsabile HACCP"],
                ["studio_consulenza", "Studio consulenza"],
              ].map(([campo, etichetta]) => (
                <div key={campo}>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: NAVY, marginBottom: 4 }}>{etichetta}</label>
                  <input
                    value={azienda[campo] || ""}
                    onChange={(e) => setAz(campo, e.target.value)}
                    style={{ ...inp, width: "100%" }}
                  />
                </div>
              ))}
            </div>

            <div style={{ marginTop: 14 }}>
              <button onClick={salvaAzienda} disabled={azSaving} style={{ ...btn(SAGE), opacity: azSaving ? 0.6 : 1 }}>
                <Save size={15} /> {azSaving ? "Salvo…" : "Salva dati azienda"}
              </button>
            </div>
          </>
        )}
      </section>

      {/* ── 1) PIN operatori ───────────────────────────── */}
      <section style={sezione}>
        <h3 style={titoloSez}><KeyRound size={18} color={SAGE} /> PIN operatori</h3>
        {!pinSbloccato ? (
          <>
            <p style={{ margin: "0 0 12px", fontSize: 13, color: "#9aa593" }}>
              Inserisci il PIN amministratore per gestire i PIN degli operatori.
              I PIN non sono leggibili da nessuno, nemmeno da qui: se un dipendente
              lo dimentica gliene assegni uno nuovo con un tocco, e il vecchio smette
              subito di funzionare.
            </p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <input type="password" inputMode="numeric" value={pinInput}
                onChange={(e) => setPinInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && sblocca()}
                placeholder="PIN amministratore"
                style={{ ...inp, flex: "1 1 200px" }} />
              <button onClick={sblocca} disabled={sbloccando} style={{ ...btn(SAGE), opacity: sbloccando ? 0.6 : 1 }}>
                <KeyRound size={15} /> {sbloccando ? "Verifico…" : "Gestisci PIN"}
              </button>
            </div>
          </>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {pinList.map((o) => (
              <div key={o.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10, padding: "10px 12px", border: `1px solid ${LINE}`, borderRadius: 10 }}>
                <div style={{ minWidth: 160 }}>
                  <div style={{ fontWeight: 700, color: NAVY }}>{o.nome} {o.cognome || ""}</div>
                  <div style={{ fontSize: 11, color: "#9aa593" }}>{o.ruolo === "amministratore" ? "Amministratore" : (o.postazione || "—")}</div>
                </div>
                <div style={{ minWidth: 110 }}>
                  {o.pin_impostato
                    ? <span style={{ fontSize: 12, fontWeight: 700, color: "#3d8168", background: "#e7f0ea", borderRadius: 6, padding: "3px 9px" }}>{o.pin_condiviso ? "PIN condiviso" : "PIN impostato"}</span>
                    : <span style={{ fontSize: 12, fontWeight: 700, color: "#9c6a32", background: "#fbf0dd", borderRadius: 6, padding: "3px 9px" }}>PIN da assegnare</span>}
                </div>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <input inputMode="numeric" value={resetVal[o.id] || ""} onChange={(e) => setResetVal((s) => ({ ...s, [o.id]: e.target.value }))}
                    placeholder="nuovo PIN" style={{ ...inp, width: 110 }} />
                  <button onClick={() => resetPin(o.id)} disabled={resetting === o.id}
                    style={{ ...btn(NAVY), padding: "9px 11px", opacity: resetting === o.id ? 0.6 : 1 }}>
                    <RefreshCw size={14} /> {resetting === o.id ? "…" : (o.pin_condiviso ? "Imposta PIN condiviso" : "Reimposta PIN")}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── 2) Nuovi dipendenti dal gestionale ─────────── */}
      <section style={sezione}>
        <h3 style={titoloSez}>
          <UserPlus size={18} color={SAGE} /> Nuovi dipendenti dal gestionale
          {!loadingNuovi && nuovi.length > 0 && (
            <span style={{ fontSize: 12, fontWeight: 800, background: SAGE, color: "#fff", borderRadius: 20, padding: "2px 9px", fontFamily: "inherit" }}>{nuovi.length}</span>
          )}
        </h3>
        <p style={{ margin: "0 0 12px", fontSize: 13, color: "#9aa593" }}>
          Per chi usa già Lotti compare «Collega esistente»: conserva PIN e storico. Per una persona nuova assegna un PIN e premi «Abilita».
        </p>
        {loadingNuovi ? (
          <div style={{ color: "#9aa593", fontSize: 13 }}>Caricamento…</div>
        ) : nuovi.length === 0 ? (
          <div style={{ color: "#9aa593", fontSize: 13 }}>Nessun nuovo dipendente da abilitare.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {nuovi.map((dip) => {
              const dipKey = chiaveDipendente(dip);
              const f = abilVal[dipKey] || {};
              return (
                <div key={dipKey} style={{ border: `1px solid ${LINE}`, borderRadius: 12, padding: "12px 14px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
                    <div style={{ fontWeight: 700, color: NAVY, fontSize: 15 }}>
                      {dip.nome} {dip.cognome} {dip.mansione ? <span style={{ fontWeight: 500, color: "#9aa593", fontSize: 13 }}>· {dip.mansione}</span> : null}
                    </div>
                    <div style={{ fontSize: 11, color: "#9aa593", fontFamily: "monospace" }}>{dip.codice_fiscale || "senza CF"}</div>
                  </div>
                  {dip.candidato_operatore && (
                    <div style={{ margin: "0 0 10px", padding: "9px 11px", borderRadius: 10, background: "#edf5f0", color: "#315e4b", fontSize: 12, fontWeight: 700 }}>
                      Possibile corrispondenza in Lotti: {dip.candidato_operatore.nome}
                      <button onClick={() => collegaEsistente(dip)} disabled={abilitando === dipKey}
                        style={{ ...btn(SAGE), marginLeft: 10, padding: "7px 11px", opacity: abilitando === dipKey ? 0.6 : 1 }}>
                        Collega esistente
                      </button>
                    </div>
                  )}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 8, alignItems: "end" }}>
                    <div>
                      <label style={{ fontSize: 11, color: "#9aa593", fontWeight: 600 }}>PIN</label>
                      <input inputMode="numeric" value={f.pin || ""} onChange={(e) => setAbil(dipKey, "pin", e.target.value)}
                        placeholder="min 4 cifre" style={{ ...inp, width: "100%" }} />
                    </div>
                    <div>
                      <label style={{ fontSize: 11, color: "#9aa593", fontWeight: 600 }}>Postazione</label>
                      <select value={f.postazione || ""} onChange={(e) => setAbil(dipKey, "postazione", e.target.value)}
                        style={{ ...inp, width: "100%", background: "#fff" }}>
                        <option value="">—</option>
                        {POSTAZIONI.map((p) => <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>)}
                      </select>
                    </div>
                    <button onClick={() => abilita(dip)} disabled={abilitando === dipKey}
                      style={{ ...btn(SAGE), opacity: abilitando === dipKey ? 0.6 : 1 }}>
                      <UserPlus size={15} /> {abilitando === dipKey ? "…" : "Abilita"}
                    </button>
                    <button onClick={() => ignora(dip)} title="Non proporlo più"
                      style={{ ...btn("transparent"), color: "#b0563f", border: `1px solid ${LINE}` }}>
                      <UserX size={15} /> Ignora
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* ── 3) Personale e libretti sanitari ───────────── */}
      <section style={sezione}>
        <h3 style={titoloSez}><IdCard size={18} color={SAGE} /> Personale e libretti sanitari</h3>
        <p style={{ margin: "0 0 14px", fontSize: 13, color: "#9aa593" }}>
          Mansione, postazione e scadenza del libretto sanitario. Gli avvisi di scadenza compaiono sulla campanella entro 30 giorni.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {dipendenti.map((d) => {
            const v = valori[d.id] || {};
            const badge = statoLibretto(v.libretto_sanitario_scadenza);
            return (
              <div key={d.id} style={{ border: `1px solid ${LINE}`, borderRadius: 14, padding: "14px 16px" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
                  <div style={{ fontSize: 16, fontWeight: 700, color: NAVY }}>{d.nome} {d.cognome || ""}</div>
                  {badge && <span style={{ fontSize: 11, fontWeight: 700, background: badge.bg, color: badge.fg, borderRadius: 6, padding: "3px 9px" }}>{badge.txt}</span>}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10, alignItems: "end" }}>
                  <div>
                    <label style={{ fontSize: 11, color: "#9aa593", fontWeight: 600 }}>Mansione</label>
                    <input list={`mansioni-${d.id}`} value={v.mansione} onChange={(e) => setCampo(d.id, "mansione", e.target.value)}
                      placeholder="es. Pasticcere" style={{ ...inp, width: "100%" }} />
                    <datalist id={`mansioni-${d.id}`}>
                      {MANSIONI.map((m) => <option key={m} value={m} />)}
                    </datalist>
                  </div>
                  <div>
                    <label style={{ fontSize: 11, color: "#9aa593", fontWeight: 600 }}>Postazione</label>
                    <select value={v.postazione} onChange={(e) => setCampo(d.id, "postazione", e.target.value)}
                      style={{ ...inp, width: "100%", background: "#fff" }}>
                      <option value="">—</option>
                      {POSTAZIONI.map((p) => <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>)}
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: 11, color: "#9aa593", fontWeight: 600 }}>
                      <IdCard size={11} style={{ verticalAlign: "middle" }} /> Scadenza libretto
                    </label>
                    <input type="date" value={v.libretto_sanitario_scadenza} onChange={(e) => setCampo(d.id, "libretto_sanitario_scadenza", e.target.value)}
                      style={{ ...inp, width: "100%" }} />
                  </div>
                  <button onClick={() => salva(d.id)} disabled={salvando === d.id} style={{ ...btn(SAGE), opacity: salvando === d.id ? 0.6 : 1 }}>
                    <Save size={15} /> {salvando === d.id ? "Salvo…" : "Salva"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── 4) Stampanti ───────────── */}
      <section style={sezione}>
        <h3 style={titoloSez}><Printer size={18} color={SAGE} /> Stampanti</h3>
        <p style={{ margin: "0 0 14px", fontSize: 13, color: "#9aa593" }}>
          Configurazione stampanti per reparto (banco, magazzino, etichette).
        </p>
        <StampantiConfigView />
      </section>
    </div>
  );
}
