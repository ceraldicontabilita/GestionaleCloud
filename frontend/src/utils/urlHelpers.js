/**
 * Utility per URL descrittivi e breadcrumb
 * Genera URL leggibili dal titolo/nome del documento
 */

// Converte stringa in slug URL-friendly
export const toSlug = text => {
  if (!text) return '';
  return text
    .toString()
    .toLowerCase()
    .trim()
    .replace(/[àáâãäå]/g, 'a')
    .replace(/[èéêë]/g, 'e')
    .replace(/[ìíîï]/g, 'i')
    .replace(/[òóôõö]/g, 'o')
    .replace(/[ùúûü]/g, 'u')
    .replace(/[ñ]/g, 'n')
    .replace(/[ç]/g, 'c')
    .replace(/[^\w\s-]/g, '') // Rimuovi caratteri speciali
    .replace(/[\s_-]+/g, '-') // Sostituisci spazi con trattini
    .replace(/^-+|-+$/g, ''); // Rimuovi trattini iniziali/finali
};

// Genera URL per cedolino
export const cedolinoUrl = cedolino => {
  if (!cedolino) return '/cedolini';
  const nome = toSlug(cedolino.nome_dipendente || cedolino.employee_nome || 'dipendente');
  const mese = getMeseNome(cedolino.mese);
  const anno = cedolino.anno || new Date().getFullYear();
  return `/cedolini/${nome}/cedolino-${mese}-${anno}`;
};

// Genera URL per fattura
export const fatturaUrl = fattura => {
  if (!fattura) return '/fatture-ricevute';
  const fornitore = toSlug(fattura.supplier_name || fattura.fornitore_nome || 'fornitore');
  const numero = toSlug(fattura.invoice_number || fattura.numero || 'fattura');
  return `/fatture-ricevute/${fornitore}/fattura-${numero}`;
};

// Genera URL per fornitore
export const fornitoreUrl = fornitore => {
  if (!fornitore) return '/fornitori';
  const nome = toSlug(fornitore.ragione_sociale || fornitore.nome || 'fornitore');
  return `/fornitori/${nome}`;
};

// Genera URL per dipendente
export const dipendenteUrl = dipendente => {
  if (!dipendente) return '/dipendenti';
  const nome = toSlug(
    dipendente.nome_completo ||
      dipendente.name ||
      `${dipendente.nome || ''} ${dipendente.cognome || ''}`
  );
  return `/dipendenti/${nome}`;
};

// Genera URL per F24
export const f24Url = f24 => {
  if (!f24) return '/f24';
  const tipo = toSlug(f24.tipo || 'f24');
  const data = f24.data_scadenza || f24.data || '';
  const dataStr = data ? toSlug(data.substring(0, 10)) : 'corrente';
  return `/f24/${tipo}-${dataStr}`;
};

// Genera URL per documento generico
export const documentoUrl = (tipo, doc) => {
  if (!doc) return '/';

  switch (tipo) {
    case 'cedolino':
      return cedolinoUrl(doc);
    case 'fattura':
      return fatturaUrl(doc);
    case 'fornitore':
      return fornitoreUrl(doc);
    case 'dipendente':
      return dipendenteUrl(doc);
    case 'f24':
      return f24Url(doc);
    default:
      return `/${tipo}/${doc.id || ''}`;
  }
};

// Nome mese da numero
const getMeseNome = meseNum => {
  const mesi = {
    1: 'gennaio',
    2: 'febbraio',
    3: 'marzo',
    4: 'aprile',
    5: 'maggio',
    6: 'giugno',
    7: 'luglio',
    8: 'agosto',
    9: 'settembre',
    10: 'ottobre',
    11: 'novembre',
    12: 'dicembre',
    13: 'tredicesima',
    14: 'quattordicesima',
  };
  return mesi[meseNum] || 'mese';
};

// Genera breadcrumb items da URL
export const generateBreadcrumb = (pathname, pageTitle = '') => {
  const parts = pathname.split('/').filter(Boolean);
  const items = [{ label: 'Home', path: '/' }];

  let currentPath = '';
  parts.forEach((part, index) => {
    currentPath += `/${part}`;

    // Decodifica e formatta il segmento
    const decodedPart = decodeURIComponent(part)
      .replace(/-/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase()); // Title case

    // Ultimo elemento usa pageTitle se fornito
    const label = index === parts.length - 1 && pageTitle ? pageTitle : decodedPart;

    items.push({
      label,
      path: currentPath,
      isLast: index === parts.length - 1,
    });
  });

  return items;
};

// Aggiorna document.title per SEO
export const updatePageTitle = (title, section = '') => {
  const baseName = 'TechRecon ERP';
  if (title && section) {
    document.title = `${title} | ${section} | ${baseName}`;
  } else if (title) {
    document.title = `${title} | ${baseName}`;
  } else {
    document.title = baseName;
  }
};
