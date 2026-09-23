/**
 * Contratto errori: il backend risponde con code/message/details/
 * correlation_id e lascia `detail` com'era. `messaggioErrore` e' l'unico
 * punto che trasforma quella risposta in una frase per l'utente.
 */
import { describe, expect, it } from 'vitest';

import { messaggioErrore } from './api';

const errore = (data, status = 400) => ({ response: { status, data }, message: 'Request failed' });

describe('messaggioErrore', () => {
  it('usa message e cita il riferimento del log', () => {
    expect(messaggioErrore(errore({
      code: 'CONFLITTO', message: 'Fattura gia\' pagata', detail: 'Fattura gia\' pagata', correlation_id: 'abc123',
    }))).toBe("Fattura gia' pagata (rif. abc123)");
  });

  it('legge detail stringa quando message manca (risposta di un endpoint che risponde da se\')', () => {
    expect(messaggioErrore(errore({ detail: 'Authentication required' }, 401))).toBe('Authentication required');
  });

  it('legge detail.message quando detail e\' un oggetto', () => {
    expect(messaggioErrore(errore({ detail: { message: 'Due candidati', candidati: [1, 2] } }, 409)))
      .toBe('Due candidati');
  });

  it('una pagina HTML non e\' un messaggio: la chiamata e\' finita fuori da /api', () => {
    expect(messaggioErrore(errore('<!doctype html><html></html>', 200)))
      .toBe('Il server ha risposto con una pagina invece che con dei dati');
  });

  it('un 405 senza corpo dice che l\'indirizzo non accetta l\'operazione', () => {
    expect(messaggioErrore(errore('', 405))).toBe('Operazione non disponibile a questo indirizzo');
  });

  it('senza risposta usa il messaggio di rete, poi il predefinito', () => {
    expect(messaggioErrore({ message: 'Network Error' })).toBe('Network Error');
    expect(messaggioErrore(null, 'Salvataggio non riuscito')).toBe('Salvataggio non riuscito');
  });
});
