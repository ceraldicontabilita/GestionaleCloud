/**
 * AttrezzatureView.jsx — «Frigoriferi e congelatori» (richiesta Enzo
 * 25/07/2026: "una voce di menu per rinominarli in un posto solo, sì").
 *
 * Prima d'ora i nomi si cambiavano SOLO cliccando sull'intestazione di una
 * colonna dentro Temperature positive / Temperature negative: funzionava, ma
 * nessuno lo avrebbe indovinato. Qui c'è un elenco unico: si legge il nome, lo
 * si corregge, si salva. Da qui si aggiunge un apparecchio nuovo, si toglie
 * uno dismesso e si segnala un guasto (che porta subito allo spostamento dei
 * lotti che c'erano dentro).
 *
 * Il nome è quello che compare OVUNQUE: registri temperature, etichette dei
 * lotti, scelta del posto dal tablet. Cambiandolo qui si aggiorna anche lo
 * storico dei controlli già registrati (il registro resta leggibile: un
 * apparecchio che oggi si chiama "Cella 1" era lo stesso anche a gennaio).
 */
import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { conferma } from "../../utils/conferma";
import { apiError } from "../../utils/apiError";
import { API } from "../../utils/constants";
import { Refrigerator, Snowflake, Plus, Trash2, Check, RotateCcw } from "lucide-react";
import SegnalaGuasto from "./shared/SegnalaGuasto";

const GRUPPI = [
  {
    tipo: "frigo",
    titolo: "Frigoriferi",
    singolare: "frigorifero",
    sottotitolo: "Temperatura di riferimento 0 °C / +4 °C",
    icona: Refrigerator,
    campo: "frigoriferi",
    categoria: "Frigorifero",
    esempio: "es. Cella 1, Frigo pasticceria, Banco bar",
  },
  {
    tipo: "congelatore",
    titolo: "Congelatori",
    singolare: "congelatore",
    sottotitolo: "Temperatura di riferimento −22 °C / −18 °C",
    icona: Snowflake,
    campo: "congelatori",
    categoria: "Congelatore",
    esempio: "es. Pozzetto gelati, Congelatore magazzino",
  },
];

// Una riga = un apparecchio. Il nome è modificabile sul posto; il bottone
// «Salva» compare solo quando il testo è davvero cambiato, così un tocco per
// sbaglio non riscrive nulla.
function RigaAttrezzatura({ item, gruppo, onRinomina, onElimina }) {
  const [nome, setNome] = useState(item.nome || "");
  const [salvando, setSalvando] = useState(false);
  useEffect(() => { setNome(item.nome || ""); }, [item.nome]);

  const cambiato = nome.trim() !== (item.nome || "").trim();

  const salva = async () => {
    if (!nome.trim()) { toast.error("Il nome non può restare vuoto"); return; }
    setSalvando(true);
    try {
      await onRinomina(gruppo.tipo, item.numero, nome.trim());
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div style={{
      background: "#fffefb", border: "1px solid #e6e0d4", borderRadius: 14,
      padding: 12, display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center",
    }}>
      <span style={{
        minWidth: 42, height: 42, borderRadius: 12, background: "#f2f6f3",
        border: "1px solid #cfdfd5", color: "#3f5a4e", fontWeight: 900, fontSize: 15,
        display: "inline-flex", alignItems: "center", justifyContent: "center",
      }}>
        N°{item.numero}
      </span>

      <input
        value={nome}
        onChange={(e) => setNome(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && cambiato) salva(); }}
        aria-label={`Nome ${gruppo.singolare} numero ${item.numero}`}
        style={{
          flex: "1 1 180px", minWidth: 0, minHeight: 44, padding: "10px 12px",
          fontSize: 15, fontWeight: 700, color: "#2a3329", fontFamily: "inherit",
          border: cambiato ? "2px solid #5b7a6b" : "2px solid #e6e0d4",
          borderRadius: 12, background: "#fff", boxSizing: "border-box",
        }}
      />

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginLeft: "auto" }}>
        {cambiato && (
          <>
            <button type="button" onClick={() => setNome(item.nome || "")} title="Annulla la modifica"
              style={{
                minWidth: 44, minHeight: 44, borderRadius: 12, border: "1.5px solid #e6e0d4",
                background: "#fffefb", color: "#6b7669", cursor: "pointer",
                display: "inline-flex", alignItems: "center", justifyContent: "center",
              }}>
              <RotateCcw size={16} />
            </button>
            <button type="button" onClick={salva} disabled={salvando}
              style={{
                minHeight: 44, padding: "0 16px", borderRadius: 12, border: "none",
                background: "#5b7a6b", color: "#fff", fontSize: 14, fontWeight: 800,
                fontFamily: "inherit", cursor: salvando ? "wait" : "pointer",
                opacity: salvando ? 0.6 : 1,
                display: "inline-flex", alignItems: "center", gap: 6,
              }}>
              <Check size={16} /> {salvando ? "Salvo…" : "Salva"}
            </button>
          </>
        )}
        <SegnalaGuasto attrezzatura={item.nome} categoria={gruppo.categoria} compatto={false} />
        <button type="button" onClick={() => onElimina(gruppo.tipo, item)} title="Togli dall'elenco"
          style={{
            minWidth: 44, minHeight: 44, borderRadius: 12, border: "1.5px solid #e6e0d4",
            background: "#fffefb", color: "#a08c7a", cursor: "pointer",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
          }}>
          <Trash2 size={16} />
        </button>
      </div>
    </div>
  );
}

