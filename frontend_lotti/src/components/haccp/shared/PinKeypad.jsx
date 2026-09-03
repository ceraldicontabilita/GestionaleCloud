import { useState, useEffect } from "react";
import { apiError } from "../../../utils/apiError";
import axios from "axios";
import { API } from "../../../utils/constants";
import { saveToken, saveRuolo, saveOperatoreNome } from "@/auth";

const buzz = (ms = 12) => {
  try {
    navigator.vibrate && navigator.vibrate(ms);
  } catch (e) {
    /* no-op */
  }
};

/**
 * Keypad PIN riutilizzabile (login dipendenti e admin).
 *
 * Props:
 *  - titolo, sottotitolo
 *  - colore: tinta principale (default salvia)
 *  - maxLen: lunghezza PIN (4 dipendenti, 6 admin)
 *  - soloAdmin: se true, accetta solo ruolo amministratore
 *  - onSuccess(operatore), onCancel()
 */
export default function PinKeypad({
  titolo,
  sottotitolo,
  colore = "#5b7a6b",
  maxLen = 6,
  soloAdmin = false,
  onSuccess,
  onCancel,
}) {
  const [digits, setDigits] = useState("");
  const [errore, setErrore] = useState("");
  const [shake, setShake] = useState(false);
  const [loading, setLoading] = useState(false);
  const [okNome, setOkNome] = useState(null);
  const [scelte, setScelte] = useState([]);

  const conferma = async (operatoreId = null) => {
    if (loading || digits.length < 4) return;
    setLoading(true);
    try {
      const res = await axios.post(`${API}/tablet-operatori/login`, {
        pin: digits,
        ...(operatoreId ? { operatore_id: operatoreId } : {}),
      });
      if (res.data?.scelta_operatore) {
        const candidati = (res.data.operatori || []).filter(
          (op) => !soloAdmin || op?.ruolo === "amministratore"
        );
        if (!candidati.length) {
          setErrore("Solo l'amministratore può accedere");
          setDigits("");
        } else {
          setScelte(candidati);
        }
        setLoading(false);
        return;
      }
      const op = res.data.operatore;
      if (res.data && res.data.token) saveToken(res.data.token);
      saveRuolo(op?.ruolo || "operatore");
      saveOperatoreNome(op?.nome || "");
      if (soloAdmin && op?.ruolo !== "amministratore") {
        buzz([40, 60, 40]);
        setErrore("Solo l'amministratore può accedere");
        setShake(true);
        setTimeout(() => {
          setShake(false);
          setDigits("");
          setScelte([]);
          setLoading(false);
        }, 700);
        return;
      }
      buzz(20);
      setOkNome(op?.nome || "");
      setTimeout(() => onSuccess(op), 650);
    } catch (err) {
      buzz([40, 60, 40]);
      setErrore(apiError(err, "PIN non riconosciuto"));
      setShake(true);
      setTimeout(() => {
        setShake(false);
        setDigits("");
        setScelte([]);
        setLoading(false);
      }, 700);
    }
  };

  useEffect(() => {
    if (digits.length === maxLen) conferma();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [digits]);

  const addDigit = (d) => {
    if (loading || digits.length >= maxLen) return;
    buzz(10);
    setDigits((p) => p + d);
    setErrore("");
  };
  const delDigit = () => {
    if (loading) return;
    buzz(10);
    setDigits((d) => d.slice(0, -1));
    setErrore("");
  };

  const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫"];

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(42,51,41,0.55)",
        backdropFilter: "blur(3px)",
        WebkitBackdropFilter: "blur(3px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 400,
        padding: 16,
      }}
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fffefb",
          borderRadius: 26,
          padding: "30px 24px",
          width: "100%",
          maxWidth: 340,
          boxShadow: "0 24px 70px rgba(42,51,41,0.35)",
          animation: shake ? "shake .5s" : "none",
        }}
      >
        <style>{`
          @keyframes shake {
            0%,100%{transform:translateX(0)}
            20%{transform:translateX(-12px)}
            40%{transform:translateX(12px)}
            60%{transform:translateX(-8px)}
            80%{transform:translateX(8px)}
          }
          @keyframes popIn { 0%{transform:scale(.6);opacity:0} 100%{transform:scale(1);opacity:1} }
          .pin-key:active { transform: scale(.94); }
        `}</style>

        {okNome !== null ? (
          <div style={{ textAlign: "center", padding: "24px 0" }}>
            <div
              style={{
                width: 72,
                height: 72,
                borderRadius: 99,
                margin: "0 auto 16px",
                background: colore,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                animation: "popIn .35s ease",
                boxShadow: `0 8px 24px ${colore}55`,
              }}
            >
              <span style={{ fontSize: 38, color: "#fff" }}>✓</span>
            </div>
            <h2
              style={{
                margin: 0,
                fontSize: 22,
                fontWeight: 600,
                color: "#2a3329",
                fontFamily: "'Fraunces', Georgia, serif",
              }}
            >
              Ciao{okNome ? `, ${okNome}` : ""}
            </h2>
            <p style={{ margin: "6px 0 0", fontSize: 13, color: "#6b7669" }}>Accesso effettuato</p>
          </div>
        ) : scelte.length > 0 ? (
          <div>
            <div style={{ textAlign: "center", marginBottom: 20 }}>
              <div style={{ fontSize: 34, marginBottom: 8 }}>👤</div>
              <h2 style={{ margin: 0, fontSize: 21, fontWeight: 600, color: "#2a3329", fontFamily: "'Fraunces', Georgia, serif" }}>
                Chi sta operando?
              </h2>
              <p style={{ margin: "7px 0 0", fontSize: 13, color: "#6b7669" }}>
                Il PIN è condiviso; scegli il nome da registrare nei log.
              </p>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {scelte.map((op) => (
                <button
                  key={op.id}
                  onClick={() => conferma(op.id)}
                  disabled={loading}
                  style={{ padding: "15px 14px", border: "none", borderRadius: 14, background: colore, color: "#fff", fontFamily: "inherit", fontSize: 16, fontWeight: 700, cursor: "pointer", opacity: loading ? 0.6 : 1 }}
                >
                  {op.nome}
                </button>
              ))}
            </div>
            <button
              onClick={() => { setScelte([]); setDigits(""); setErrore(""); }}
              disabled={loading}
              style={{ width: "100%", marginTop: 14, padding: 12, border: "1.5px solid #e6e0d4", borderRadius: 14, background: "#fffefb", color: "#6b7669", fontFamily: "inherit", fontSize: 14, fontWeight: 600, cursor: "pointer" }}
            >
              Indietro
            </button>
          </div>
        ) : (
          <>
            <div style={{ textAlign: "center", marginBottom: 22 }}>
              <div style={{ fontSize: 34, marginBottom: 8 }}>🔐</div>
              <h2
                style={{
                  margin: 0,
                  fontSize: 21,
                  fontWeight: 600,
                  color: "#2a3329",
                  fontFamily: "'Fraunces', Georgia, serif",
                  letterSpacing: "-0.01em",
                }}
              >
                {titolo}
              </h2>
              {sottotitolo && (
                <p style={{ margin: "6px 0 0", fontSize: 13, color: "#6b7669" }}>{sottotitolo}</p>
              )}
            </div>

            <div style={{ display: "flex", justifyContent: "center", gap: 12, marginBottom: 22 }}>
              {Array.from({ length: maxLen }).map((_, i) => (
                <div
                  key={i}
                  style={{
                    width: 15,
                    height: 15,
                    borderRadius: 99,
                    background: i < digits.length ? colore : "#e6e0d4",
                    transition: "all .15s",
                    transform: i < digits.length ? "scale(1.1)" : "scale(1)",
                    boxShadow: i < digits.length ? `0 0 0 4px ${colore}22` : "none",
                  }}
                />
              ))}
            </div>

            {errore && (
              <div
                style={{
                  background: "#fbe6e2",
                  border: "1px solid #f3cfc8",
                  borderRadius: 10,
                  padding: "10px 14px",
                  marginBottom: 16,
                  textAlign: "center",
                  fontSize: 13,
                  fontWeight: 600,
                  color: "#8f3829",
                }}
              >
                {errore}
              </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10 }}>
              {KEYS.map((k, i) => {
                if (k === "") return <div key={i} />;
                const isDel = k === "⌫";
                return (
                  <button
                    key={i}
                    className="pin-key"
                    onClick={() => (isDel ? delDigit() : addDigit(k))}
                    disabled={loading}
                    style={{
                      height: 62,
                      borderRadius: 14,
                      border: "none",
                      background: isDel ? "#f0ebe0" : "#f7f4ec",
                      color: isDel ? "#6b7669" : "#2a3329",
                      fontSize: isDel ? 22 : 25,
                      fontWeight: 600,
                      cursor: "pointer",
                      userSelect: "none",
                      transition: "transform .08s, background .12s",
                      WebkitTapHighlightColor: "transparent",
                      fontFamily: "inherit",
                    }}
                    onTouchStart={(e) =>
                      (e.currentTarget.style.background = isDel ? "#e6e0d4" : "#e8efe9")
                    }
                    onTouchEnd={(e) =>
                      (e.currentTarget.style.background = isDel ? "#f0ebe0" : "#f7f4ec")
                    }
                  >
                    {k}
                  </button>
                );
              })}
            </div>

            <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
              <button
                onClick={onCancel}
                style={{
                  flex: 1,
                  padding: "13px",
                  border: "1.5px solid #e6e0d4",
                  borderRadius: 14,
                  background: "#fffefb",
                  fontFamily: "inherit",
                  fontSize: 14,
                  fontWeight: 600,
                  color: "#6b7669",
                  cursor: "pointer",
                }}
              >
                Annulla
              </button>
              <button
                onClick={() => conferma()}
                disabled={loading || digits.length < 4}
                style={{
                  flex: 2,
                  padding: "13px",
                  border: "none",
                  borderRadius: 14,
                  background: colore,
                  color: "#fff",
                  fontFamily: "inherit",
                  fontSize: 14,
                  fontWeight: 700,
                  cursor: "pointer",
                  opacity: loading || digits.length < 4 ? 0.45 : 1,
                  boxShadow: `0 4px 14px ${colore}40`,
                  transition: "opacity .15s",
                }}
              >
                {loading ? "Verifica…" : "Conferma"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
