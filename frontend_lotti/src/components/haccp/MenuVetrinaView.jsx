// «In menu» — il contenitore visivo dei prodotti da vendere (19/09/2026).
//
// Dettatura del titolare: «prendere ad esempio la ricetta della sfogliatella ed
// inserirla in menu dopo aver spuntato "inserisci in menu", quindi visualizzo
// immagine, breve descrizione, prezzo tavolo, allergeni se presenti
// evidenziati, e la categoria dove inserirla. Quindi il menu Lotti deve essere
// un contenitore visivo dei prodotti da vendere.»
//
// Qui NON si modifica la ricetta: si guarda com'è messa e, se qualcosa manca,
// si apre la stessa scheda di sempre (FormRicetta, pagina Produzione) con il
// meccanismo già in uso — `sessionStorage("apri_ricetta_id")` + navigazione.
//
// Il ragionamento (prezzo esposto, categoria di destinazione, cosa manca) sta
// tutto in `utils/menuVetrina.js`, gemello del ponte backend: qui c'è solo la
// presentazione.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import {
  AlertTriangle, ChevronRight, Image as ImageIcon, Loader2, Pencil, RefreshCw,
  ShieldAlert, Tags, UploadCloud, Utensils,
} from "lucide-react";
import { conferma } from "../../utils/conferma";
import { isAdmin } from "../../auth";
import { toast } from "./backoffice/toastBackoffice";
import { useCategorieMenu } from "../../hooks/useCategorieMenu";
import {
  ORDINE_PROBLEMI, PROBLEMI, allergeniRicetta, destinazioneMenu, fotoRicetta,
  ordinaPerUrgenza, prezzoPerMenu, problemiRicettaMenu, riepilogoProblemi, ricetteInMenu,
} from "../../utils/menuVetrina";

const API = process.env.REACT_APP_LOTTI_BACKEND_URL + "/api";
const BACKEND = process.env.REACT_APP_LOTTI_BACKEND_URL || "";
const fotoSrc = (u) => (u ? (/^https?:/.test(u) ? u : BACKEND + u) : "");

const euro = (n) => (n == null ? "—" : `${Number(n).toFixed(2)} €`);

// Colori semantici caldi del design system: ogni tono ha SEMPRE anche il testo.
const TONO = {
  pericolo: { bg: "var(--danger-soft)", bordo: "var(--danger-border)", testo: "var(--danger-text)" },
  avviso: { bg: "var(--warning-soft)", bordo: "var(--warning-border)", testo: "var(--warning-text)" },
  successo: { bg: "var(--success-soft)", bordo: "var(--success-border)", testo: "var(--success-text)" },
  info: { bg: "var(--info-soft)", bordo: "var(--info-border)", testo: "var(--info-text)" },
};

const badge = (tono) => ({
  display: "inline-flex", alignItems: "center", gap: 5,
  padding: "4px 9px", borderRadius: 999, fontSize: 11, fontWeight: 800,
  lineHeight: 1.3, border: "1px solid",
  background: TONO[tono].bg, borderColor: TONO[tono].bordo, color: TONO[tono].testo,
});

const bottone = (primario) => ({
  display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
  minHeight: 44, padding: "10px 16px", borderRadius: 10,
  fontFamily: "var(--font)", fontSize: 13, fontWeight: 800, cursor: "pointer",
  border: primario ? "none" : "1.5px solid var(--border)",
  background: primario ? "var(--primary)" : "var(--card)",
  color: primario ? "#fff" : "var(--text-2)",
});

