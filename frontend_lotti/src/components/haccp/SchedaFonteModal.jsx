/**
 * SchedaFonteModal — pannello per singolo prodotto (da Materie Prime → fornitore → prodotto).
 * Tre vie per ottenere la composizione (ingredienti/coloranti/allergeni) del prodotto composto:
 *   1) Sito del produttore  → POST /schede-tecniche/scrape   (scraping web, gratis)
 *   2) Foto etichetta        → OCR gratuito nel browser (tesseract.js) → POST /parse-etichetta
 *   3) Incolla testo a mano   → POST /parse-etichetta   (rete di sicurezza)
 * Il risultato (composizione, coloranti E100-199, allergeni, avviso azoici) viene mostrato e
 * salvato come scheda tipo='produttore', poi ereditato nel prodotto finito per gli allergeni.
 */
import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { X, Globe, Camera, Loader2, Save, AlertTriangle, Search } from "lucide-react";
import { API } from "../../utils/constants";

// Carica tesseract.js da CDN solo quando serve (niente peso sul bundle).
let _tessPromise = null;
function caricaOCR() {
  if (window.Tesseract) return Promise.resolve(window.Tesseract);
  if (_tessPromise) return _tessPromise;
  _tessPromise = new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js";
    s.onload = () => res(window.Tesseract);
    s.onerror = () => rej(new Error("OCR non caricato"));
    document.body.appendChild(s);
  });
  return _tessPromise;
}

