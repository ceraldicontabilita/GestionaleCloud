/**
 * CONFIGURAZIONE DI NAVIGAZIONE UNICA — fonte di verità per TUTTI i menù:
 * colonna a sinistra (desktop), menù mobile a griglia, barra inferiore
 * mobile e pagina 404. Qualsiasi voce nuova va aggiunta SOLO qui.
 *
 * Le voci sono raggruppate per MOMENTO DEL LAVORO (si entra, i documenti, il
 * registro, le prove, la sintesi, i controlli), non per modulo tecnico: il
 * gruppo dice in che parte del lavoro ci si trova. Nessuna voce sta dietro un
 * menù «Altro» o una tendina: prima undici sezioni su sedici erano nascoste
 * lì, e le quindici pagine di Contabilità stavano in un <select>.
 *
 * `colore` del gruppo: un punto accanto all'intestazione, che resta sempre
 * scritta — il colore aiuta a riconoscere la famiglia, non la sostituisce.
 */
import {
  LayoutDashboard,
  Bell,
  PlusCircle,
  Upload,
  FileText,
  Wallet,
  Building2,
  BookMarked,
  FolderOpen,
  HardDrive,
  Receipt,
  Clock,
  Car,
  FileBarChart,
  Search,
  BookOpen,
  Banknote,
  Landmark,
  ArrowLeftRight,
  ScrollText,
  CreditCard,
  ListChecks,
  BarChart3,
  TrendingUp,
  Calendar,
  Lock,
  ClipboardList,
  Wrench,
  Target,
  Package,
  Gauge,
  Briefcase,
  CalendarRange,
  CalendarCheck,
  BadgeCheck,
  ShieldCheck,
  Menu,
  Users,
  Bot,
  Settings,
  Workflow,
  Mail,
} from 'lucide-react';

export const NAV_GRUPPI = [
  {
    id: 'inizio',
    titolo: 'IN PRIMO PIANO',
    colore: '#2a3329',
    voci: [
      { to: '/', label: 'Dashboard', Icon: LayoutDashboard },
      { to: '/dashboard/alerts', label: 'Alert', Icon: Bell },
    ],
  },
  {
    id: 'si-entra',
    titolo: 'SI ENTRA',
    colore: '#15803d',
    voci: [
      { to: '/rapido', label: 'Inserisci', Icon: PlusCircle },
      { to: '/documenti/import', label: 'Importa', Icon: Upload },
    ],
  },
  {
    id: 'documenti',
    titolo: 'I DOCUMENTI',
    colore: '#b45309',
    voci: [
      { to: '/fatture', label: 'Fatture', Icon: FileText },
      { to: '/fatture/corrispettivi', label: 'Corrispettivi', Icon: Wallet },
      { to: '/fornitori', label: 'Fornitori', Icon: Building2 },
      { to: '/documenti/atti', label: 'Atti amministrativi', Icon: BookMarked },
      { to: '/documenti/archivio', label: 'Archivio documenti', Icon: FolderOpen },
      { to: '/documenti/drive', label: 'Cartelle Google Drive', Icon: HardDrive },
      { to: '/riconciliazione/f24', label: 'F24', Icon: Receipt },
      { to: '/scadenze', label: 'Scadenze', Icon: Clock },
      { to: '/ritenute', label: 'Ritenute', Icon: Receipt },
      { to: '/noleggio', label: 'Noleggi', Icon: Car },
      { to: '/piano-tributi', label: 'Piano tributi', Icon: CalendarCheck, adminOnly: true },
      { to: '/situazione-fiscale', label: 'Situazione fiscale', Icon: FileBarChart, adminOnly: true },
      { to: '/strumenti/visure', label: 'Visure', Icon: Search },
    ],
  },
  {
    id: 'registro',
    titolo: 'IL REGISTRO',
    colore: '#3f5a4e',
    voci: [
      { to: '/prima-nota', label: 'Prima nota', Icon: BookOpen },
      { to: '/riconciliazione/movimenti-banca', label: 'Movimenti', Icon: Banknote },
      { to: '/contabilita/giornale', label: 'Libro giornale', Icon: BookOpen },
    ],
  },
  {
    id: 'prove',
    titolo: 'LE PROVE',
    colore: '#b8860b',
    voci: [
      { to: '/riconciliazione', label: 'Riconciliazione', Icon: Landmark },
      { to: '/riconciliazione/coerenza-pos', label: 'Coerenza POS', Icon: Banknote },
      { to: '/riconciliazione/assegni', label: 'Assegni', Icon: ScrollText },
      { to: '/riconciliazione/archivio-bonifici', label: 'Bonifici', Icon: ArrowLeftRight },
      { to: '/riconciliazione/pagopa', label: 'PagoPA', Icon: Receipt },
      { to: '/riconciliazione/paypal', label: 'PayPal', Icon: CreditCard },
      { to: '/riconciliazione/regole-banca', label: 'Regole banca', Icon: ListChecks },
    ],
  },
  {
    id: 'sintesi',
    titolo: 'LA SINTESI',
    colore: '#1a211a',
    voci: [
      { to: '/iva', label: 'Gestione IVA', Icon: Receipt },
      { to: '/contabilita', label: 'Piano dei conti', Icon: BarChart3 },
      { to: '/contabilita/bilancio', label: 'Bilancio', Icon: TrendingUp },
      { to: '/contabilita/calendario', label: 'Calendario fiscale', Icon: Calendar },
      { to: '/contabilita/cespiti', label: 'Cespiti', Icon: Building2 },
      { to: '/contabilita/finanziaria', label: 'Finanziaria', Icon: Banknote },
      { to: '/contabilita/mutui', label: 'Mutui', Icon: Landmark },
      { to: '/contabilita/budget', label: 'Budget', Icon: ClipboardList },
      { to: '/contabilita/utile', label: 'Utile obiettivo', Icon: Target },
      { to: '/contabilita/previsioni-acquisti', label: 'Previsioni acquisti', Icon: Package },
      { to: '/contabilita/dati-isa', label: 'Dati ISA', Icon: Gauge },
      { to: '/contabilita/avanzata', label: 'Contabilità avanzata', Icon: Wrench },
      { to: '/contabilita/chiusura', label: 'Chiusura esercizio', Icon: Lock },
      { to: '/strumenti/commercialista', label: 'Commercialista', Icon: Briefcase },
      { to: '/strumenti/pianificazione', label: 'Pianificazione', Icon: CalendarRange },
    ],
  },
  {
    id: 'controlli',
    titolo: 'I CONTROLLI',
    colore: '#b91c1c',
    voci: [
      { to: '/contabilita/controllo', label: 'Controllo mensile', Icon: CalendarCheck },
      { to: '/contabilita/verifica', label: 'Verifica bilancio', Icon: BadgeCheck },
      { to: '/strumenti', label: 'Verifica coerenza', Icon: ShieldCheck },
    ],
  },
  {
    id: 'app',
    titolo: 'LE ALTRE APP',
    colore: '#5b7a6b',
    // App del gruppo portate pari pari dentro il gestionale: ognuna ha il
    // proprio login ed e' servita a pagina intera dal backend montato a
    // /menu, /hr, /lotti. Si aprono in una scheda nuova.
    voci: [
      { href: '/menu/admin', label: 'Menu', Icon: Menu, external: true },
      { href: '/hr/', label: 'HR', Icon: Users, external: true, adminOnly: true },
      { href: '/lotti/', label: 'HACCP Lotti', Icon: ShieldCheck, external: true },
    ],
  },
  {
    id: 'impostazioni',
    titolo: 'IMPOSTAZIONI',
    colore: '#8a6f47',
    voci: [
      { to: '/utenti', label: 'Utenti', Icon: Users, adminOnly: true },
      { to: '/admin', label: 'Admin', Icon: Settings, adminOnly: true },
      { to: '/admin/mfa', label: 'Sicurezza MFA', Icon: ShieldCheck, adminOnly: true },
      { to: '/admin/elaborazioni', label: 'Elaborazioni', Icon: Workflow, adminOnly: true },
      { to: '/integrazioni/mittenti-email', label: 'Mittenti email', Icon: Mail, adminOnly: true },
      { to: '/impostazioni-ai', label: 'Assistente AI', Icon: Bot, adminOnly: true },
    ],
  },
];

