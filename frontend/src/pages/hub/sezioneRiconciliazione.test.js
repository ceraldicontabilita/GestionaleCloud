import { describe, expect, it } from 'vitest';
import { sezioneRiconciliazione } from './sezioneRiconciliazione';

describe('sezioneRiconciliazione', () => {
  it('non confonde banca con movimenti-banca o regole-banca', () => {
    expect(sezioneRiconciliazione('/riconciliazione')).toBe('');
    expect(sezioneRiconciliazione('/riconciliazione/banca')).toBe('banca');
    expect(sezioneRiconciliazione('/riconciliazione/banca?movimento=1')).toBe('banca');
    expect(sezioneRiconciliazione('/riconciliazione/movimenti-banca')).toBe('movimenti-banca');
    expect(sezioneRiconciliazione('/riconciliazione/regole-banca')).toBe('regole-banca');
    expect(sezioneRiconciliazione('/riconciliazione/archivio-bonifici')).toBe('bonifici');
    expect(sezioneRiconciliazione('/riconciliazione/gestione-assegni')).toBe('assegni');
    expect(sezioneRiconciliazione('/riconciliazione/assegni')).toBe('assegni');
    expect(sezioneRiconciliazione('/riconciliazione/f24')).toBe('f24');
  });
});
