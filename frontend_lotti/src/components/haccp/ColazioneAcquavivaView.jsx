import React, { useState, useEffect, useCallback } from "react";
import { conferma } from "../../utils/conferma";
import { apiError } from "../../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import { API, BACKEND_URL, withToken } from "../../utils/constants";

/**
 * ColazioneAcquaviva — UI ottimizzata per tablet pasticceria.
 * Mostra TUTTI i prodotti con spunta grande, +/- quantità e avvia tutto al banco in un click.
 * Due modalità:
 *   - "configura": seleziona prodotti e quantità di default (salvati come template)
 *   - "avvia": ogni mattina spunta cosa esce oggi e manda al banco
 */
const ColazioneAcquavivaView = ({ onClose, modoTablet = false }) => {
  const [prodottiDisponibili, setProdottiDisponibili] = useState([]);
  const [presetList, setPresetList]   = useState([]);
  const [presetSel, setPresetSel]     = useState(null);   // nome preset stagione attivo
  const [template, setTemplate]       = useState({ nome: "", items: [], note: "" });
  const [loading, setLoading]         = useState(true);
  const [saving, setSaving]           = useState(false);
  const [registrando, setRegistrando] = useState(false);
  const [risultato, setRisultato]     = useState(null);
  const [search, setSearch]           = useState("");
  const [modalita, setModalita]       = useState("avvia"); // "avvia" | "configura"
  const [piuUsati, setPiuUsati]       = useState([]);
  const [preferiti, setPreferiti]     = useState(new Set());
  const [modificaPeriodo, setModificaPeriodo] = useState(false);
  const [periodoForm, setPeriodoForm] = useState({ data_inizio: "", data_fine: "" });
  // Rete di sicurezza (23/07/2026): se un prodotto comprato non viene
  // riconosciuto dal matching, questa spunta mostra TUTTO il catalogo.
  const [mostraTutti, setMostraTutti] = useState(false);
  const [popolandoAcquisti, setPopolandoAcquisti] = useState(false);
  // La lista scorre: quando cambia la ricerca si torna in cima (23/07/2026:
  // "se faccio cerca esco giù a tutto")
  const listaRef = React.useRef(null);
  useEffect(() => { listaRef.current?.scrollTo?.({ top: 0 }); }, [search]);

  // Carica un preset specifico (stagione)
  const caricaPreset = useCallback(async (nome) => {
    try {
      const res = await axios.get(`${API}/colazione-acquaviva`, { params: { nome } });
      setTemplate(res.data?.items ? res.data : { nome, items: [], note: "" });
    } catch (e) {
      toast.error("Errore caricamento preset: " + apiError(e));
    }
  }, []);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const [resProdotti, resPreset, resPiuUsati, resPreferiti, resStagioneAttiva] = await Promise.all([
        axios.get(`${API}/colazione-acquaviva/prodotti-disponibili?catalogo=true&solo_acquistati=${!mostraTutti}`),
        axios.get(`${API}/colazione-acquaviva/preset`),
        axios.get(`${API}/colazione-acquaviva/prodotti-piu-usati`),
        axios.get(`${API}/colazione-acquaviva/preferiti`),
        axios.get(`${API}/colazione-acquaviva/stagione-attiva`).catch(() => null),
      ]);
      setProdottiDisponibili(resProdotti.data || []);
      const lista = resPreset.data || [];
      setPresetList(lista);
      setPiuUsati(resPiuUsati.data || []);
      setPreferiti(new Set(resPreferiti.data || []));
      // Pre-seleziona la stagione il cui periodo (equinozi/solstizi, modificabili)
      // contiene la data di oggi — niente più scelta manuale ogni mattina.
      const stagioneOggi = resStagioneAttiva?.data?.stagione;
      const primo = (stagioneOggi && lista.some(p => p.nome === stagioneOggi))
        ? stagioneOggi : (lista[0]?.nome || "Estiva");
      setPresetSel(primo);
      await caricaPreset(primo);
    } catch (e) {
      toast.error("Errore caricamento: " + apiError(e));
    } finally {
      setLoading(false);
    }
  }, [caricaPreset, mostraTutti]);

  const togglePreferito = async (prod) => {
    const eraPreferito = preferiti.has(prod.id);
    // Ottimistico: aggiorna subito la stella, poi conferma dal server
    setPreferiti(prev => {
      const next = new Set(prev);
      eraPreferito ? next.delete(prod.id) : next.add(prod.id);
      return next;
    });
    try {
      const res = await axios.post(`${API}/colazione-acquaviva/preferito`, {
        prodotto_id: prod.id,
        prodotto_nome: prod.nome,
        foto_url: prod.foto_url || null,
        categoria: prod.categoria || null,
        prezzo_vendita: prod.prezzo_vendita || 0,
        fonte: prod.fonte || null,
      });
      if (res.data.preferito) {
        toast.success(`⭐ ${prod.nome} aggiunto a tutte e 4 le stagioni`);
        const resPreset = await axios.get(`${API}/colazione-acquaviva/preset`);
        setPresetList(resPreset.data || []);
        if (presetSel) await caricaPreset(presetSel);
      } else {
        toast(`${prod.nome} tolto dai preferiti`);
      }
    } catch (e) {
      toast.error("Errore: " + apiError(e));
      setPreferiti(prev => {
        const next = new Set(prev);
        eraPreferito ? next.add(prod.id) : next.delete(prod.id);
        return next;
      });
    }
  };

  const popolaDaAcquisti = async () => {
    if (!await conferma(
      "Aggiungere a Primavera, Estiva, Autunnale e Invernale tutti i prodotti dolci trovati nelle fatture?\n\nLe quantità già impostate non verranno cambiate. I prodotti mancanti partiranno da 6 pezzi e potrai rimuoverli o regolarli da ogni stagione.",
      { titolo: "Popola le quattro colazioni", ok: "Aggiungi acquistati" }
    )) return;
    setPopolandoAcquisti(true);
    try {
      const r = await axios.post(`${API}/colazione-acquaviva/popola-quattro-stagioni`);
      const d = r.data || {};
      toast.success(d.totale_aggiunte
        ? `${d.prodotti_acquistati || 0} prodotti riconosciuti · ${d.totale_aggiunte} inserimenti nelle quattro stagioni`
        : `${d.prodotti_acquistati || 0} prodotti riconosciuti: erano già tutti presenti`);
      await carica();
    } catch (e) {
      toast.error("Errore popolamento: " + apiError(e));
    } finally { setPopolandoAcquisti(false); }
  };

  const apriModificaPeriodo = () => {
    const p = presetList.find(x => x.nome === presetSel);
    setPeriodoForm({ data_inizio: p?.data_inizio || "", data_fine: p?.data_fine || "" });
    setModificaPeriodo(true);
  };

  const salvaPeriodo = async () => {
    if (!/^\d{2}-\d{2}$/.test(periodoForm.data_inizio) || !/^\d{2}-\d{2}$/.test(periodoForm.data_fine)) {
      toast.error("Formato data non valido: usa MM-GG, es. 03-21");
      return;
    }
    try {
      await axios.put(`${API}/colazione-acquaviva/preset/${encodeURIComponent(presetSel)}/periodo`, periodoForm);
      toast.success("Periodo aggiornato");
      setModificaPeriodo(false);
      const resPreset = await axios.get(`${API}/colazione-acquaviva/preset`);
      setPresetList(resPreset.data || []);
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    }
  };

  useEffect(() => { carica(); }, [carica]);

  const cambiaPreset = async (nome) => {
    setPresetSel(nome);
    setRisultato(null);
    await caricaPreset(nome);
  };

  // Creazione nuova colazione con input INLINE (niente window.prompt: brutto
  // su tablet e fuori dal design — regola conferme uniformi 20/07/2026).
  const [nuovaColazione, setNuovaColazione] = useState(null); // null=chiuso, ""=aperto
  const creaPreset = async () => {
    const nome = (nuovaColazione || "").trim();
    if (!nome) { setNuovaColazione(null); return; }
    setNuovaColazione(null);
    try {
      await axios.put(`${API}/colazione-acquaviva`, { nome, items: [], note: "" });
      const res = await axios.get(`${API}/colazione-acquaviva/preset`);
      setPresetList(res.data || []);
      setPresetSel(nome);
      setTemplate({ nome, items: [], note: "" });
      setModalita("configura");
      toast.success(`Colazione "${nome}" creata — aggiungi i prodotti`);
    } catch (e) {
      toast.error("Errore creazione: " + apiError(e));
    }
  };

  const eliminaPreset = async (nome) => {
    if (!await conferma(`Eliminare la colazione "${nome}"?`)) return;
    try {
      await axios.delete(`${API}/colazione-acquaviva/preset/${encodeURIComponent(nome)}`);
      const res = await axios.get(`${API}/colazione-acquaviva/preset`);
      const lista = res.data || [];
      setPresetList(lista);
      const primo = lista[0]?.nome || null;
      setPresetSel(primo);
      if (primo) await caricaPreset(primo); else setTemplate({ nome: "", items: [], note: "" });
      toast.success(`Eliminata: ${nome}`);
    } catch (e) {
      toast.error("Errore eliminazione: " + apiError(e));
    }
  };

  // ── Helpers template ────────────────────────────────────────────────────────
  const getItem = (id) => template.items.find(i => i.prodotto_id === id);

  const toggleProdotto = (prod) => {
    setTemplate(prev => {
      const exists = prev.items.find(i => i.prodotto_id === prod.id);
      if (exists) {
        return { ...prev, items: prev.items.filter(i => i.prodotto_id !== prod.id) };
      }
      return {
        ...prev,
        items: [...prev.items, {
          prodotto_id: prod.id,
          prodotto_nome: prod.nome,
          pezzi: 6,
          foto_url: prod.foto_url || null,
          categoria: prod.categoria || null,
          prezzo_vendita: prod.prezzo_vendita || 0,
          attivo: true
        }]
      };
    });
  };

  const setPezzi = (id, val) => {
    setTemplate(prev => ({
      ...prev,
      items: prev.items.map(i =>
        i.prodotto_id === id ? { ...i, pezzi: Math.max(1, parseInt(val) || 1) } : i
      )
    }));
  };

  const toggleAttivo = (id) => {
    setTemplate(prev => ({
      ...prev,
      items: prev.items.map(i =>
        i.prodotto_id === id ? { ...i, attivo: !i.attivo } : i
      )
    }));
  };

  // ── Salva template ──────────────────────────────────────────────────────────
  const salvaTemplate = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/colazione-acquaviva`, { ...template, nome: presetSel });
      toast.success(`Menù "${presetSel}" salvato!`);
      // Menù sistemato → si torna alla schermata del mattino (un passaggio in meno)
      setModalita("avvia");
    } catch (e) {
      toast.error("Errore salvataggio");
    } finally {
      setSaving(false);
    }
  };

  // ── Avvia colazione → manda tutto al banco ──────────────────────────────────
  const avviaColazione = async () => {
    const attivi = template.items.filter(i => i.attivo);
    if (attivi.length === 0) { toast.error("Seleziona almeno un prodotto"); return; }
    setRegistrando(true);
    try {
      await axios.put(`${API}/colazione-acquaviva`, { ...template, nome: presetSel });
      const res = await axios.post(`${API}/colazione-acquaviva/registra`, { nome: presetSel });
      setRisultato(res.data);
      toast.success(`Colazione avviata: ${attivi.length} prodotti, ${totPezzi} pezzi`);
      // Auto-chiudi modale dopo 1.5 secondi
      if (onClose) setTimeout(() => onClose(), 1500);
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    } finally {
      setRegistrando(false);
    }
  };

  // ── KPI ─────────────────────────────────────────────────────────────────────
  const attivi    = template.items.filter(i => i.attivo);
  const totPezzi  = attivi.reduce((s, i) => s + (i.pezzi || 0), 0);
  const totValore = attivi.reduce((s, i) => s + (i.prezzo_vendita || 0) * (i.pezzi || 0), 0);

  // Normalizza l'URL foto: assoluto → così com'è; relativo (/api/foto, /uploads) → prefissa backend
  const fotoSrc = (u) => {
    if (!u) return null;
    if (/^https?:\/\//i.test(u)) return u;
    return `${BACKEND_URL}${u.startsWith("/") ? "" : "/"}${u}`;
  };

  // AVVIA: gli item realmente nel template (inclusi prodotti NON a catalogo, es. pasticceria)
  const normNome = (s) => (s || "").trim().toLowerCase();
  const prodottiInTemplate = template.items
    .map(it => {
      // Prima per id; se l'item è stato salvato con un id diverso (es. ricetta
      // ricreata), riaggancia foto e categoria per NOME.
      const cat = prodottiDisponibili.find(p => p.id === it.prodotto_id)
        || (it.prodotto_nome ? prodottiDisponibili.find(p => normNome(p.nome) === normNome(it.prodotto_nome)) : null);
      return {
        id: it.prodotto_id,
        nome: it.prodotto_nome || cat?.nome || "—",
        foto_url: it.foto_url || cat?.foto_url || null,
        categoria: it.categoria || cat?.categoria || null,
      };
    })
    .filter(p => (p.nome || "").toLowerCase().includes(search.toLowerCase()));

  // ── Schermata risultato ─────────────────────────────────────────────────────
  if (risultato) {
    return (
      <div style={{
        position: "fixed", inset: 0, background: "#f0fdf4", zIndex: 9999,
        display: "flex", flexDirection: "column", alignItems: "center",
        justifyContent: "center", padding: 24
      }}>
        <div style={{
          background: "#fff", borderRadius: 24, padding: 32,
          maxWidth: 480, width: "100%",
          boxShadow: "0 20px 60px rgba(0,0,0,0.12)", textAlign: "center"
        }}>
          <div style={{ fontSize: 60, marginBottom: 12 }}>☕</div>
          <h2 style={{ margin: "0 0 4px", fontSize: 26, fontWeight: 800, color: "var(--success-dark)" }}>
            Colazione Registrata!
          </h2>
          <p style={{ color: "#6b7280", margin: "0 0 24px", fontSize: 14 }}>{risultato.data}</p>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
            <div style={{ background: "#f0fdf4", borderRadius: 14, padding: "14px", border: "2px solid #bbf7d0" }}>
              <p style={{ margin: 0, fontSize: 32, fontWeight: 900, color: "var(--success)" }}>{risultato.prodotti_registrati}</p>
              <p style={{ margin: 0, fontSize: 11, color: "#6b7280", fontWeight: 700 }}>PRODOTTI</p>
            </div>
            <div style={{ background: "#fff7ed", borderRadius: 14, padding: "14px", border: "2px solid #fed7aa" }}>
              <p style={{ margin: 0, fontSize: 32, fontWeight: 900, color: "#ea580c" }}>{risultato.pezzi_totali}</p>
              <p style={{ margin: 0, fontSize: 11, color: "#6b7280", fontWeight: 700 }}>PEZZI</p>
            </div>
          </div>

          <div style={{ background: "#f0fdf4", borderRadius: 14, padding: "14px", marginBottom: 20, border: "2px solid #bbf7d0" }}>
            <p style={{ margin: 0, fontSize: 26, fontWeight: 900, color: "var(--success-dark)" }}>
              €{(risultato.valore_totale || 0).toFixed(2)}
            </p>
            <p style={{ margin: 0, fontSize: 11, color: "#6b7280", fontWeight: 700 }}>VALORE TOTALE AL BANCO</p>
          </div>

          <div style={{ textAlign: "left", maxHeight: 180, overflowY: "auto", marginBottom: 20 }}>
            {risultato.registrati?.map((r, i) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "8px 0", borderBottom: "1px solid #f1f5f9"
              }}>
                <span style={{ fontSize: 13, color: "#374151", fontWeight: 600 }}>{r.nome}</span>
                <span style={{ fontSize: 13, color: "#6b7280", fontWeight: 700 }}>{r.pezzi} pz</span>
              </div>
            ))}
          </div>

          <button onClick={() => { setRisultato(null); onClose?.(); }}
            style={{
              width: "100%", padding: "16px",
              background: "linear-gradient(135deg, var(--success-dark), var(--success))",
              color: "#fff", border: "none", borderRadius: 14,
              fontSize: 16, fontWeight: 800, cursor: "pointer"
            }}>
            Chiudi
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 9998,
      background: modoTablet ? "#fff" : "rgba(0,0,0,0.6)",
      display: "flex", flexDirection: "column"
    }}>
      <div style={{
        flex: 1, display: "flex", flexDirection: "column",
        background: "#fff",
        margin: modoTablet ? 0 : "16px",
        borderRadius: modoTablet ? 0 : 20,
        overflow: "hidden",
        maxWidth: modoTablet ? "100%" : 700,
        alignSelf: "center", width: "100%"
      }}>

        {/* ── Header ── La mattina serve UNA cosa sola: spuntare e avviare.
            Stagioni, periodo, catalogo e quantità di default stanno tutti
            dietro «Modifica menù» (semplificazione Enzo 20/07/2026: la
            gestione non deve stare davanti agli occhi ogni mattina — la
            stagione giusta si seleziona già da sola per data). */}
        <div style={{
          background: "linear-gradient(135deg, var(--warning-text), var(--warning-dark))",
          padding: "14px 16px"
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
            <div style={{ minWidth: 0 }}>
              <h2 style={{ color: "#fff", margin: 0, fontSize: 20, fontWeight: 800 }}>
                {modalita === "avvia" ? "Colazione" : "Menù colazione"}{presetSel ? ` · ${presetSel}` : ""}
              </h2>
              <p style={{ color: "rgba(255,255,255,0.8)", margin: "2px 0 0", fontSize: 12 }}>
                {attivi.length} prodotti · {totPezzi} pezzi · €{totValore.toFixed(2)}
              </p>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
              {modalita === "avvia" ? (
                <button onClick={() => setModalita("configura")} style={{
                  background: "rgba(255,255,255,0.16)", border: "2px solid rgba(255,255,255,0.5)",
                  color: "#fff", borderRadius: 10, padding: "8px 14px",
                  fontWeight: 800, cursor: "pointer", fontSize: 13
                }}>⚙️ Modifica menù</button>
              ) : (
                <button onClick={() => setModalita("avvia")} style={{
                  background: "#fff", border: "none",
                  color: "var(--warning-text)", borderRadius: 10, padding: "8px 14px",
                  fontWeight: 800, cursor: "pointer", fontSize: 13
                }}>← Torna alla colazione</button>
              )}
              {onClose && (
                <button onClick={onClose} style={{
                  background: "rgba(255,255,255,0.2)", border: "none",
                  color: "#fff", borderRadius: 10, padding: "8px 14px",
                  fontWeight: 700, cursor: "pointer", fontSize: 16
                }}>✕</button>
              )}
            </div>
          </div>

          {/* Gestione stagioni: SOLO in modalità menù */}
          {modalita === "configura" && (
            <>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "12px 0 0", alignItems: "center" }}>
                {presetList.map(p => (
                  <button key={p.nome} onClick={() => cambiaPreset(p.nome)} style={{
                    padding: "6px 12px", borderRadius: 999, fontWeight: 800, fontSize: 12, cursor: "pointer",
                    border: `2px solid rgba(255,255,255,${presetSel === p.nome ? 0.95 : 0.35})`,
                    background: presetSel === p.nome ? "#fff" : "rgba(255,255,255,0.12)",
                    color: presetSel === p.nome ? "var(--warning-text)" : "#fff"
                  }}>
                    {p.nome}{p.n_prodotti ? ` · ${p.n_prodotti}` : ""}
                  </button>
                ))}
                {nuovaColazione === null ? (
                  <button onClick={() => setNuovaColazione("")} style={{
                    padding: "6px 12px", borderRadius: 999, fontWeight: 800, fontSize: 12, cursor: "pointer",
                    border: "2px dashed rgba(255,255,255,0.6)", background: "transparent", color: "#fff"
                  }}>＋ Nuova</button>
                ) : (
                  <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
                    <input autoFocus type="text" value={nuovaColazione} placeholder="es. Natale"
                      onChange={e => setNuovaColazione(e.target.value)}
                      onKeyDown={e => { if (e.key === "Enter") creaPreset(); if (e.key === "Escape") setNuovaColazione(null); }}
                      style={{ width: 110, padding: "5px 10px", borderRadius: 999, border: "none", fontSize: 12, fontWeight: 700 }} />
                    <button onClick={creaPreset} style={{
                      padding: "5px 10px", borderRadius: 999, border: "none", background: "#fff",
                      color: "var(--warning-text)", fontWeight: 800, fontSize: 12, cursor: "pointer"
                    }}>Crea</button>
                  </span>
                )}
                {presetSel && presetList.length > 1 && (
                  <button onClick={() => eliminaPreset(presetSel)} title="Elimina questa colazione" style={{
                    padding: "6px 10px", borderRadius: 999, fontWeight: 800, fontSize: 12, cursor: "pointer",
                    border: "2px solid rgba(239,68,68,0.6)", background: "rgba(239,68,68,0.18)", color: "#fff"
                  }}>🗑</button>
                )}
                {presetSel && presetList.length > 1 && (
                  <button
                    onClick={async () => {
                      const altre = presetList.filter(p => p.nome !== presetSel).map(p => p.nome);
                      if (!await conferma(
                        `Copiare il menù "${presetSel}" (${template.items.length} prodotti) in: ${altre.join(", ")}?\n\nI loro menù attuali verranno sostituiti (i periodi restano).`,
                        { titolo: "Copia nelle altre stagioni", ok: "Copia" }
                      )) return;
                      try {
                        const r = await axios.post(`${API}/colazione-acquaviva/copia-preset`, { da: presetSel });
                        toast.success(`Menù "${presetSel}" copiato in: ${(r.data?.copiate_in || []).join(", ")}`);
                        const res = await axios.get(`${API}/colazione-acquaviva/preset`);
                        setPresetList(res.data || []);
                      } catch (e) { toast.error("Errore copia: " + apiError(e)); }
                    }}
                    title="Copia questo menù in tutte le altre stagioni"
                    style={{
                      padding: "6px 12px", borderRadius: 999, fontWeight: 800, fontSize: 12, cursor: "pointer",
                      border: "2px solid rgba(255,255,255,0.6)", background: "rgba(255,255,255,0.12)", color: "#fff"
                    }}>⧉ Copia nelle altre stagioni</button>
                )}
                <button
                  onClick={popolaDaAcquisti}
                  disabled={popolandoAcquisti}
                  title="Aggiunge alle quattro stagioni soltanto i prodotti dolci realmente acquistati, senza cambiare quelli già regolati"
                  style={{
                    padding: "6px 12px", borderRadius: 999, fontWeight: 800, fontSize: 12,
                    cursor: popolandoAcquisti ? "wait" : "pointer", opacity: popolandoAcquisti ? .65 : 1,
                    border: "2px solid rgba(255,255,255,0.75)", background: "#fff", color: "var(--warning-text)"
                  }}>
                  {popolandoAcquisti ? "Popolo…" : "＋ Tutti gli acquistati nelle 4 stagioni"}
                </button>
                {/* ZIP delle foto Acquaviva già in archivio, rinominate col nome prodotto */}
                <button
                  onClick={() => window.open(withToken(`${API}/acquaviva/export-foto-zip`), "_blank")}
                  title="Scarica uno zip con le foto dei prodotti Acquaviva, ogni file col nome del prodotto"
                  style={{
                    padding: "6px 12px", borderRadius: 999, fontWeight: 800, fontSize: 12, cursor: "pointer",
                    border: "2px solid rgba(255,255,255,0.6)", background: "rgba(255,255,255,0.12)", color: "#fff"
                  }}>⬇️ Zip foto Acquaviva</button>
              </div>

              {/* Periodo stagione (richiesta Enzo 03/07/2026): la stagione entra in
                  vigore da sola alla data giusta — qui si corregge se serve. */}
              {presetSel && (
                <div style={{ marginTop: 10 }}>
                  {!modificaPeriodo ? (
                    (() => {
                      const p = presetList.find(x => x.nome === presetSel);
                      const fmt = mmdd => mmdd ? `${mmdd.slice(3, 5)}/${mmdd.slice(0, 2)}` : "?";
                      return (
                        <button onClick={apriModificaPeriodo} style={{
                          background: "none", border: "none", color: "rgba(255,255,255,0.85)",
                          fontSize: 11, cursor: "pointer", padding: 0, textDecoration: "underline"
                        }}>
                          📅 {p?.data_inizio ? `In vigore dal ${fmt(p.data_inizio)} al ${fmt(p.data_fine)}` : "Nessun periodo impostato"} — modifica
                        </button>
                      );
                    })()
                  ) : (
                    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", background: "rgba(255,255,255,0.12)", borderRadius: 8, padding: "6px 8px" }}>
                      <span style={{ fontSize: 11, color: "#fff", fontWeight: 700 }}>Dal (mese-giorno)</span>
                      <input type="text" placeholder="03-21" value={periodoForm.data_inizio}
                        onChange={e => setPeriodoForm(p => ({ ...p, data_inizio: e.target.value }))}
                        style={{ width: 56, padding: "4px 6px", borderRadius: 6, border: "none", fontSize: 11, textAlign: "center" }} />
                      <span style={{ fontSize: 11, color: "#fff", fontWeight: 700 }}>al</span>
                      <input type="text" placeholder="06-20" value={periodoForm.data_fine}
                        onChange={e => setPeriodoForm(p => ({ ...p, data_fine: e.target.value }))}
                        style={{ width: 56, padding: "4px 6px", borderRadius: 6, border: "none", fontSize: 11, textAlign: "center" }} />
                      <button onClick={salvaPeriodo} style={{ background: "#fff", color: "var(--warning-text)", border: "none", borderRadius: 6, padding: "4px 10px", fontSize: 11, fontWeight: 800, cursor: "pointer" }}>Salva</button>
                      <button onClick={() => setModificaPeriodo(false)} style={{ background: "none", color: "rgba(255,255,255,0.8)", border: "none", fontSize: 11, cursor: "pointer" }}>Annulla</button>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* ── Barra ricerca ── */}
        <div style={{ padding: "10px 14px", borderBottom: "1px solid #e5e7eb", background: "#fafafa" }}>
          <input
            type="text" placeholder="Cerca prodotto..."
            value={search} onChange={e => setSearch(e.target.value)}
            style={{
              width: "100%", padding: "10px 14px", borderRadius: 10,
              border: "2px solid #e5e7eb", fontSize: 14, outline: "none",
              boxSizing: "border-box"
            }}
          />
          {modalita === "avvia" && prodottiInTemplate.length === 0 && !loading && (
            <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--warning-text)", fontWeight: 600 }}>
              Nessun prodotto in questo menù. Tocca <b>⚙️ Modifica menù</b> in alto per aggiungerne.
            </p>
          )}
          {/* Più usati: scorciatoia per non scorrere tutto il catalogo ogni
              volta (richiesta Enzo 03/07/2026) — solo a ricerca vuota. */}
          {modalita === "configura" && !search && piuUsati.length > 0 && (
            <div style={{ marginTop: 10 }}>
              <p style={{ margin: "0 0 6px", fontSize: 11, fontWeight: 800, color: "#6b7280", textTransform: "uppercase" }}>
                ⭐ Più usati
              </p>
              <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 2 }}>
                {piuUsati.map(prod => {
                  const inTemplate = getItem(prod.id);
                  return (
                    <button key={prod.id} onClick={() => toggleProdotto(prod)}
                      style={{
                        flexShrink: 0, padding: "7px 12px", borderRadius: 20, whiteSpace: "nowrap",
                        border: `2px solid ${inTemplate ? "var(--warning)" : "#e5e7eb"}`,
                        background: inTemplate ? "var(--warning-soft)" : "#fff",
                        color: inTemplate ? "var(--warning-text)" : "#374151",
                        fontSize: 12, fontWeight: 700, cursor: "pointer"
                      }}>
                      {inTemplate ? "✓ " : ""}{prod.nome}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* ── Lista prodotti ── */}
        <div ref={listaRef} style={{ flex: 1, overflowY: "auto", padding: "10px 12px" }}>
          {loading ? (
            <div style={{ textAlign: "center", padding: 60, color: "#9ca3af" }}>Caricamento...</div>
          ) : (
            <>
              {/* MODALITA CONFIGURA: tutti i prodotti con toggle aggiungi/rimuovi */}
              {modalita === "configura" && (
                <>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
                    <p style={{ margin: 0, fontSize: 12, fontWeight: 700, color: "#6b7280", textTransform: "uppercase" }}>
                      {prodottiDisponibili.length} prodotti disponibili — tocca per aggiungerli al menù
                    </p>
                    {/* Rete di sicurezza: se un prodotto comprato non viene
                        riconosciuto, questa spunta mostra tutto il catalogo */}
                    <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 700, color: "#6b7280", cursor: "pointer" }}>
                      <input type="checkbox" checked={mostraTutti} onChange={e => setMostraTutti(e.target.checked)} />
                      mostra anche mai acquistati
                    </label>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 8, marginBottom: 16 }}>
                    {prodottiDisponibili
                      .filter(p => (p.nome || "").toLowerCase().includes(search.toLowerCase()))
                      .map(prod => {
                        const inTemplate = getItem(prod.id);
                        return (
                          <div key={prod.id}
                            onClick={() => toggleProdotto(prod)}
                            style={{
                              borderRadius: 12, overflow: "hidden",
                              border: `2px solid ${inTemplate ? "var(--warning)" : "#e5e7eb"}`,
                              background: inTemplate ? "var(--warning-soft)" : "#fff",
                              cursor: "pointer", position: "relative",
                              boxShadow: inTemplate ? "0 2px 10px rgba(245,158,11,0.2)" : "0 1px 4px rgba(0,0,0,0.06)"
                            }}
                          >
                            {inTemplate && (
                              <div style={{
                                position: "absolute", top: 5, right: 5,
                                background: "var(--warning)", color: "#fff", borderRadius: "50%",
                                width: 22, height: 22, display: "flex", alignItems: "center",
                                justifyContent: "center", fontSize: 13, fontWeight: 900, zIndex: 2
                              }}>✓</div>
                            )}
                            {/* Preferito (richiesta Enzo 03/07/2026): marca il
                                prodotto come da inserire SEMPRE in tutte e 4 le
                                stagioni, senza doverlo ricercare ogni volta. */}
                            <button
                              onClick={e => { e.stopPropagation(); togglePreferito(prod); }}
                              title={preferiti.has(prod.id) ? "Preferito colazione — tocca per togliere" : "Segna come preferito colazione (va in tutte le stagioni)"}
                              style={{
                                position: "absolute", top: 5, left: 5, zIndex: 2,
                                width: 22, height: 22, borderRadius: "50%", border: "none",
                                background: preferiti.has(prod.id) ? "#fff" : "rgba(0,0,0,0.35)",
                                color: preferiti.has(prod.id) ? "var(--warning)" : "#fff",
                                fontSize: 13, cursor: "pointer", display: "flex",
                                alignItems: "center", justifyContent: "center"
                              }}>
                              {preferiti.has(prod.id) ? "★" : "☆"}
                            </button>
                            {fotoSrc(prod.foto_url) && (
                              <img src={fotoSrc(prod.foto_url)} alt={prod.nome}
                                onError={(e) => { e.target.style.display = "none"; }}
                                style={{ width: "100%", height: 80, objectFit: "cover", objectPosition: "center", background: "#faf7f0" }} />
                            )}
                            <div style={{ padding: "8px 10px" }}>
                              {prod.fonte === "casa" && (
                                <p style={{ margin: "0 0 2px", fontSize: 9, fontWeight: 800, color: "var(--success-text, #234d3d)", textTransform: "uppercase", letterSpacing: 0.3 }}>
                                  🏠 fatto in casa
                                </p>
                              )}
                              <p style={{ margin: 0, fontSize: 12, fontWeight: 700, color: "#1e293b", lineHeight: 1.3 }}>
                                {prod.nome}
                              </p>
                              {prod.fonte !== "casa" && prod.gia_acquistato === false && !inTemplate && (
                                <p style={{ margin: "2px 0 0", fontSize: 10, color: "#94a3b8", fontWeight: 600 }}>
                                  mai acquistato
                                </p>
                              )}
                              {inTemplate && (
                                <p style={{ margin: "2px 0 0", fontSize: 11, color: "var(--warning-text)", fontWeight: 700 }}>
                                  {inTemplate.pezzi} pz
                                </p>
                              )}
                            </div>
                          </div>
                        );
                      })}
                  </div>

                  {/* Template corrente */}
                  {template.items.length > 0 && (
                    <>
                      <p style={{ margin: "0 0 8px", fontSize: 12, fontWeight: 700, color: "#6b7280", textTransform: "uppercase" }}>
                        Nel menù ({template.items.length} prodotti) — regola le quantità del mattino
                      </p>
                      <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 12 }}>
                        {template.items.map(item => (
                          <div key={item.prodotto_id} style={{
                            display: "flex", alignItems: "center", gap: 10,
                            padding: "10px 12px", background: "#fff",
                            borderRadius: 12, border: "2px solid #e5e7eb"
                          }}>
                            <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: "#1e293b" }}>
                              {item.prodotto_nome}
                            </span>
                            {/* Quantità */}
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              <button onClick={e => { e.stopPropagation(); setPezzi(item.prodotto_id, (item.pezzi||1) - 1); }}
                                style={{ width: 32, height: 32, borderRadius: 8, border: "2px solid #e5e7eb", background: "#f1f5f9", fontWeight: 900, cursor: "pointer", fontSize: 16 }}>
                                −
                              </button>
                              <input
                                type="number" value={item.pezzi} min={1}
                                onChange={e => setPezzi(item.prodotto_id, e.target.value)}
                                onClick={e => e.stopPropagation()}
                                style={{ width: 46, textAlign: "center", border: "2px solid #e5e7eb", borderRadius: 8, padding: "4px 0", fontWeight: 800, fontSize: 15 }}
                              />
                              <button onClick={e => { e.stopPropagation(); setPezzi(item.prodotto_id, (item.pezzi||1) + 1); }}
                                style={{ width: 32, height: 32, borderRadius: 8, border: "2px solid #e5e7eb", background: "#f1f5f9", fontWeight: 900, cursor: "pointer", fontSize: 16 }}>
                                +
                              </button>
                            </div>
                            {/* Rimuovi */}
                            <button onClick={() => toggleProdotto({ id: item.prodotto_id })}
                              style={{ background: "var(--danger-soft)", border: "none", color: "var(--danger)", borderRadius: 8, width: 32, height: 32, fontWeight: 900, cursor: "pointer", fontSize: 16 }}>
                              ✕
                            </button>
                          </div>
                        ))}
                      </div>

                      <button onClick={salvaTemplate} disabled={saving}
                        style={{
                          width: "100%", padding: "14px",
                          background: "linear-gradient(135deg, var(--warning-text), var(--warning-dark))",
                          color: "#fff", border: "none", borderRadius: 14,
                          fontSize: 15, fontWeight: 800, cursor: "pointer",
                          opacity: saving ? 0.7 : 1
                        }}>
                        {saving ? "Salvataggio..." : "✓ Salva menù e torna alla colazione"}
                      </button>
                    </>
                  )}
                </>
              )}

              {/* MODALITA AVVIA: solo prodotti nel template, con spunta grande e +/- */}
              {modalita === "avvia" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {prodottiInTemplate.map(prod => {
                    const item = getItem(prod.id);
                    if (!item) return null;
                    const isAttivo = item.attivo !== false;
                    return (
                      <div key={prod.id} style={{
                        display: "flex", alignItems: "center", gap: 12,
                        padding: "12px 14px",
                        background: isAttivo ? "#fff" : "#f8fafc",
                        borderRadius: 16,
                        border: `2px solid ${isAttivo ? "var(--warning)" : "#e2e8f0"}`,
                        boxShadow: isAttivo ? "0 2px 10px rgba(245,158,11,0.15)" : "none",
                        opacity: isAttivo ? 1 : 0.55,
                        transition: "all 0.15s"
                      }}>
                        {/* Foto */}
                        <div style={{
                          width: 52, height: 52, borderRadius: 10, flexShrink: 0, overflow: "hidden",
                          background: "var(--warning-soft)", display: "flex", alignItems: "center",
                          justifyContent: "center", fontSize: 22
                        }}>
                          {fotoSrc(prod.foto_url)
                            ? <img src={fotoSrc(prod.foto_url)} alt={prod.nome}
                                onError={(e) => { e.target.style.display = "none"; e.target.parentNode.innerHTML = "🧁"; }}
                                style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "center" }} />
                            : "🧁"}
                        </div>

                        {/* Nome */}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <p style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1e293b", lineHeight: 1.3 }}>
                            {item.prodotto_nome}
                          </p>
                          {item.prezzo_vendita > 0 && (
                            <p style={{ margin: "2px 0 0", fontSize: 11, color: "var(--warning-text)", fontWeight: 600 }}>
                              €{((item.prezzo_vendita || 0) * item.pezzi).toFixed(2)} valore
                            </p>
                          )}
                        </div>

                        {/* Controllo quantità */}
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <button onClick={() => setPezzi(item.prodotto_id, (item.pezzi||1) - 1)}
                            style={{
                              width: 36, height: 36, borderRadius: 10, border: "2px solid #e5e7eb",
                              background: "#f1f5f9", fontWeight: 900, cursor: "pointer", fontSize: 18, flexShrink: 0
                            }}>−</button>
                          <span style={{ fontSize: 18, fontWeight: 900, color: "#1e293b", minWidth: 30, textAlign: "center" }}>
                            {item.pezzi}
                          </span>
                          <button onClick={() => setPezzi(item.prodotto_id, (item.pezzi||1) + 1)}
                            style={{
                              width: 36, height: 36, borderRadius: 10, border: "2px solid #e5e7eb",
                              background: "#f1f5f9", fontWeight: 900, cursor: "pointer", fontSize: 18, flexShrink: 0
                            }}>+</button>
                        </div>

                        {/* Spunta grande */}
                        <button
                          onClick={() => toggleAttivo(item.prodotto_id)}
                          style={{
                            width: 44, height: 44, borderRadius: 12, flexShrink: 0,
                            border: `3px solid ${isAttivo ? "var(--warning)" : "#d1d5db"}`,
                            background: isAttivo ? "var(--warning)" : "#fff",
                            color: isAttivo ? "#fff" : "#9ca3af",
                            fontSize: 20, fontWeight: 900, cursor: "pointer",
                            display: "flex", alignItems: "center", justifyContent: "center"
                          }}>
                          {isAttivo ? "✓" : ""}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>

        {/* ── Footer con bottone Avvia ── */}
        {modalita === "avvia" && attivi.length > 0 && (
          <div style={{
            padding: "14px 16px",
            background: "#fff",
            borderTop: "2px solid #e5e7eb"
          }}>
            <button onClick={avviaColazione} disabled={registrando}
              data-testid="avvia-colazione-btn"
              style={{
                width: "100%", padding: "18px",
                background: registrando ? "#d1d5db" : "linear-gradient(135deg, var(--warning-text), var(--warning-dark))",
                color: "#fff", border: "none", borderRadius: 16,
                fontSize: 17, fontWeight: 900, cursor: registrando ? "not-allowed" : "pointer",
                boxShadow: registrando ? "none" : "0 4px 20px rgba(146,64,14,0.35)"
              }}>
              {registrando
                ? "Registrazione in corso..."
                : `Avvia Colazione — ${attivi.length} prodotti, ${totPezzi} pezzi`
              }
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ColazioneAcquavivaView;