// Tutte le voci, in ordine di colonna — usate dal menù mobile, dalla 404 e dai test.
export const NAV_TUTTE = NAV_GRUPPI.flatMap(g => g.voci);

/** Gruppi con le sole voci che l'utente puo' vedere. */
export function gruppiVisibili(isAdmin) {
  return NAV_GRUPPI
    .map(g => ({ ...g, voci: g.voci.filter(v => !v.adminOnly || isAdmin) }))
    .filter(g => g.voci.length > 0);
}

/**
 * La voce che corrisponde a un indirizzo: quella col prefisso piu' lungo.
 * `/riconciliazione/f24` e' la voce F24, non Riconciliazione; `/fatture/123`
 * resta Fatture. Restituisce `{ voce, gruppo }` oppure `null`.
 */
export function voceDi(pathname) {
  const percorso = (pathname || '/').replace(/\/+$/, '') || '/';
  let trovata = null;
  for (const gruppo of NAV_GRUPPI) {
    for (const voce of gruppo.voci) {
      if (!voce.to) continue;
      const combacia = voce.to === '/'
        ? percorso === '/'
        : percorso === voce.to || percorso.startsWith(`${voce.to}/`);
      if (combacia && (!trovata || voce.to.length > trovata.voce.to.length)) {
        trovata = { voce, gruppo };
      }
    }
  }
  return trovata;
}

// Barra inferiore mobile: 4 scorciatoie + bottone Menu che apre la griglia.
export const NAV_MOBILE_BAR = [
  { to: '/', label: 'Dashboard', Icon: LayoutDashboard },
  { to: '/fatture', label: 'Fatture', Icon: FileText },
  { to: '/prima-nota', label: 'Prima Nota', Icon: BookOpen },
  { to: '/riconciliazione', label: 'Riconciliazione', Icon: ArrowLeftRight },
  { to: '/more', label: 'Menu', Icon: Menu, isMenu: true },
];
