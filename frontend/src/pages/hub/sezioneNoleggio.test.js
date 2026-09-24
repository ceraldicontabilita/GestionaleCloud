import { describe, expect, it } from 'vitest';
import { sezioneNoleggio } from './VeicoliHub.jsx';

describe('sezioneNoleggio', () => {
  it('non confonde i pezzi', () => {
    expect(sezioneNoleggio('/noleggio')).toBe('flotta');
    expect(sezioneNoleggio('/noleggio/verbali')).toBe('verbali');
    expect(sezioneNoleggio('/noleggio/posizione')).toBe('posizione');
    expect(sezioneNoleggio('/noleggio/costi')).toBe('costi');
    expect(sezioneNoleggio('/noleggio/verbali-extra')).toBe('flotta');
  });
});
