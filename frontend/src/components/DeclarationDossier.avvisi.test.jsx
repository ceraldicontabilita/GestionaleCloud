import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import DeclarationDossier from './DeclarationDossier';

it('distingue avviso da ravvedimento, apre compliance, avviso e quietanza e conserva la verifica VL30', () => {
  const onOpen = vi.fn();
  const q = { id:'q', filename:'quietanza.pdf', pdf_url:'/q' };
  render(<DeclarationDossier onOpen={onOpen} dossier={{document_type:'DICHIARAZIONE_IVA',tax_year:2024,
    originals:[],quietanze:[],tax_check:{paid_cents:685965,groups:[],comparisons:[{
      id:'vl30',label:'IVA periodica dichiarata versata',stato:'PAGATO',stato_label:'Importo riscontrato nelle quietanze',
      declared_cents:686000,paid_cents:685965,difference_cents:-35,classification_review:true,
    }],avvisi:[{codice_atto:'05354492513',anno:2024,stato:'PAGATA',totale_cents:163304,
      versato_cents:163304,imposta_cents:146315,sanzioni_cents:14632,interessi_cents:2357,
      avviso:{filename:'avviso.pdf',pdf_url:'/a'},compliance:[{id:'c',filename:'compliance.pdf',pdf_url:'/c'}],quietanze:[q]}]}}} />);
  fireEvent.click(screen.getByText('Apri fascicolo'));
  expect(screen.getByText('Pagato tramite avviso bonario')).toBeInTheDocument();
  expect(screen.getByText(/classificazione in dichiarazione da verificare/)).toBeInTheDocument();
  expect(screen.getByText(/Imposta:/)).toHaveTextContent(/1\.?463,15/);
  expect(screen.getByText(/Imposta:/)).toHaveTextContent('146,32');
  expect(screen.getByText(/Imposta:/)).toHaveTextContent('23,57');
  for (const [name, url, titolo] of [['Apri avviso bonario','/a','avviso.pdf'],['Apri compliance','/c','compliance.pdf'],['Apri quietanza','/q','quietanza.pdf']]) {
    fireEvent.click(screen.getByRole('button',{name}));
    expect(onOpen).toHaveBeenLastCalledWith({url,titolo});
  }
});