// ── Card di un prodotto in vetrina ────────────────────────────────────────
function CardInMenu({ ricetta, indice, onApri }) {
  const foto = fotoRicetta(ricetta);
  const { prezzo, origine: origPrezzo } = prezzoPerMenu(ricetta);
  const dest = destinazioneMenu(ricetta, indice);
  const allergeni = allergeniRicetta(ricetta);
  const problemi = problemiRicettaMenu(ricetta, indice);
  const descrizione = (ricetta.descrizione || "").trim();

  return (
    <article style={{
      background: "var(--card)", border: "1px solid var(--border)", borderRadius: 16,
      boxShadow: "var(--shadow-list)", overflow: "hidden", display: "flex", flexDirection: "column",
    }}>
      {/* Immagine: è la prima cosa che il titolare vuole vedere */}
      <div style={{
        height: 150, position: "relative", display: "grid", placeItems: "center",
        background: foto ? `center/cover no-repeat url('${fotoSrc(foto)}')` : "var(--primary-soft)",
      }}>
        {!foto && (
          <div style={{ display: "grid", placeItems: "center", gap: 6, color: "var(--primary)" }}>
            <ImageIcon size={30} aria-hidden="true" />
            <span style={{ fontSize: 11, fontWeight: 800 }}>Senza foto</span>
          </div>
        )}
        <span style={{
          position: "absolute", top: 8, left: 8, fontSize: 10, fontWeight: 800,
          textTransform: "uppercase", letterSpacing: ".05em",
          background: "rgba(42,51,41,.72)", color: "#fff", borderRadius: 6, padding: "3px 8px",
        }}>
          {ricetta.reparto || "senza reparto"}
        </span>
      </div>

      <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 10, flex: 1 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: "var(--text)", lineHeight: 1.25 }}>
          {ricetta.nome || "Senza nome"}
        </h3>

        {descrizione ? (
          <p style={{ margin: 0, fontSize: 13, fontWeight: 500, color: "var(--text-2)", lineHeight: 1.4 }}>
            {descrizione}
          </p>
        ) : (
          <p style={{ margin: 0, fontSize: 12, fontWeight: 700, color: "var(--warning-text)" }}>
            Descrizione mancante: nel Menu resta solo il nome.
          </p>
        )}

        {/* Prezzi: nel Menu esce il tavolo; il banco resta a fianco per confronto */}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "baseline" }}>
          <span style={{
            fontSize: 20, fontWeight: 800, fontVariantNumeric: "tabular-nums",
            color: origPrezzo === "assente" ? "var(--danger-text)" : "var(--text)",
          }}>
            {euro(prezzo)}
          </span>
          <span style={{ fontSize: 11, fontWeight: 800, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: ".04em" }}>
            {origPrezzo === "tavolo" ? "al tavolo — nel Menu"
              : origPrezzo === "banco" ? "al banco — ripiego nel Menu"
                : "nessun prezzo"}
          </span>
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-3)", fontVariantNumeric: "tabular-nums" }}>
            {origPrezzo === "tavolo"
              ? `banco ${euro(ricetta.prezzo_vendita || null)}`
              : "tavolo non deciso"}
          </span>
        </div>

        {/* Categoria di destinazione nel Menu */}
        <div style={{ display: "flex", alignItems: "flex-start", gap: 6, fontSize: 12, fontWeight: 700, color: "var(--text-2)" }}>
          <Tags size={14} style={{ marginTop: 2, flexShrink: 0 }} aria-hidden="true" />
          <span>
            {dest.categoria}
            {dest.sottocategoria ? <> <ChevronRight size={11} style={{ verticalAlign: "-1px" }} aria-hidden="true" /> {dest.sottocategoria}</> : null}
            <span style={{ fontWeight: 600, color: "var(--text-3)" }}> · assegnata automaticamente</span>
          </span>
        </div>

        {/* Allergeni evidenziati — obbligo di legge (Reg. UE 1169/2011) */}
        {allergeni.length > 0 && (
          <div style={{
            background: "var(--danger-soft)", border: "1.5px solid var(--danger-border)",
            borderRadius: 10, padding: "8px 10px",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6, color: "var(--danger-text)" }}>
              <AlertTriangle size={14} aria-hidden="true" />
              <span style={{ fontSize: 11, fontWeight: 800, textTransform: "uppercase", letterSpacing: ".05em" }}>
                Contiene allergeni
              </span>
            </div>
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
              {allergeni.map((a) => (
                <span key={a} style={{
                  fontSize: 11, fontWeight: 800, color: "var(--danger-text)",
                  background: "var(--card)", border: "1px solid var(--danger-border)",
                  borderRadius: 999, padding: "3px 8px",
                }}>{a}</span>
              ))}
            </div>
          </div>
        )}

        {problemi.length > 0 && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {problemi.map((c) => (
              <span key={c} style={badge(PROBLEMI[c].gravita)} title={PROBLEMI[c].aiuto}>
                <ShieldAlert size={12} aria-hidden="true" /> {PROBLEMI[c].etichetta}
              </span>
            ))}
          </div>
        )}
        {problemi.length === 0 && (
          <span style={{ ...badge("successo"), alignSelf: "flex-start" }}>Scheda completa</span>
        )}

        <button type="button" onClick={() => onApri(ricetta)} style={{ ...bottone(false), width: "100%", marginTop: "auto" }}>
          <Pencil size={15} aria-hidden="true" /> Apri e correggi
        </button>
      </div>
    </article>
  );
}

