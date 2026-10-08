/**
 * tablet/ModalCambioFoto.jsx — Modal upload/URL foto per prodotto tablet
 */
import React, { useState } from "react";
import { apiError } from "../../../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import { API, fotoSrc } from "../../../utils/constants";

export function ModalCambioFoto({ prodotto, onClose, onSalvato }) {
  const [nuovaFotoUrl, setNuovaFotoUrl] = useState(prodotto.foto_url || "");
  const [uploading, setUploading] = useState(false);
  const fileRef = React.useRef(null);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await axios.post(`${API}/ricette/${prodotto.id}/upload-foto`, form, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      const url = res.data.foto_url;
      setNuovaFotoUrl(url);
      onSalvato && onSalvato(url);
      toast.success("Foto caricata!");
      onClose();
    } catch (e) {
      toast.error("Errore upload: " + apiError(e));
    } finally {
      setUploading(false);
    }
  };

  const handleSalvaUrl = async () => {
    if (!nuovaFotoUrl.trim()) return;
    try {
      await axios.put(`${API}/ricette/${prodotto.id}/foto`, null, {
        params: { foto_url: nuovaFotoUrl.trim() }
      });
      onSalvato && onSalvato(nuovaFotoUrl.trim());
      toast.success("Foto aggiornata!");
      onClose();
    } catch (e) {
      toast.error("Errore: " + apiError(e));
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", zIndex: 1100, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <div style={{ background: "#fff", borderRadius: 20, padding: 28, width: "100%", maxWidth: 420, boxShadow: "0 20px 60px rgba(0,0,0,0.3)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, textTransform: "capitalize" }}>
            Foto — {prodotto.nome}
          </h3>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: "#a39a87" }}>✕</button>
        </div>

        {nuovaFotoUrl && (
          <div style={{ marginBottom: 14, borderRadius: 12, overflow: "hidden", height: 140, background: "#f0ebe0" }}>
            <img src={fotoSrc(nuovaFotoUrl)} alt="anteprima" style={{ width: "100%", height: "100%", objectFit: "cover" }}
              onError={(e) => { e.target.style.display = "none"; }} />
          </div>
        )}

        <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }} onChange={handleUpload} />
        <button onClick={() => fileRef.current?.click()} disabled={uploading} style={{
          width: "100%", padding: "12px 0", borderRadius: 12, border: "2px dashed #cfc6b4",
          background: "#faf7f0", fontWeight: 700, fontSize: 14, cursor: "pointer", color: "#5c564a",
          marginBottom: 12, display: "flex", alignItems: "center", justifyContent: "center", gap: 8
        }}>
          {uploading ? "Caricamento..." : "📁 Carica dal dispositivo"}
        </button>

        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <div style={{ flex: 1, height: 1, background: "#e6e0d4" }} />
          <span style={{ fontSize: 11, color: "#a39a87", fontWeight: 600 }}>oppure incolla URL</span>
          <div style={{ flex: 1, height: 1, background: "#e6e0d4" }} />
        </div>

        <input type="text" value={nuovaFotoUrl} onChange={(e) => setNuovaFotoUrl(e.target.value)}
          placeholder="https://images.pexels.com/..."
          style={{ width: "100%", padding: "12px 16px", borderRadius: 12, border: "2px solid #e6e0d4", fontSize: 14, boxSizing: "border-box", marginBottom: 14 }} />
        <div style={{ display: "flex", gap: 10 }}>
          <button onClick={onClose} style={{
            flex: 1, padding: "12px 0", borderRadius: 12, border: "1px solid #e6e0d4",
            background: "#faf7f0", fontWeight: 600, fontSize: 14, cursor: "pointer", color: "#7a7266"
          }}>Annulla</button>
          <button onClick={handleSalvaUrl} disabled={!nuovaFotoUrl.trim()} style={{
            flex: 2, padding: "12px 0", borderRadius: 12, border: "none",
            background: "linear-gradient(135deg,#a8854f,#8a6f47)", color: "#fff",
            fontWeight: 700, fontSize: 15, cursor: nuovaFotoUrl.trim() ? "pointer" : "not-allowed",
            opacity: nuovaFotoUrl.trim() ? 1 : 0.5
          }}>Salva URL</button>
        </div>
      </div>
    </div>
  );
}

export default ModalCambioFoto;
