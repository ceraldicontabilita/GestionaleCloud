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
  Receipt,
  BookMarked,
  Car,
  Wrench,
  Users,
  Settings,
  Clock,
  Menu,
  ArrowLeftRight,
  ShieldCheck,
} from 'lucide-react';

// Voci principali: barra desktop + prima parte del menù mobile.
// Assegni e PayPal non sono pagine di primo livello: sono sezioni interne
// dell'hub Riconciliazione e restano raggiungibili dai suoi tab.
export const NAV_PRINCIPALI = [
  { to: '/', label: 'Dashboard', Icon: LayoutDashboard },
  { to: '/fatture', label: 'Fatture', Icon: FileText },
  { to: '/prima-nota', label: 'Prima Nota', Icon: BookOpen },
  { to: '/fornitori', label: 'Fornitori', Icon: Building2 },
  { to: '/riconciliazione', label: 'Riconciliazione', Icon: Landmark },
  // "Tracciabilità" (/tracciabilita, HACCP nativo) rimossa il 03/09/2026 su
  // ordine del titolare: doppione dell'app Lotti, che vive a /lotti (voce
  // "HACCP Lotti" nel menu Altro).
];

// Voci secondarie: dropdown "Altro" su desktop + resto del menù mobile.
// Corrispettivi NON è qui: si raggiunge dal tab dentro Fatture.
// F24 e Coerenza POS sono sezioni dell'hub Riconciliazione e non duplicano
// più la navigazione principale. Mappa gestionale resta raggiungibile via URL
// e verrà ricollocata nell'area diagnostica/admin.
export const NAV_ALTRO = [
  { to: '/iva', label: 'Gestione IVA', Icon: Receipt },
  { to: '/situazione-fiscale', label: 'Situazione fiscale', Icon: FileBarChart, adminOnly: true },
  { to: '/contabilita', label: 'Contabilita', Icon: FileBarChart },
  { to: '/documenti', label: 'Documenti', Icon: BookMarked },
  { to: '/noleggio', label: 'Noleggi', Icon: Car },
  { to: '/scadenze', label: 'Scadenze', Icon: Clock },
  { to: '/ritenute', label: 'Ritenute', Icon: Receipt },
  // "Cedolini paga" (/salari) rimossa il 03/09/2026: doppione dell'app HR
  // (AppDipendenti) che vive a /hr (voce "HR" qui sotto).
  { to: '/strumenti', label: 'Strumenti', Icon: Wrench },
  // App del gruppo portate pari pari dentro il gestionale (decisione del
  // titolare 03/09/2026): ognuna e' un documento a se', con il proprio login,
  // servita a pagina intera dal backend originale montato a /menu, /hr, /lotti.
  { href: '/menu/admin', label: 'Menu', Icon: Menu, external: true },
  { href: '/hr/', label: 'HR', Icon: Users, external: true, adminOnly: true },
  { href: '/lotti/', label: 'HACCP Lotti', Icon: ShieldCheck, external: true },
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