export default function AttrezzatureView() {
  const [dati, setDati] = useState({ frigoriferi: [], congelatori: [] });
  const [loading, setLoading] = useState(true);
  const [nuovi, setNuovi] = useState({ frigo: "", congelatore: "" });
  const [aggiungendo, setAggiungendo] = useState(null);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/attrezzature/`);
      setDati({
        frigoriferi: Array.isArray(data?.frigoriferi) ? data.frigoriferi : [],
        congelatori: Array.isArray(data?.congelatori) ? data.congelatori : [],
      });
    } catch (e) {
      toast.error("Errore caricamento: " + apiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const rinomina = async (tipo, numero, nome) => {
    try {
      await axios.put(`${API}/attrezzature/${tipo}/${numero}/rinomina`, null, { params: { nome } });
      toast.success(`Rinominato in «${nome}» — aggiornato ovunque, anche nei registri già fatti`);
      await carica();
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    }
  };

  const aggiungi = async (tipo) => {
    const nome = (nuovi[tipo] || "").trim();
    if (!nome) { toast.error("Scrivi come si chiama"); return; }
    setAggiungendo(tipo);
    try {
      await axios.post(`${API}/attrezzature/${tipo}`, { nome });
      toast.success(`«${nome}» aggiunto`);
      setNuovi((p) => ({ ...p, [tipo]: "" }));
      await carica();
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    } finally {
      setAggiungendo(null);
    }
  };

  const elimina = async (tipo, item) => {
    const ok = await conferma(
      `Togliere «${item.nome}» dall'elenco? Non comparirà più tra i posti dove mettere la merce. ` +
      "I controlli di temperatura già registrati e i lotti che risultano lì dentro restano come sono."
    );
    if (!ok) return;
    try {
      await axios.delete(`${API}/attrezzature/${tipo}/${item.numero}`);
      toast.success(`«${item.nome}» tolto dall'elenco`);
      await carica();
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    }
  };

  return (
    <div style={{ maxWidth: 860 }}>
      <div style={{
        background: "#f2f6f3", border: "1px solid #cfdfd5", borderRadius: 14,
        padding: "12px 16px", marginBottom: 18, fontSize: 14, color: "#3f5a4e", lineHeight: 1.55,
      }}>
        Qui dai il nome vero ai tuoi apparecchi: <strong>Cella 1</strong>, <strong>Frigo
        pasticceria</strong>, <strong>Pozzetto gelati</strong>. Il nome che scrivi
        compare dappertutto — nei registri delle temperature, sulle etichette dei
        lotti e nella scelta del posto dal tablet — e si aggiorna anche sui
        controlli già registrati, così il registro resta leggibile.
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "60px 0", color: "#9aa89c", fontSize: 14 }}>
          Caricamento…
        </div>
      ) : GRUPPI.map((g) => {
        const Icona = g.icona;
        const lista = dati[g.campo] || [];
        return (
          <section key={g.tipo} style={{ marginBottom: 26 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 2 }}>
              <Icona size={20} color="#5b7a6b" />
              <h2 style={{ margin: 0, fontSize: 17, fontWeight: 900, color: "#2a3329" }}>
                {g.titolo}
              </h2>
              <span style={{
                fontSize: 12, fontWeight: 800, color: "#5b7a6b", background: "#f2f6f3",
                border: "1px solid #cfdfd5", borderRadius: 999, padding: "2px 9px",
              }}>
                {lista.length}
              </span>
            </div>
            <p style={{ margin: "0 0 10px 30px", fontSize: 12.5, color: "#8b968a" }}>
              {g.sottotitolo}
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {lista.length === 0 && (
                <div style={{
                  background: "#fffefb", border: "1px dashed #e6e0d4", borderRadius: 14,
                  padding: 18, textAlign: "center", color: "#9aa89c", fontSize: 13.5,
                }}>
                  Nessun {g.singolare} in elenco. Aggiungine uno qui sotto.
                </div>
              )}
              {lista.map((item) => (
                <RigaAttrezzatura
                  key={`${g.tipo}-${item.numero}`}
                  item={item}
                  gruppo={g}
                  onRinomina={rinomina}
                  onElimina={elimina}
                />
              ))}
            </div>

            <div style={{
              marginTop: 10, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center",
            }}>
              <input
                value={nuovi[g.tipo]}
                onChange={(e) => setNuovi((p) => ({ ...p, [g.tipo]: e.target.value }))}
                onKeyDown={(e) => { if (e.key === "Enter") aggiungi(g.tipo); }}
                placeholder={g.esempio}
                aria-label={`Nome del nuovo ${g.singolare}`}
                style={{
                  flex: "1 1 200px", minWidth: 0, minHeight: 44, padding: "10px 12px",
                  fontSize: 14, fontFamily: "inherit", color: "#2a3329",
                  border: "2px solid #e6e0d4", borderRadius: 12, background: "#fffefb",
                  boxSizing: "border-box",
                }}
              />
              <button type="button" onClick={() => aggiungi(g.tipo)} disabled={aggiungendo === g.tipo}
                style={{
                  minHeight: 44, padding: "0 18px", borderRadius: 12, border: "none",
                  background: "linear-gradient(135deg,#6f9180,#5b7a6b)", color: "#fff",
                  fontSize: 14, fontWeight: 800, fontFamily: "inherit",
                  cursor: aggiungendo === g.tipo ? "wait" : "pointer",
                  opacity: aggiungendo === g.tipo ? 0.6 : 1,
                  display: "inline-flex", alignItems: "center", gap: 7,
                }}>
                <Plus size={16} /> Aggiungi
              </button>
            </div>
          </section>
        );
      })}
    </div>
  );
}
