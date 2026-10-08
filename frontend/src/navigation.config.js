/**
 * CONFIGURAZIONE DI NAVIGAZIONE UNICA — fonte di verità per TUTTI i menù:
 * colonna a sinistra (desktop), menù mobile a griglia, barra inferiore
 * mobile e pagina 404. Qualsiasi voce nuova va aggiunta SOLO qui.
 *
 * Le voci sono raggruppate per MOMENTO DEL LAVORO (si entra, i documenti, il
 * registro, le prove, la sintesi, i controlli), non per modulo tecnico: il
 * gruppo dice in che parte del lavoro ci si trova.
 *
 * Decisione del titolare (07/10/2026): in colonna stanno solo i HUB, poche voci
 * per gruppo; le pagine di ogni hub sono le sue `schede`, mostrate TUTTE in una
 * riga in cima alla pagina (SchedeHub), mai dietro una tendina. Prima la colonna
 * aveva 54 voci in piano e non si leggeva piu'. Una voce con `schede` prende
 * come indirizzo quello della prima scheda; ogni scheda ha il suo `perche'`.
 *
 * `colore` del gruppo: un punto accanto all'intestazione, che resta sempre
 * scritta — il colore aiuta a riconoscere la famiglia, non la sostituisce.
 *
 * `perche`: la riga grigia sotto il titolo di ogni pagina (al massimo venti
 * parole, senza sigle). La testata la legge da qui se la pagina non ne
 * passa una sua: una pagina che non dice perche' esiste non si capisce.
 */
import {
  Coffee,
  LayoutDashboard,
  Bell,
  PlusCircle,
  Upload,
  FileText,
  FileOutput,
  Wallet,
  Building2,
  BookMarked,
  FolderOpen,
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
  ShoppingCart,
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
  Inbox,
  Globe,
} from 'lucide-react';

