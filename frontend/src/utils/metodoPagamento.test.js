/**
 * «Senza metodo pagamento» deve contare le fatture senza metodo, non quelle
 * con un metodo vero. Il filtro dell'archivio metteva `misto` fra i mancanti
 * (326 fatture invece di 53).
 */
import { describe, expect, it } from 'vitest';
import { metodoNonConfigurato } from './metodoPagamento';

describe('metodo di pagamento non configurato', () => {
  it.each([undefined, null, '', '  ', 'sospesa', 'Sospesa', 'da_configurare', 'none', 'NULL'])(
    'riconosce %s come mancante',
    valore => {
      expect(metodoNonConfigurato(valore)).toBe(true);
    }
  );

  it.each(['misto', 'cassa', 'banca', 'bonifico', 'altro'])('%s e\' un metodo vero', valore => {
    expect(metodoNonConfigurato(valore)).toBe(false);
  });
});
