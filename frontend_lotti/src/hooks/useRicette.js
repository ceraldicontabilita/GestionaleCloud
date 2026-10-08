import { useState, useCallback, useEffect } from "react";
import { apiError } from "../utils/apiError";
import axios from "axios";
import { toast } from "sonner";
import { API } from "../utils/constants";

export function useRicette() {
  const [ricette, setRicette] = useState([]);
  const [searchRicette, setSearchRicette] = useState("");
  const [loadingRicette, setLoadingRicette] = useState(true);

  const fetchRicette = useCallback(async () => {
    // retry robusto: Render puo essere in cold-start (anche 40-60s) sulla prima chiamata
    setLoadingRicette(true);
    let ultimoErr = null;
    for (let tentativo = 0; tentativo < 5; tentativo++) {
      try {
        const res = await axios.get(`${API}/ricette`, { params: { search: searchRicette || undefined }, timeout: 45000 });
        setRicette(Array.isArray(res.data) ? res.data : (res.data?.ricette || []));
        setLoadingRicette(false);
        return;
      } catch (e) {
        ultimoErr = e;
        await new Promise((r) => setTimeout(r, 2000 * (tentativo + 1)));
      }
    }
    console.error("Errore ricette:", ultimoErr);
    setLoadingRicette(false);
  }, [searchRicette]);

  useEffect(() => {
    const timer = setTimeout(() => fetchRicette(), 300);
    return () => clearTimeout(timer);
  }, [searchRicette, fetchRicette]);

  const handleAddRicetta = async (data) => {
    try {
      const res = await axios.post(`${API}/ricette`, data);
      toast.success("Ricetta aggiunta!");
      await fetchRicette();
      return res.data;
    } catch (e) {
      toast.error("Errore nell'aggiunta");
    }
  };

  const handleUpdateRicetta = async (id, data) => {
    try {
      await axios.put(`${API}/ricette/${id}`, data);
      toast.success("Ricetta aggiornata!");
      await fetchRicette();
    } catch (e) {
      toast.error("Errore nell'aggiornamento");
    }
  };

  const handleDeleteRicetta = async (id) => {
    try {
      await axios.delete(`${API}/ricette/${id}`);
      toast.success("Ricetta eliminata");
      await fetchRicette();
    } catch (e) {
      toast.error("Errore nell'eliminazione: " + apiError(e));
    }
  };

  const handleClonaRicetta = async (ricetta) => {
    const nuovoNome = `${ricetta.nome} (copia)`;
    try {
      const payload = {
        nome: nuovoNome,
        ingredienti: [...(ricetta.ingredienti || [])],
        ingredienti_dettaglio: [...(ricetta.ingredienti_dettaglio || [])],
        note: ricetta.note || "",
        reparto: ricetta.reparto || "",
        ricetta_base_id: ricetta.ricetta_base_id || ricetta.id,
        ricetta_base_nome: ricetta.ricetta_base_id ? ricetta.ricetta_base_nome : ricetta.nome,
      };
      await axios.post(`${API}/ricette`, payload);
      toast.success(`"${nuovoNome}" creata come variante di "${payload.ricetta_base_nome}"!`);
      await fetchRicette();
    } catch {
      toast.error("Errore nella clonazione");
    }
  };

  return {
    ricette,
    loadingRicette,
    searchRicette,
    setSearchRicette,
    fetchRicette,
    handleAddRicetta,
    handleUpdateRicetta,
    handleDeleteRicetta,
    handleClonaRicetta,
  };
}
