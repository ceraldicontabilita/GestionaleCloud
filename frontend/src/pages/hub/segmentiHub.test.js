import { describe, expect, it } from 'vitest';
import {
  sezioneDocumenti,
  sezioneStrumenti,
  sezioneFatture,
  sezionePrimaNota,
  tabUnificataDaPath,
} from './segmentiHub';

describe('segmentiHub', () => {
  it('documenti', () => {
    expect(sezioneDocumenti('/documenti/atti')).toBe('atti');
    expect(sezioneDocumenti('/documenti/drive')).toBe('drive');
    expect(sezioneDocumenti('/import-documenti')).toBe('import');
    expect(sezioneDocumenti('/documenti/atti-extra')).toBe('import');
  });

  it('strumenti', () => {
    expect(sezioneStrumenti('/strumenti')).toBe('verifica');
    expect(sezioneStrumenti('/strumenti/visure')).toBe('visure');
  });

  it('fatture e prima nota', () => {
    expect(sezioneFatture('/fatture')).toBe('archivio');
    expect(sezioneFatture('/fatture/corrispettivi')).toBe('corrispettivi');
    expect(sezionePrimaNota('/prima-nota')).toBe('prima-nota');
    expect(sezionePrimaNota('/prima-nota/pulizia')).toBe('pulizia');
  });

  it('unificata: niente -unificata e niente taglio hyphen', () => {
    expect(tabUnificataDaPath('/riconciliazione/banca')).toBe('banca');
    expect(tabUnificataDaPath('/riconciliazione/f24')).toBe('f24');
    expect(tabUnificataDaPath('/riconciliazione/movimenti-banca')).toBe('dashboard');
    expect(tabUnificataDaPath('/riconciliazione-unificata/banca')).toBe('dashboard');
  });
});