export default function SchedaFonteModal({ prodotto, onClose }) {
  const nome = prodotto?.descrizione || prodotto?.nome || "";
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState("");
  const [ocrProg, setOcrProg] = useState(0);
  const [testo, setTesto] = useState("");
  const [scheda, setScheda] = useState(null);
  const [fotoFile, setFotoFile] = useState(null);
  const [webRes, setWebRes] = useState(null);

  const applica = (data) => {
    const s = data?.scheda || data || {};
    setScheda({
      composizione: s.composizione || [],
      coloranti: s.coloranti || [],
      allergeni: s.allergeni || [],
      avviso: s.avviso_coloranti_azoici || [],
    });
  };

  useEffect(() => {
    let attivo = true;
    (async () => {
      try {
        const r = await axios.get(`${API}/schede-tecniche/scheda`, { params: { nome } });
        if (attivo && r.data?.trovata) applica(r.data);
      } catch { /* nessuna scheda ancora: pannello vuoto, ok */ }
    })();
    return () => { attivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nome]);

  const ricercaWeb = async () => {
    setBusy("web");
    try {
      const r = await axios.post(`${API}/schede-tecniche/ricerca-web`, {
        descrizione: nome, fornitore: prodotto?.fornitore || "", salva: true,
      }, { timeout: 100000 });
      setWebRes(r.data);
      if (r.data?.composizione?.length) applica(r.data);
      if (r.data?.url_scheda) setUrl(r.data.url_scheda);
      if (r.data?.confidenza === "alta") {
        toast.success(`Identificato: ${r.data.prodotto_identificato}${r.data.salvato_mapping ? " — canonico imparato" : ""}`);
      } else {
        toast.warning("Identificazione incerta: verifica prima di usare il risultato");
      }
    } catch (e) {
      const code = e?.response?.status;
      toast.error(code === 503 ? "Ricerca web non configurata sul server" : "Ricerca web non riuscita");
    }
    finally { setBusy(""); }
  };

  const estraiDaSito = async () => {
    if (!url.trim().startsWith("http")) { toast.error("Inserisci un URL valido (http...)"); return; }
    setBusy("scrape");
    try {
      const r = await axios.post(`${API}/schede-tecniche/scrape`, { url: url.trim(), prodotto_key: nome, nome_prodotto: nome });
      applica(r.data);
      toast.success(r.data?.salvato ? "Composizione estratta e salvata" : "Composizione estratta");
    } catch { toast.error("Estrazione dal sito non riuscita"); }
    finally { setBusy(""); }
  };

  const salvaSito = async () => {
    if (!url.trim().startsWith("http")) { toast.error("URL non valido"); return; }
    setBusy("save");
    try {
      await axios.post(`${API}/schede-tecniche/salva`, { prodotto_key: nome, nome_prodotto: nome, url: url.trim(), tipo: "produttore" });
      toast.success("Sito produttore salvato");
    } catch { toast.error("Salvataggio non riuscito"); }
    finally { setBusy(""); }
  };

  const leggiFoto = async (file) => {
    if (!file) return;
    setFotoFile(file);
    setBusy("ocr"); setOcrProg(0);
    try {
      const T = await caricaOCR();
      const { data } = await T.recognize(file, "ita", {
        logger: (m) => { if (m.status === "recognizing text") setOcrProg(Math.round((m.progress || 0) * 100)); },
      });
      const txt = (data?.text || "").trim();
      setTesto(txt);
      if (txt.length < 5) { toast.error("OCR non ha letto testo: usa \"Leggi con AI\" o incolla a mano"); return; }
      const r = await axios.post(`${API}/schede-tecniche/parse-etichetta`, { testo: txt, prodotto_key: nome, nome_prodotto: nome, fonte: "foto-etichetta" });
      applica(r.data);
      toast.success("Etichetta letta (OCR gratuito)");
    } catch { toast.error("OCR non disponibile: usa \"Leggi con AI\" o incolla il testo"); }
    finally { setBusy(""); }
  };

  const leggiFotoAI = async () => {
    if (!fotoFile) { toast.error("Scatta o scegli prima una foto dell'etichetta"); return; }
    setBusy("ai");
    try {
      const b64 = await new Promise((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(String(r.result));
        r.onerror = () => rej(new Error("lettura file fallita"));
        r.readAsDataURL(fotoFile);
      });
      const r = await axios.post(`${API}/schede-tecniche/leggi-foto-ai`, {
        immagine_base64: b64, prodotto_key: nome, nome_prodotto: nome, fonte: "foto-etichetta-ai",
      }, { timeout: 90000 });
      if (r.data?.testo_ocr) setTesto(r.data.testo_ocr);
      applica(r.data);
      toast.success("Etichetta letta con AI");
    } catch (e) {
      const code = e?.response?.status;
      toast.error(code === 503 ? "AI-visione non configurata sul server" : "Lettura AI non riuscita");
    }
    finally { setBusy(""); }
  };

  const interpretaTesto = async () => {
    if (testo.trim().length < 5) { toast.error("Incolla il testo dell'etichetta"); return; }
    setBusy("ocr");
    try {
      const r = await axios.post(`${API}/schede-tecniche/parse-etichetta`, { testo: testo.trim(), prodotto_key: nome, nome_prodotto: nome, fonte: "testo-manuale" });
      applica(r.data);
      toast.success("Testo interpretato");
    } catch { toast.error("Interpretazione non riuscita"); }
    finally { setBusy(""); }
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl max-w-lg w-full max-h-[88vh] overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <h3 className="font-bold text-gray-900 text-base">Scheda / Fonte prodotto</h3>
            <p className="text-xs text-gray-500 mt-0.5 break-words">{nome}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 shrink-0"><X size={20} /></button>
        </div>

        <div className="border rounded-lg p-3 mb-3" style={{ borderColor: "#5b7a6b", background: "#faf7f0" }}>
          <div className="flex items-center gap-2 text-xs font-semibold mb-2" style={{ color: "#5b7a6b" }}>
            <Search size={14} /> Ricerca web automatica
          </div>
          <p className="text-xs text-gray-500 mb-2">
            Cerca sul web la descrizione esatta della fattura, identifica il prodotto,
            trova la scheda tecnica e impara il nome canonico.
          </p>
          <button onClick={ricercaWeb} disabled={!!busy}
            className="w-full text-white rounded-md py-2 text-sm font-semibold flex items-center justify-center gap-1.5 disabled:opacity-60"
            style={{ background: "#5b7a6b" }}>
            {busy === "web" && <Loader2 size={15} className="animate-spin" />}
            {busy === "web" ? "Cerco sul web…" : "Cerca e identifica"}
          </button>
          {webRes && (
            <div className="mt-2 text-xs text-gray-700 space-y-0.5">
              <p><b>Prodotto:</b> {webRes.prodotto_identificato || "—"} {webRes.marca ? `(${webRes.marca})` : ""}</p>
              <p><b>Nome canonico:</b> {webRes.nome_canonico || "—"}{webRes.impiego ? ` · impiego: ${webRes.impiego}` : ""}</p>
              <p><b>Confidenza:</b> {webRes.confidenza}{webRes.salvato_mapping ? " · mapping salvato ✓" : ""}{webRes.salvato_scheda ? " · scheda salvata ✓" : ""}</p>
              {webRes.url_scheda && (
                <p><a href={webRes.url_scheda} target="_blank" rel="noreferrer" style={{ color: "#5b7a6b" }} className="underline">Apri scheda tecnica ↗</a></p>
              )}
            </div>
          )}
        </div>

        <div className="border border-gray-200 rounded-lg p-3 mb-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-gray-700 mb-2"><Globe size={14} /> Sito del produttore</div>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.elenka.it/..."
            className="w-full border border-gray-200 rounded-md px-2.5 py-2 text-sm mb-2 box-border" />
          <div className="flex gap-2">
            <button onClick={estraiDaSito} disabled={!!busy}
              className="flex-1 bg-[#4d6a5c] text-white rounded-md py-2 text-sm font-semibold flex items-center justify-center gap-1.5 disabled:opacity-60">
              {busy === "scrape" && <Loader2 size={15} className="animate-spin" />} Estrai dal sito
            </button>
            <button onClick={salvaSito} disabled={!!busy}
              className="px-3 bg-gray-100 text-gray-700 rounded-md py-2 text-sm font-semibold flex items-center gap-1.5"><Save size={14} /> Salva</button>
          </div>
        </div>

        <div className="border border-gray-200 rounded-lg p-3 mb-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-gray-700 mb-2"><Camera size={14} /> Foto etichetta (OCR gratuito)</div>
          <input type="file" accept="image/*" capture="environment" onChange={(e) => leggiFoto(e.target.files?.[0])}
            className="block w-full text-xs text-gray-600 mb-2" />
          {busy === "ocr" && ocrProg > 0 && <p className="text-xs text-gray-500 mb-2">Lettura… {ocrProg}%</p>}
          <button onClick={leggiFotoAI} disabled={!!busy || !fotoFile}
            className="w-full mb-2 bg-[#e8efe9] text-[#3f5a4e] rounded-md py-2 text-sm font-semibold flex items-center justify-center gap-1.5 disabled:opacity-50">
            {busy === "ai" && <Loader2 size={15} className="animate-spin" />} Leggi con AI (etichette difficili)
          </button>
          <textarea value={testo} onChange={(e) => setTesto(e.target.value)} rows={3}
            placeholder="…oppure incolla qui il testo dell'etichetta"
            className="w-full border border-gray-200 rounded-md px-2.5 py-2 text-xs mb-2 box-border" />
          <button onClick={interpretaTesto} disabled={!!busy}
            className="w-full bg-gray-100 text-gray-700 rounded-md py-2 text-sm font-semibold disabled:opacity-60">Interpreta testo</button>
        </div>

        {scheda && (
          <div className="border border-[#cfdfd5] bg-[#f2f6f3] rounded-lg p-3">
            <div className="text-xs font-semibold text-gray-700 mb-1.5">Composizione rilevata</div>
            {scheda.composizione.length
              ? <p className="text-xs text-gray-700 mb-2">{scheda.composizione.join(", ")}</p>
              : <p className="text-xs text-gray-400 italic mb-2">Nessun ingrediente riconosciuto</p>}
            {scheda.coloranti.length > 0 && <p className="text-xs text-gray-700 mb-1"><b>Coloranti:</b> {scheda.coloranti.join(", ")}</p>}
            {scheda.allergeni.length > 0 && <p className="text-xs text-gray-700 mb-1"><b>Allergeni:</b> {scheda.allergeni.join(", ")}</p>}
            {scheda.avviso.length > 0 && (
              <p className="text-xs text-amber-700 flex items-start gap-1 mt-1">
                <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                Coloranti azoici ({scheda.avviso.join(", ")}): possono influire su attività e attenzione dei bambini.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
