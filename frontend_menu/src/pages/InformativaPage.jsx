import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { ArrowLeft } from 'lucide-react';
import { leggiLingua } from '../lib/preferenzeCliente';
import { COLLEGAMENTI_PUBBLICI } from '../lib/collegamentiPubblici';

// Anello di focus salvia, visibile anche sul fondo verde scuro del menu.
const FOCUS_SALVIA =
  'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[#5b7a6b] focus-visible:ring-offset-2 focus-visible:ring-offset-[#faf7f0]';

// Informativa privacy e cookie del menu clienti. Il testo descrive cio' che
// questo codice fa davvero (campi dell'ordine in `app/menu/models`, chiavi
// salvate da `lib/preferenzeCliente.js`, font da Google Fonts in `index.css`,
// foto dei prodotti ancora ospitate su server esterni):
// se cambia il codice, cambia anche qui. Il titolare arriva dall'anagrafica
// azienda unica (`GET /api/menu/titolare`), mai scritto a mano: se non si
// legge, la pagina lo dice invece di inventarlo.
import { MENU_BACKEND_URL as BACKEND_URL } from '@/lib/backend';

export const DATA_AGGIORNAMENTO = '26/09/2026';

function Titolare({ titolare, stato, t }) {
  if (stato === 'caricamento') return <p>{t('Caricamento dei dati del titolare…', 'Loading controller details…')}</p>;
  if (!titolare || !titolare.ragione_sociale) {
    return (
      <p>
        {t(
          'I dati del titolare non sono leggibili in questo momento: chiedili al personale del locale.',
          'The controller details cannot be loaded right now: please ask the staff.'
        )}
      </p>
    );
  }
  return (
    <p data-testid="titolare">
      <strong>{titolare.ragione_sociale}</strong>
      {titolare.indirizzo && <>, {titolare.indirizzo}</>}
      {titolare.partita_iva && <>, {t('P.IVA', 'VAT no.')} {titolare.partita_iva}</>}
      {titolare.email && <>, {titolare.email}</>}
      {titolare.telefono && <>, {t('tel.', 'phone')} {titolare.telefono}</>}
    </p>
  );
}

function Sezione({ titolo, children }) {
  return (
    <section className="mb-6">
      <h2 className="text-lg font-bold text-[#d4af37] mb-2">{titolo}</h2>
      <div className="space-y-2 text-white/90 leading-relaxed">{children}</div>
    </section>
  );
}

function TestoPrivacy({ t, titolare, stato }) {
  return (
    <>
      <Sezione titolo={t('Titolare del trattamento', 'Data controller')}>
        <Titolare titolare={titolare} stato={stato} t={t} />
      </Sezione>
      <Sezione titolo={t('Quali dati trattiamo', 'What data we process')}>
        <p>
          {t(
            'Per consultare il menu non serve nessun dato personale. Se invii un ordine dal menu registriamo: i prodotti scelti con le eventuali note, il tavolo e la sala, il numero di coperti, il metodo di pagamento che indichi e, solo se lo scrivi, il tuo nome.',
            'No personal data is needed to browse the menu. If you send an order we record: the chosen products with any notes, table and room, number of covers, the payment method you indicate and, only if you type it, your name.'
          )}
        </p>
        <p>
          {t(
            'Non chiediamo email, telefono né dati di carta: il pagamento avviene al locale.',
            'We do not ask for email, phone or card details: you pay at the venue.'
          )}
        </p>
      </Sezione>
      <Sezione titolo={t('Perché e su quale base', 'Purpose and legal basis')}>
        <p>
          {t(
            "Solo per preparare e servirti l'ordine, cioè per dare seguito a una tua richiesta (art. 6, par. 1, lett. b del Regolamento UE 2016/679).",
            'Only to prepare and serve your order, i.e. to act on your request (Art. 6(1)(b) of Regulation (EU) 2016/679).'
          )}
        </p>
      </Sezione>
      <Sezione titolo={t('Chi li vede e dove stanno', 'Who sees them and where they are stored')}>
        <p>
          {t(
            "L'ordine lo vede il personale del locale nelle schermate ordini, cassa e cucina. I dati stanno sui servizi di hosting (Render) e di database (Supabase) che il locale usa per il menu, come responsabili del trattamento. Non li cediamo a nessuno e non li usiamo per pubblicità.",
            'Orders are seen by the staff on the orders, till and kitchen screens. Data is stored on the hosting (Render) and database (Supabase) services the venue uses for the menu, acting as processors. We do not share it with anyone else or use it for advertising.'
          )}
        </p>
        <p>
          {t(
            "Il carattere tipografico della pagina è caricato da Google Fonts e parte delle foto dei prodotti da server esterni di immagini: per consegnarli, quei server ricevono l'indirizzo IP del tuo dispositivo.",
            'The page typeface is loaded from Google Fonts and some product photos from external image servers: to deliver them, those servers receive your device IP address.'
          )}
        </p>
      </Sezione>
      <Sezione titolo={t('Per quanto tempo', 'How long')}>
        <p>
          {t(
            "Gli ordini restano nell'elenco ordini del locale finché il personale non li elimina. Puoi chiederne la cancellazione in qualsiasi momento.",
            "Orders stay in the venue's order list until the staff delete them. You can ask for deletion at any time."
          )}
        </p>
      </Sezione>
      <Sezione titolo={t('I tuoi diritti', 'Your rights')}>
        <p>
          {t(
            'Puoi chiedere al titolare accesso, rettifica, cancellazione, limitazione e opposizione (artt. 15-22 del Regolamento UE 2016/679), e proporre reclamo al Garante per la protezione dei dati personali (www.garanteprivacy.it).',
            'You can ask the controller for access, rectification, erasure, restriction and objection (Arts. 15-22 of Regulation (EU) 2016/679), and lodge a complaint with the Italian Data Protection Authority (www.garanteprivacy.it).'
          )}
        </p>
      </Sezione>
    </>
  );
}

