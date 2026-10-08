import { useEffect, useState } from "react";
import axios from "axios";
import { conferma } from "../../../utils/conferma";
import { API } from "../../../utils/constants";
import { toast } from "./toastBackoffice";

export default function RicetteCestino({ onRipristinata }) {
  const [voci, setVoci] = useState([]);
  const [caricando, setCaricando] = useState(true);
  const [ripristinando, setRipristinando] = useState(null);

  useEffect(() => {
    let attivo = true;
    axios.get(`${API}/ricette-cestino`)
      .then(risposta => { if (attivo) setVoci(risposta.data || []); })
      .catch(() => { if (attivo) toast("Impossibile caricare il cestino", "err"); })
      .finally(() => { if (attivo) setCaricando(false); });
    return () => { attivo = false; };
  }, []);

  const ripristina = async (voce) => {
    if (ripristinando) return;
    const messaggio = voce.unita_in
      ? `Ripristinare “${voce.nome}”? Questa copia era stata unita a un'altra ricetta: controlla le due schede dopo il ripristino.`
      : `Ripristinare “${voce.nome}” con il suo ID originale?`;
    if (!await conferma(messaggio, { titolo: "Ripristina ricetta", ok: "Ripristina" })) return;
    setRipristinando(voce.id);
    try {
      await axios.post(`${API}/ricette-cestino/${voce.id}/ripristina`);
      setVoci(correnti => correnti.filter(item => item.id !== voce.id));
      await onRipristinata();
      toast("Ricetta ripristinata nelle ricette operative");
    } catch (error) {
      const dettaglio = error?.response?.data?.detail;
      toast(typeof dettaglio === "string" ? dettaglio : "Impossibile ripristinare la ricetta", "err");
    } finally { setRipristinando(null); }
  };

  if (caricando) return <div style={{ textAlign: "center", padding: 40 }}>Caricamento cestino…</div>;
  return <div style={{ display: "grid", gap: 10 }}>
    {voci.map(voce => <div key={voce.id} style={{ display: "flex", alignItems: "center", gap: 12, justifyContent: "space-between", padding: 14, border: "1px solid var(--border)", borderRadius: 12, background: "var(--card)" }}>
      <div>
        <div style={{ fontWeight: 800 }}>{voce.nome || voce.ricetta_id}</div>
        <div style={{ fontSize: 12, color: "var(--text-2)" }}>{voce.motivo || "Eliminazione manuale"}{voce.unita_in ? ` · unita in ${voce.unita_in}` : ""}</div>
      </div>
      <button type="button" disabled={ripristinando === voce.id} onClick={() => ripristina(voce)}
        style={{ padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--primary-soft)", color: "var(--text)", fontWeight: 800, cursor: "pointer" }}>
        {ripristinando === voce.id ? "Ripristino…" : "Ripristina"}
      </button>
    </div>)}
    {voci.length === 0 && <p style={{ textAlign: "center", padding: 40, color: "var(--text-3)" }}>Cestino vuoto</p>}
  </div>;
}