export const NAV_GRUPPI = [
  {
    id: 'inizio',
    titolo: 'IN PRIMO PIANO',
    colore: '#141413',
    voci: [
      {
        label: 'Dashboard', Icon: LayoutDashboard, perche: "Dove sta l'attività adesso e le cose che chiedono una risposta.",
        schede: [
          { to: '/', label: 'Dashboard', Icon: LayoutDashboard, perche: "Dove sta l'attività adesso: liquidità, incassi, spese, e le cose che chiedono una risposta." },
          { to: '/dashboard/alerts', label: 'Alert', Icon: Bell, perche: "Le segnalazioni aperte, ognuna con i record che la causano." },
        ],
      },
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
      {
        label: 'Fatture', Icon: FileText, perche: "Le fatture ricevute ed emesse, le righe e i corrispettivi.",
        schede: [
          { to: '/fatture', label: 'Ricevute', Icon: FileText, perche: "Le fatture ricevute dell'anno, con fornitore, importo e stato del pagamento." },
          { to: '/fatture-estere-verifica', label: 'Estere', Icon: Globe, perche: "Le fatture dall'estero lette dal file: si confermano qui, e la conferma rifà conto e registrazione." },
          { to: '/fatture/emesse', label: 'Emesse', Icon: FileOutput, perche: "Le fatture fatte dopo lo scontrino, collegate al corrispettivo del giorno: non aumentano le entrate." },
          { to: '/fatture/righe', label: 'Righe acquisti', Icon: ShoppingCart, perche: "Le righe lette dalle fatture ricevute, con originale, pagamenti dichiarati e classificazioni da verificare." },
          { to: '/fatture/corrispettivi', label: 'Corrispettivi', Icon: Wallet, perche: "Le chiusure giornaliere del registratore di cassa: l'unica fonte dei ricavi." },
        ],
      },
      { to: '/fornitori', label: 'Fornitori', Icon: Building2, perche: "Chi ti fattura, con partita IVA, metodo di pagamento e quanto hai comprato." },
      {
        label: 'Documenti', Icon: FolderOpen, perche: "Tutti i documenti archiviati, gli atti degli enti e le visure.",
        schede: [
          { to: '/documenti/archivio', label: 'Archivio', Icon: FolderOpen, perche: "Tutti i documenti archiviati, cercabili per nome, tipo e data." },
          { to: '/documenti/atti', label: 'Atti amministrativi', Icon: BookMarked, perche: "Gli atti amministrativi ricevuti: avvisi, cartelle, comunicazioni degli enti." },
          { to: '/strumenti/visure', label: 'Visure', Icon: Search, perche: "Le visure delle aziende con cui lavori, lette dal registro imprese." },
        ],
      },
      { to: '/noleggio', label: 'Noleggi', Icon: Car, perche: "Le auto a noleggio: contratti, costi, verbali e chi le guidava." },
    ],
  },
  {
    id: 'registro',
    titolo: 'IL REGISTRO',
    colore: '#5b7a6b',
    // Il libro giornale e' spento (CLAUDE.md §24): la pagina resta al suo
    // indirizzo /contabilita/giornale, ma non sta in colonna finche' resta spento.
    voci: [
      {
        label: 'Prima nota', Icon: BookOpen, perche: "Cassa e banca, un conto alla volta, e i movimenti come li scrive la banca.",
        schede: [
          { to: '/prima-nota', label: 'Prima nota', Icon: BookOpen, perche: "Un conto alla volta, in ordine, con il saldo che cammina." },
          { to: '/riconciliazione/movimenti-banca', label: 'Movimenti banca', Icon: Banknote, perche: "I movimenti dell'estratto conto come li ha scritti la banca." },
        ],
      },
    ],
  },
  {
    id: 'prove',
    titolo: 'LE PROVE',
    colore: '#b07d1a',
    voci: [
      {
        label: 'Riconciliazione', Icon: Landmark, perche: "Ogni movimento della banca contro il documento che lo giustifica.",
        schede: [
          { to: '/riconciliazione', label: 'Riepilogo', Icon: Landmark, perche: "Ogni movimento della banca contro il documento che lo giustifica. Se i candidati sono più d'uno non si sceglie." },
          { to: '/riconciliazione/banca', label: 'Banca', Icon: Landmark, perche: "I movimenti della banca ancora senza documento, con i candidati trovati." },
          { to: '/riconciliazione/stipendi', label: 'Stipendi', Icon: Banknote, perche: "I bonifici degli stipendi contro i cedolini del mese." },
          { to: '/riconciliazione/documenti', label: 'Documenti', Icon: Receipt, perche: "I documenti di pagamento (ricevute, quietanze) da collegare al movimento in banca." },
          { to: '/riconciliazione/coerenza-pos', label: 'Coerenza POS', Icon: Banknote, perche: "Il registratore di cassa, il terminale e la banca devono raccontare lo stesso giorno." },
          { to: '/riconciliazione/assegni', label: 'Assegni', Icon: ScrollText, perche: "Gli assegni emessi, la fattura che pagano e il giorno in cui la banca li ha addebitati." },
          { to: '/riconciliazione/archivio-bonifici', label: 'Bonifici', Icon: ArrowLeftRight, perche: "I bonifici disposti, con la ricevuta e la fattura o lo stipendio che pagano." },
          { to: '/distinta-bonifici', label: 'Distinta bonifici', Icon: ArrowLeftRight, perche: "Le fatture da pagare in un file per la banca: un bonifico per fornitore, il pagamento lo fai tu." },
          { to: '/riconciliazione/pagopa', label: 'PagoPA', Icon: Receipt, perche: "I pagamenti PagoPA e l'avviso che chiudono." },
          { to: '/riconciliazione/paypal', label: 'PayPal', Icon: CreditCard, perche: "PayPal non è un conto, è un passaggio: ogni acquisto ha il pagamento e la provvista." },
          { to: '/riconciliazione/regole-banca', label: 'Regole banca', Icon: ListChecks, perche: "Le regole imparate per riconoscere da sole le causali della banca." },
        ],
      },
    ],
  },
  {
    id: 'sintesi',
    titolo: 'LA SINTESI',
    colore: '#8a6f47',
    voci: [
      {
        label: 'Contabilità', Icon: BarChart3, perche: "Piano dei conti, bilancio, cespiti, mutui, budget e chiusura.",
        schede: [
          { to: '/contabilita', label: 'Piano dei conti', Icon: BarChart3, perche: "Il piano dei conti CEE su cui si registra ogni scrittura." },
          { to: '/contabilita/bilancio', label: 'Bilancio', Icon: TrendingUp, perche: "Stato patrimoniale e conto economico, letti dal libro giornale." },
          { to: '/contabilita/cespiti', label: 'Cespiti', Icon: Building2, perche: "I beni che durano più di un anno e la quota di ammortamento di ognuno." },
          { to: '/contabilita/finanziaria', label: 'Finanziaria', Icon: Banknote, perche: "Liquidità, debiti e crediti in un colpo d'occhio." },
          { to: '/contabilita/mutui', label: 'Mutui', Icon: Landmark, perche: "I mutui e i finanziamenti, rata per rata, con il debito che resta." },
          { to: '/contabilita/budget', label: 'Budget', Icon: ClipboardList, perche: "Quanto pensavi di spendere e incassare, contro quanto è successo." },
          { to: '/contabilita/utile', label: 'Utile obiettivo', Icon: Target, perche: "Quanto manca all'utile che ti sei dato come obiettivo." },
          { to: '/contabilita/previsioni-acquisti', label: 'Previsioni acquisti', Icon: Package, perche: "Che cosa comprerai nei prossimi mesi, stimato da quello che hai comprato." },
          { to: '/contabilita/dati-isa', label: 'Dati ISA', Icon: Gauge, perche: "I dati che servono agli indici sintetici di affidabilità fiscale." },
          { to: '/contabilita/avanzata', label: 'Avanzata', Icon: Wrench, perche: "Gli strumenti di contabilità meno frequenti, per chi sa cosa cerca." },
          { to: '/contabilita/chiusura', label: 'Chiusura esercizio', Icon: Lock, perche: "La chiusura dell'esercizio: checklist, anteprima, conferma." },
        ],
      },
      {
        label: 'Fisco e scadenze', Icon: FileBarChart, perche: "Scadenze, F24, calendario, IVA e la situazione dei tributi.",
        schede: [
          { to: '/scadenze', label: 'Scadenze', Icon: Clock, perche: "Che cosa va pagato o presentato, e entro quando." },
          { to: '/riconciliazione/f24', label: 'F24', Icon: Receipt, perche: "Deleghe e quietanze. Un modello F24 non è una prova di pagamento: la prova è il movimento in banca." },
          { to: '/contabilita/calendario', label: 'Calendario fiscale', Icon: Calendar, perche: "Le scadenze fiscali dell'anno, una per riga, con quello che le soddisfa." },
          { to: '/iva', label: 'Gestione IVA', Icon: Receipt, perche: "Liquidazioni, LIPE, credito e debito periodo per periodo." },
          { to: '/situazione-fiscale', alias: ['/tributi', '/piano-tributi', '/ritenute', '/fiscale/tributi', '/fiscale/f24'], label: 'Situazione fiscale', Icon: FileBarChart, adminOnly: true, perche: "Che cosa dovevi versare, che cosa risulta versato e con quale prova: tributo per tributo, F24 per F24." },
        ],
      },
      {
        label: 'Commercialista', Icon: Briefcase, perche: "Quello che serve al commercialista e le attività programmate.",
        schede: [
          { to: '/strumenti/commercialista', label: 'Commercialista', Icon: Briefcase, perche: "Quello che serve al commercialista, pronto da mandare." },
          { to: '/strumenti/pianificazione', label: 'Pianificazione', Icon: CalendarRange, perche: "Le attività programmate e il loro stato." },
        ],
      },
    ],
  },
  {
    id: 'controlli',
    titolo: 'I CONTROLLI',
    colore: '#b0362b',
    voci: [
      {
        label: 'Controlli', Icon: ShieldCheck, perche: "Il mese, il bilancio e gli archivi devono tornare; qui si vede dove non tornano.",
        schede: [
          { to: '/contabilita/controllo', label: 'Controllo mensile', Icon: CalendarCheck, perche: "Il registratore di cassa, il terminale POS e la banca devono raccontare lo stesso mese. Qui si vede dove non tornano." },
          { to: '/contabilita/verifica', label: 'Verifica bilancio', Icon: BadgeCheck, perche: "Il saldo di ogni conto, dare contro avere: se non quadra, qui si vede dove." },
          { to: '/strumenti', label: 'Verifica coerenza', Icon: ShieldCheck, perche: "I controlli di coerenza fra archivi: quello che dovrebbe coincidere e non coincide." },
          { to: '/agenti', label: 'Agenti', Icon: Bot, adminOnly: true, perche: "Per ogni settore: cosa ha letto e associato l'ultimo giro, cosa è fermo, e le proposte dell'AI sui documenti che i lettori non riconoscono." },
        ],
      },
    ],
  },
  {
    id: 'app',
    titolo: 'LE ALTRE APP',
    colore: '#7a776e',
    // App del gruppo portate pari pari dentro il gestionale: ognuna ha il
    // proprio login ed e' servita a pagina intera dal backend montato a
    // /menu, /hr, /lotti (Colazioni B&B e' una pagina statica a /convenzioni/). Si aprono in una scheda nuova.
    voci: [
      { href: '/menu/admin', label: 'Menu', Icon: Menu, external: true },
      { href: '/hr/', label: 'HR', Icon: Users, external: true, adminOnly: true },
      { href: '/lotti/', label: 'HACCP Lotti', Icon: ShieldCheck, external: true },
      { href: '/convenzioni/', label: 'Colazioni B&B', Icon: Coffee, external: true },
    ],
  },
  {
    id: 'impostazioni',
    titolo: 'IMPOSTAZIONI',
    colore: '#7a776e',
    voci: [
      {
        label: 'Impostazioni', Icon: Settings, adminOnly: true, perche: "Sistema, utenti, sicurezza, elaborazioni e integrazioni.",
        schede: [
          { to: '/admin', label: 'Sistema', Icon: Settings, adminOnly: true, perche: "La configurazione tecnica: integrazioni, scheduler, manutenzione." },
          { to: '/utenti', label: 'Utenti', Icon: Users, adminOnly: true, perche: "Chi può entrare nel gestionale e con quale ruolo." },
          { to: '/admin/mfa', label: 'Sicurezza MFA', Icon: ShieldCheck, adminOnly: true, perche: "Il secondo fattore di accesso per gli amministratori." },
          { to: '/admin/elaborazioni', label: 'Elaborazioni', Icon: Workflow, adminOnly: true, perche: "Le elaborazioni in sottofondo: che cosa gira, che cosa è finito, che cosa è fallito." },
          { to: '/integrazioni', label: 'Integrazioni', Icon: Inbox, adminOnly: true, perche: "Da dove arrivano i documenti da fuori: OpenAPI, mittenti email, A-Cube (SdI e Cassetto fiscale)." },
          { to: '/impostazioni-f24-email', label: 'Email automatica', Icon: Mail, adminOnly: true, perche: "Come il gestionale scarica da solo gli F24 dalla posta: casella, mittenti, ultime scansioni." },
          { to: '/impostazioni-ai', label: 'Assistente AI', Icon: Bot, adminOnly: true, perche: "Come si comporta l'assistente e che cosa può leggere." },
        ],
      },
    ],
  },
];

