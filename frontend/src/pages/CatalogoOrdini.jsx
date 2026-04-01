import { useState, useEffect, useRef } from "react";
import api from "../api";
import PageLayout from "../components/PageLayout";
import { COLORS, STYLES, SPACING, button } from "../lib/utils";

const CATEGORIE = ["Tutti", "Pasticceria", "Rosticceria", "Bar"];

function formatTesto(carrello, fornitore) {
  let txt = `*Ordine Ceraldi Group* — ${new Date().toLocaleDateString("it-IT")}\n`;
  if (fornitore) txt += `Fornitore: ${fornitore}\n`;
  txt += "\n";
  carrello.forEach(item => {
    txt += `• ${item.nome} × ${item.qty} ${item.unita || "pz"}\n`;
  });
  txt += `\nTOTALE PRODOTTI: ${carrello.reduce((s, i) => s + i.qty, 0)}`;
  return txt;
}

export default function CatalogoOrdini() {
  const [prodotti, setProdotti] = useState([]);
  const [fornitori, setFornitori] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [categoria, setCategoria] = useState("Tutti");
  const [fornitoreSelezionato, setFornitoreSelezionato] = useState("");
  const [carrello, setCarrello] = useState({}); // { id: { prodotto, qty } }
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    loadAll();
  }, []);

  async function loadAll() {
    setLoading(true);
    try {
      const [r1, r2] = await Promise.all([
        api.get("/api/cucina/ordini-fornitori/prodotti-suggeriti?limit=700"),
        api.get("/api/fornitori"),
      ]);
      setProdotti(r1.data);
      setFornitori(r2.data?.suppliers || r2.data || []);
    } catch (e) {
      setErr("Errore caricamento prodotti");
    } finally {
      setLoading(false);
    }
  }

  function addToCart(prodotto) {
    setCarrello(prev => ({
      ...prev,
      [prodotto.id]: {
        prodotto,
        qty: (prev[prodotto.id]?.qty || 0) + 1,
      },
    }));
  }

  function removeFromCart(id) {
    setCarrello(prev => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }

  function updateQty(id, qty) {
    if (qty <= 0) { removeFromCart(id); return; }
    setCarrello(prev => ({
      ...prev,
      [id]: { ...prev[id], qty },
    }));
  }

  const itemsCarrello = Object.values(carrello);
  const totaleItems = itemsCarrello.reduce((s, i) => s + i.qty, 0);

  const prodottiFiltrati = prodotti.filter(p => {
    const matchSearch = !search || p.nome?.toLowerCase().includes(search.toLowerCase());
    const matchCat = categoria === "Tutti" || p.categoria?.toLowerCase() === categoria.toLowerCase();
    const matchFornitore = !fornitoreSelezionato || p.fornitore === fornitoreSelezionato;
    return matchSearch && matchCat && matchFornitore;
  });

  async function salvaOrdine() {
    if (itemsCarrello.length === 0) return;
    setSalvando(true);
    try {
      const items = itemsCarrello.map(i => ({
        nome: i.prodotto.nome,
        qty: i.qty,
        unita: i.prodotto.unita_confezione || "pz",
        prezzo_kg: i.prodotto.prezzo_kg,
      }));
      await api.post("/api/ordini-fornitori", {
        source: "gestionale",
        stato: "bozza",
        fornitore: fornitoreSelezionato || "Vario",
        items,
        data_ordine: new Date().toISOString(),
      });
      setMsg("Ordine salvato come bozza!");
      setCarrello({});
      setTimeout(() => setMsg(""), 3000);
    } catch (e) {
      setErr("Errore salvataggio ordine");
    } finally {
      setSalvando(false);
    }
  }

  function inviaWhatsApp() {
    if (itemsCarrello.length === 0) return;
    const txt = formatTesto(itemsCarrello.map(i => ({ ...i.prodotto, qty: i.qty })), fornitoreSelezionato);
    window.open("https://wa.me/?text=" + encodeURIComponent(txt), "_blank");
  }

  return (
    <PageLayout>
      <div style={{ ...STYLES.page, display: "flex", gap: SPACING.lg, alignItems: "flex-start" }}>
        {/* Colonna principale */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Header */}
          <div style={STYLES.header} data-testid="catalogo-header">
            <div>
              <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>Catalogo Ordini</h1>
              <div style={{ fontSize: 13, opacity: 0.8, marginTop: 4 }}>
                {prodotti.length} prodotti disponibili
              </div>
            </div>
          </div>

          {err && <div style={{ background: "#fee2e2", color: COLORS.danger, padding: 12, borderRadius: 8, marginBottom: 12, fontSize: 13 }}>{err}</div>}
          {msg && <div style={{ background: "#dcfce7", color: "#166534", padding: 12, borderRadius: 8, marginBottom: 12, fontSize: 13 }}>{msg}</div>}

          {/* Filtri */}
          <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
            <input
              style={{ ...STYLES.input, maxWidth: 240 }}
              placeholder="Cerca prodotto..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              data-testid="search-catalogo"
            />
            <select
              style={{ ...STYLES.select, maxWidth: 180 }}
              value={fornitoreSelezionato}
              onChange={e => setFornitoreSelezionato(e.target.value)}
              data-testid="select-fornitore"
            >
              <option value="">Tutti i fornitori</option>
              {[...new Set(prodotti.map(p => p.fornitore).filter(Boolean))].sort().map(f => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </div>

          {/* Tab categorie */}
          <div style={{ display: "flex", gap: 0, borderBottom: `2px solid ${COLORS.grayLight}`, marginBottom: 16 }}>
            {CATEGORIE.map(cat => (
              <button
                key={cat}
                data-testid={`cat-${cat}`}
                onClick={() => setCategoria(cat)}
                style={{
                  padding: "8px 16px", border: "none", background: "transparent",
                  borderBottom: categoria === cat ? `2px solid ${COLORS.primary}` : "2px solid transparent",
                  color: categoria === cat ? COLORS.primary : COLORS.gray,
                  fontWeight: categoria === cat ? 700 : 500,
                  cursor: "pointer", fontSize: 13, marginBottom: -2,
                }}
              >{cat}</button>
            ))}
          </div>

          {loading ? (
            <div style={{ textAlign: "center", padding: 60, color: COLORS.gray }}>Caricamento...</div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 12 }}>
              {prodottiFiltrati.map(p => {
                const inCarrello = carrello[p.id]?.qty || 0;
                return (
                  <div
                    key={p.id}
                    data-testid={`card-prodotto-${p.id}`}
                    style={{
                      ...STYLES.card, padding: 0, overflow: "hidden",
                      border: inCarrello > 0 ? `2px solid ${COLORS.success}` : `1px solid ${COLORS.grayLight}`,
                      cursor: "pointer", transition: "transform 0.12s, box-shadow 0.12s",
                    }}
                    onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "0 6px 20px rgba(0,0,0,0.12)"; }}
                    onMouseLeave={e => { e.currentTarget.style.transform = "translateY(0)"; e.currentTarget.style.boxShadow = "0 2px 8px rgba(0,0,0,0.08)"; }}
                  >
                    {/* Immagine o placeholder */}
                    <div style={{ height: 120, background: p.immagine_url ? "#f0f0f0" : (p.categoria === "pasticceria" ? "#fef3c7" : "#dbeafe"), overflow: "hidden", position: "relative" }}>
                      {p.immagine_url ? (
                        <img src={p.immagine_url} alt={p.nome} style={{ width: "100%", height: "100%", objectFit: "cover" }} onError={e => { e.target.style.display = "none"; }} />
                      ) : (
                        <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 36 }}>
                          {p.categoria === "pasticceria" ? "🎂" : p.categoria === "bar" ? "☕" : "🍕"}
                        </div>
                      )}
                      {p.sotto_scorta && (
                        <div style={{ position: "absolute", top: 6, right: 6, background: COLORS.danger, color: "white", fontSize: 9, padding: "2px 6px", borderRadius: 10, fontWeight: 700 }}>SCORTA</div>
                      )}
                    </div>
                    <div style={{ padding: "10px 12px" }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: COLORS.primary, marginBottom: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={p.nome}>{p.nome}</div>
                      {p.fornitore && <div style={{ fontSize: 11, color: COLORS.gray, marginBottom: 6 }}>{p.fornitore}</div>}
                      <div style={{ fontSize: 12, color: COLORS.gray, marginBottom: 8 }}>
                        {p.prezzo_kg > 0 ? `€ ${p.prezzo_kg.toFixed(2)}/kg` : "Prezzo N/D"}
                      </div>
                      {inCarrello > 0 ? (
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <button style={{ width: 26, height: 26, border: `1px solid ${COLORS.grayLight}`, borderRadius: 6, background: "white", cursor: "pointer", fontSize: 14 }} onClick={() => updateQty(p.id, inCarrello - 1)}>−</button>
                          <span style={{ fontWeight: 700, minWidth: 24, textAlign: "center", color: COLORS.success }}>{inCarrello}</span>
                          <button style={{ width: 26, height: 26, border: `1px solid ${COLORS.grayLight}`, borderRadius: 6, background: "white", cursor: "pointer", fontSize: 14 }} onClick={() => updateQty(p.id, inCarrello + 1)}>+</button>
                        </div>
                      ) : (
                        <button
                          style={{ ...button("primary"), width: "100%", padding: "6px 0", fontSize: 12 }}
                          onClick={() => addToCart(p)}
                          data-testid={`btn-add-${p.id}`}
                        >+ Aggiungi</button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          {!loading && prodottiFiltrati.length === 0 && (
            <div style={{ textAlign: "center", padding: 60, color: COLORS.gray }}>Nessun prodotto trovato</div>
          )}
        </div>

        {/* Carrello laterale fisso */}
        <div style={{
          width: 300, flexShrink: 0, position: "sticky", top: 20,
          ...STYLES.card, border: `2px solid ${totaleItems > 0 ? COLORS.success : COLORS.grayLight}`,
        }} data-testid="carrello-laterale">
          <h3 style={{ margin: 0, marginBottom: 12, color: COLORS.primary, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            Carrello
            {totaleItems > 0 && (
              <span style={{ background: COLORS.success, color: "white", borderRadius: "50%", width: 24, height: 24, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700 }}>
                {totaleItems}
              </span>
            )}
          </h3>
          {itemsCarrello.length === 0 ? (
            <div style={{ textAlign: "center", padding: "24px 0", color: COLORS.gray, fontSize: 13 }}>
              Nessun prodotto nel carrello
            </div>
          ) : (
            <>
              <div style={{ maxHeight: 340, overflowY: "auto", marginBottom: 12 }}>
                {itemsCarrello.map(({ prodotto, qty }) => (
                  <div key={prodotto.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: `1px solid ${COLORS.grayLight}` }}>
                    <div style={{ flex: 1, fontSize: 12, fontWeight: 600 }}>{prodotto.nome}</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <button style={{ width: 20, height: 20, border: `1px solid ${COLORS.grayLight}`, borderRadius: 4, background: "white", cursor: "pointer", fontSize: 12 }} onClick={() => updateQty(prodotto.id, qty - 1)}>−</button>
                      <span style={{ fontSize: 12, fontWeight: 700, minWidth: 20, textAlign: "center" }}>{qty}</span>
                      <button style={{ width: 20, height: 20, border: `1px solid ${COLORS.grayLight}`, borderRadius: 4, background: "white", cursor: "pointer", fontSize: 12 }} onClick={() => updateQty(prodotto.id, qty + 1)}>+</button>
                      <button style={{ width: 20, height: 20, border: "none", background: "#fee2e2", color: COLORS.danger, borderRadius: 4, cursor: "pointer", fontSize: 11 }} onClick={() => removeFromCart(prodotto.id)}>✕</button>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ paddingTop: 8, borderTop: `1px solid ${COLORS.grayLight}`, fontSize: 12, color: COLORS.gray, marginBottom: 12 }}>
                {itemsCarrello.length} prodotti · {totaleItems} pezzi totali
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <button
                  style={{ ...button("success"), width: "100%" }}
                  onClick={inviaWhatsApp}
                  data-testid="btn-whatsapp"
                >Invia WhatsApp</button>
                <button
                  style={{ ...button("primary"), width: "100%" }}
                  onClick={salvaOrdine}
                  disabled={salvando}
                  data-testid="btn-salva-ordine"
                >{salvando ? "Salvataggio..." : "Salva Bozza"}</button>
                <button
                  style={{ ...button("outline"), width: "100%", fontSize: 12 }}
                  onClick={() => setCarrello({})}
                >Svuota carrello</button>
              </div>
            </>
          )}
        </div>
      </div>
    </PageLayout>
  );
}