function TestoCookie({ t, titolare, stato }) {
  return (
    <>
      <Sezione titolo={t('In breve', 'In short')}>
        <p>
          {t(
            'Il menu non usa cookie di profilazione, di statistica o di pubblicità, né strumenti di tracciamento di terze parti.',
            'The menu uses no profiling, analytics or advertising cookies, and no third-party tracking tools.'
          )}
        </p>
      </Sezione>
      <Sezione titolo={t('Cosa salviamo nel tuo browser', 'What we store in your browser')}>
        <p>
          {t(
            'Solo due preferenze tecniche, nella memoria locale del browser (localStorage), che non escono dal tuo dispositivo:',
            'Only two technical preferences, in the browser local storage (localStorage), which never leave your device:'
          )}
        </p>
        <ul className="list-disc pl-6 space-y-1">
          <li><code>menu_lingua</code>: {t('la lingua che hai scelto (italiano o inglese).', 'the language you chose (Italian or English).')}</li>
          <li><code>menu_consenso_cookie</code>: {t('la scelta che hai fatto sul banner dei cookie, con la data.', 'the choice you made on the cookie banner, with its date.')}</li>
        </ul>
        <p>
          {t(
            'Non scadono da sole: le cancelli quando vuoi dalle impostazioni del browser (dati dei siti).',
            'They do not expire on their own: you can delete them at any time from your browser settings (site data).'
          )}
        </p>
      </Sezione>
      <Sezione titolo={t('Servizi esterni', 'External services')}>
        <p>
          {t(
            "Il carattere tipografico arriva da Google Fonts e parte delle foto dei prodotti da server esterni: quei server ricevono l'indirizzo IP del dispositivo. I pulsanti Facebook e Instagram sono semplici link: solo se li apri passi ai loro siti, con le loro regole sui cookie.",
            'The typeface comes from Google Fonts and some product photos from external servers: those servers receive the device IP address. The Facebook and Instagram buttons are plain links: only if you open them do you move to their sites, under their cookie rules.'
          )}
        </p>
      </Sezione>
      <Sezione titolo={t('Titolare', 'Controller')}>
        <Titolare titolare={titolare} stato={stato} t={t} />
      </Sezione>
    </>
  );
}

const InformativaPage = ({ tipo }) => {
  const [titolare, setTitolare] = useState(null);
  const [stato, setStato] = useState('caricamento');
  const language = leggiLingua();
  const t = (it, en) => (language === 'it' ? it : en);

  useEffect(() => {
    let attivo = true;
    axios
      .get(`${BACKEND_URL}/api/menu/titolare`, { timeout: 15000 })
      .then((r) => { if (attivo) { setTitolare(r.data); setStato('pronto'); } })
      .catch(() => { if (attivo) setStato('errore'); });
    return () => { attivo = false; };
  }, []);

  const privacy = tipo === 'privacy';
  const titolo = privacy
    ? t('Informativa sulla privacy', 'Privacy policy')
    : t('Politica sui cookie', 'Cookie policy');
  const altra = privacy ? COLLEGAMENTI_PUBBLICI.cookiePolicy : COLLEGAMENTI_PUBBLICI.privacyPolicy;
  const base = process.env.PUBLIC_URL || '';

  return (
    <div className="min-h-screen bg-[#4a5d4a] overflow-x-clip">
      <main className="max-w-2xl mx-auto px-4 py-8">
        <a
          href={`${base}/carta/index.html`}
          className={`inline-flex items-center gap-2 min-h-[44px] px-4 mb-6 rounded-lg bg-[#3d4d3d] text-white hover:bg-[#354535] transition-colors ${FOCUS_SALVIA}`}
        >
          <ArrowLeft className="w-5 h-5" aria-hidden="true" /> {t('Torna al menu', 'Back to the menu')}
        </a>
        <h1 className="text-2xl font-extrabold text-white mb-1" style={{ letterSpacing: '-0.02em' }}>{titolo}</h1>
        <p className="text-white/70 text-sm mb-6">{t('Aggiornata il', 'Updated on')} {DATA_AGGIORNAMENTO}</p>
        {privacy
          ? <TestoPrivacy t={t} titolare={titolare} stato={stato} />
          : <TestoCookie t={t} titolare={titolare} stato={stato} />}
        <a
          href={`${base}${altra}`}
          className={`inline-flex items-center min-h-[44px] text-white/80 underline hover:text-white rounded ${FOCUS_SALVIA}`}
        >
          {privacy ? t('Leggi la politica sui cookie', 'Read the cookie policy') : t("Leggi l'informativa sulla privacy", 'Read the privacy policy')}
        </a>
      </main>
    </div>
  );
};

export default InformativaPage;
