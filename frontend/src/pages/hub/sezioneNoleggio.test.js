import { describe, expect, it } from 'vitest';
import { sezioneNoleggio } from './sezioneNoleggio';

describe('sezioneNoleggio', () => {
  it('non usa includes e ignora i suffissi', () => {
    expect(sezioneNoleggio('/noleggio')).toBe('flotta');
    expect(sezioneNoleggio('/noleggio/verbali')).toBe('verbali');
    expect(sezioneNoleggio('/noleggio/posizione')).toBe('posizione');
    expect(sezioneNoleggio('/noleggio/costi')).toBe('costi');
    expect(sezioneNoleggio('/noleggio/verbali-extra')).toBe('flotta');
  });
});
