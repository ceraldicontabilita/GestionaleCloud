import {
  AlertCircle, AlertTriangle, BarChart3, BookMarked, BookOpen, Bug,
  Building2, ChefHat, ClipboardCheck, FileText, Flame, FlaskConical,
  Globe, HelpCircle, IceCreamBowl, Layers, Network, Package,
  Refrigerator, Scale, Settings, ShieldCheck, ShoppingCart, Snowflake,
  Sparkles, Tag, Thermometer, TrendingUp, Truck, Users, Wallet, Wheat,
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
  { section: "Acquisti e vendita", id: "fornitori", label: "Fornitori", icon: Building2 },
  { section: "Acquisti e vendita", id: "comparatore", label: "Confronto prezzi", icon: Scale },
  { section: "Acquisti e vendita", id: "prodotti", label: "Listini e cataloghi", icon: Tag },
  { section: "Acquisti e vendita", id: "corrispettivi", label: "Corrispettivi", icon: TrendingUp },
  { section: "Analisi", id: "dashboard_economica", label: "Dashboard economica", icon: Wallet },
  { section: "Analisi", id: "mappa_tracciabilita", label: "Mappa tracciabilità", icon: Network },
  { section: "Amministrazione", id: "controllo_dati", label: "Verifica dati", icon: ShieldCheck },
  { section: "Amministrazione", id: "cataloghi_esterni", label: "Cataloghi fornitori", icon: Globe },
  { section: "Amministrazione", id: "dizionario", label: "Dizionario ingredienti", icon: BookMarked },
  // 25/07/2026 — prima i nomi si cambiavano solo dall'intestazione delle
  // colonne in Temperature: qui c'è un elenco unico e trovabile.
  { section: "Amministrazione", id: "attrezzature", label: "Frigoriferi e congelatori", icon: Refrigerator },
  { section: "Amministrazione", id: "backoffice", label: "Backoffice", icon: Settings },
  { section: "Amministrazione", id: "configura", label: "Configurazione", icon: ClipboardCheck },
  { section: "Amministrazione", id: "collaudi", label: "Collaudi", icon: FlaskConical },
  { section: "Supporto", id: "guida", label: "Guida", icon: HelpCircle },
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
  ...HACCP_TABS.map((tab) => tab.id),
  "fatture", "ricettario", "food_cost", "listino", "magazzino_prodotti",
  "sconti_merce", "backup", "stampanti",
];
