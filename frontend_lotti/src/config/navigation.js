import {
  AlertCircle, AlertTriangle, BarChart3, BookMarked, BookOpen, Bug,
  Building2, ChefHat, ClipboardCheck, FileText, Flame, FlaskConical,
  Globe, HelpCircle, IceCreamBowl, Layers, Network, Package,
  Refrigerator, Scale, Settings, ShieldCheck, ShoppingCart, Snowflake,
  Sparkles, Tag, Thermometer, TrendingUp, Truck, UtensilsCrossed, Users,
  Wheat,
} from "lucide-react";

// Le cinque destinazioni più frequenti restano sempre visibili.
export const PRIMARY_TABS = [
  { id: "dashboard", label: "Oggi", icon: BarChart3 },
  { id: "ricette", label: "Produzione", icon: ChefHat },
  { id: "lotti", label: "Tracciabilità", icon: Layers },
  { id: "movimenti_magazzino", label: "Magazzino", icon: Package },
  { id: "ordini", label: "Acquisti", icon: ShoppingCart },
];

// Le funzioni meno frequenti sono raggruppate per attività, non per struttura tecnica.
export const SECONDARY_TABS = [
  { section: "Produzione e scorte", id: "gelati", label: "Gelati e semilavorati", icon: IceCreamBowl },
  { section: "Produzione e scorte", id: "cosa_usare_oggi", label: "Lotti da usare oggi", icon: AlertTriangle },
  { section: "Produzione e scorte", id: "produzione_consigliata", label: "Produzione consigliata", icon: ChefHat },
  { section: "Produzione e scorte", id: "storico_produzioni", label: "Storico produzioni", icon: FileText },
  { section: "Produzione e scorte", id: "materie", label: "Materie prime", icon: Wheat },
  // 19/09/2026 — la vetrina di ciò che i clienti vedono nel Menu digitale:
  // sta fra le voci di vendita, non nel backoffice (è un contenitore visivo
  // dei prodotti da vendere, non una pagina di amministrazione).
  { section: "Acquisti e vendita", id: "in_menu", label: "In menu", icon: UtensilsCrossed },
  { section: "Acquisti e vendita", id: "fornitori", label: "Fornitori", icon: Building2 },
  { section: "Acquisti e vendita", id: "comparatore", label: "Confronto prezzi", icon: Scale },
  { section: "Acquisti e vendita", id: "prodotti", label: "Listini e cataloghi", icon: Tag },
  { section: "Acquisti e vendita", id: "corrispettivi", label: "Corrispettivi", icon: TrendingUp },
  { section: "Analisi", id: "mappa_tracciabilita", label: "Mappa tracciabilità", icon: Network },
  { section: "Supporto", id: "guida", label: "Guida", icon: HelpCircle },
];

// Impostazioni e amministrazione: si aprono dall'ingranaggio fisso in alto a
// destra, visibile solo al titolare (26/09/2026). Non stanno più sotto «Altro».
export const IMPOSTAZIONI_TABS = [
  { id: "backoffice", label: "Backoffice", icon: Settings },
  { id: "configura", label: "Configurazione", icon: ClipboardCheck },
  // 25/07/2026 — prima i nomi si cambiavano solo dall'intestazione delle
  // colonne in Temperature: qui c'è un elenco unico e trovabile.
  { id: "attrezzature", label: "Frigoriferi e congelatori", icon: Refrigerator },
  { id: "dizionario", label: "Dizionario ingredienti", icon: BookMarked },
  { id: "cataloghi_esterni", label: "Cataloghi fornitori", icon: Globe },
  { id: "controllo_dati", label: "Verifica dati", icon: ShieldCheck },
  // GC-02h: il titolare segna «n.a.» lo storico HACCP senza firma
  { id: "attendibilita_haccp", label: "Attendibilità registri HACCP", icon: ShieldCheck },
  { id: "collaudi", label: "Collaudi", icon: FlaskConical },
];

export const HACCP_TABS = [
  { id: "disinfestazione", label: "Disinfestazione", icon: Bug, color: "text-red-600" },
  { id: "sanificazione", label: "Sanificazione", icon: Sparkles, color: "text-[#5b7a6b]" },
  { id: "temp_negative", label: "Temperature negative", icon: Snowflake, color: "text-[#5b7a6b]" },
  { id: "temp_positive", label: "Temperature positive", icon: Thermometer, color: "text-orange-600" },
  { id: "anomalie", label: "Anomalie", icon: AlertCircle, color: "text-amber-600" },
  { id: "controllo_olio", label: "Olio frittura", icon: Flame, color: "text-orange-600" },
  { id: "temp_cottura", label: "Temperature cottura", icon: Thermometer, color: "text-red-600" },
  { id: "ricezione_merce", label: "Ricezione merce", icon: Truck, color: "text-[#5b7a6b]" },
  { id: "manuale", label: "Manuale HACCP", icon: BookOpen, color: "text-green-600" },
  { id: "registro_haccp", label: "Registro HACCP", icon: ClipboardCheck, color: "text-green-700" },
  { id: "allergeni", label: "Allergeni", icon: AlertTriangle, color: "text-amber-700" },
  { id: "schede_tecniche", label: "Schede tecniche", icon: FileText, color: "text-slate-600" },
  { id: "personale", label: "Personale", icon: Users, color: "text-green-700" },
];

export const VALID_TABS = [
  ...PRIMARY_TABS.map((tab) => tab.id),
  ...SECONDARY_TABS.map((tab) => tab.id),
  ...IMPOSTAZIONI_TABS.map((tab) => tab.id),
  ...HACCP_TABS.map((tab) => tab.id),
  "ricettario", "food_cost", "listino", "magazzino_prodotti",
  "sconti_merce", "backup", "stampanti",
];
