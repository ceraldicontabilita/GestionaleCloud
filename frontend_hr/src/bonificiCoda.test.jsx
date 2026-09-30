import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, test, vi } from 'vitest'
import {
  AvvisoMultiDipendente, CandidatiBonifico, CodaRiferimenti, MOTIVI_AVVISO, eurDaCentesimi, periodoCandidato,
} from './bonificiCoda.jsx'

// Coda «Bonifici da associare»: il CRO e il riferimento banca si vedono, il
// distintivo dice il motivo a parole, i candidati sono bottoni (mai testo libero).

const candidato = (extra = {}) => ({
  dipendente_id: 'dip-russo-c', nome: 'Russo Carmine', mese: 3, anno: 2026, periodo: '03/2026',
  importo_residuo_cents: 95000, prova: 'cognome_importo_residuo',
  prova_testo: 'cognome nella causale e importo uguale al residuo della busta', punteggio: 70, ...extra,
})

describe('riferimenti del bonifico', () => {
  test('mostra CRO e riferimento banca con etichetta, in cifre allineate e selezionabili', () => {
    const html = renderToStaticMarkup(<CodaRiferimenti b={{ cro: '5034903683956034480340003400IT', rif_banca: 'MB0B00923006' }} />)
    expect(html).toContain('CRO')
    expect(html).toContain('5034903683956034480340003400IT')
    expect(html).toContain('Rif. banca')
    expect(html).toContain('MB0B00923006')
    expect(html).toContain('dc-coda-rif-val')
  })

  test('senza riferimenti mostra un trattino, non un valore inventato', () => {
    const html = renderToStaticMarkup(<CodaRiferimenti b={{}} />)
    expect(html).not.toContain('CRO')
    expect(html).toContain('—')
  })

  test('accetta anche rif_interno per le righe più vecchie', () => {
    expect(renderToStaticMarkup(<CodaRiferimenti b={{ rif_interno: 'MB0B11112222' }} />)).toContain('MB0B11112222')
  })
})

describe('avviso multi-dipendente', () => {
  test('con avviso mostra il motivo a parole e un\'icona, non il solo colore', () => {
    for (const motivo of Object.keys(MOTIVI_AVVISO)) {
      const html = renderToStaticMarkup(<AvvisoMultiDipendente b={{ avviso_multi_dipendente: true, avviso_motivo: motivo }} />)
      expect(html).toContain(MOTIVI_AVVISO[motivo])
      expect(html).toContain('<svg')
      expect(html).toContain(`data-motivo="${motivo}"`)
    }
  })

  test('senza avviso non disegna niente', () => {
    expect(renderToStaticMarkup(<AvvisoMultiDipendente b={{ avviso_multi_dipendente: false }} />)).toBe('')
    expect(renderToStaticMarkup(<AvvisoMultiDipendente b={null} />)).toBe('')
  })

  test('un motivo sconosciuto ripiega su un testo generico, mai vuoto', () => {
    const html = renderToStaticMarkup(<AvvisoMultiDipendente b={{ avviso_multi_dipendente: true, avviso_motivo: 'nuovo' }} />)
    expect(html).toContain('più dipendenti')
  })
})

describe('candidati come chip', () => {
  test('un bottone per candidato, con nome, periodo e residuo in euro', () => {
    const html = renderToStaticMarkup(<CandidatiBonifico candidati={[candidato(), candidato({ dipendente_id: 'dip-russo-a', nome: 'Russo Anna', importo_residuo_cents: 70000 })]} />)
    expect(html).toContain('Scegli dipendente')
    expect(html.match(/<button/g)).toHaveLength(2)
    expect(html).toContain('Russo Carmine')
    expect(html).toContain('Russo Anna')
    expect(html).toContain('Busta 03/2026')
    expect(html).toContain('950,00')
    expect(html).toContain('700,00')
    expect(html).toContain('type="button"')
  })

  test('nessun campo di testo: si sceglie toccando', () => {
    const html = renderToStaticMarkup(<CandidatiBonifico candidati={[candidato()]} />)
    expect(html).not.toContain('<input')
    expect(html).not.toContain('<textarea')
  })

  test('senza candidati rimanda alla tendina', () => {
    expect(renderToStaticMarkup(<CandidatiBonifico candidati={[]} />)).toContain('Nessun candidato')
    expect(renderToStaticMarkup(<CandidatiBonifico candidati={undefined} />)).toContain('Nessun candidato')
  })

  test('busta non trovata e residuo assente non si inventano', () => {
    const html = renderToStaticMarkup(<CandidatiBonifico candidati={[candidato({ periodo: null, mese: null, anno: null, importo_residuo_cents: null })]} />)
    expect(html).toContain('Busta non trovata')
    expect(html).not.toContain('residuo €')
  })

  test('il tocco chiama onScegli con il candidato, e nient\'altro', () => {
    const onScegli = vi.fn()
    const albero = CandidatiBonifico({ candidati: [candidato()], onScegli })
    // il primo bottone dentro il gruppo
    const lista = albero.props.children[1].props.children
    const bottone = lista[0]
    expect(bottone.type).toBe('button')
    bottone.props.onClick()
    expect(onScegli).toHaveBeenCalledTimes(1)
    expect(onScegli.mock.calls[0][0].dipendente_id).toBe('dip-russo-c')
  })
})

describe('formati', () => {
  test('euro da centesimi in italiano, nullo resta nullo', () => {
    expect(eurDaCentesimi(95000)).toBe('950,00')
    expect(eurDaCentesimi(null)).toBeNull()
    expect(eurDaCentesimi(undefined)).toBeNull()
  })

  test('periodo dal candidato, senza inventarlo', () => {
    expect(periodoCandidato({ mese: 3, anno: 2026 })).toBe('03/2026')
    expect(periodoCandidato({ periodo: '11/2025' })).toBe('11/2025')
    expect(periodoCandidato({})).toBeNull()
  })
})