// ── Ripubblicazione in massa ──────────────────────────────────────────────
// Le ricette già in archivio prima del ponte non sono mai arrivate nel Menu.
// Mai in automatico all'apertura: prima la simulazione, poi la conferma.
function RipubblicaMenu() {
  const [anteprima, setAnteprima] = useState(null);
  const [stato, setStato] = useState(null);
  const [occupato, setOccupato] = useState("");
  const timer = useRef(null);

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const messaggio = (e, fallback) => {
    const d = e?.response?.data?.detail;
    return typeof d === "string" && d ? d : fallback;
  };

  const sonda = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/ricette-ripubblica-menu/stato`);
      setStato(r.data || null);
      if (r.data?.in_corso || r.data?.stato === "in_corso") {
        timer.current = setTimeout(sonda, 2500);
      } else if (r.data?.stato === "completato") {
        toast("Ripubblicazione nel Menu completata");
      } else if (r.data?.stato === "errore") {
        toast(`Ripubblicazione interrotta: ${r.data?.errore || "errore sconosciuto"}`, "err");
      }
    } catch (e) {
      toast(messaggio(e, "Non riesco a leggere lo stato della ripubblicazione"), "err");
    }
  }, []);

  const simula = async () => {
    setOccupato("dry");
    try {
      const r = await axios.post(`${API}/ricette-ripubblica-menu?dry_run=true`);
      setAnteprima(r.data || null);
    } catch (e) {
      toast(messaggio(e, "Simulazione non riuscita"), "err");
    } finally {
      setOccupato("");
    }
  };

  const avvia = async () => {
    const a = anteprima || {};
    const ok = await conferma(
      `Rimando nel Menu tutte le ${a.ricette_totali ?? "?"} ricette?\n\n` +
      `• ${a.visibili ?? "?"} resteranno visibili ai clienti\n` +
      `• ${a.nascoste ?? "?"} arriveranno nascoste (non le hai spuntate)\n` +
      `• ${a.senza_prezzo_tavolo ?? "?"} non hanno prezzo al tavolo: mostreranno quello al banco\n\n` +
      "Il giro non crea doppioni: aggiorna ciò che c'è già.",
      { titolo: "Ripubblica nel Menu", ok: "Ripubblica" },
    );
    if (!ok) return;
    setOccupato("run");
    try {
      const r = await axios.post(`${API}/ricette-ripubblica-menu`);
      toast(r.data?.messaggio || "Ripubblicazione avviata");
      setStato({ stato: "in_corso", in_corso: true, avanzamento: { fatte: 0, totale: anteprima?.ricette_totali || 0 } });
      sonda();
    } catch (e) {
      toast(messaggio(e, "Avvio non riuscito"), "err");
    } finally {
      setOccupato("");
    }
  };

  const avanz = stato?.avanzamento || {};
  const inCorso = !!(stato?.in_corso || stato?.stato === "in_corso");
  const pct = avanz.totale ? Math.min(100, Math.round((avanz.fatte / avanz.totale) * 100)) : 0;

  return (
    <section style={{
      background: "var(--card)", border: "1.5px solid var(--border)", borderRadius: 14,
      padding: "14px 16px", display: "flex", flexDirection: "column", gap: 12,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <UploadCloud size={18} color="var(--info)" aria-hidden="true" />
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 800, color: "var(--text)" }}>
          Rimanda tutte le ricette nel Menu
        </h2>
      </div>
      <p style={{ margin: 0, fontSize: 13, fontWeight: 500, color: "var(--text-2)", lineHeight: 1.45 }}>
        Le ricette salvate prima che esistesse il ponte non sono mai arrivate nel Menu.
        Questo giro le rimanda tutte: chi non è spuntato arriva <strong>nascosto</strong>, mai visibile.
        Prima guarda i numeri, poi conferma.
      </p>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" onClick={simula} disabled={!!occupato || inCorso} style={bottone(false)}>
          {occupato === "dry" ? <Loader2 size={15} aria-hidden="true" /> : <RefreshCw size={15} aria-hidden="true" />}
          {occupato === "dry" ? "Conto…" : "1. Guarda i numeri (simulazione)"}
        </button>
        <button
          type="button" onClick={avvia}
          disabled={!anteprima || !!occupato || inCorso}
          style={{ ...bottone(true), opacity: anteprima && !occupato && !inCorso ? 1 : 0.5 }}
        >
          <UploadCloud size={15} aria-hidden="true" /> 2. Ripubblica davvero
        </button>
      </div>

      {anteprima && (
        <div style={{
          background: "var(--info-soft)", border: "1.5px solid var(--info-border)",
          borderRadius: 10, padding: "10px 12px", fontSize: 13, color: "var(--info-text)",
          display: "flex", flexDirection: "column", gap: 4, fontWeight: 700,
        }}>
          {anteprima.menu_configurato === false && <span>Menu digitale non configurato su questo ambiente.</span>}
          <span>Ricette in tutto: {anteprima.ricette_totali ?? 0}</span>
          <span>Visibili ai clienti: {anteprima.visibili ?? 0} · nascoste: {anteprima.nascoste ?? 0}</span>
          <span>Senza prezzo al tavolo: {anteprima.senza_prezzo_tavolo ?? 0} (esporranno il prezzo al banco)</span>
          {(anteprima.campioni_senza_prezzo_tavolo || []).length > 0 && (
            <span style={{ fontWeight: 600 }}>
              Per esempio: {(anteprima.campioni_senza_prezzo_tavolo || []).slice(0, 5).map((c) => c.nome).join(", ")}
            </span>
          )}
          <span style={{ fontWeight: 600 }}>Simulazione: non è stato scritto nulla.</span>
        </div>
      )}

      {stato && (
        <div style={{
          background: "var(--bg)", border: "1.5px solid var(--border)", borderRadius: 10,
          padding: "10px 12px", fontSize: 13, fontWeight: 700, color: "var(--text-2)",
          display: "flex", flexDirection: "column", gap: 8,
        }}>
          <span>
            {inCorso ? `In corso: ${avanz.fatte ?? 0} di ${avanz.totale ?? 0}`
              : stato.stato === "completato" ? "Completata"
                : stato.stato === "errore" ? `Errore: ${stato.errore || "sconosciuto"}`
                  : "Nessuna ripubblicazione in corso"}
          </span>
          {inCorso && (
            <div style={{ height: 8, borderRadius: 999, background: "var(--border-subtle)", overflow: "hidden" }}>
              <div style={{ width: `${pct}%`, height: "100%", background: "var(--primary)" }} />
            </div>
          )}
        </div>
      )}
    </section>
  );
}

// ── Vista ─────────────────────────────────────────────────────────────────
export default function MenuVetrinaView({ onNavigate }) {
  const [ricette, setRicette] = useState([]);
  const [caricando, setCaricando] = useState(true);
  const [filtro, setFiltro] = useState("");   // "" = tutte, altrimenti codice problema
  const { indice, errore: erroreCategorie, ricarica: ricaricaCategorie } = useCategorieMenu();
  const amministratore = isAdmin();

  const carica = useCallback(async () => {
    setCaricando(true);
    try {
      const r = await axios.get(`${API}/ricette`);
      setRicette(Array.isArray(r.data) ? r.data : []);
    } catch {
      toast("Errore caricamento ricette", "err");
    } finally {
      setCaricando(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const inMenu = useMemo(() => ricetteInMenu(ricette), [ricette]);
  const riepilogo = useMemo(() => riepilogoProblemi(inMenu, indice), [inMenu, indice]);
  const visibili = useMemo(() => {
    const base = filtro
      ? inMenu.filter((r) => problemiRicettaMenu(r, indice).includes(filtro))
      : inMenu;
    return ordinaPerUrgenza(base, indice);
  }, [inMenu, indice, filtro]);

  const apriRicetta = (r) => {
    try { sessionStorage.setItem("apri_ricetta_id", r.id); } catch { /* no-op */ }
    if (onNavigate) onNavigate("ricette");
    else window.location.hash = "#ricette";
  };

  const chip = (attivo) => ({
    display: "inline-flex", alignItems: "center", gap: 6, minHeight: 44,
    padding: "9px 14px", borderRadius: 999, cursor: "pointer",
    border: "1.5px solid", fontFamily: "var(--font)", fontSize: 13, fontWeight: 800,
    background: attivo ? "var(--primary)" : "var(--card)",
    color: attivo ? "#fff" : "var(--text-2)",
    borderColor: attivo ? "var(--primary)" : "var(--border)",
  });

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "0 16px 40px", display: "flex", flexDirection: "column", gap: 16 }}>

      {/* Riepilogo */}
      <section style={{
        background: "var(--card)", border: "1.5px solid var(--border)", borderRadius: 14,
        padding: "14px 16px", display: "flex", flexDirection: "column", gap: 12,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <Utensils size={18} color="var(--primary)" aria-hidden="true" />
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 800, color: "var(--text)" }}>
            {caricando ? "Leggo le ricette…" : `${riepilogo.totale} prodotti nel Menu digitale`}
          </h2>
          <button type="button" onClick={() => { carica(); ricaricaCategorie(); }} style={{ ...bottone(false), marginLeft: "auto" }}>
            <RefreshCw size={15} aria-hidden="true" /> Aggiorna
          </button>
        </div>
        <p style={{ margin: 0, fontSize: 13, fontWeight: 500, color: "var(--text-2)", lineHeight: 1.45 }}>
          Sono le ricette con «Mostra nel menu pubblico» spuntato: quello che i clienti
          vedono davvero inquadrando il QR al tavolo.
          {riepilogo.daSistemare > 0 && <> <strong>{riepilogo.daSistemare} sono da sistemare.</strong></>}
        </p>

        {erroreCategorie && (
          <div style={{
            fontSize: 12, fontWeight: 700, color: "var(--warning-text)",
            background: "var(--warning-soft)", border: "1.5px solid var(--warning-border)",
            borderRadius: 10, padding: "8px 10px",
          }}>
            {erroreCategorie} — le categorie mostrate qui sotto possono non essere aggiornate.
          </div>
        )}

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" onClick={() => setFiltro("")} style={chip(filtro === "")}>
            Tutti ({riepilogo.totale})
          </button>
          {ORDINE_PROBLEMI.filter((c) => riepilogo.conteggio[c] > 0).map((c) => (
            <button key={c} type="button" onClick={() => setFiltro(filtro === c ? "" : c)}
              style={chip(filtro === c)} title={PROBLEMI[c].aiuto}>
              {PROBLEMI[c].etichetta} ({riepilogo.conteggio[c]})
            </button>
          ))}
        </div>
      </section>

      {amministratore && <RipubblicaMenu />}

      {/* Vetrina */}
      {caricando ? (
        <div style={{ textAlign: "center", padding: 40, color: "var(--text-3)", fontWeight: 700 }}>Caricamento…</div>
      ) : visibili.length === 0 ? (
        <div style={{
          textAlign: "center", padding: "48px 20px", background: "var(--card)",
          border: "1.5px dashed var(--border)", borderRadius: 14, color: "var(--text-2)",
        }}>
          <Utensils size={30} color="var(--text-3)" aria-hidden="true" />
          <p style={{ margin: "12px 0 0", fontSize: 14, fontWeight: 700 }}>
            {filtro ? "Nessun prodotto con questo problema." : "Nessun prodotto nel Menu digitale."}
          </p>
          {!filtro && (
            <p style={{ margin: "6px 0 0", fontSize: 13, fontWeight: 500 }}>
              Apri una ricetta in Produzione e spunta «Mostra nel menu pubblico».
            </p>
          )}
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 14 }}>
          {visibili.map((r) => (
            <CardInMenu key={r.id} ricetta={r} indice={indice} onApri={apriRicetta} />
          ))}
        </div>
      )}
    </div>
  );
}
