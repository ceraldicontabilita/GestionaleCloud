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
 *
 * `perche`: la riga grigia sotto il titolo di ogni pagina (al massimo venti
 * parole, senza sigle). La testata la legge da qui se la pagina non ne
 * passa una sua: una pagina che non dice perche' esiste non si capisce.
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
    colore: '#141413',
    voci: [
      { to: '/', label: 'Dashboard', Icon: LayoutDashboard, perche: "Dove sta l'attività adesso: liquidità, incassi, spese, e le cose che chiedono una risposta." },
      { to: '/dashboard/alerts', label: 'Alert', Icon: Bell, perche: "Le segnalazioni aperte, ognuna con i record che la causano." },
    ],
  },
  {
    id: 'si-entra',
    titolo: 'SI ENTRA',
    colore: '#c15f3c',
    voci: [
      { to: '/rapido', label: 'Inserisci', Icon: PlusCircle, perche: "Una riga alla volta, con il minimo indispensabile: data, importo, conto, categoria." },
      { to: '/documenti/import', label: 'Importa', Icon: Upload, perche: "La porta unica dei documenti: ogni file entra da qui, e l'impronta impedisce che entri due volte." },
    ],
  },
  {
    id: 'documenti',
    titolo: 'I DOCUMENTI',
    colore: '#2f7a4f',
    voci: [
      { to: '/fatture', label: 'Fatture', Icon: FileText, perche: "Le fatture ricevute dell'anno, con fornitore, importo e stato del pagamento." },
      { to: '/fatture/corrispettivi', label: 'Corrispettivi', Icon: Wallet, perche: "Le chiusure giornaliere del registratore di cassa: l'unica fonte dei ricavi." },
      { to: '/fornitori', label: 'Fornitori', Icon: Building2, perche: "Chi ti fattura, con partita IVA, metodo di pagamento e quanto hai comprato." },
      { to: '/documenti/atti', label: 'Atti amministrativi', Icon: BookMarked, perche: "Gli atti amministrativi ricevuti: avvisi, cartelle, comunicazioni degli enti." },
      { to: '/documenti/archivio', label: 'Archivio documenti', Icon: FolderOpen, perche: "Tutti i documenti archiviati, cercabili per nome, tipo e data." },
      { to: '/documenti/drive', label: 'Cartelle Google Drive', Icon: HardDrive, perche: "Le cartelle di Google Drive da cui il gestionale legge i documenti." },
      { to: '/riconciliazione/f24', label: 'F24', Icon: Receipt, perche: "Deleghe e quietanze. Un modello F24 non è una prova di pagamento: la prova è il movimento in banca." },
      { to: '/scadenze', label: 'Scadenze', Icon: Clock, perche: "Che cosa va pagato o presentato, e entro quando." },
      { to: '/ritenute', label: 'Ritenute', Icon: Receipt, perche: "Le ritenute d'acconto sulle fatture dei professionisti e il loro versamento con F24." },
      { to: '/noleggio', label: 'Noleggi', Icon: Car, perche: "Le auto a noleggio: contratti, costi, verbali e chi le guidava." },
      { to: '/piano-tributi', label: 'Piano tributi', Icon: CalendarCheck, adminOnly: true, perche: "I tributi ricorrenti attesi per periodo, soddisfatti solo dall'addebito in banca." },
      { to: '/situazione-fiscale', label: 'Situazione fiscale', Icon: FileBarChart, adminOnly: true, perche: "Che cosa risulta dovuto, che cosa è stato versato, che cosa è rimasto aperto." },
      { to: '/strumenti/visure', label: 'Visure', Icon: Search, perche: "Le visure delle aziende con cui lavori, lette dal registro imprese." },
    ],
  },
  {
    id: 'registro',
    titolo: 'IL REGISTRO',
    colore: '#5b7a6b',
    voci: [
      { to: '/prima-nota', label: 'Prima nota', Icon: BookOpen, perche: "Un conto alla volta, in ordine, con il saldo che cammina." },
      { to: '/riconciliazione/movimenti-banca', label: 'Movimenti', Icon: Banknote, perche: "I movimenti dell'estratto conto come li ha scritti la banca." },
      { to: '/contabilita/giornale', label: 'Libro giornale', Icon: BookOpen, perche: "Le scritture in partita doppia, in ordine di registrazione: dare e avere sempre in pari." },
    ],
  },
  {
    id: 'prove',
    titolo: 'LE PROVE',
    colore: '#b07d1a',
    voci: [
      { to: '/riconciliazione', label: 'Riconciliazione', Icon: Landmark, perche: "Ogni movimento della banca contro il documento che lo giustifica. Se i candidati sono più d'uno non si sceglie." },
      { to: '/riconciliazione/coerenza-pos', label: 'Coerenza POS', Icon: Banknote, perche: "Il registratore di cassa, il terminale e la banca devono raccontare lo stesso giorno." },
      { to: '/riconciliazione/assegni', label: 'Assegni', Icon: ScrollText, perche: "Gli assegni emessi, la fattura che pagano e il giorno in cui la banca li ha addebitati." },
      { to: '/riconciliazione/archivio-bonifici', label: 'Bonifici', Icon: ArrowLeftRight, perche: "I bonifici disposti, con la ricevuta e la fattura o lo stipendio che pagano." },
      { to: '/riconciliazione/pagopa', label: 'PagoPA', Icon: Receipt, perche: "I pagamenti PagoPA e l'avviso che chiudono." },
      { to: '/riconciliazione/paypal', label: 'PayPal', Icon: CreditCard, perche: "PayPal non è un conto, è un passaggio: ogni acquisto ha il pagamento e la provvista." },
      { to: '/riconciliazione/regole-banca', label: 'Regole banca', Icon: ListChecks, perche: "Le regole imparate per riconoscere da sole le causali della banca." },
    ],
  },
  {
    id: 'sintesi',
    titolo: 'LA SINTESI',
    colore: '#8a6f47',
    voci: [
      { to: '/iva', label: 'Gestione IVA', Icon: Receipt, perche: "Liquidazioni, LIPE, credito e debito periodo per periodo." },
      { to: '/contabilita', label: 'Piano dei conti', Icon: BarChart3, perche: "Il piano dei conti CEE su cui si registra ogni scrittura." },
      { to: '/contabilita/bilancio', label: 'Bilancio', Icon: TrendingUp, perche: "Stato patrimoniale e conto economico, letti dal libro giornale." },
      { to: '/contabilita/calendario', label: 'Calendario fiscale', Icon: Calendar, perche: "Le scadenze fiscali dell'anno, una per riga, con quello che le soddisfa." },
      { to: '/contabilita/cespiti', label: 'Cespiti', Icon: Building2, perche: "I beni che durano più di un anno e la quota di ammortamento di ognuno." },
      { to: '/contabilita/finanziaria', label: 'Finanziaria', Icon: Banknote, perche: "Liquidità, debiti e crediti in un colpo d'occhio." },
      { to: '/contabilita/mutui', label: 'Mutui', Icon: Landmark, perche: "I mutui e i finanziamenti, rata per rata, con il debito che resta." },
      { to: '/contabilita/budget', label: 'Budget', Icon: ClipboardList, perche: "Quanto pensavi di spendere e incassare, contro quanto è successo." },
      { to: '/contabilita/utile', label: 'Utile obiettivo', Icon: Target, perche: "Quanto manca all'utile che ti sei dato come obiettivo." },
      { to: '/contabilita/previsioni-acquisti', label: 'Previsioni acquisti', Icon: Package, perche: "Che cosa comprerai nei prossimi mesi, stimato da quello che hai comprato." },
      { to: '/contabilita/dati-isa', label: 'Dati ISA', Icon: Gauge, perche: "I dati che servono agli indici sintetici di affidabilità fiscale." },
      { to: '/contabilita/avanzata', label: 'Contabilità avanzata', Icon: Wrench, perche: "Gli strumenti di contabilità meno frequenti, per chi sa cosa cerca." },
      { to: '/contabilita/chiusura', label: 'Chiusura esercizio', Icon: Lock, perche: "La chiusura dell'esercizio: checklist, anteprima, conferma." },
      { to: '/strumenti/commercialista', label: 'Commercialista', Icon: Briefcase, perche: "Quello che serve al commercialista, pronto da mandare." },
      { to: '/strumenti/pianificazione', label: 'Pianificazione', Icon: CalendarRange, perche: "Le attività programmate e il loro stato." },
    ],
  },
  {
    id: 'controlli',
    titolo: 'I CONTROLLI',
    colore: '#b0362b',
    voci: [
      { to: '/contabilita/controllo', label: 'Controllo mensile', Icon: CalendarCheck, perche: "Il registratore di cassa, il terminale POS e la banca devono raccontare lo stesso mese. Qui si vede dove non lo fanno." },
      { to: '/contabilita/verifica', label: 'Verifica bilancio', Icon: BadgeCheck, perche: "Il saldo di ogni conto, dare contro avere: se non quadra, qui si vede dove." },
      { to: '/strumenti', label: 'Verifica coerenza', Icon: ShieldCheck, perche: "I controlli di coerenza fra archivi: quello che dovrebbe coincidere e non coincide." },
    ],
  },
  {
    id: 'app',
    titolo: 'LE ALTRE APP',
    colore: '#7a776e',
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
    colore: '#7a776e',
    voci: [
      { to: '/utenti', label: 'Utenti', Icon: Users, adminOnly: true, perche: "Chi può entrare nel gestionale e con quale ruolo." },
      { to: '/admin', label: 'Admin', Icon: Settings, adminOnly: true, perche: "La configurazione tecnica: integrazioni, scheduler, manutenzione." },
      { to: '/admin/mfa', label: 'Sicurezza MFA', Icon: ShieldCheck, adminOnly: true, perche: "Il secondo fattore di accesso per gli amministratori." },
      { to: '/admin/elaborazioni', label: 'Elaborazioni', Icon: Workflow, adminOnly: true, perche: "Le elaborazioni in sottofondo: che cosa gira, che cosa è finito, che cosa è fallito." },
      { to: '/integrazioni/mittenti-email', label: 'Mittenti email', Icon: Mail, adminOnly: true, perche: "Da quali indirizzi il gestionale accetta documenti per posta." },
      { to: '/impostazioni-ai', label: 'Assistente AI', Icon: Bot, adminOnly: true, perche: "Come si comporta l'assistente e che cosa può leggere." },
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
