import React, { useState, useEffect, useRef } from "react";
import { apiError } from "../../../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import { API } from "../../../utils/constants";
import { stampaDoc } from "../../../utils/stampa";
import SelettoreQuantita from "./registraLotto/SelettoreQuantita";
import SelettorePosizione from "./registraLotto/SelettorePosizione";

export function ModalRegistraLotto({ prodotto, reparto, onClose, onSuccess, onHome, onRefreshLista, frigoriferi = [], congelatori = [] }) {
  const [pezzi, setPezzi]               = useState(1);
  const [unita, setUnita]               = useState("pz");
  const [frigo, setFrigo]               = useState("");
  const [destinazione, setDestinazione] = useState("frigo");
  // Scrittura libera della posizione: serve solo per un apparecchio non ancora
  // censito. Il caso normale è SCEGLIERE dall'elenco (vedi selettore sotto).
  const [posizioneAMano, setPosizioneAMano] = useState(false);
  const [stampare, setStampare]         = useState(true);
  const [loading, setLoading]           = useState(false);
  const [lottoCreato, setLottoCreato]   = useState(null);
  const [codiceLottoPreview, setCodiceLottoPreview] = useState(null);

  // ── Posizione obbligatoria con blocco morbido (decisione Enzo 04/07/2026):
  // frigo/abbattitore senza apparecchio indicato blocca la registrazione a
  // meno che l'operatore non confermi esplicitamente di voler procedere
  // comunque — stesso principio già usato per la giacenza (soft block, mai
  // impedimento definitivo: in cucina può esserci un motivo legittimo).
  const [confermaSenzaPosizione, setConfermaSenzaPosizione] = useState(false);

  // ── Giacenza già in frigo/abbattitore (richiesta Enzo 03/07/2026): prima
  // di far produrre di nuovo, mostra cosa c'è già e lascia mandarlo al banco.
  const [giacenzaLotti, setGiacenzaLotti] = useState(prodotto.giacenza_lotti || []);
  const [confermaComunque, setConfermaComunque] = useState(false);
  const [mandandoId, setMandandoId] = useState(null);
  const [mandandoTutto, setMandandoTutto] = useState(false);
  // Quantità scelta per ciascun lotto in giacenza (richiesta Enzo 03/07/2026:
  // "ne ho 301 ma ne voglio mandare solo 24" — non sempre tutto il lotto).
  // Default = intero lotto (tap singolo resta il caso comune).
  const [mandaQty, setMandaQty] = useState(() => {
    const q = {};
    (prodotto.giacenza_lotti || []).forEach(l => { q[l.id] = l.quantita; });
    return q;
  });
  const giacenzaTotale = giacenzaLotti.reduce((s, l) => s + (l.quantita || 0), 0);
  const bloccatoDaGiacenza = giacenzaTotale > 0 && !confermaComunque;
  const posizioneMancante = (destinazione === "frigo" || destinazione === "abbattitore") && !frigo.trim();
  const bloccatoDaPosizioneMancante = posizioneMancante && !confermaSenzaPosizione;

  // ── Farciture (richiesta Enzo 03/07/2026): per prodotti-base come
  // "Cornetto Vuoto", dividi la giacenza nei gusti secondo Colazione invece
  // di mandarla al banco tutta com'è.
  const [farcituraConf, setFarcituraConf] = useState(null); // {disponibile, gusti}
  const [stagioni, setStagioni] = useState([]);
  const [farcituraApertaId, setFarcituraApertaId] = useState(null);
  const [stagioneSel, setStagioneSel] = useState("");
  const [divisione, setDivisione] = useState({});
  const [caricandoAnteprima, setCaricandoAnteprima] = useState(false);
  const [confermandoFarcitura, setConfermandoFarcitura] = useState(false);

  useEffect(() => {
    if (!prodotto?.nome) return;
    axios.get(`${API}/farciture/prodotto-base/${encodeURIComponent(prodotto.nome)}`)
      .then(r => setFarcituraConf(r.data))
      .catch(() => setFarcituraConf({ disponibile: false }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prodotto?.nome]);

  const caricaAnteprimaDivisione = async (lotto, qty, stagione) => {
    setCaricandoAnteprima(true);
    try {
      const res = await axios.get(`${API}/farciture/anteprima-divisione`, {
        params: { prodotto_base_nome: prodotto.nome, pezzi: qty, stagione },
      });
      setDivisione(res.data.divisione || {});
    } catch (e) {
      toast.error("Errore: " + apiError(e));
      setDivisione({});
    } finally {
      setCaricandoAnteprima(false);
    }
  };

  const apriFarcitura = async (lotto) => {
    setFarcituraApertaId(lotto.id);
    let stag = stagioneSel;
    if (!stagioni.length) {
      try {
        const res = await axios.get(`${API}/colazione-acquaviva/preset`);
        const lista = res.data || [];
        setStagioni(lista);
        stag = lista[0]?.nome || "";
        setStagioneSel(stag);
      } catch (e) {
        toast.error("Errore caricamento stagioni: " + apiError(e));
        return;
      }
    }
    await caricaAnteprimaDivisione(lotto, mandaQty[lotto.id] ?? lotto.quantita, stag);
  };

  const cambiaStagioneFarcitura = async (lotto, nomeStagione) => {
    setStagioneSel(nomeStagione);
    await caricaAnteprimaDivisione(lotto, mandaQty[lotto.id] ?? lotto.quantita, nomeStagione);
  };

  const setDivisioneGusto = (gusto, val) => {
    setDivisione(prev => ({ ...prev, [gusto]: Math.max(0, parseInt(val, 10) || 0) }));
  };

  const confermaFarcitura = async (lotto) => {
    const sessionOp = _operatoreSessione();
    setConfermandoFarcitura(true);
    try {
      const res = await axios.post(`${API}/farciture/${lotto.id}/dividi-e-manda-al-banco`, {
        prodotto_base_nome: prodotto.nome,
        stagione: stagioneSel,
        divisione,
        reparto,
        ...(sessionOp?.id && { operatore_id: sessionOp.id }),
        ...(sessionOp?.nome && { operatore_nome: sessionOp.nome }),
      });
      toast.success(`✓ ${res.data.pezzi_totali} ${prodotto.nome} divisi nei gusti e mandati al banco`);
      const restanti = giacenzaLotti
        .map(l => l.id === lotto.id ? { ...l, quantita: l.quantita - res.data.pezzi_totali } : l)
        .filter(l => l.quantita > 0);
      setGiacenzaLotti(restanti);
      setFarcituraApertaId(null);
      onRefreshLista && onRefreshLista();
      if (restanti.length === 0) setTimeout(onClose, 500);
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    } finally {
      setConfermandoFarcitura(false);
    }
  };

  // IDEMPOTENZA (tranche 4): id operazione stabile per tentativo — se la rete
  // rispedisce la richiesta, il backend riconosce il doppione e non riscala.
  const opIds = useRef({});
  const _opId = (chiave) => {
    if (!opIds.current[chiave]) {
      opIds.current[chiave] = (window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`);
    }
    return opIds.current[chiave];
  };
  const _opDone = (chiave) => { delete opIds.current[chiave]; };

  const _operatoreSessione = () => {
    try { return JSON.parse(sessionStorage.getItem("tablet_operatore") || "null"); } catch { return null; }
  };

  const _mandaUnLotto = (lotto, qty) => {
    const sessionOp = _operatoreSessione();
    return axios.post(`${API}/lotti/${lotto.id}/manda-al-banco`, null, {
      params: {
        pezzi: qty,
        reparto,
        operation_id: _opId(`banco_${lotto.id}`),
        ...(sessionOp?.id && { operatore_id: sessionOp.id }),
        ...(sessionOp?.nome && { operatore_nome: sessionOp.nome }),
      },
    });
  };

  const setQtyLotto = (lotto, qty) => {
    const q = Math.max(1, Math.min(lotto.quantita, Math.round(qty) || 1));
    setMandaQty(prev => ({ ...prev, [lotto.id]: q }));
  };

  // Stampa la distinta di movimentazione (DA quale frigo/congelatore → banco):
  // richiesta Enzo 20/07/2026, "manda al banco" registrava ma non confermava
  // né stampava da dove era stata presa la merce.
  const stampaMovimento = (movimentoId, numeroLotto) => {
    if (!movimentoId) return;
    stampaDoc({
      categoria: "etichette",
      url: `${API}/stampa/movimento/${movimentoId}`,
      formato: "html",
      titolo: `Movimento ${numeroLotto || movimentoId}`,
    }).catch(() => {});
  };

  const handleMandaAlBanco = async (lotto) => {
    const qty = mandaQty[lotto.id] ?? lotto.quantita;
    setMandandoId(lotto.id);
    try {
      const res = await _mandaUnLotto(lotto, qty);
      _opDone(`banco_${lotto.id}`);
      const d = res.data || {};
      const daDove = d.frigo_numero || lotto.frigo_numero || "";
      toast.success(
        `✓ ${qty}${lotto.unita_misura || "pz"} di ${prodotto.nome}${daDove ? ` da ${daDove}` : ""} mandati al banco — tracciabilità registrata`
      );
      if (stampare) stampaMovimento(d.movimento_id, d.numero_lotto);
      const resta = lotto.quantita - qty;
      const restanti = resta > 0
        ? giacenzaLotti.map(l => l.id === lotto.id ? { ...l, quantita: resta } : l)
        : giacenzaLotti.filter(l => l.id !== lotto.id);
      if (resta > 0) setMandaQty(prev => ({ ...prev, [lotto.id]: resta }));
      setGiacenzaLotti(restanti);
      onRefreshLista && onRefreshLista();
      // Giacenza svuotata: non c'è altro da fare qui, chiudi subito
      // (richiesta Enzo 03/07/2026: era troppo lento scaricare le produzioni).
      if (restanti.length === 0) setTimeout(onClose, 500);
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    } finally {
      setMandandoId(null);
    }
  };

  // "Manda tutto" — un solo tap invece di uno per lotto quando ce ne sono
  // più d'uno (es. avanzi di ieri + di oggi dello stesso prodotto).
  const handleMandaTuttoAlBanco = async () => {
    setMandandoTutto(true);
    const unitaMsg = giacenzaLotti[0]?.unita_misura || "pz";
    let totale = 0;
    const fonti = []; // "60 da Congelatore 1", "10 da Frigo 2"...
    const falliti = [];
    for (const lotto of giacenzaLotti) {
      try {
        const res = await _mandaUnLotto(lotto, lotto.quantita);
        const d = res.data || {};
        totale += lotto.quantita || 0;
        const daDove = d.frigo_numero || lotto.frigo_numero || "";
        fonti.push(`${lotto.quantita}${daDove ? ` da ${daDove}` : ""}`);
        if (stampare) stampaMovimento(d.movimento_id, d.numero_lotto);
      } catch (e) {
        falliti.push(lotto);
      }
    }
    if (totale > 0) {
      toast.success(
        `✓ ${totale}${unitaMsg} di ${prodotto.nome} mandati al banco (${fonti.join(" + ")}) — tracciabilità registrata`
      );
    }
    if (falliti.length > 0) toast.error(`${falliti.length} lotto/i non inviati, riprova`);
    setGiacenzaLotti(falliti);
    onRefreshLista && onRefreshLista();
    setMandandoTutto(false);
    if (falliti.length === 0) setTimeout(onClose, 500);
  };

  const [bomComponenti, setBomComponenti] = useState([]);
  const [stepRegistrazione, setStepRegistrazione] = useState("base");
  const [lottiDisponibili, setLottiDisponibili] = useState({});
  const [lottiSelezionati, setLottiSelezionati] = useState({});

  // ── Aggiungi a colazione ──────────────────────────────────────────────────
  const [colPicker, setColPicker]   = useState(false);
  const [colPresets, setColPresets] = useState([]);
  const [colBusy, setColBusy]       = useState(false);

  const addAColazione = async (preset) => {
    if (!preset) return;
    setColBusy(true);
    try {
      await axios.post(`${API}/colazione-acquaviva/aggiungi-prodotto`, {
        preset,
        prodotto_id: prodotto.id,
        prodotto_nome: prodotto.nome,
        pezzi,
        foto_url: prodotto.foto_url || null,
        categoria: prodotto.categoria || null,
      });
      toast.success(`✓ ${prodotto.nome} aggiunto alla colazione ${preset} (${pezzi}${unita})`);
      setColPicker(false);
    } catch (e) {
      toast.error("Errore: " + (e?.response?.data?.detail || e?.message || ""));
    } finally {
      setColBusy(false);
    }
  };

  const apriColazione = async () => {
    try {
      const res = await axios.get(`${API}/colazione-acquaviva/preset`);
      const lista = res.data || [];
      if (lista.length <= 1) { await addAColazione(lista[0]?.nome || "Estiva"); return; }
      setColPresets(lista);
      setColPicker(true);
    } catch (e) {
      toast.error("Errore colazione: " + (e?.message || ""));
    }
  };

  useEffect(() => {
    if (!prodotto?.id) return;
    axios.get(`${API}/ricette/${prodotto.id}/bom`)
      .then(r => {
        const struttura = r.data?.struttura || [];
        const sottoRicette = struttura.filter(c => c.tipo === "sotto_ricetta");
        if (sottoRicette.length > 0) {
          setBomComponenti(sottoRicette);
          const promises = sottoRicette.map(c =>
            axios.get(`${API}/lotti?search=${encodeURIComponent(c.nome)}&limit=20`)
              .then(lr => [c.nome, lr.data || []])
              .catch(() => [c.nome, []])
          );
          Promise.all(promises).then(entries => {
            const map = {};
            entries.forEach(([nome, lotti]) => { map[nome] = lotti; });
            setLottiDisponibili(map);
          });
        } else {
          setBomComponenti([]);
        }
      })
      .catch(() => setBomComponenti([]));
  // setBomComponenti/setLottiDisponibili sono state setter stabili; axios/API sono module-level
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prodotto?.id]);

  useEffect(() => {
    if (!prodotto?.nome) return;
    const dataProd = new Date().toISOString().split("T")[0];
    axios.get(`${API}/anteprima-codice-lotto/${encodeURIComponent(prodotto.nome)}`, {
      params: { quantita: pezzi, unita_misura: unita, data_produzione: dataProd }
    }).then(r => setCodiceLottoPreview(r.data)).catch(() => {});
  }, [prodotto?.nome, pezzi, unita]);

  // ── Scadenza PROPOSTA e MODIFICABILE (Enzo 23/07/2026: "il panettone
  // artigianale dura 3 mesi, non domani per le uova"). La data corretta a
  // mano viene ricordata per il prodotto (se la spunta resta attiva).
  const [scadenzaProposta, setScadenzaProposta] = useState("");   // ISO proposta dal sistema
  const [scadenza, setScadenza] = useState("");                   // ISO modificabile
  const [scadenzaInfo, setScadenzaInfo] = useState(null);
  const [ricordaDurata, setRicordaDurata] = useState(true);

  const _ddmmyyyyToIso = (s) => {
    const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(s || "");
    return m ? `${m[3]}-${m[2]}-${m[1]}` : "";
  };

  useEffect(() => {
    if (!prodotto?.id) return;
    const dataProd = new Date().toISOString().split("T")[0];
    axios.get(`${API}/anteprima-scadenza/${prodotto.id}`, { params: { data_produzione: dataProd } })
      .then(r => {
        const iso = _ddmmyyyyToIso(r.data?.data_scadenza);
        setScadenzaProposta(iso);
        setScadenza(iso);
        setScadenzaInfo(r.data);
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prodotto?.id]);

  const opzioniFrigo = frigoriferi.length > 0
    ? frigoriferi.map(f => f.label || f.nome)
    : ["Frigo 1","Frigo 2","Frigo 3","Cella Frigo A","Cella Frigo B"];
  const opzioniCongelatori = congelatori.length > 0
    ? congelatori.map(c => c.label || c.nome)
    : ["Congelatore 1","Congelatore 2","Abbattitore 1","Surgelatore"];

  // Pre-seleziona la prima posizione (frigo/abbattitore) così l'etichetta ha
  // già un luogo: zero digitazione nel caso comune. L'operatore può cambiarla.
  useEffect(() => {
    if (destinazione === "frigo" && !frigo && opzioniFrigo.length) setFrigo(opzioniFrigo[0]);
    if (destinazione === "abbattitore" && !frigo && opzioniCongelatori.length) setFrigo(opzioniCongelatori[0]);
    setPosizioneAMano(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [destinazione]);

  const handleRegistra = async () => {
    if (giacenzaLotti.length > 0 && !confermaComunque) {
      toast.error("Ci sono già scorte in frigo/abbattitore: mandale al banco o conferma che vuoi produrne comunque.");
      return;
    }
    if (posizioneMancante && !confermaSenzaPosizione) {
      toast.error("Indica il frigo/congelatore di destinazione, o conferma di voler procedere senza.");
      return;
    }
    if (bomComponenti.length > 0 && stepRegistrazione === "base") {
      setStepRegistrazione("componenti");
      return;
    }
    setLoading(true);
    try {
      const lottiComponenti = Object.entries(lottiSelezionati)
        .filter(([, v]) => v && v !== "")
        .map(([nome, lotto_id]) => {
          const lotti = lottiDisponibili[nome] || [];
          const lotto = lotti.find(l => l.id === lotto_id) || {};
          return { lotto_id, numero_lotto: lotto.numero_lotto || "", nome, quantita_usata: null, unita: "" };
        });

      // Leggi operatore dalla sessione tablet
      const sessionOpRaw = sessionStorage.getItem("tablet_operatore");
      const sessionOp = sessionOpRaw ? JSON.parse(sessionOpRaw) : null;

      const params = {
        ricetta_id: prodotto.id,
        pezzi,
        pezzi_base: pezzi,
        costo_totale: 0,
        data_produzione: new Date().toISOString().split("T")[0],
        operation_id: _opId("produzione"),
        ...(sessionOp?.id   && { operatore_id:   sessionOp.id }),
        ...(sessionOp?.nome && { operatore_nome: sessionOp.nome }),
      };
      if ((destinazione === "frigo" || destinazione === "abbattitore") && frigo) {
        params.frigo_numero = frigo;
      }
      if (lottiComponenti.length > 0) {
        params.lotti_componenti_json = JSON.stringify(lottiComponenti);
      }
      // Scadenza (eventualmente corretta a mano); se diversa dalla proposta e
      // la spunta è attiva, il sistema ricorda la durata per questo prodotto.
      if (scadenza) {
        params.data_scadenza = scadenza;
        if (scadenzaProposta && scadenza !== scadenzaProposta && ricordaDurata) {
          params.memorizza_durata = true;
        }
      }
      const res = await axios.post(`${API}/registra-produzione-lotto`, null, { params });
      _opDone("produzione");
      setLottoCreato({ ...res.data, destinazione });
      toast.success(`Lotto ${res.data.numero_lotto} registrato!`);
      // Avvisi scorte: prodotti finiti durante questo scarico FIFO
      const _lf = res.data.lotti_fornitori || {};
      (_lf.lotti_esauriti || []).forEach((e) =>
        toast(`⚠️ ${e.prodotto}${e.fornitore ? " (" + e.fornitore + ")" : ""} finito — passa al prossimo lotto`)
      );
      // Unità incompatibili: lotto NON scalato (tranche 4)
      (_lf.conversioni_non_disponibili || []).forEach((c) =>
        toast.error(`⚠️ ${c.ingrediente}: conversione non disponibile (${c.unita_lotto} → ${c.unita_ricetta}) — lotto non scalato, censisci il contenuto confezione`)
      );
      // Scarico PARZIALE: i lotti non coprivano il fabbisogno (audit 24/07)
      (_lf.ingredienti_insufficienti || []).forEach((i) =>
        toast.error(`⚠️ ${i.ingrediente}: mancavano ${i.mancante} ${i.unita} — giacenza insufficiente, controlla gli ordini`)
      );

      if (destinazione === "banco") {
        try {
          // Recupera operatore dalla sessione tablet se disponibile
          const operatore = sessionOp;

          await axios.post(`${API}/vendita-banco/registra`, {
            prodotto_id: prodotto.id,
            prodotto_nome: prodotto.nome,
            reparto,
            pezzi_prodotti: pezzi,
            foto_url: prodotto.foto_url || null,
            data: new Date().toISOString().split("T")[0],
            lotto_id: res.data.id || res.data.lotto?.id || null,          // ← tracciabilità
            numero_lotto: res.data.numero_lotto || res.data.lotto?.numero_lotto || null,
            operatore_id: operatore?.id || null,
            operatore_nome: operatore?.nome || null,
          });
          toast.success("Registrato per la vendita al banco!");
        } catch (err) { console.warn("Vendita banco non registrata:", err?.message); }
      }
      if (stampare && destinazione !== "banco") {
        setTimeout(() => handleStampa(res.data), 600);
      }
      onSuccess && onSuccess(res.data);
      setStepRegistrazione("base");
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    } finally {
      setLoading(false);
    }
  };

  const handleStampa = async (lotto = lottoCreato) => {
    if (!lotto) return;
    const id = lotto.numero_lotto || lotto.id;
    try {
      const r = await stampaDoc({
        categoria: "etichette",
        url: `${API}/stampa/lotto/${encodeURIComponent(id)}`,
        formato: "html",
        titolo: `Etichetta ${id}`,
      });
      if (r.accodato) toast.success("Etichetta inviata alla stampa automatica");
    } catch (e) {
      toast.error("Errore stampa: " + apiError(e));
    }
  };

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", zIndex: 1000,
      display: "flex", alignItems: "flex-start", justifyContent: "center",
      padding: "8px", overflowY: "auto"
    }}>
      <div style={{
        background: "#fff", borderRadius: 14, padding: "12px 14px",
        width: "100%", maxWidth: 360,
        boxShadow: "0 16px 48px rgba(0,0,0,0.3)",
        boxSizing: "border-box", marginTop: 8
      }}>
        {!lottoCreato ? (
          <>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              {onHome ? (
                <button onClick={onHome} style={{
                  background: "#f0ebe0", border: "none", borderRadius: 7, padding: "4px 8px",
                  fontWeight: 700, fontSize: 11, cursor: "pointer", color: "#5c564a", flexShrink: 0
                }}>← Home</button>
              ) : <span />}
              <span style={{ fontSize: 14, fontWeight: 800, textTransform: "capitalize", color: "#2a3329",
                flex: 1, textAlign: "center", padding: "0 4px",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {prodotto.nome}
              </span>
              <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 17,
                cursor: "pointer", color: "#a39a87", padding: "2px 4px", flexShrink: 0 }}>✕</button>
            </div>

            {/* Giacenza già pronta in frigo/abbattitore: PRIMA di far produrre
                di nuovo, mostro cosa c'è già e lascio mandarlo al banco. */}
            {giacenzaLotti.length > 0 && stepRegistrazione === "base" && (
              <div style={{
                background: "#fff1e6", border: "2px solid #7c2d12", borderRadius: 10,
                padding: "8px 10px", marginBottom: 8
              }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, marginBottom: 6 }}>
                  <p style={{ margin: 0, fontSize: 12, fontWeight: 800, color: "#7c2d12" }}>
                    🧊 Ne hai già {giacenzaTotale} pronti, non ancora al banco:
                  </p>
                  {giacenzaLotti.length > 1 && (
                    <button onClick={handleMandaTuttoAlBanco} disabled={mandandoTutto || mandandoId !== null}
                      style={{
                        padding: "6px 10px", borderRadius: 7, border: "none",
                        background: "#3f5a4e", color: "#fff", fontWeight: 800, fontSize: 11,
                        cursor: mandandoTutto ? "default" : "pointer", flexShrink: 0, whiteSpace: "nowrap"
                      }}>
                      {mandandoTutto ? "..." : `🛒 Tutto (${giacenzaTotale})`}
                    </button>
                  )}
                </div>
                {giacenzaLotti.map(l => {
                  const qty = mandaQty[l.id] ?? l.quantita;
                  const disabilitato = mandandoId === l.id || mandandoTutto;
                  return (
                    <div key={l.id} style={{
                      background: "#fff", borderRadius: 7, padding: "6px 8px", marginBottom: 5
                    }}>
                      <span style={{ fontSize: 11, color: "#7c2d12" }}>
                        <b>{l.quantita}{l.unita_misura || "pz"} disponibili</b> · {l.frigo_numero || "—"} · prod. {l.data_produzione}
                      </span>
                      <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 5 }}>
                        <button onClick={() => setQtyLotto(l, qty - 1)} disabled={disabilitato}
                          style={{ width: 26, height: 26, borderRadius: 6, border: "1.5px solid #e0c9b8",
                            background: "#fff8f2", color: "#7c2d12", fontWeight: 800, fontSize: 14, cursor: disabilitato ? "default" : "pointer", flexShrink: 0 }}>−</button>
                        <input type="number" value={qty} min={1} max={l.quantita} disabled={disabilitato}
                          onChange={e => setQtyLotto(l, parseInt(e.target.value, 10))}
                          style={{ width: 44, textAlign: "center", padding: "4px 0", fontSize: 12, fontWeight: 800,
                            border: "1.5px solid #e0c9b8", borderRadius: 6, color: "#7c2d12", minWidth: 0 }} />
                        <button onClick={() => setQtyLotto(l, qty + 1)} disabled={disabilitato}
                          style={{ width: 26, height: 26, borderRadius: 6, border: "1.5px solid #e0c9b8",
                            background: "#fff8f2", color: "#7c2d12", fontWeight: 800, fontSize: 14, cursor: disabilitato ? "default" : "pointer", flexShrink: 0 }}>+</button>
                        <button onClick={() => setQtyLotto(l, l.quantita)} disabled={disabilitato}
                          style={{ fontSize: 10, fontWeight: 700, color: "#a06a3f", background: "none", border: "none",
                            cursor: disabilitato ? "default" : "pointer", padding: "0 2px", textDecoration: "underline" }}>tutto</button>
                        <button onClick={() => handleMandaAlBanco(l)} disabled={disabilitato}
                          style={{
                            padding: "6px 10px", borderRadius: 7, border: "none", marginLeft: "auto",
                            background: "#7c2d12", color: "#fff", fontWeight: 700, fontSize: 11,
                            cursor: disabilitato ? "default" : "pointer", flexShrink: 0,
                            opacity: mandandoTutto && mandandoId !== l.id ? 0.5 : 1
                          }}>
                          {mandandoId === l.id ? "..." : `🛒 ${qty}`}
                        </button>
                      </div>
                      {farcituraConf?.disponibile && (
                        <button onClick={() => farcituraApertaId === l.id ? setFarcituraApertaId(null) : apriFarcitura(l)}
                          disabled={disabilitato}
                          style={{
                            width: "100%", marginTop: 5, padding: "6px 10px", borderRadius: 7,
                            border: "1.5px dashed #a06a3f", background: farcituraApertaId === l.id ? "#fff1e0" : "#fffaf3",
                            color: "#a06a3f", fontWeight: 700, fontSize: 11, cursor: disabilitato ? "default" : "pointer"
                          }}>
                          🥐 {farcituraApertaId === l.id ? "Chiudi divisione gusti" : "Dividi nei gusti"}
                        </button>
                      )}
                      {farcituraApertaId === l.id && (
                        <div style={{ marginTop: 6, padding: "8px 9px", background: "#fffaf3", border: "1.5px solid #f0dcc4", borderRadius: 8 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                            <span style={{ fontSize: 10, fontWeight: 700, color: "#a06a3f" }}>Stagione:</span>
                            <select value={stagioneSel} onChange={e => cambiaStagioneFarcitura(l, e.target.value)}
                              style={{ flex: 1, fontSize: 11, padding: "4px 6px", borderRadius: 6, border: "1.5px solid #e0c9b8" }}>
                              {stagioni.map(s => <option key={s.nome} value={s.nome}>{s.nome}</option>)}
                            </select>
                          </div>
                          {caricandoAnteprima ? (
                            <p style={{ fontSize: 11, color: "#a06a3f", margin: 0 }}>Calcolo divisione...</p>
                          ) : Object.keys(divisione).length === 0 ? (
                            <p style={{ fontSize: 11, color: "#a06a3f", margin: 0 }}>Nessuna proporzione impostata in Colazione per questa stagione.</p>
                          ) : (
                            <>
                              {Object.entries(divisione).map(([gusto, val]) => (
                                <div key={gusto} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                                  <span style={{ flex: 1, fontSize: 11, color: "#7c2d12", textTransform: "capitalize" }}>{gusto}</span>
                                  <input type="number" value={val} min={0}
                                    onChange={e => setDivisioneGusto(gusto, e.target.value)}
                                    style={{ width: 50, textAlign: "center", padding: "3px 0", fontSize: 11, fontWeight: 800,
                                      border: "1.5px solid #e0c9b8", borderRadius: 6, color: "#7c2d12" }} />
                                </div>
                              ))}
                              <p style={{ fontSize: 10, color: "#a06a3f", margin: "4px 0 6px" }}>
                                Totale: {Object.values(divisione).reduce((s, v) => s + v, 0)} — correggi i numeri sopra se serve.
                              </p>
                              <button onClick={() => confermaFarcitura(l)} disabled={confermandoFarcitura}
                                style={{
                                  width: "100%", padding: "8px 0", borderRadius: 7, border: "none",
                                  background: "#a06a3f", color: "#fff", fontWeight: 800, fontSize: 12,
                                  cursor: confermandoFarcitura ? "default" : "pointer"
                                }}>
                                {confermandoFarcitura ? "..." : "✓ Conferma farcitura e manda al banco"}
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
                <label style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4, cursor: "pointer" }}>
                  <input type="checkbox" checked={confermaComunque}
                    onChange={e => setConfermaComunque(e.target.checked)} />
                  <span style={{ fontSize: 11, fontWeight: 700, color: "#7c2d12" }}>
                    Ho controllato, voglio produrne comunque altri
                  </span>
                </label>
              </div>
            )}

            {/* Guida: è già tutto pronto, basta il pulsante in fondo */}
            {stepRegistrazione === "base" && giacenzaLotti.length === 0 && (
              <div style={{ fontSize: 11, color: "#7a7266", textAlign: "center", marginBottom: 8 }}>
                Già pronto: tocca <b>Registra</b> in fondo. Cambia solo ciò che serve. 👇
              </div>
            )}

            <SelettoreQuantita unita={unita} setUnita={setUnita} pezzi={pezzi} setPezzi={setPezzi} />

            <SelettorePosizione
              reparto={reparto}
              destinazione={destinazione} setDestinazione={setDestinazione}
              frigo={frigo} setFrigo={setFrigo}
              opzioniFrigo={opzioniFrigo} opzioniCongelatori={opzioniCongelatori}
              posizioneAMano={posizioneAMano} setPosizioneAMano={setPosizioneAMano}
              posizioneMancante={posizioneMancante}
              confermaSenzaPosizione={confermaSenzaPosizione}
              setConfermaSenzaPosizione={setConfermaSenzaPosizione}
            />

            {/* Stampa */}
            {destinazione !== "banco" ? (
              <div style={{
                display: "flex", alignItems: "center", gap: 7, padding: "6px 10px",
                background: stampare ? "var(--info-soft)" : "#faf7f0",
                border: `1.5px solid ${stampare ? "var(--info-border)" : "#e6e0d4"}`,
                borderRadius: 8, marginBottom: 10, cursor: "pointer"
              }} onClick={() => setStampare(v => !v)}>
                <div style={{ width: 16, height: 16, borderRadius: 4,
                  border: `2px solid ${stampare ? "var(--info)" : "#cfc6b4"}`,
                  background: stampare ? "var(--info)" : "#fff", display: "flex",
                  alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  {stampare && <span style={{ color: "#fff", fontSize: 10, fontWeight: 900 }}>✓</span>}
                </div>
                <span style={{ margin: 0, fontWeight: 600, fontSize: 11, color: "#374151" }}>
                  Stampa etichetta {stampare ? "— attiva" : "— no"}
                </span>
              </div>
            ) : (
              <div style={{ padding: "8px 12px", background: "#f0fdf4", borderRadius: 8, border: "1px solid #bbf7d0", marginBottom: 10 }}>
                <span style={{ fontSize: 12, color: "var(--success)" }}>✓ Salvato direttamente in archivio lotti</span>
              </div>
            )}

            {/* Anteprima codice lotto */}
            {codiceLottoPreview && (
              <div style={{
                marginBottom: 8, padding: "6px 10px", borderRadius: 8,
                background: "#f0fdf4", border: "1.5px solid #86efac",
                display: "flex", alignItems: "center", gap: 8
              }}>
                <span style={{ fontSize: 9, fontWeight: 700, color: "var(--success-dark)", textTransform: "uppercase", flexShrink: 0 }}>Codice Lotto</span>
                <span style={{
                  fontFamily: "monospace", fontSize: 11, fontWeight: 900,
                  color: "#166534", background: "#dcfce7", padding: "2px 6px", borderRadius: 4,
                  flex: 1, wordBreak: "break-all"
                }}>
                  {codiceLottoPreview.codice_lotto}
                </span>
                <span style={{ fontSize: 9, color: "#4ade80", flexShrink: 0 }}>#{codiceLottoPreview.progressivo}</span>
              </div>
            )}

            {/* Scadenza proposta — modificabile (es. panettone artigianale 3 mesi) */}
            {scadenza && (
              <div style={{ marginBottom: 8, padding: "8px 10px", borderRadius: 8,
                background: "#fffdf7", border: "1.5px solid var(--warning-soft)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 11, fontWeight: 800, color: "var(--warning-text)", textTransform: "uppercase", flexShrink: 0 }}>
                    📅 Scadenza
                  </span>
                  <input type="date" value={scadenza} onChange={e => setScadenza(e.target.value)}
                    style={{ padding: "6px 8px", borderRadius: 7, border: "1.5px solid var(--warning-soft)",
                      fontSize: 13, fontWeight: 700, background: "#fff", color: "#374151" }} />
                  {scadenzaInfo && scadenza === scadenzaProposta && (
                    <span style={{ fontSize: 10, color: "#8a6f47" }}>
                      {scadenzaInfo.durata_memorizzata
                        ? `durata memorizzata: ${scadenzaInfo.giorni} giorni`
                        : `proposta: ${scadenzaInfo.giorni} giorni${scadenzaInfo.ingrediente_critico ? ` (critico: ${scadenzaInfo.ingrediente_critico})` : ""}`}
                    </span>
                  )}
                </div>
                {scadenza !== scadenzaProposta && (
                  <div onClick={() => setRicordaDurata(v => !v)}
                    style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 7, cursor: "pointer" }}>
                    <div style={{ width: 16, height: 16, borderRadius: 4, flexShrink: 0,
                      border: "2px solid var(--warning)", background: ricordaDurata ? "var(--warning)" : "#fff",
                      display: "flex", alignItems: "center", justifyContent: "center" }}>
                      {ricordaDurata && <span style={{ color: "#fff", fontSize: 10, fontWeight: 900 }}>✓</span>}
                    </div>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "var(--warning-text)" }}>
                      Ricorda questa durata per «{prodotto.nome}» (le prossime produzioni partono già giuste)
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* Step componenti BOM */}
            {stepRegistrazione === "componenti" && bomComponenti.length > 0 && (
              <div style={{
                background: "#f0fdf4", border: "1.5px solid #86efac", borderRadius: 10,
                padding: "10px 12px", marginBottom: 6
              }}>
                <p style={{ fontSize: 12, fontWeight: 700, color: "var(--success-dark)", marginBottom: 6 }}>
                  Seleziona lotti per le sotto-ricette (opzionale):
                </p>
                {bomComponenti.map((comp, idx) => (
                  <div key={comp.nome || comp.id || comp.ricetta_id} style={{ marginBottom: 8 }}>
                    <p style={{ fontSize: 11, fontWeight: 600, color: "#166534", marginBottom: 3 }}>
                      {comp.nome} ({comp.porzioni_usate} porzioni)
                    </p>
                    <select
                      value={lottiSelezionati[comp.nome] || ""}
                      onChange={e => setLottiSelezionati(p => ({ ...p, [comp.nome]: e.target.value }))}
                      data-testid={`seleziona-lotto-comp-${idx}`}
                      style={{ width: "100%", padding: "6px 8px", borderRadius: 7, border: "1px solid #86efac",
                               fontSize: 11, background: "#fff" }}
                    >
                      <option value="">— Nessun lotto specifico —</option>
                      {(lottiDisponibili[comp.nome] || []).map(l => (
                        <option key={l.id} value={l.id}>
                          {l.numero_lotto} — {l.prodotto} — scad. {l.data_scadenza}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
                <button onClick={() => setStepRegistrazione("base")}
                  style={{ fontSize: 11, color: "#6b7280", background: "none", border: "none",
                    cursor: "pointer", textDecoration: "underline", marginTop: 2 }}>
                  Torna indietro
                </button>
              </div>
            )}

            {/* Aggiungi a colazione (solo pasticceria) */}
            {reparto === "pasticceria" && (
              <div style={{ marginBottom: 8 }}>
                {!colPicker ? (
                  <button onClick={apriColazione} disabled={colBusy} style={{
                    width: "100%", padding: "11px 0", borderRadius: 9, border: "2px solid var(--warning)",
                    background: "var(--warning-soft)", color: "var(--warning-text)", fontWeight: 800,
                    fontSize: 13, cursor: colBusy ? "default" : "pointer"
                  }}>
                    ☕ Aggiungi anche al menù colazione ({pezzi}{unita})
                  </button>
                ) : (
                  <div style={{ border: "2px solid var(--warning)", borderRadius: 10, padding: 8, background: "#fffdf7" }}>
                    <div style={{ fontSize: 11, fontWeight: 800, color: "#92400e", marginBottom: 6 }}>In quale menù colazione lo metto? (lo ritrovi nel tasto ☕ Colazione)</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {colPresets.map(p => (
                        <button key={p.nome} onClick={() => addAColazione(p.nome)} disabled={colBusy} style={{
                          padding: "7px 12px", borderRadius: 999, border: "2px solid var(--warning)",
                          background: "#fff", color: "var(--warning-text)", fontWeight: 800, fontSize: 12, cursor: "pointer"
                        }}>{p.nome}</button>
                      ))}
                      <button onClick={() => setColPicker(false)} style={{
                        padding: "7px 12px", borderRadius: 999, border: "2px solid #e6e0d4",
                        background: "#faf7f0", color: "#7a7266", fontWeight: 700, fontSize: 12, cursor: "pointer"
                      }}>Annulla</button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Pulsanti */}
            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={onClose} style={{
                flex: 1, padding: "10px 0", borderRadius: 9, border: "2px solid #e6e0d4",
                background: "#faf7f0", fontWeight: 600, fontSize: 13, cursor: "pointer", color: "#7a7266"
              }}>Annulla</button>
              <button onClick={handleRegistra}
                disabled={loading || (stepRegistrazione === "base" && (bloccatoDaGiacenza || bloccatoDaPosizioneMancante))} style={{
                flex: 2, padding: "10px 0", borderRadius: 9, border: "none",
                background: (stepRegistrazione === "base" && (bloccatoDaGiacenza || bloccatoDaPosizioneMancante))
                  ? "#cfc6b4"
                  : reparto === "pasticceria"
                  ? "linear-gradient(135deg,var(--warning),var(--warning-dark))"
                  : destinazione === "banco"
                    ? "linear-gradient(135deg,#f97316,#ea580c)"
                    : destinazione === "abbattitore"
                      ? "linear-gradient(135deg,#5b7a6b,#3f5a4e)"
                      : "linear-gradient(135deg,var(--info),var(--info-dark))",
                color: "#fff", fontWeight: 700, fontSize: 14,
                cursor: (loading || (stepRegistrazione === "base" && (bloccatoDaGiacenza || bloccatoDaPosizioneMancante))) ? "not-allowed" : "pointer",
                opacity: loading ? 0.7 : 1
              }}>
                {loading ? "..." : (stepRegistrazione === "base" && bloccatoDaGiacenza)
                  ? "🧊 Manda al banco o conferma sopra"
                  : (stepRegistrazione === "base" && bloccatoDaPosizioneMancante)
                  ? "📍 Indica la posizione o conferma sopra"
                  : stepRegistrazione === "componenti"
                  ? "Conferma Registrazione"
                  : destinazione === "banco"
                  ? `🛒 ${pezzi}${unita} al Banco`
                  : destinazione === "abbattitore"
                    ? `❄️ Abbattitore ${pezzi}${unita}`
                    : bomComponenti.length > 0
                      ? "Avanti →"
                      : `🧊 Frigo ${pezzi}${unita}`}
              </button>
            </div>
          </>
        ) : (
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 32, marginBottom: 4 }}>✅</div>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: "#166534", margin: "0 0 4px" }}>Registrato!</h2>
            <div style={{
              fontFamily: "monospace", fontSize: 14, fontWeight: 700,
              background: "var(--info-soft)", color: "var(--info-dark)", padding: "4px 12px",
              borderRadius: 7, display: "inline-block", margin: "4px 0",
              cursor: "pointer", wordBreak: "break-all"
            }} onClick={() => { navigator.clipboard?.writeText(lottoCreato.numero_lotto); toast.success("Codice copiato!"); }}>
              {lottoCreato.numero_lotto}
            </div>
            <p style={{ fontSize: 9, color: "#a39a87", margin: "1px 0 6px" }}>tocca per copiare</p>
            <div style={{ background: "#faf7f0", border: "1px solid #e6e0d4", borderRadius: 8, padding: "6px 10px", marginBottom: 6, textAlign: "left" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 3 }}>
                <span style={{ color: "#7a7266" }}>Prodotto il:</span>
                <strong style={{ color: "#2a3329" }}>{lottoCreato.data_produzione}</strong>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: lottoCreato.data_scadenza_abbattuto ? 3 : 0 }}>
                <span style={{ color: "#7a7266" }}>Scad. Frigo (0-4°C):</span>
                <strong style={{ color: "var(--danger-dark)" }}>{lottoCreato.data_scadenza}</strong>
              </div>
              {lottoCreato.data_scadenza_abbattuto && (
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                  <span style={{ color: "#7a7266" }}>Scad. Abbattuto (-18°C):</span>
                  <strong style={{ color: "#3f5a4e" }}>{lottoCreato.data_scadenza_abbattuto || lottoCreato.scadenza_abbattuto}</strong>
                </div>
              )}
            </div>
            <p style={{ color: "#7a7266", fontSize: 11, margin: "0 0 6px" }}>
              {lottoCreato.frigo_numero && lottoCreato.destinazione !== "abbattitore" && <span style={{ color: "#8a6f47" }}>🧊 {lottoCreato.frigo_numero}</span>}
              {lottoCreato.frigo_numero && lottoCreato.destinazione === "abbattitore" && <span style={{ color: "#3f5a4e" }}>❄️ {lottoCreato.frigo_numero}</span>}
              {lottoCreato.destinazione === "banco" && <span style={{ color: "#f97316" }}>🛒 Banco</span>}
            </p>
            {lottoCreato.conservazione_note && (
              <div style={{ background: "#fefce8", border: "1px solid #fde047", borderRadius: 7, padding: "5px 8px", marginBottom: 6, fontSize: 10, color: "#713f12", textAlign: "left" }}>
                <strong>Conservazione:</strong> {lottoCreato.conservazione_note}
              </div>
            )}
            {lottoCreato.allergeni_testo && (
              <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 7, padding: "5px 8px", marginBottom: 6, fontSize: 10, color: "#7f1d1d", textAlign: "left" }}>
                <strong>Allergeni:</strong> {lottoCreato.allergeni_testo}
              </div>
            )}
            {lottoCreato.lotti_fornitori && (() => {
              const lf = lottoCreato.lotti_fornitori || {};
              const scalati = lf.lotti_scalati || [];
              const esauriti = lf.lotti_esauriti || [];
              const daRiordinare = lf.da_riordinare || [];
              const nonTrovati = lf.ingredienti_non_trovati || [];
              if (!scalati.length && !esauriti.length && !daRiordinare.length && !nonTrovati.length) return null;
              return (
                <div style={{ textAlign: "left" }}>
                  {scalati.length > 0 && (
                    <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 7, padding: "5px 8px", marginBottom: 6, fontSize: 10, color: "#166534" }}>
                      <strong>📦 Scaricato dai lotti (FIFO):</strong>
                      {scalati.map((s, i) => (
                        <div key={i}>• {s.prodotto || s.ingrediente} — {s.fornitore || "?"} (−{s.quantita_consumata} {String(s.unita || "").toLowerCase()}, restano {s.quantita_rimasta})</div>
                      ))}
                    </div>
                  )}
                  {esauriti.length > 0 && (
                    <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 7, padding: "6px 9px", marginBottom: 6, fontSize: 11, color: "#7f1d1d" }}>
                      <strong>🔴 Prodotto finito — da riordinare:</strong>
                      {esauriti.map((e, i) => (
                        <div key={i}>• {e.prodotto} {e.fornitore ? `(${e.fornitore})` : ""} esaurito → passa al prossimo lotto</div>
                      ))}
                    </div>
                  )}
                  {daRiordinare.length > 0 && (
                    <div style={{ background: "var(--info-soft)", border: "1px solid var(--info-border)", borderRadius: 7, padding: "6px 9px", marginBottom: 6, fontSize: 11, color: "var(--info-text)" }}>
                      <strong>🛒 Ordine automatico creato:</strong>
                      {daRiordinare.map((d, i) => (
                        <div key={i}>• {d.prodotto} esaurito → bozza ordine in “Ordini”</div>
                      ))}
                    </div>
                  )}
                  {nonTrovati.length > 0 && (
                    <div style={{ background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 7, padding: "5px 8px", marginBottom: 6, fontSize: 10, color: "#92400e" }}>
                      <strong>⚠️ Senza lotto registrato:</strong> {nonTrovati.join(", ")}
                      <div style={{ fontSize: 9, color: "#b45309", marginTop: 2 }}>Nessuna fattura trovata per questi ingredienti (non ancora ricevuti o nome diverso).</div>
                    </div>
                  )}
                </div>
              );
            })()}
            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={() => handleStampa(lottoCreato)} style={{
                flex: 1, padding: "9px 0", borderRadius: 8, border: "2px solid #e6e0d4",
                background: "#faf7f0", fontWeight: 600, fontSize: 12, cursor: "pointer", color: "#374151"
              }}>Stampa</button>
              <button onClick={onClose} style={{
                flex: 2, padding: "9px 0", borderRadius: 8, border: "none",
                background: "linear-gradient(135deg,#22c55e,var(--success))",
                color: "#fff", fontWeight: 700, fontSize: 13, cursor: "pointer"
              }}>Chiudi</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default ModalRegistraLotto;
