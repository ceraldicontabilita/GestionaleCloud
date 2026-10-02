import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import axios from 'axios';
import ProductManager from './ProductManager';
import { toast } from '../../hooks/use-toast';

jest.mock('../../hooks/use-toast', () => ({ toast: jest.fn() }));
global.IS_REACT_ACT_ENVIRONMENT = true;

describe('X reversibile per i possibili doppioni del Menu', () => {
  let node, root;
  const products = [
    {id:100,nameIT:'Babà',name:'Babà',price:'3.00€',image:'/menu/baba.jpg'},
    {id:101,nameIT:'BABA',name:'BABA',price:'4.00€'},
    {id:102,nameIT:'Cannolo',name:'Cannolo',price:'5.00€'},
  ];
  beforeEach(() => {
    node = document.createElement('div'); document.body.appendChild(node); root = createRoot(node);
    jest.spyOn(window, 'confirm').mockReturnValue(true);
    jest.spyOn(axios, 'get').mockImplementation(url => Promise.resolve({data: url.includes('/all') ? {products} : []}));
    jest.spyOn(axios, 'put').mockResolvedValue({data:{success:true,menu_sync:{esito:'aggiornato'}}});
    toast.mockClear();
  });
  afterEach(async () => { await act(async () => root.unmount()); node.remove(); jest.restoreAllMocks(); });
  const render = () => act(async () => root.render(<ProductManager />));
  const check = label => [...node.querySelectorAll('label')].find(l => l.textContent.includes(label)).querySelector('input');
  const button = label => node.querySelector(`button[aria-label="${label}"]`);

  test('mostra foto e filtra stesso nome, senza cancellazioni automatiche', async () => {
    await render();
    expect(node.querySelector('img').getAttribute('src')).toBe('/menu/baba.jpg');
    await act(async () => check('Possibili doppioni').click());
    expect(button('Nascondi Babà')).not.toBeNull();
    expect(button('Nascondi BABA')).not.toBeNull();
    expect(button('Nascondi Cannolo')).toBeNull();
    expect(axios.put).not.toHaveBeenCalled();
  });
  test('un prodotto Lotti non offre un secondo punto di modifica della visibilità', async () => {
    axios.get.mockImplementation(url=>Promise.resolve({data:url.includes('/all')?{products:[{...products[0],origine:'lotti',lotti_ref:'ricetta:r1'}]}:[]}));
    await render();
    expect(button('Nascondi Babà')).toBeNull();
    expect(button('Modifica Babà').textContent).toContain('Ricetta');
    expect(axios.put).not.toHaveBeenCalled();
  });
  test('nasconde solo ID scelto dopo conferma e permette ripristino', async () => {
    await render();
    await act(async () => button('Nascondi Babà').click());
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('Babà'));
    expect(axios.put).toHaveBeenCalledWith(expect.stringContaining('/products/100/visibilita'), {visible:false}, expect.any(Object));
    expect(button('Nascondi Babà')).toBeNull();
    expect(button('Nascondi BABA')).not.toBeNull();
    await act(async () => check('Mostra anche nascosti').click());
    await act(async () => button('Ripristina Babà').click());
    expect(axios.put).toHaveBeenLastCalledWith(expect.stringContaining('/products/100/visibilita'), {visible:true}, expect.any(Object));
    expect(button('Nascondi Babà')).not.toBeNull();
  });
  test('annulla senza scrivere sul server', async () => {
    window.confirm.mockReturnValue(false);
    await render(); await act(async () => button('Nascondi Babà').click());
    expect(axios.put).not.toHaveBeenCalled();
    expect(button('Nascondi Babà')).not.toBeNull();
  });
  test('fallimento del ponte conserva la voce e segnala di riprovare', async () => {
    axios.put.mockResolvedValue({data:{success:true,menu_sync:{esito:'errore'}}});
    await render(); await act(async () => button('Nascondi Babà').click());
    expect(button('Nascondi Babà')).not.toBeNull();
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({title:'Visibilità non aggiornata'}));
  });
});
