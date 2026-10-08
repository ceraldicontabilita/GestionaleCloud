import React, { useState, useEffect, useCallback } from "react";
import { conferma } from "../../utils/conferma";
import { apiError } from "../../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import { API, BACKEND_URL } from "../../utils/constants";
import { apriDocumentoAutenticato, loginGestionale } from "../../auth";
import { ChevronRight, X } from "lucide-react";
import CatalogoColazione from "./CatalogoColazione";

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
  const [erroreCaricamento, setErroreCaricamento] = useState("");
  const [saving, setSaving]           = useState(false);
  const [registrando, setRegistrando] = useState(false);
  const [risultato, setRisultato]     = useState(null);
  const [search, setSearch]           = useState("");
  const [modalita, setModalita]       = useState(() => window.location.hash.includes("/colazione/configura") ? "configura" : "avvia");
  const [modificaPeriodo, setModificaPeriodo] = useState(false);
  const [periodoForm, setPeriodoForm] = useState({ data_inizio: "", data_fine: "" });
  // Rete di sicurezza (23/07/2026): se un prodotto comprato non viene
  // riconosciuto dal matching, questa spunta mostra TUTTO il catalogo.
  const [aggiungendoStagioni, setAggiungendoStagioni] = useState(null);
  const salvatoRef = React.useRef("");
  const operazioneRef = React.useRef(false);
  const [popolandoAcquisti, setPopolandoAcquisti] = useState(false);
  // Doppia fonte: coppie dichiarate dal titolare (Acquaviva o nostra produzione) e scelta di oggi
  const [coppie, setCoppie]           = useState([]);
  const [scelteOggi, setScelteOggi]   = useState({});
  const [sceltaAperta, setSceltaAperta] = useState(null); // coppia in attesa di scelta
  // La lista scorre: quando cambia la ricerca si torna in cima (23/07/2026:
  // "se faccio cerca esco giù a tutto")
  const listaRef = React.useRef(null);
  const modificheNonSalvate = () => !!salvatoRef.current && JSON.stringify(template) !== salvatoRef.current;
  const lasciaPagina = async (azione) => {
    if (operazioneRef.current || saving || registrando) return;
    if (modificheNonSalvate() && !await conferma("Uscire senza salvare le modifiche?", { titolo: "Modifiche non salvate", ok: "Esci senza salvare" })) return;
    azione();
  };
  const naviga = (hash) => lasciaPagina(() => { window.location.hash = hash; });
  useEffect(() => { listaRef.current?.scrollTo?.({ top: 0 }); }, [search]);

  // Carica un preset specifico (stagione)
  const caricaPreset = useCallback(async (nome) => {
    try {
      const res = await axios.get(`${API}/colazione-acquaviva`, { params: { nome } });
      const letto = res.data?.items ? res.data : { nome, items: [], note: "" };
      setTemplate(letto);
      salvatoRef.current = JSON.stringify(letto);
    } catch (e) {
      setErroreCaricamento(apiError(e));
      throw e;
    }
  }, []);

  const caricaCoppie = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/colazione-acquaviva/coppie`);
      setCoppie(r.data?.coppie || []);
      setScelteOggi(r.data?.scelte_oggi || {});
    } catch (e) {
      toast.error("Doppia fonte non disponibile: " + apiError(e));
    }
  }, []);

  const coppiaDi = (prodottoId) => coppie.find(c =>
    String(c.ricetta_id) === String(prodottoId) || (c.acquaviva_ids || []).map(String).includes(String(prodottoId)));

  const scegliFonte = async (coppia, fonte) => {
    try {
      await axios.post(`${API}/colazione-acquaviva/scelta-fonte`, { coppia_id: coppia.id, fonte });
      setScelteOggi(prev => ({ ...prev, [coppia.id]: fonte }));
      setSceltaAperta(null);
    } catch (e) {
      toast.error("Scelta non salvata: " + apiError(e));
    }
  };

  const carica = useCallback(async () => {
    setLoading(true);
    setErroreCaricamento("");
    try {
      const [resProdotti, resPreset, resStagioneAttiva] = await Promise.all([
        axios.get(`${API}/colazione-acquaviva/prodotti-disponibili?catalogo=true&solo_acquistati=false&includi_rosticceria=true`),
        axios.get(`${API}/colazione-acquaviva/preset`),
        axios.get(`${API}/colazione-acquaviva/stagione-attiva`),
      ]);
      setProdottiDisponibili(resProdotti.data || []);
      const lista = resPreset.data || [];
      setPresetList(lista);
      // Pre-seleziona la stagione il cui periodo (equinozi/solstizi, modificabili)
      // contiene la data di oggi — niente più scelta manuale ogni mattina.
      const stagioneOggi = resStagioneAttiva?.data?.stagione;
      const primo = (stagioneOggi && lista.some(p => p.nome === stagioneOggi))
        ? stagioneOggi : lista[0]?.nome;
      if (!primo) throw new Error("Nessuna stagione disponibile: verifica i menu colazione.");
      setPresetSel(primo);
      await caricaPreset(primo);
      await caricaCoppie();
    } catch (e) {
      setErroreCaricamento(apiError(e));
      toast.error("Errore caricamento: " + apiError(e));
    } finally {
      setLoading(false);
    }
  }, [caricaPreset, caricaCoppie]);

  const aggiungiTutteStagioni = async (prod) => {
    if (operazioneRef.current || prod.ammesso_colazione === false) return;
    const modificato = JSON.stringify(template) !== salvatoRef.current;
    operazioneRef.current = true;
    if (!await conferma(`Aggiungere “${prod.nome}” alle quattro stagioni?\n\nLe quantità già impostate restano invariate. Dove manca, verrà aggiunto con 6 pezzi, modificabili.${modificato ? "\nVerranno salvate anche le modifiche di questa stagione." : ""}`, { titolo: "Un prodotto in tutte le stagioni", ok: "Aggiungi alle 4 stagioni" })) { operazioneRef.current = false; return; }
    setAggiungendoStagioni(prod.id);
    try {
      if (modificato) {
        await axios.put(`${API}/colazione-acquaviva`, { ...template, nome: presetSel });
        salvatoRef.current = JSON.stringify(template);
      }
      const res = await axios.post(`${API}/colazione-acquaviva/preferito`, {
        azione: "aggiungi",
        prodotto_id: prod.id,
        prodotto_nome: prod.nome,
        foto_url: prod.foto_url || null,
        categoria: prod.categoria || null,
        prezzo_vendita: prod.prezzo_vendita || 0,
        fonte: prod.fonte || null,
      });
      if (res.data.preferito) {
        toast.success(`${prod.nome} presente in tutte e 4 le stagioni`);
        const resPreset = await axios.get(`${API}/colazione-acquaviva/preset`);
        setPresetList(resPreset.data || []);
        if (presetSel) await caricaPreset(presetSel);
      }
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    } finally { operazioneRef.current = false; setAggiungendoStagioni(null); }
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
    if (saving || operazioneRef.current) return;
    if (JSON.stringify(template) !== salvatoRef.current && !await conferma("Cambiare stagione senza salvare le modifiche?", { titolo: "Modifiche non salvate", ok: "Cambia senza salvare" })) return;
    setLoading(true);
    setErroreCaricamento("");
    try {
      await caricaPreset(nome);
      setPresetSel(nome);
      setRisultato(null);
    } catch (e) { toast.error("Stagione non disponibile: " + apiError(e)); }
    finally { setLoading(false); }
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
    if (operazioneRef.current || prod.ammesso_colazione === false) return;
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
    if (operazioneRef.current || loading || erroreCaricamento || !presetSel) return;
    operazioneRef.current = true;
    setSaving(true);
    try {
      await axios.put(`${API}/colazione-acquaviva`, { ...template, nome: presetSel });
      toast.success(`Menù "${presetSel}" salvato!`);
      salvatoRef.current = JSON.stringify(template);
      // Menù sistemato → si torna alla schermata del mattino (un passaggio in meno)
      setModalita("avvia");
    } catch (e) {
      toast.error("Errore salvataggio");
    } finally {
      setSaving(false);
      operazioneRef.current = false;
    }
  };

  // ── Avvia colazione → manda tutto al banco ──────────────────────────────────
  const avviaColazione = async () => {
    if (registrando || loading || erroreCaricamento || !presetSel) return;
    const attivi = template.items.filter(i => i.attivo);
    if (attivi.length === 0) { toast.error("Seleziona almeno un prodotto"); return; }
    const senzaScelta = attivi.map(i => coppiaDi(i.prodotto_id)).filter(c => c && !scelteOggi[c.id]);
    if (senzaScelta.length) {
      toast.error(`Scegli Acquaviva o nostra produzione per ${senzaScelta[0].nome}`);
      setSceltaAperta(senzaScelta[0]);
      return;
    }
    setRegistrando(true);
    try {
      await axios.put(`${API}/colazione-acquaviva`, { ...template, nome: presetSel });
      const res = await axios.post(`${API}/colazione-acquaviva/registra`, { nome: presetSel });
      setRisultato(res.data);
      if (res.data?.errori?.length) toast.error("Registrazione parziale: controlla i prodotti non registrati.");
      else toast.success(`Colazione avviata: ${res.data.prodotti_registrati} prodotti, ${res.data.pezzi_totali} pezzi`);
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

  useEffect(() => {
    const precedente = document.title;
    document.title = `Lotti · Colazione · ${modalita === "configura" ? "Menu stagionale" : "Preparazione del mattino"}${presetSel ? ` · ${presetSel}` : ""}`;
    return () => { document.title = precedente; };
  }, [modalita, presetSel]);

  const tornaAlMattino = async () => {
    if (JSON.stringify(template) !== salvatoRef.current) { await salvaTemplate(); return; }
    setModalita("avvia");
  };

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
            {risultato.errori?.length ? "Registrazione parziale" : "Colazione registrata"}
          </h2>
          <p style={{ color: "#6b7669", margin: "0 0 24px", fontSize: 14 }}>{risultato.data}</p>
          {risultato.errori?.length > 0 && <div role="alert"><p>Non ripetere tutta la produzione: questi prodotti non sono stati registrati.</p>{risultato.errori.map((e,i)=><p key={i}>{e.nome}: {e.errore}</p>)}</div>}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
            <div style={{ background: "#f0fdf4", borderRadius: 14, padding: "14px", border: "2px solid #bbf7d0" }}>
              <p style={{ margin: 0, fontSize: 32, fontWeight: 900, color: "var(--success)" }}>{risultato.prodotti_registrati}</p>
              <p style={{ margin: 0, fontSize: 11, color: "#6b7669", fontWeight: 700 }}>PRODOTTI</p>
            </div>
            <div style={{ background: "#fff7ed", borderRadius: 14, padding: "14px", border: "2px solid #fed7aa" }}>
              <p style={{ margin: 0, fontSize: 32, fontWeight: 900, color: "#ea580c" }}>{risultato.pezzi_totali}</p>
              <p style={{ margin: 0, fontSize: 11, color: "#6b7669", fontWeight: 700 }}>PEZZI</p>
            </div>
          </div>

          <div style={{ background: "#f0fdf4", borderRadius: 14, padding: "14px", marginBottom: 20, border: "2px solid #bbf7d0" }}>
            <p style={{ margin: 0, fontSize: 26, fontWeight: 900, color: "var(--success-dark)" }}>
              €{(risultato.valore_totale || 0).toFixed(2)}
            </p>
            <p style={{ margin: 0, fontSize: 11, color: "#6b7669", fontWeight: 700 }}>VALORE TOTALE AL BANCO</p>
          </div>

          <div style={{ textAlign: "left", maxHeight: 180, overflowY: "auto", marginBottom: 20 }}>
            {risultato.registrati?.map((r, i) => (
              <div key={i} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "8px 0", borderBottom: "1px solid #faf7f0"
              }}>
                <span style={{ fontSize: 13, color: "#495247", fontWeight: 600 }}>{r.nome}</span>
                <span style={{ fontSize: 13, color: "#6b7669", fontWeight: 700 }}>{r.pezzi} pz</span>
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
        maxWidth: modoTablet ? "100%" : 1100,
        alignSelf: "center", width: modoTablet ? "100%" : "calc(100% - 32px)"
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
          <nav aria-label="Percorso Colazione" className="colazione-percorso">
            <a href="#tablet/home" onClick={e => { e.preventDefault(); naviga("tablet/home"); }}>Reparti</a><ChevronRight size={14} />
            <a href="#tablet/pasticceria" onClick={e => { e.preventDefault(); naviga("tablet/pasticceria"); }}>Pasticceria</a><ChevronRight size={14} />
            <span>Colazione</span><ChevronRight size={14} />
            <span aria-current="page">{modalita === "configura" ? "Menu stagionale" : "Preparazione del mattino"}{presetSel ? ` · ${presetSel}` : ""}</span>
          </nav>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
            <div style={{ minWidth: 0 }}>
              <h2 style={{ color: "#fff", margin: 0, fontSize: 20, fontWeight: 800 }}>
                {modalita === "avvia" ? "Colazione" : "Menù colazione"}{presetSel ? ` · ${presetSel}` : ""}
              </h2>
              <p style={{ color: "rgba(255,255,255,0.8)", margin: "2px 0 0", fontSize: 12 }}>
                {loading ? "Caricamento della stagione…" : erroreCaricamento ? "Dati non disponibili" : `${attivi.length} prodotti · ${totPezzi} pezzi · €${totValore.toFixed(2)}`}
              </p>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
              {modalita === "avvia" ? (
                <button disabled={loading || !!erroreCaricamento} onClick={() => setModalita("configura")} style={{
                  background: "rgba(255,255,255,0.16)", border: "2px solid rgba(255,255,255,0.5)",
                  color: "#fff", borderRadius: 10, padding: "8px 14px",
                  fontWeight: 800, cursor: "pointer", fontSize: 13
                }}>⚙️ Modifica menù</button>
              ) : (
                <button onClick={tornaAlMattino} disabled={saving || !!aggiungendoStagioni} style={{
                  background: "#fff", border: "none",
                  color: "var(--warning-text)", borderRadius: 10, padding: "8px 14px",
                  fontWeight: 800, cursor: "pointer", fontSize: 13
                }}>← Torna alla colazione</button>
              )}
              {onClose && (
                <button aria-label="Chiudi Colazione" onClick={() => lasciaPagina(onClose)} style={{
                  background: "rgba(255,255,255,0.2)", border: "none",
                  color: "#fff", borderRadius: 10, padding: "8px 14px",
                  fontWeight: 700, cursor: "pointer", fontSize: 16
                }}><X size={20} /></button>
              )}
            </div>
          </div>

          {/* Gestione stagioni: SOLO in modalità menù */}
          {modalita === "configura" && !loading && !erroreCaricamento && (
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
              </div>
              <details style={{ marginTop: 10, color: "#fff" }}>
                <summary style={{ minHeight: 44, cursor: "pointer", display: "flex", alignItems: "center", fontWeight: 700 }}>Altre opzioni stagioni</summary>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
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
                  onClick={() => apriDocumentoAutenticato(`${API}/acquaviva/export-foto-zip`, { scarica: true })}
                  title="Scarica uno zip con le foto dei prodotti Acquaviva, ogni file col nome del prodotto"
                  style={{
                    padding: "6px 12px", borderRadius: 999, fontWeight: 800, fontSize: 12, cursor: "pointer",
                    border: "2px solid rgba(255,255,255,0.6)", background: "rgba(255,255,255,0.12)", color: "#fff"
                  }}>⬇️ Zip foto Acquaviva</button>
                </div>
              </details>

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
        {modalita === "avvia" && !erroreCaricamento && <div style={{ padding: "10px 14px", borderBottom: "1px solid #e6e0d4", background: "#fafafa" }}>
          <input
            type="text" placeholder="Cerca prodotto..."
            value={search} onChange={e => setSearch(e.target.value)}
            style={{
              width: "100%", padding: "10px 14px", borderRadius: 10,
              border: "2px solid #e6e0d4", fontSize: 14, outline: "none",
              boxSizing: "border-box"
            }}
          />
          {modalita === "avvia" && prodottiInTemplate.length === 0 && !loading && (
            <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--warning-text)", fontWeight: 600 }}>
              Nessun prodotto in questo menù. Tocca <b>⚙️ Modifica menù</b> in alto per aggiungerne.
            </p>
          )}
        </div>}

        {/* ── Lista prodotti ── */}
        <div ref={listaRef} style={{ flex: 1, overflowY: "auto", padding: "10px 12px" }}>
          {loading ? (
            <div style={{ textAlign: "center", padding: 60, color: "#9aa593" }}>Caricamento...</div>
          ) : erroreCaricamento ? (
            <div role="alert" style={{ padding: 24, background: "var(--warning-soft)", borderRadius: 12 }}>
              <h3>Impossibile caricare la colazione</h3>
              <p>{erroreCaricamento}</p><p>Questo non significa che i prodotti siano stati eliminati.</p>
              <button onClick={carica} style={{ minHeight: 44 }}>Riprova</button>{" "}
              <a href={loginGestionale()}>Rifai l'accesso</a>
            </div>
          ) : (
            <>
              {/* MODALITA CONFIGURA: tutti i prodotti con toggle aggiungi/rimuovi */}
              {modalita === "configura" && (
                <>
                  <CatalogoColazione prodotti={prodottiDisponibili} template={template} stagione={presetSel}
                    onNavigate={naviga}
                    fotoSrc={fotoSrc} onToggle={toggleProdotto} onTutteStagioni={aggiungiTutteStagioni} busy={aggiungendoStagioni} />

                  {/* Template corrente */}
                  {(
                    <>
                      <p style={{ margin: "0 0 8px", fontSize: 12, fontWeight: 700, color: "#6b7669", textTransform: "uppercase" }}>
                        Nel menù ({template.items.length} prodotti) — regola le quantità del mattino
                      </p>
                      <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 12 }}>
                        {template.items.map(item => (
                          <div key={item.prodotto_id} style={{
                            display: "flex", alignItems: "center", gap: 10,
                            padding: "10px 12px", background: "#fff",
                            borderRadius: 12, border: "2px solid #e6e0d4"
                          }}>
                            <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: "#3f5a4e" }}>
                              {item.prodotto_nome}
                            </span>
                            {/* Quantità */}
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              <button onClick={e => { e.stopPropagation(); setPezzi(item.prodotto_id, (item.pezzi||1) - 1); }}
                                style={{ width: 32, height: 32, borderRadius: 8, border: "2px solid #e6e0d4", background: "#faf7f0", fontWeight: 900, cursor: "pointer", fontSize: 16 }}>
                                −
                              </button>
                              <input
                                type="number" value={item.pezzi} min={1}
                                onChange={e => setPezzi(item.prodotto_id, e.target.value)}
                                onClick={e => e.stopPropagation()}
                                style={{ width: 46, textAlign: "center", border: "2px solid #e6e0d4", borderRadius: 8, padding: "4px 0", fontWeight: 800, fontSize: 15 }}
                              />
                              <button onClick={e => { e.stopPropagation(); setPezzi(item.prodotto_id, (item.pezzi||1) + 1); }}
                                style={{ width: 32, height: 32, borderRadius: 8, border: "2px solid #e6e0d4", background: "#faf7f0", fontWeight: 900, cursor: "pointer", fontSize: 16 }}>
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
                        background: isAttivo ? "#fff" : "#faf7f0",
                        borderRadius: 16,
                        border: `2px solid ${isAttivo ? "var(--warning)" : "#e6e0d4"}`,
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
                        <div style={{ flex: 1, minWidth: 0, cursor: coppiaDi(item.prodotto_id) ? "pointer" : "default" }}
                          onClick={() => { const c = coppiaDi(item.prodotto_id); if (c) setSceltaAperta(c); }}>
                          <p style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#3f5a4e", lineHeight: 1.3 }}>
                            {(() => { const c = coppiaDi(item.prodotto_id); const f = c && scelteOggi[c.id];
                              return f === "acquaviva" ? (c.acquaviva_nome || item.prodotto_nome) : f === "casa" ? (c.nome || item.prodotto_nome) : item.prodotto_nome; })()}
                          </p>
                          {(() => { const c = coppiaDi(item.prodotto_id); if (!c) return null; const f = scelteOggi[c.id];
                            return <p style={{ margin: "2px 0 0", fontSize: 12, fontWeight: 800, color: f ? "var(--success)" : "var(--warning-text)" }}>
                              {f === "acquaviva" ? "Di Acquaviva" : f === "casa" ? "Nostra produzione" : "Tocca per scegliere: Acquaviva o nostra produzione"}
                            </p>; })()}
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
                              width: 36, height: 36, borderRadius: 10, border: "2px solid #e6e0d4",
                              background: "#faf7f0", fontWeight: 900, cursor: "pointer", fontSize: 18, flexShrink: 0
                            }}>−</button>
                          <span style={{ fontSize: 18, fontWeight: 900, color: "#3f5a4e", minWidth: 30, textAlign: "center" }}>
                            {item.pezzi}
                          </span>
                          <button onClick={() => setPezzi(item.prodotto_id, (item.pezzi||1) + 1)}
                            style={{
                              width: 36, height: 36, borderRadius: 10, border: "2px solid #e6e0d4",
                              background: "#faf7f0", fontWeight: 900, cursor: "pointer", fontSize: 18, flexShrink: 0
                            }}>+</button>
                        </div>

                        {/* Spunta grande */}
                        <button
                          onClick={() => toggleAttivo(item.prodotto_id)}
                          style={{
                            width: 44, height: 44, borderRadius: 12, flexShrink: 0,
                            border: `3px solid ${isAttivo ? "var(--warning)" : "#c7cfc2"}`,
                            background: isAttivo ? "var(--warning)" : "#fff",
                            color: isAttivo ? "#fff" : "#9aa593",
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

        {sceltaAperta && (
          <div role="dialog" aria-modal="true" aria-label="Scegli la fonte" onClick={() => setSceltaAperta(null)}
            style={{ position: "fixed", inset: 0, background: "rgba(42,51,41,0.55)", zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}>
            <div onClick={e => e.stopPropagation()} style={{ background: "#fffefb", borderRadius: 20, padding: 20, width: "100%", maxWidth: 420 }}>
              <p style={{ margin: "0 0 4px", fontSize: 18, fontWeight: 800, color: "#2a3329" }}>{sceltaAperta.nome}</p>
              <p style={{ margin: "0 0 14px", fontSize: 14, color: "#6b7669" }}>Questa mattina è di Acquaviva o di nostra produzione?</p>
              <button onClick={() => scegliFonte(sceltaAperta, "acquaviva")}
                style={{ width: "100%", minHeight: 56, marginBottom: 10, borderRadius: 14, border: "none", background: "var(--warning)", color: "#fff", fontSize: 16, fontWeight: 800, cursor: "pointer" }}>
                Di Acquaviva · {sceltaAperta.acquaviva_nome}
              </button>
              <button onClick={() => scegliFonte(sceltaAperta, "casa")}
                style={{ width: "100%", minHeight: 56, marginBottom: 10, borderRadius: 14, border: "none", background: "#3f5a4e", color: "#fff", fontSize: 16, fontWeight: 800, cursor: "pointer" }}>
                Nostra produzione
              </button>
              <button onClick={() => setSceltaAperta(null)}
                style={{ width: "100%", minHeight: 44, borderRadius: 14, border: "2px solid #e6e0d4", background: "#faf7f0", color: "#3f5a4e", fontSize: 14, fontWeight: 700, cursor: "pointer" }}>
                Annulla
              </button>
            </div>
          </div>
        )}

        {/* ── Footer con bottone Avvia ── */}
        {modalita === "avvia" && !loading && !erroreCaricamento && attivi.length > 0 && (
          <div style={{
            padding: "14px 16px",
            background: "#fff",
            borderTop: "2px solid #e6e0d4"
          }}>
            <button onClick={avviaColazione} disabled={registrando}
              data-testid="avvia-colazione-btn"
              style={{
                width: "100%", padding: "18px",
                background: registrando ? "#c7cfc2" : "linear-gradient(135deg, var(--warning-text), var(--warning-dark))",
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