// Una voce con schede prende l'indirizzo della prima scheda: e' dove si
// arriva cliccandola in colonna. Si calcola qui una volta, non a mano.
for (const gruppo of NAV_GRUPPI) {
  for (const voce of gruppo.voci) {
    if (voce.schede?.length && !voce.to) voce.to = voce.schede[0].to;
  }
}

// Voci di colonna (hub e pagine singole), in ordine.
export const NAV_COLONNA = NAV_GRUPPI.flatMap(g => g.voci);

// Tutte le destinazioni, una volta sola: le schede dei hub e le voci senza
// schede — usate dal menù mobile, dalla 404 e dai test.
export const NAV_TUTTE = NAV_GRUPPI.flatMap(g => g.voci.flatMap(v => (v.schede?.length ? v.schede : [v])));

function vociVisibili(voci, isAdmin) {
  return voci
    .filter(v => !v.adminOnly || isAdmin)
    .map(v => {
      if (!v.schede?.length) return v;
      const schede = v.schede.filter(s => !s.adminOnly || isAdmin);
      // L'hub arriva alla prima scheda che l'utente puo' vedere.
      return { ...v, schede, to: schede[0]?.to || v.to };
    })
    .filter(v => !v.schede || v.schede.length > 0);
}

/** Gruppi con le sole voci (e schede) che l'utente puo' vedere. */
export function gruppiVisibili(isAdmin) {
  return NAV_GRUPPI
    .map(g => ({ ...g, voci: vociVisibili(g.voci, isAdmin) }))
    .filter(g => g.voci.length > 0);
}

