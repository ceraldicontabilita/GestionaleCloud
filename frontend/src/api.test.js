/**
 * Contratto errori: il backend risponde con code/message/details/
 * correlation_id e lascia `detail` com'era. `messaggioErrore` e' l'unico
 * punto che trasforma quella risposta in una frase per l'utente.
 */
import { describe, expect, it, vi } from 'vitest';

import api, { ATTESE_RITENTATIVI_MS, eErroreTransitorio, messaggioErrore } from './api';

vi.mock('sonner', () => ({ toast: { loading: vi.fn(), dismiss: vi.fn() } }));

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


describe('letture durante il riavvio del servizio', () => {
  it('502, 503, 504 e una richiesta caduta sono transitori; un 400 o un 500 no', () => {
    expect(eErroreTransitorio({ response: { status: 502 } })).toBe(true);
    expect(eErroreTransitorio({ response: { status: 503 } })).toBe(true);
    expect(eErroreTransitorio({ response: { status: 504 } })).toBe(true);
    expect(eErroreTransitorio({ message: 'Network Error' })).toBe(true);
    expect(eErroreTransitorio({ response: { status: 400 } })).toBe(false);
    expect(eErroreTransitorio({ response: { status: 500 } })).toBe(false);
  });

  it('le attese coprono circa un minuto: un riavvio di Render non arriva all\'errore rosso', () => {
    const totale = ATTESE_RITENTATIVI_MS.reduce((a, b) => a + b, 0);
    expect(totale).toBeGreaterThanOrEqual(60000);
    expect(ATTESE_RITENTATIVI_MS.length).toBeGreaterThanOrEqual(5);
  });

  it('una lettura ritenta finche\' il servizio risponde; una scrittura no', async () => {
    vi.useFakeTimers();
    let chiamate = 0;
    const adattatore = config => {
      chiamate += 1;
      if (chiamate <= 3) return Promise.reject({ config, response: { status: 502, data: '' } });
      return Promise.resolve({ data: { ok: true }, status: 200, statusText: 'OK', headers: {}, config });
    };
    const lettura = api.get('/api/prova', { adapter: adattatore });
    await vi.runAllTimersAsync();
    expect((await lettura).data).toEqual({ ok: true });
    expect(chiamate).toBe(4);

    chiamate = 0;
    const scrittura = api.post('/api/prova', {}, { adapter: adattatore });
    const esito = scrittura.catch(e => e);
    await vi.runAllTimersAsync();
    expect((await esito).response.status).toBe(502);
    expect(chiamate).toBe(1);
    vi.useRealTimers();
  });
});
