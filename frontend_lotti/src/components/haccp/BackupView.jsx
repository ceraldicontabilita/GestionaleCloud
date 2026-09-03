import React, { useState, useEffect, useCallback } from "react";
import { apiError } from "../../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import { API, formatDate } from "../../utils/constants";

export default function BackupView({ onBack }) {
  const [lista, setLista]           = useState([]);
  const [stato, setStato]           = useState(null);
  const [loading, setLoading]       = useState(true);
  const [backingUp, setBackingUp]   = useState(false);
  const [ripristino, setRipristino] = useState(null);   // filename in corso di restore
  const [conferma, setConferma]     = useState(null);   // filename da confermare
  const [risultato, setRisultato]   = useState(null);

  const carica = useCallback(async () => {
    setLoading(true);
    try {
      const [resLista, resStato] = await Promise.all([
        axios.get(`${API}/backup/lista`),
        axios.get(`${API}/backup/stato`),
      ]);
      setLista(resLista.data.backup || []);
      setStato(resStato.data);
    } catch { toast.error("Errore caricamento backup"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const eseguiBackup = async () => {
    setBackingUp(true);
    try {
      const res = await axios.post(`${API}/backup/esegui`);
      toast.success(`Backup creato: ${res.data.file} (${res.data.dimensione})`);
      await carica();
    } catch (e) {
      toast.error("Errore backup: " + apiError(e));
    } finally { setBackingUp(false); }
  };

  const avviaRipristino = async (filename) => {
    setConferma(null);
    setRipristino(filename);
    setRisultato(null);
    try {
      const res = await axios.post(`${API}/backup/ripristina/${encodeURIComponent(filename)}`);
      setRisultato({ success: true, ...res.data });
      toast.success("Database ripristinato con successo");
      await carica();
    } catch (e) {
      const msg = apiError(e);
      setRisultato({ success: false, messaggio: msg });
      toast.error("Restore fallito: " + msg);
    } finally { setRipristino(null); }
  };

  const formatData = (iso) => formatDate(iso, true);

  return (
    <div style={{ minHeight: "100vh", background: "#0f172a" }}>

      {/* ── Header ── */}
      <div style={{
        background: "linear-gradient(135deg, #1e293b, #0f172a)",
        borderBottom: "1px solid #1e293b",
        padding: "16px 20px",
        display: "flex", alignItems: "center", gap: 14
      }}>
        <button onClick={onBack} style={{
          background: "#1e293b", border: "1px solid #334155",
          color: "#94a3b8", borderRadius: 10, padding: "8px 14px",
          fontWeight: 700, cursor: "pointer", fontSize: 13
        }}>← Indietro</button>
        <div>
          <h1 style={{ color: "#f1f5f9", margin: 0, fontSize: 20, fontWeight: 800 }}>
            Backup & Ripristino
          </h1>
          <p style={{ color: "#475569", margin: "2px 0 0", fontSize: 12 }}>
            Database: <span style={{ color: "#d4b87f", fontWeight: 700 }}>Gestionale</span>
            {stato?.stato === "ok" && (
              <span style={{ color: "#64748b" }}> · ultimo backup: {formatData(stato.data)}</span>
            )}
          </p>
        </div>
      </div>

      <div style={{ padding: "20px", maxWidth: 700, margin: "0 auto" }}>

        {/* ── Stato + Azione backup ── */}
        <div style={{
          background: "#1e293b", borderRadius: 16,
          border: "1px solid #334155", padding: "20px",
          marginBottom: 20, display: "flex",
          alignItems: "center", justifyContent: "space-between", gap: 16
        }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <div style={{
                width: 10, height: 10, borderRadius: "50%",
                background: stato?.stato === "ok" ? "#22c55e" : "var(--warning)"
              }} />
              <span style={{ color: "#f1f5f9", fontWeight: 700, fontSize: 15 }}>
                {lista.length} backup disponibili
              </span>
            </div>
            <p style={{ color: "#64748b", margin: 0, fontSize: 12 }}>
              Rotazione automatica: mantieni ultimi 7 · Nightly ore 02:30
            </p>
          </div>
          <button
            onClick={eseguiBackup}
            disabled={backingUp}
            data-testid="backup-esegui-btn"
            style={{
              padding: "12px 22px",
              background: backingUp ? "#334155" : "linear-gradient(135deg, #a8854f, #8a6f47)",
              color: "#fff", border: "none", borderRadius: 12,
              fontWeight: 800, fontSize: 14, cursor: backingUp ? "not-allowed" : "pointer",
              whiteSpace: "nowrap", flexShrink: 0,
              boxShadow: backingUp ? "none" : "0 4px 14px rgba(138,111,71,0.35)"
            }}>
            {backingUp ? "Backup in corso..." : "Backup Ora"}
          </button>
        </div>

        {/* ── Risultato restore ── */}
        {risultato && (
          <div style={{
            background: risultato.success ? "#052e16" : "#1c0a0a",
            border: `1px solid ${risultato.success ? "#166534" : "#7f1d1d"}`,
            borderRadius: 14, padding: "16px 18px", marginBottom: 20
          }}>
            <p style={{
              margin: "0 0 4px", fontWeight: 800, fontSize: 15,
              color: risultato.success ? "#22c55e" : "var(--danger)"
            }}>
              {risultato.success ? "✓ Ripristino completato" : "✗ Ripristino fallito"}
            </p>
            <p style={{ margin: 0, fontSize: 13, color: "#94a3b8" }}>{risultato.messaggio}</p>
            {risultato.success && (
              <p style={{ margin: "6px 0 0", fontSize: 12, color: "#475569" }}>
                Backup di sicurezza pre-restore: <strong style={{ color: "#d4b87f" }}>{risultato.backup_sicurezza}</strong>
                {" "}· Durata: {risultato.durata_s}s
              </p>
            )}
            <button
              onClick={() => setRisultato(null)}
              style={{
                marginTop: 10, padding: "6px 14px", background: "#334155",
                border: "none", color: "#94a3b8", borderRadius: 8,
                fontWeight: 600, cursor: "pointer", fontSize: 12
              }}>
              Chiudi
            </button>
          </div>
        )}

        {/* ── Lista backup ── */}
        <div style={{
          background: "#1e293b", borderRadius: 16,
          border: "1px solid #334155", overflow: "hidden"
        }}>
        <div style={{ overflowX: "auto" }}>
          {/* Header tabella */}
          <div style={{
            display: "grid", gridTemplateColumns: "1fr 90px 140px 140px",
            padding: "10px 18px",
            borderBottom: "1px solid #334155",
            background: "#0f172a"
          }}>
            {["File", "Dim.", "Data", "Azione"].map(h => (
              <span key={h} style={{
                fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase"
              }}>{h}</span>
            ))}
          </div>

          {loading ? (
            <div style={{ padding: 40, textAlign: "center", color: "#475569" }}>
              Caricamento...
            </div>
          ) : lista.length === 0 ? (
            <div style={{ padding: 40, textAlign: "center" }}>
              <p style={{ color: "#475569", margin: 0 }}>Nessun backup disponibile</p>
              <p style={{ color: "#334155", fontSize: 12, margin: "4px 0 0" }}>
                Clicca "Backup Ora" per crearne uno
              </p>
            </div>
          ) : lista.map((b, idx) => (
            <div key={b.file}>
              {/* Riga backup */}
              <div style={{
                display: "grid", gridTemplateColumns: "1fr 90px 140px 140px",
                padding: "13px 18px", alignItems: "center",
                borderBottom: idx < lista.length - 1 ? "1px solid #1e293b" : "none",
                background: idx === 0 ? "rgba(138,111,71,0.06)" : "transparent",
                transition: "background 0.1s"
              }}>
                {/* Nome file */}
                <div>
                  <p style={{ margin: 0, fontSize: 13, fontWeight: 600, color: "#cbd5e1",
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {b.file.replace("", "")}
                  </p>
                  {idx === 0 && (
                    <span style={{
                      fontSize: 10, fontWeight: 700, color: "#a8854f",
                      background: "rgba(138,111,71,0.15)", borderRadius: 4,
                      padding: "1px 6px", marginTop: 2, display: "inline-block"
                    }}>PIÙ RECENTE</span>
                  )}
                </div>

                {/* Dimensione */}
                <span style={{ fontSize: 13, color: "#64748b", fontWeight: 600 }}>
                  {b.dimensione}
                </span>

                {/* Data */}
                <span style={{ fontSize: 12, color: "#64748b" }}>
                  {formatData(b.data)}
                </span>

              {/* Azione */}
                <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
                  {/* Download */}
                  <a
                    href={`${API}/backup/download/${encodeURIComponent(b.file)}`}
                    download={b.file}
                    data-testid={`backup-download-${idx}`}
                    title="Scarica backup"
                    style={{
                      padding: "5px 8px", background: "rgba(16,185,129,0.1)",
                      color: "var(--success)", border: "1px solid rgba(16,185,129,0.3)",
                      borderRadius: 7, fontWeight: 700, cursor: "pointer",
                      fontSize: 11, textDecoration: "none", display: "inline-flex",
                      alignItems: "center", gap: 4
                    }}
                  >
                    ↓
                  </a>
                  {ripristino === b.file ? (
                    <span style={{ fontSize: 12, color: "var(--warning)", fontWeight: 700 }}>
                      Ripristino...
                    </span>
                  ) : conferma === b.file ? (
                    <div style={{ display: "flex", gap: 6 }}>
                      <button
                        onClick={() => avviaRipristino(b.file)}
                        data-testid={`restore-confirm-${idx}`}
                        style={{
                          padding: "5px 10px", background: "var(--danger)",
                          color: "#fff", border: "none", borderRadius: 7,
                          fontWeight: 800, cursor: "pointer", fontSize: 11
                        }}>Sì, ripristina</button>
                      <button
                        onClick={() => setConferma(null)}
                        style={{
                          padding: "5px 10px", background: "#334155",
                          color: "#94a3b8", border: "none", borderRadius: 7,
                          fontWeight: 700, cursor: "pointer", fontSize: 11
                        }}>Annulla</button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setConferma(b.file)}
                      disabled={!!ripristino}
                      data-testid={`restore-btn-${idx}`}
                      style={{
                        padding: "6px 12px", background: "#334155",
                        color: "#94a3b8", border: "1px solid #475569",
                        borderRadius: 8, fontWeight: 700, cursor: "pointer", fontSize: 12,
                        opacity: ripristino ? 0.4 : 1
                      }}>
                      Ripristina
                    </button>
                  )}
                </div>
              </div>

              {/* Banner conferma — appare sotto la riga */}
              {conferma === b.file && (
                <div style={{
                  background: "#1c0a0a", borderTop: "1px solid #7f1d1d",
                  padding: "12px 18px"
                }}>
                  <p style={{ margin: 0, color: "#fca5a5", fontSize: 13, fontWeight: 700 }}>
                    Attenzione: questa operazione sovrascrive TUTTI i dati attuali.
                  </p>
                  <p style={{ margin: "4px 0 0", color: "var(--danger)", fontSize: 12 }}>
                    Prima del ripristino verrà creato automaticamente un backup di sicurezza.
                    Vuoi continuare con <strong>{b.file}</strong>?
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
        </div>

        {/* ── Info scheduler ── */}
        <div style={{
          marginTop: 14, padding: "12px 16px",
          background: "#1e293b", borderRadius: 12,
          border: "1px solid #334155",
          display: "flex", alignItems: "center", gap: 10
        }}>
          <div style={{
            width: 8, height: 8, borderRadius: "50%",
            background: "#22c55e", flexShrink: 0,
            boxShadow: "0 0 6px rgba(34,197,94,0.5)"
          }} />
          <p style={{ margin: 0, fontSize: 12, color: "#64748b" }}>
            Backup automatico ogni notte alle <strong style={{ color: "#d4b87f" }}>02:30</strong>
            {" "}· Rotazione automatica: ultimi <strong style={{ color: "#d4b87f" }}>7 giorni</strong>
            {" "}· Percorso: <code style={{ color: "#94a3b8", fontSize: 11 }}>/app/backups/db/</code>
          </p>
        </div>
      </div>
    </div>
  );
}
