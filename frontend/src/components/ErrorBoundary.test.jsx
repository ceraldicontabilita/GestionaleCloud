import { describe, expect, it } from 'vitest';
import { isStaleChunkError } from './ErrorBoundary';

describe('isStaleChunkError', () => {
  it.each([
    'Failed to fetch dynamically imported module: /assets/Pagina.js',
    'Importing a module script failed.',
    'ChunkLoadError: Loading chunk 128 failed',
    'CSS_CHUNK_LOAD_FAILED',
  ])('riconosce un asset non più disponibile dopo il deploy: %s', (message) => {
    expect(isStaleChunkError(new Error(message))).toBe(true);
  });

  it('non ricarica automaticamente per un normale errore applicativo', () => {
    expect(isStaleChunkError(new Error('Risposta API non valida'))).toBe(false);
  });
});
