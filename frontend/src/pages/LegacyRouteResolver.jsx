import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import PaginaNonTrovata from './PaginaNonTrovata';

const EXACT_REDIRECTS = {
  '/analytics': '/',
  '/archivio-fatture-ricevute': '/fatture',
  '/fatture-ricevute': '/fatture',
  '/corrispettivi': '/fatture/corrispettivi',
  '/ordini-fornitori': '/fornitori',
  '/dati-provvisori': '/prima-nota#sezione=provvisori',
  '/veicoli': '/noleggio',
  '/noleggio-auto': '/noleggio',
  '/verbali-riconciliazione': '/noleggio/verbali',
  '/contabilita-hub': '/contabilita',
  '/bilancio': '/contabilita/bilancio',
  '/bilancio-verifica': '/contabilita/verifica',
  '/partitario': '/contabilita/bilancio',
  '/budget-previsionale': '/contabilita/budget',
  '/mutui': '/contabilita/mutui',
  '/piano-dei-conti': '/contabilita',
  '/controllo-mensile': '/contabilita/controllo',
  '/calendario-fiscale': '/contabilita/calendario',
  '/cespiti': '/contabilita/cespiti',
  '/finanziaria': '/contabilita/finanziaria',
  '/chiusura-esercizio': '/contabilita/chiusura',
  '/utile-obiettivo': '/contabilita/utile',
  '/previsioni-acquisti': '/contabilita/previsioni-acquisti',
  '/coerenza-pos': '/riconciliazione/coerenza-pos',
  '/centri-costo': '/contabilita',
  '/gestione-assegni': '/riconciliazione/assegni',
  '/assegni': '/riconciliazione/assegni',
  '/archivio-bonifici': '/riconciliazione/archivio-bonifici',
  '/paypal': '/riconciliazione/paypal',
  '/import-documenti': '/documenti/import',
  '/import-unificato': '/documenti/import',
  '/import-export': '/documenti/import',
  '/import-ai': '/documenti/import',
  '/ai-parser': '/documenti/import',
  '/lettura-documenti': '/documenti/import',
  '/documenti-email': '/documenti/archivio',
  '/documenti-fiscali': '/documenti/archivio',
  '/regole-categorizzazione': '/learning-machine/regole',
  '/fornitori-learning': '/fornitori',
  '/verifica-coerenza': '/strumenti',
  '/verifica-coerenza/iva': '/iva',
  '/verifica-coerenza/discrepanze': '/strumenti/verifica/discrepanze',
  '/commercialista': '/strumenti/commercialista',
  '/pianificazione': '/strumenti/pianificazione',
  '/visure': '/strumenti/visure',
  '/integrazioni-openapi': '/integrazioni',
  '/pagopa': '/integrazioni/pagopa',
  '/batch-reprocessing': '/admin/batch-reprocessing',
  '/batch-processor': '/admin/batch-processor',
  '/fisco': '/contabilita/calendario',
  '/riconciliazione-unificata': '/riconciliazione',
};

const PREFIX_REDIRECTS = [
  ['/analytics/', '/'],
  ['/fatture-ricevute/', '/fatture'],
  ['/corrispettivi/', '/fatture/corrispettivi'],
  ['/ordini-fornitori/', '/fornitori'],
  ['/noleggio-auto/', '/noleggio'],
  ['/verbali-riconciliazione/', '/noleggio/verbali'],
  ['/bilancio/', '/contabilita/bilancio'],
  ['/partitario/', '/contabilita/bilancio'],
  ['/budget-previsionale/', '/contabilita/budget'],
  ['/piano-dei-conti/', '/contabilita'],
  ['/controllo-mensile/', '/contabilita/controllo'],
  ['/cespiti/', '/contabilita/cespiti'],
  ['/finanziaria/', '/contabilita/finanziaria'],
  ['/chiusura-esercizio/', '/contabilita/chiusura'],
  ['/utile-obiettivo/', '/contabilita/utile'],
  ['/previsioni-acquisti/', '/contabilita/previsioni-acquisti'],
  ['/magazzino', '/riconciliazione/coerenza-pos'],
  ['/inventario', '/riconciliazione/coerenza-pos'],
  ['/ricerca-prodotti', '/riconciliazione/coerenza-pos'],
  ['/dizionario-articoli', '/riconciliazione/coerenza-pos'],
  ['/dizionario-prodotti', '/riconciliazione/coerenza-pos'],
  ['/centri-costo/', '/contabilita'],
  ['/import-unificato/', '/documenti/import'],
  ['/ai-parser/', '/documenti/import'],
  ['/commercialista/', '/strumenti/commercialista'],
  ['/pianificazione/', '/strumenti/pianificazione'],
  ['/integrazioni-openapi/', '/integrazioni'],
  ['/pagopa/', '/integrazioni/pagopa'],
  ['/fisco/', '/contabilita/calendario'],
];

export default function LegacyRouteResolver() {
  const { pathname } = useLocation();
  const exact = EXACT_REDIRECTS[pathname];
  const prefixed = PREFIX_REDIRECTS.find(([prefix]) => pathname.startsWith(prefix));
  const target = exact || prefixed?.[1];

  if (target && target !== pathname) return <Navigate to={target} replace />;
  return <PaginaNonTrovata />;
}
