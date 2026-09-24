import { describe, expect, it } from 'vitest';
import {
  sezioneContabilita,
  sezioneContabilitaSconosciuta,
} from './sezioneContabilita';

describe('sezioneContabilita', () => {
  it('non confonde bilancio e bilancio-verifica', () => {
    expect(sezioneContabilita('/contabilita/bilancio')).toBe('bilancio');
    expect(sezioneContabilita('/contabilita/bilancio-verifica')).toBe('verifica');
    expect(sezioneContabilita('/contabilita/verifica')).toBe('verifica');
  });

  it('mappa gli alias e ignora la query', () => {
    expect(sezioneContabilita('/contabilita')).toBe('piano-conti');
    expect(sezioneContabilita('/contabilita/piano-dei-conti')).toBe('piano-conti');
    expect(sezioneContabilita('/contabilita/giornale')).toBe('giornale');
    expect(sezioneContabilita('/contabilita/previsioni-acquisti')).toBe('previsioni-acquisti');
    expect(sezioneContabilita('/contabilita/dati-isa?x=1')).toBe('dati-isa');
    expect(sezioneContabilita('/piano-dei-conti')).toBe('piano-conti');
    expect(sezioneContabilita('/bilancio-verifica')).toBe('verifica');
  });

  it('segnala le sezioni inesistenti', () => {
    expect(sezioneContabilita('/contabilita/inesistente')).toBe('piano-conti');
    expect(sezioneContabilitaSconosciuta('/contabilita/inesistente')).toBe(true);
    expect(sezioneContabilitaSconosciuta('/contabilita/bilancio')).toBe(false);
    expect(sezioneContabilitaSconosciuta('/contabilita')).toBe(false);
  });
});
