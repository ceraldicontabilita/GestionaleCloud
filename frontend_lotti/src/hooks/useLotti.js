import { useState, useCallback, useEffect } from "react";
import { apiError } from "../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import { API } from "../utils/constants";

export function useLotti() {
  const [lotti, setLotti] = useState([]);
  const [searchLotti, setSearchLotti] = useState("");
  const [filtroDataDaLotti, setFiltroDataDaLotti] = useState("");
  const [filtroDataALotti, setFiltroDataALotti] = useState("");

  const fetchLotti = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/lotti`, {
        params: {
          search: searchLotti || undefined,
          data_da: filtroDataDaLotti || undefined,
          data_a: filtroDataALotti || undefined,
        },
      });
      setLotti(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      // Non lasciare la pagina muta: mostra la causa reale (server in avvio, non
      // autorizzato, errore server) invece di una lista vuota senza spiegazione.
      console.error("Errore lotti:", e);
      const stato = e?.response?.status;
      const msg = stato === 401 || stato === 403
        ? "Sessione scaduta: rifai l'accesso"
        : !e?.response
          ? "Server non raggiungibile (forse in avvio): riprova tra poco"
          : apiError(e, "Errore nel caricamento dei lotti");
      toast.error(msg);
    }
  }, [searchLotti, filtroDataDaLotti, filtroDataALotti]);

  useEffect(() => {
    const timer = setTimeout(() => fetchLotti(), 300);
    return () => clearTimeout(timer);
  }, [searchLotti, filtroDataDaLotti, filtroDataALotti, fetchLotti]);

  const handleDeleteLotto = async (id) => {
    if (!id || id === "__refresh__") {
      await fetchLotti();
      window.dispatchEvent(new CustomEvent("haccp:lotti-changed"));
      return;
    }
    try {
      await axios.delete(`${API}/lotti/${id}`);
      toast.success("Lotto eliminato");
      await fetchLotti();
      window.dispatchEvent(new CustomEvent("haccp:lotti-changed"));
    } catch (e) {
      toast.error("Errore nell'eliminazione: " + apiError(e));
    }
  };

  // 25/07/2026 — rimosso handleGeneraLotto: il lotto si crea SOLO producendo
  // una ricetta (tablet "Registra produzione"), che scarica gli ingredienti e
  // ne eredita la provenienza. La creazione a mano dalla pagina Lotti generava
  // lotti senza tracciabilità ed era comunque irraggiungibile.
  return {
    lotti,
    searchLotti,
    setSearchLotti,
    filtroDataDaLotti,
    setFiltroDataDaLotti,
    filtroDataALotti,
    setFiltroDataALotti,
    fetchLotti,
    handleDeleteLotto,
  };
}
