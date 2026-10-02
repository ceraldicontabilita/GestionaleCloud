// Navigazione dell'app principale (hash routing) — estratta da App.js
// (fase 2 ristrutturazione 24/07/2026). Un solo posto per: tab iniziale,
// cambio pagina con controllo permessi, sincronizzazione tasto Indietro,
// titolo documento e hash sempre allineato.
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { isAdmin } from "../auth";
import { PAGE_NAMES } from "../config/pageMeta";
import { puoAprireTab, tabRiservataAdmin } from "../config/permissions";

// Alias storici: i vecchi deep-link #ricettario/#food_cost aprono Ricette
const ALIAS_TAB = { ricettario: "ricette", food_cost: "ricette", in_menu: "ricette" };

export function getInitialTab() {
  const hash = window.location.hash.replace("#", "").split("/")[0];
  if (ALIAS_TAB[hash]) return ALIAS_TAB[hash];
  if (!hash) return "dashboard";
  // Un indirizzo sconosciuto resta tale: la pagina dice «non trovata» e
  // riporta alla Home, invece di aprire la Home in silenzio.
  return hash;
}

export function useAppNavigation() {
  const [activeTab, setActiveTab] = useState(getInitialTab);

  const handleTabChange = (tabId) => {
    // Sezioni riservate all'amministratore: i dipendenti girano liberi su
    // tutte le altre pagine (fonte unica: config/permissions.js)
    if (!puoAprireTab(tabId, isAdmin())) {
      toast.error("Sezione riservata all'amministratore");
      return;
    }
    setActiveTab(tabId);
    window.location.hash = tabId;
  };

  // Sync browser back/forward (tasto Indietro) + guardia admin sugli hash
  useEffect(() => {
    const onHash = () => {
      const hash = window.location.hash.replace("#", "").split("/")[0];
      if (hash && tabRiservataAdmin(hash) && !isAdmin()) {
        window.location.hash = "dashboard";
        return;
      }
      const dest = ALIAS_TAB[hash] || hash;
      if (hash === "in_menu") window.location.hash = "ricette/prezzi";
      if (dest && dest !== activeTab) setActiveTab(dest);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [activeTab]);

  // Titolo della pagina + URL sempre allineato (per condividere il link esatto)
  useEffect(() => {
    const nome = PAGE_NAMES[activeTab] || "Gestionale";
    document.title = `${nome} · HACCP Ceraldi`;
    const cur = window.location.hash.replace("#", "").split("/")[0];
    if (activeTab && cur !== activeTab) window.location.hash = cur === "in_menu" ? "ricette/prezzi" : activeTab;
  }, [activeTab]);

  return { activeTab, setActiveTab, handleTabChange };
}
