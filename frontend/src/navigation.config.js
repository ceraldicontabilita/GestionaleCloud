/**
 * CONFIGURAZIONE DI NAVIGAZIONE UNICA — fonte di verità per TUTTI i menù:
 * barra desktop (TopNav), dropdown "Altro" (TopNav), barra inferiore mobile
 * e menù mobile a griglia (App.jsx).
 *
 * Prima esistevano QUATTRO elenchi mantenuti a mano (NAV_ITEMS, ALTRO_ITEMS,
 * MOBILE_NAV, ALL_NAV_ITEMS) che erano già andati fuori sincrono: etichette
 * diverse, voci presenti solo su mobile, Corrispettivi rimasto nel menù
 * mobile dopo che l'utente l'aveva voluto togliere dai menù (10/07).
 * Qualsiasi voce nuova va aggiunta SOLO qui.
 */
import {
  LayoutDashboard,
  FileText,
  Bot,
  BookOpen,
  Building2,
  Landmark,
  FileBarChart,
  CreditCard,
  Receipt,
  BookMarked,
  Upload,
  Car,
  Wrench,
  Map,
  Users,
  Settings,
  Clock,
  Menu,
  ArrowLeftRight,
  FolderArchive,
} from 'lucide-react';

export const APP_DIPENDENTI_URL = 'https://appdipendenti.onrender.com';

// Voci principali: barra desktop + prima parte del menù mobile.
export const NAV_PRINCIPALI = [
  { to: '/', label: 'Dashboard', Icon: LayoutDashboard },
  { to: '/fatture', label: 'Fatture', Icon: FileText },
  { to: '/prima-nota', label: 'Prima Nota', Icon: BookOpen },
  { to: '/fornitori', label: 'Fornitori', Icon: Building2 },
  { to: '/riconciliazione', label: 'Riconciliazione', Icon: Landmark },
  { to: '/riconciliazione/assegni', label: 'Assegni', Icon: FileBarChart },
  { to: '/riconciliazione/paypal', label: 'PayPal', Icon: CreditCard },
];

// Voci secondarie: dropdown "Altro" su desktop + resto del menù mobile.
// Corrispettivi NON è qui: si raggiunge dal tab dentro Fatture
// (richiesta utente 10/07, un solo posto canonico).
export const NAV_ALTRO = [
  { to: '/riconciliazione/f24', label: 'F24', Icon: Receipt },
  { to: '/iva', label: 'Gestione IVA', Icon: Receipt },
  { to: '/contabilita', label: 'Contabilita', Icon: FileBarChart },
  { to: '/documenti', label: 'Documenti', Icon: BookMarked },
  { to: '/documenti/import', label: 'Import Documenti', Icon: Upload },
  { to: '/documenti-fiscali', label: 'Documenti fiscali', Icon: FolderArchive },
  { to: '/riconciliazione/coerenza-pos', label: 'Incassi POS', Icon: CreditCard },
  { to: '/noleggio', label: 'Noleggi', Icon: Car },
  { to: '/scadenze', label: 'Scadenze', Icon: Clock },
  { to: '/strumenti', label: 'Strumenti', Icon: Wrench },
  { to: '/mappa-gestionale', label: 'Mappa gestionale', Icon: Map },
  { to: null, href: APP_DIPENDENTI_URL, label: 'HR', Icon: Users, external: true },
  { to: '/impostazioni-ai', label: 'Assistente AI', Icon: Bot, adminOnly: true },
  { to: '/utenti', label: 'Utenti', Icon: Users, adminOnly: true },
  { to: '/admin', label: 'Admin', Icon: Settings, adminOnly: true },
];

// Tutte le voci raggiungibili — usate dal menù mobile a griglia e dai test.
export const NAV_TUTTE = [...NAV_PRINCIPALI, ...NAV_ALTRO];

// Barra inferiore mobile: 4 scorciatoie + bottone Menu che apre la griglia.
export const NAV_MOBILE_BAR = [
  { to: '/', label: 'Dashboard', Icon: LayoutDashboard },
  { to: '/fatture', label: 'Fatture', Icon: FileText },
  { to: '/prima-nota', label: 'Prima Nota', Icon: BookOpen },
  { to: '/riconciliazione', label: 'Riconciliazione', Icon: ArrowLeftRight },
  { to: '/more', label: 'Menu', Icon: Menu, isMenu: true },
];