function combacia(voce, percorso) {
  if (!voce.to) return false;
  // `alias`: altri prefissi che appartengono alla stessa voce (le viste per id
  // `/fiscale/tributi/:codice` e `/fiscale/f24/:id` stanno sotto «Situazione fiscale»).
  const prefissi = [voce.to, ...(voce.alias || [])];
  return voce.to === '/'
    ? percorso === '/'
    : prefissi.some(p => percorso === p || percorso.startsWith(`${p}/`));
}

/**
 * La voce che corrisponde a un indirizzo: quella col prefisso piu' lungo fra
 * tutte le destinazioni (schede comprese). `/riconciliazione/f24` e' la scheda
 * F24 di «Fisco e scadenze», non il Riepilogo della Riconciliazione;
 * `/fatture/123` resta «Ricevute» di Fatture.
 * Restituisce `{ voce, gruppo, hub }` oppure `null`: `voce` e' la scheda (o la
 * voce singola), `hub` la voce di colonna che la contiene.
 */
export function voceDi(pathname) {
  const percorso = (pathname || '/').replace(/\/+$/, '') || '/';
  let trovata = null;
  for (const gruppo of NAV_GRUPPI) {
    for (const hub of gruppo.voci) {
      for (const voce of (hub.schede?.length ? hub.schede : [hub])) {
        if (combacia(voce, percorso) && (!trovata || voce.to.length > trovata.voce.to.length)) {
          trovata = { voce, gruppo, hub };
        }
      }
    }
  }
  return trovata;
}

/**
 * Le schede del hub in cui si trova l'indirizzo, gia' filtrate per ruolo:
 * `{ hub, gruppo, schede, attiva }`, oppure `null` se la pagina non sta in un
 * hub o il hub ha una scheda sola (niente da scegliere).
 */
export function schedeDi(pathname, isAdmin) {
  const trovata = voceDi(pathname);
  if (!trovata?.hub.schede?.length) return null;
  const schede = trovata.hub.schede.filter(s => !s.adminOnly || isAdmin);
  if (schede.length < 2) return null;
  return { hub: trovata.hub, gruppo: trovata.gruppo, schede, attiva: trovata.voce };
}

// Barra inferiore mobile: 4 scorciatoie + bottone Menu che apre la griglia.
export const NAV_MOBILE_BAR = [
  { to: '/', label: 'Dashboard', Icon: LayoutDashboard },
  { to: '/fatture', label: 'Fatture', Icon: FileText },
  { to: '/prima-nota', label: 'Prima Nota', Icon: BookOpen },
  { to: '/riconciliazione', label: 'Riconciliazione', Icon: ArrowLeftRight },
  { to: '/more', label: 'Menu', Icon: Menu, isMenu: true },
];
