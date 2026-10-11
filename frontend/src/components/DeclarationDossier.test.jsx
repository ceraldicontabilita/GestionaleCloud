import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import DeclarationDossier from './DeclarationDossier';

it('IVA: apre rigo e quietanza, mostra differenza e separa credito dal pagamento', () => {
  const onOpen=vi.fn();
  const payment={id:'p',codice:'6007',data:'2025-02-17',amount_cents:98252,ravvedimento:true,
    quietanze:[{id:'q',filename:'Quietanza IVA.pdf',pdf_url:'/originale/iva-q'}]};
  render(<DeclarationDossier onOpen={onOpen} dossier={{document_type:'DICHIARAZIONE_IVA',tax_year:2024,originals:[],tax_check:{
    paid_cents:539650,comparisons:[{id:'vl30',submission:'INVIO-IVA',label:'IVA periodica dichiarata versata',
      stato:'IMPORTO_DIVERSO',stato_label:'Differenza da verificare',declared_cents:686000,paid_cents:539650,
      difference_cents:-146350,cutoff:'2025-04-18',warnings:[],payments:[payment],
      field:{sources:[{id:'vl',filename:'IVA.pdf',pdf_url:'/originale/iva',row:'VL30',column:3,page:8}]}}],
    groups:[{codice:'6007',label:'IVA mese 07',paid_cents:98252,ravvedimento:true,payments:[payment]}],
    credits:[{...payment,id:'credit',codice:'6099',amount_cents:357400}],
    accessories:[{...payment,id:'interest',codice:'1991',label:'Interessi ravvedimento IVA',amount_cents:929,principal_codes:['6007']}]
  }}} />);
  fireEvent.click(screen.getByText('Apri fascicolo'));
  expect(screen.getByText('Differenza da verificare').closest('details')).toHaveClass('declaration-withholding-importo_diverso');
  fireEvent.click(screen.getByText('IVA periodica dichiarata versata'));
  fireEvent.click(screen.getByRole('button',{name:'Apri VL30 col. 3 · pagina 8'}));
  expect(onOpen).toHaveBeenLastCalledWith({url:'/originale/iva',titolo:'IVA.pdf'});
  fireEvent.click(screen.getAllByRole('button',{name:'Apri quietanza'})[0]);
  expect(onOpen).toHaveBeenLastCalledWith({url:'/originale/iva-q',titolo:'Quietanza IVA.pdf'});
  expect(screen.getByText(/Differenza quietanze/)).toHaveTextContent(/1\.?463,50/);
  expect(screen.getByText(/Tributi documentati/)).toHaveTextContent(/5\.?396,50/);
  expect(screen.getByText('Crediti utilizzati in compensazione')).toBeInTheDocument();
  expect(screen.getByText(/presente ravvedimento/)).toBeInTheDocument();
});

describe('Fascicolo dichiarazione annuale', () => {
  it('riunisce invii e allegati e apre ogni originale e la quietanza senza F24', () => {
    const onOpen = vi.fn();
    render(<DeclarationDossier onOpen={onOpen} dossier={{
      document_type: 'MODELLO_770', tax_year: 2023, model_years: [2024], taxpayer_id: '04523831214',
      original_count: 3, receipt_count: 1,
      originals: [
        { id: 'front', filename: 'Frontespizio.pdf', role: 'Frontespizio', declaration_identifier: 'INVIO-1', pdf_url: '/api/originale/documento/front' },
        { id: 'st', filename: 'ST.pdf', role: 'Quadro ST', declaration_identifier: 'INVIO-1', pdf_url: '/api/originale/documento/st' },
        { id: 'integrativa', filename: 'Integrativa.pdf', declaration_identifier: 'INVIO-2', pdf_url: '/api/originale/documento_fiscale/integrativa' },
      ],
      quietanze: [{ chiave: 'q', data: '2024-01-16', importo_cents: 12500, senza_modello: true,
        tax_rows: [{ codice: '1001', mese: 12, anno: 2023, importo_debito_cents: 12500 }],
        quietanze: [{ id: 'q', filename: 'Quietanza.pdf', pdf_url: '/api/originale/quietanza/q' }],
      }],
    }} />);
    expect(screen.getByText('770 · Anno d’imposta 2023')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Apri fascicolo'));
    for (const [filename, url] of [['Frontespizio.pdf', '/api/originale/documento/front'], ['ST.pdf', '/api/originale/documento/st'],
      ['Integrativa.pdf', '/api/originale/documento_fiscale/integrativa'], ['Quietanza.pdf', '/api/originale/quietanza/q']]) {
      fireEvent.click(screen.getByRole('button', { name: `Apri PDF ${filename}` }));
      expect(onOpen).toHaveBeenLastCalledWith({ url, titolo: filename });
    }
    expect(screen.getByText('Invio INVIO-1')).toBeInTheDocument();
    expect(screen.getByText('Invio INVIO-2')).toBeInTheDocument();
    expect(screen.getByText(/12\/2023/)).toBeInTheDocument();
  });
});

it('mostra ravvedimento, originale, quietanza e differenze senza nasconderle', () => {
  const onOpen=vi.fn();
  const check={id:'1040',codice:'1040',mese:12,anno:2024,submission:'INVIO-1',stato:'PAGATO_RAVVEDIMENTO',
    stato_label:'Pagato · ravvedimento',dichiarato_cents:52157,quietanzato_cents:52157,differenza_cents:0,
    data_dichiarata:'2025-03-12',warnings:[],candidates:[],
    rows:[{rigo:'ST7',modulo:1,ritenute_operate_cents:52000,importo_versato_cents:52157,interessi_cents:157,ravvedimento:true,
      sources:[{id:'770',filename:'770.pdf',pdf_url:'/originale/770',page:4}]}],
    payments:[{data:'2025-03-12',importo_cents:52157,protocollo:'PROT',receipt_row:{periodo_riferimento:'12/2024'},
      quietanze:[{id:'q',filename:'Quietanza.pdf',pdf_url:'/originale/q'}]}],
    sanzioni:[{data:'2025-03-12',row:{codice:'8948',importo_debito_cents:722},quietanze:[{id:'q',filename:'Quietanza.pdf',pdf_url:'/originale/q'}]}]};
  render(<DeclarationDossier onOpen={onOpen} dossier={{document_type:'MODELLO_770',tax_year:2024,originals:[],
    withholding_check:{declared_rows:2,counts:{PAGATO_RAVVEDIMENTO:1,QUIETANZA_MANCANTE:1},groups:[check,
      {...check,id:'missing',codice:'1001',stato:'QUIETANZA_MANCANTE',stato_label:'Pagamento non documentato · quietanza mancante',payments:[],sanzioni:[],rows:[]}]}}} />);
  fireEvent.click(screen.getByText('Apri fascicolo'));
  fireEvent.click(screen.getByText('1040 · 12/2024'));
  fireEvent.click(screen.getByRole('button',{name:'Apri 770 · pagina 4'}));
  expect(onOpen).toHaveBeenLastCalledWith({url:'/originale/770',titolo:'770.pdf'});
  fireEvent.click(screen.getByRole('button',{name:'Apri quietanza del tributo'}));
  expect(onOpen).toHaveBeenLastCalledWith({url:'/originale/q',titolo:'Quietanza.pdf'});
  expect(screen.getByText(/Sanzione 8948/)).toHaveTextContent('7,22');
  expect(screen.getByText(/Interessi inclusi/)).toHaveTextContent('1,57');
  expect(screen.getByText(/Pagamento non documentato · quietanza mancante/).closest('details')).toHaveClass('declaration-withholding-quietanza_mancante');
});
