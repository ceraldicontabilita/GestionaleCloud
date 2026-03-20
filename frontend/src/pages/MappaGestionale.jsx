/**
 * MappaGestionale.jsx
 * Mappa interattiva del gestionale Ceraldi ERP.
 * - Diagramma Mermaid modificabile
 * - Descrizione umanizzata che si aggiorna in base al diagramma
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import mermaid from 'mermaid';

// ─────────────────────────────────────────────────────────────────────────────
// Dizionario sezioni del gestionale
// ─────────────────────────────────────────────────────────────────────────────
const SEZIONI_DICT = {
  DASHBOARD: {
    titolo: "Dashboard — Cruscotto Aziendale",
    icona: "📊",
    colore: "#1a40b5",
    descrizione: `La Dashboard è il punto di partenza del gestionale. Appena entri, vedi in un colpo d'occhio come sta andando l'azienda: il volume d'affari dell'anno, i costi sostenuti, quanti dipendenti sono in servizio e lo stato della liquidità. I dati si aggiornano in tempo reale e puoi scegliere l'anno da analizzare. È pensata per il titolare che vuole capire subito la situazione senza dover aprire ogni modulo.`,
    funzioni: ["KPI in tempo reale", "Volume d'affari e costi", "Grafici mensili", "Confronto anni precedenti"]
  },
  CICLO_PASSIVO: {
    titolo: "Ciclo Passivo — Fatture Ricevute & Corrispettivi",
    icona: "📥",
    colore: "#dc2626",
    descrizione: `Qui gestisci tutto quello che entra dall'esterno: le fatture che ricevi dai fornitori (gas, luce, materie prime, servizi) e i corrispettivi del Registratore Telematico. Le fatture XML vengono caricate e il sistema le legge in automatico estraendo fornitore, importo, scadenza e IVA. I corrispettivi mostrano giorno per giorno quanto hai incassato al bancone, separando contanti e POS. È il cuore del ciclo passivo aziendale.`,
    funzioni: ["Fatture XML fornitori", "Corrispettivi RT giornalieri", "Archivio fatture ricevute", "Scadenze di pagamento"]
  },
  PRIMA_NOTA: {
    titolo: "Prima Nota — Cassa & Banca",
    icona: "📒",
    colore: "#16a34a",
    descrizione: `La Prima Nota è il registro contabile dei movimenti di denaro. È divisa in due grandi sezioni: la Cassa (i soldi fisici) e la Banca (il conto corrente). Per la Cassa, il sistema registra automaticamente ogni corrispettivo come entrata e ogni pagamento POS come uscita verso la banca — così sai sempre quanti contanti hai in cassa. Per la Banca, carichi l'estratto conto CSV del Banco BPM e vedi tutti i movimenti bancari, con la possibilità di filtrare per data, importo e categoria.`,
    funzioni: ["Prima Nota Cassa (contanti)", "Prima Nota Banca (estratto conto)", "Import CSV Banco BPM", "Saldo progressivo per giorno"]
  },
  FORNITORI: {
    titolo: "Fornitori — Anagrafica & Rapporti",
    icona: "🏭",
    colore: "#7c3aed",
    descrizione: `La sezione Fornitori raccoglie tutte le informazioni sui tuoi partner commerciali. Per ogni fornitore vedi lo storico delle fatture ricevute, gli importi totali, le scadenze ancora aperte e il metodo di pagamento preferito (bonifico, SEPA, carta). Puoi cercare un fornitore specifico e vedere tutto il suo storico in un'unica schermata. Il sistema impara dai tuoi dati e suggerisce automaticamente la categoria merceologica delle nuove fatture dello stesso fornitore.`,
    funzioni: ["Anagrafica fornitori", "Storico fatture per fornitore", "Metodi di pagamento", "Ordini e previsioni acquisti"]
  },
  DIPENDENTI: {
    titolo: "Dipendenti — HR & Gestione Personale",
    icona: "👥",
    colore: "#0369a1",
    descrizione: `Il modulo HR gestisce tutto il personale dell'azienda. Puoi vedere la lista completa dei dipendenti, il loro stato (in carico o no), le ore di presenza, le ferie richieste e i permessi. Il flag "in carico" indica se il dipendente è attualmente attivo in azienda. Dalla stessa schermata puoi modificare i periodi di ferie, approvare richieste o eliminarle. È il pannello di controllo per la gestione quotidiana del personale.`,
    funzioni: ["Lista dipendenti con stato", "Presenze e timbrature", "Ferie e permessi", "Flag 'In carico'"]
  },
  PAGHE: {
    titolo: "Paghe & Retribuzioni",
    icona: "💰",
    colore: "#b45309",
    descrizione: `La sezione Paghe raccoglie i cedolini di tutti i dipendenti, anche quelli che non lavorano più in azienda. Puoi cercare per nome, anno e mese. Il sistema mostra i dettagli di ogni busta paga con retribuzione lorda, netta, contributi e trattenute. È collegata alla Prima Nota Salari, dove i costi del personale vengono automaticamente registrati come uscite contabili.`,
    funzioni: ["Cedolini per dipendente", "Prima Nota Salari automatica", "TFR (Trattamento Fine Rapporto)", "Storico storico cedolini"]
  },
  FISCO: {
    titolo: "Fisco & Tributi",
    icona: "🏛️",
    colore: "#be185d",
    descrizione: `Il modulo Fiscale gestisce tutti gli adempimenti tributari. Calcola l'IVA dovuta ogni trimestre, mostra le liquidazioni, gestisce i modelli F24 pagati e quelli ancora da pagare. Puoi riconciliare i pagamenti F24 estratti dall'estratto conto con i modelli nel sistema, per avere sempre la certezza di quali tributi sono stati effettivamente pagati. È fondamentale per preparare i dati da consegnare al commercialista.`,
    funzioni: ["Liquidazione IVA trimestrale", "Modelli F24", "Riconciliazione tributi", "Codici tributari"]
  },
  BILANCIO: {
    titolo: "Bilancio & Analisi Finanziaria",
    icona: "⚖️",
    colore: "#0f766e",
    descrizione: `Il Bilancio offre una visione completa della situazione patrimoniale e economica dell'azienda. Trovate il partitario per categoria, il budget previsionale con i target di ricavo e costo, e la verifica del bilancio che controlla la coerenza dei dati contabili. È lo strumento per fare pianificazione finanziaria e capire se l'azienda sta rispettando i suoi obiettivi economici.`,
    funzioni: ["Partitario per conto", "Budget previsionale", "Analisi costi/ricavi", "Verifica coerenza bilancio"]
  },
  CONTABILITA: {
    titolo: "Contabilità — Piano dei Conti & Cespiti",
    icona: "📋",
    colore: "#475569",
    descrizione: `La Contabilità è il motore che tiene tutto insieme. Il Piano dei Conti classifica ogni movimento in voci contabili standard. I Cespiti tengono traccia di tutti i beni strumentali acquistati (attrezzature, macchinari) con il loro ammortamento. Il Calendario Fiscale ricorda le scadenze tributarie. Il Controllo Mensile confronta i dati reali con quelli attesi mese per mese.`,
    funzioni: ["Piano dei conti", "Gestione cespiti e ammortamenti", "Calendario fiscale", "Controllo mensile"]
  },
  MAGAZZINO: {
    titolo: "Magazzino & Inventario",
    icona: "📦",
    colore: "#92400e",
    descrizione: `Il Magazzino tiene traccia di tutti i prodotti presenti in azienda. Puoi fare l'inventario fisico, confrontarlo con quello contabile e gestire i movimenti di carico e scarico. Il Dizionario Articoli raccoglie tutte le denominazioni dei prodotti, utile per uniformare le descrizioni nelle fatture. La ricerca prodotti permette di trovare rapidamente qualsiasi articolo.`,
    funzioni: ["Inventario fisico e contabile", "Movimenti carico/scarico", "Dizionario articoli", "Ricerca prodotti"]
  },
  CUCINA: {
    titolo: "Cucina & Centri di Costo",
    icona: "🍽️",
    colore: "#d97706",
    descrizione: `Specifico per la ristorazione, questo modulo gestisce i centri di costo per analizzare la redditività di ogni reparto o linea di prodotto. L'Utile Obiettivo imposta i target di profitto e confronta i risultati reali. Il Learning Machine analizza i dati storici per suggerire ottimizzazioni sui costi di produzione e i margini per piatto.`,
    funzioni: ["Centri di costo per reparto", "Utile obiettivo", "Food cost", "Learning machine AI"]
  },
  RICONCILIAZIONE: {
    titolo: "Riconciliazione — Banca & Documenti",
    icona: "🔗",
    colore: "#1d4ed8",
    descrizione: `La Riconciliazione è il processo che collega i movimenti bancari ai documenti contabili. Quando arriva un accredito sul conto, il sistema cerca automaticamente la fattura o il corrispettivo corrispondente. Gestisce anche gli assegni (emessi e ricevuti) e l'archivio dei bonifici. La riconciliazione intelligente usa l'AI per suggerire i collegamenti più probabili, risparmiando ore di lavoro manuale.`,
    funzioni: ["Riconciliazione automatica AI", "Gestione assegni", "Archivio bonifici", "Riconciliazione PayPal"]
  },
  STRUMENTI: {
    titolo: "Strumenti & Commercialista",
    icona: "🔧",
    colore: "#374151",
    descrizione: `Gli Strumenti raccolgono tutte le funzionalità di supporto: il pacchetto Commercialista prepara i dati in formato Excel per il consulente fiscale, la sezione Pianificazione aiuta nella programmazione delle spese future, Visure permette di fare ricerche su aziende e persone, e Verifica Coerenza controlla che tutti i dati del gestionale siano allineati tra i vari moduli.`,
    funzioni: ["Pacchetto commercialista", "Pianificazione spese", "Verifica coerenza dati", "Visure camerali"]
  },
  IMPORT_DOCUMENTI: {
    titolo: "Import Documenti",
    icona: "📤",
    colore: "#0891b2",
    descrizione: `Il centro di importazione documenti permette di caricare fatture XML, estratti conto CSV, cedolini PDF e qualsiasi altro documento. Il parser AI legge automaticamente il documento e ne estrae i dati strutturati (importo, data, fornitore, ecc.). Puoi anche correggere manualmente i dati estratti prima di confermare l'importazione.`,
    funzioni: ["Import fatture XML", "Import estratto conto CSV", "Parser AI documenti", "Correzione manuale dati"]
  },
  INTEGRAZIONI: {
    titolo: "Integrazioni Esterne",
    icona: "🔌",
    colore: "#7c3aed",
    descrizione: `Le Integrazioni collegano il gestionale con servizi esterni. InvoiceTrading permette di inviare e ricevere fatture elettroniche tramite SDI. PagoPA gestisce i pagamenti verso la Pubblica Amministrazione. La sezione email scarica automaticamente le fatture ricevute per email e le importa nel sistema.`,
    funzioni: ["Fatturazione elettronica SDI", "PagoPA", "Download email fatture", "API OpenAPI"]
  },
  SCADENZE: {
    titolo: "Scadenzario",
    icona: "📅",
    colore: "#dc2626",
    descrizione: `Lo Scadenzario è la tua agenda fiscale e finanziaria. Mostra tutte le scadenze imminenti: fatture da pagare, F24 da versare, adempimenti fiscali, rinnovi contratti. Puoi filtrare per mese e tipo di scadenza. Il sistema invia notifiche automatiche quando si avvicina una scadenza importante.`,
    funzioni: ["Scadenze fatture fornitori", "Scadenze fiscali F24", "Alert automatici", "Calendario mensile"]
  }
};

// ─────────────────────────────────────────────────────────────────────────────
// Diagramma Mermaid predefinito
// ─────────────────────────────────────────────────────────────────────────────
const DIAGRAMMA_DEFAULT = `flowchart TD
    A[🏠 INIZIO — Accesso al Gestionale] --> B[📊 DASHBOARD\\nKPI e Cruscotto]

    B --> C[📥 CICLO PASSIVO\\nFatture & Corrispettivi]
    B --> D[📒 PRIMA NOTA\\nCassa & Banca]
    B --> E[👥 DIPENDENTI\\nHR & Personale]
    B --> F[🏛️ FISCO\\nTributi & IVA]
    B --> G[📋 CONTABILITA\\nPiano dei Conti]

    C --> C1[Fatture Fornitori XML]
    C --> C2[Corrispettivi RT]
    C1 --> H[🏭 FORNITORI\\nAnagrafica]
    C1 --> D
    C2 --> D

    D --> D1[Cassa — Contanti]
    D --> D2[Banca — Estratto Conto]
    D1 --> D3{Saldo Cassa\\n= Contanti}
    D2 --> D3

    E --> E1[Presenze & Timbrature]
    E --> E2[Ferie & Permessi]
    E --> E3[💰 PAGHE\\nCedolini & TFR]

    F --> F1[Liquidazione IVA]
    F --> F2[Modelli F24]
    F2 --> D2

    G --> G1[Piano dei Conti]
    G --> G2[Cespiti & Ammortamenti]
    G --> G3[Calendario Fiscale]

    B --> I[⚖️ BILANCIO\\nAnalisi Finanziaria]
    I --> I1[Partitario]
    I --> I2[Budget Previsionale]

    B --> J[🔗 RICONCILIAZIONE\\nBanca & Documenti]
    J --> D2
    J --> C1

    B --> K[📦 MAGAZZINO\\nInventario]
    B --> L[🍽️ CUCINA\\nCentri di Costo]
    B --> M[🔧 STRUMENTI\\nCommercialista]
    B --> N[📤 IMPORT DOCUMENTI]
    B --> O[📅 SCADENZARIO]

    style A fill:#1a40b5,color:#fff
    style B fill:#1a40b5,color:#fff
    style C fill:#dc2626,color:#fff
    style D fill:#16a34a,color:#fff
    style E fill:#0369a1,color:#fff
    style F fill:#be185d,color:#fff
    style G fill:#475569,color:#fff
    style H fill:#7c3aed,color:#fff
    style I fill:#0f766e,color:#fff
    style J fill:#1d4ed8,color:#fff
    style K fill:#92400e,color:#fff
    style L fill:#d97706,color:#fff
    style M fill:#374151,color:#fff
    style N fill:#0891b2,color:#fff
    style O fill:#dc2626,color:#fff
    style E3 fill:#b45309,color:#fff`;

// ─────────────────────────────────────────────────────────────────────────────
// Parsing del diagramma per estrarre i nodi e costruire il testo
// ─────────────────────────────────────────────────────────────────────────────
function parseNodiDiagramma(mermaidText) {
  const lines = mermaidText.split('\n');
  const sezioni = new Set();

  const keywords = {
    'DASHBOARD': 'DASHBOARD', 'CICLO PASSIVO': 'CICLO_PASSIVO',
    'PRIMA NOTA': 'PRIMA_NOTA', 'FORNITORI': 'FORNITORI',
    'DIPENDENTI': 'DIPENDENTI', 'PAGHE': 'PAGHE',
    'FISCO': 'FISCO', 'BILANCIO': 'BILANCIO',
    'CONTABILITA': 'CONTABILITA', 'MAGAZZINO': 'MAGAZZINO',
    'CUCINA': 'CUCINA', 'RICONCILIAZIONE': 'RICONCILIAZIONE',
    'STRUMENTI': 'STRUMENTI', 'IMPORT DOCUMENTI': 'IMPORT_DOCUMENTI',
    'SCADENZARIO': 'SCADENZE', 'INTEGRAZIONI': 'INTEGRAZIONI'
  };

  lines.forEach(line => {
    Object.entries(keywords).forEach(([keyword, key]) => {
      if (line.toUpperCase().includes(keyword) && SEZIONI_DICT[key]) {
        sezioni.add(key);
      }
    });
  });

  return Array.from(sezioni);
}

// ─────────────────────────────────────────────────────────────────────────────
// Componente principale
// ─────────────────────────────────────────────────────────────────────────────
let mermaidInitialized = false;

export default function MappaGestionale() {
  const [codice, setCodice] = useState(DIAGRAMMA_DEFAULT);
  const [codiceInput, setCodiceInput] = useState(DIAGRAMMA_DEFAULT);
  const [errore, setErrore] = useState(null);
  const [sezioniAttive, setSezioniAttive] = useState([]);
  const [activeSezione, setActiveSezione] = useState(null);
  const [renderKey, setRenderKey] = useState(0);
  const diagramRef = useRef(null);
  const timeoutRef = useRef(null);

  // Init mermaid once
  useEffect(() => {
    if (!mermaidInitialized) {
      mermaid.initialize({
        startOnLoad: false,
        theme: 'base',
        themeVariables: {
          primaryColor: '#1a40b5',
          primaryTextColor: '#fff',
          primaryBorderColor: '#1a40b5',
          lineColor: '#64748b',
          secondaryColor: '#f1f5f9',
          tertiaryColor: '#f8fafc',
          background: '#ffffff',
          mainBkg: '#1a40b5',
          nodeBorder: '#1a40b5',
          clusterBkg: '#f8fafc',
          titleColor: '#1e293b',
          edgeLabelBackground: '#ffffff',
          fontSize: '14px'
        },
        flowchart: { htmlLabels: true, curve: 'basis', padding: 20 },
        securityLevel: 'loose'
      });
      mermaidInitialized = true;
    }
  }, []);

  // Render diagram
  const renderDiagram = useCallback(async (code) => {
    if (!diagramRef.current) return;
    try {
      setErrore(null);
      const id = `mermaid-${Date.now()}`;
      const { svg } = await mermaid.render(id, code);
      if (diagramRef.current) {
        diagramRef.current.innerHTML = svg;
        // Scale svg to fit
        const svgEl = diagramRef.current.querySelector('svg');
        if (svgEl) {
          svgEl.style.maxWidth = '100%';
          svgEl.style.height = 'auto';
        }
      }
      const parsed = parseNodiDiagramma(code);
      setSezioniAttive(parsed);
      if (parsed.length > 0 && !activeSezione) {
        setActiveSezione(parsed[0]);
      }
    } catch (e) {
      setErrore('Errore nel diagramma: ' + e.message?.substring(0, 100));
    }
  }, [activeSezione]);

  // Initial render
  useEffect(() => {
    renderDiagram(codice);
  }, [codice]);

  // Debounced update from editor
  const handleCodiceChange = (val) => {
    setCodiceInput(val);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => {
      setCodice(val);
    }, 800);
  };

  const handleApplica = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setCodice(codiceInput);
    setRenderKey(k => k + 1);
  };

  const handleReset = () => {
    setCodiceInput(DIAGRAMMA_DEFAULT);
    setCodice(DIAGRAMMA_DEFAULT);
    setActiveSezione(null);
  };

  const sezioneInfo = activeSezione ? SEZIONI_DICT[activeSezione] : null;

  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc', fontFamily: "'Inter', sans-serif" }}>
      {/* Header */}
      <div style={{
        background: 'linear-gradient(135deg, #1a40b5 0%, #1e3a8a 100%)',
        padding: '24px 32px', color: 'white',
        boxShadow: '0 4px 20px rgba(26,64,181,0.3)'
      }}>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, letterSpacing: '-0.5px' }}>
          Mappa del Gestionale Ceraldi ERP
        </h1>
        <p style={{ margin: '6px 0 0', opacity: 0.85, fontSize: 14 }}>
          Diagramma interattivo modificabile • Clicca una sezione per leggere la descrizione dettagliata
        </p>
      </div>

      {/* Layout principale */}
      <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 0, minHeight: 'calc(100vh - 80px)' }}>

        {/* ── Colonna sinistra: editor ── */}
        <div style={{
          background: '#1e293b', padding: 20, borderRight: '1px solid #334155',
          display: 'flex', flexDirection: 'column', gap: 12
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ color: '#94a3b8', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1 }}>
              Editor Diagramma (Mermaid)
            </span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                onClick={handleApplica}
                style={{
                  padding: '5px 12px', background: '#22c55e', color: 'white',
                  border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: 600
                }}
              >
                ▶ Applica
              </button>
              <button
                onClick={handleReset}
                style={{
                  padding: '5px 10px', background: '#475569', color: '#94a3b8',
                  border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12
                }}
              >
                Reset
              </button>
            </div>
          </div>

          <textarea
            value={codiceInput}
            onChange={e => handleCodiceChange(e.target.value)}
            style={{
              flex: 1, minHeight: 400, background: '#0f172a', color: '#e2e8f0',
              border: '1px solid #334155', borderRadius: 8, padding: 14,
              fontFamily: "'Fira Code', monospace", fontSize: 12, lineHeight: 1.6,
              resize: 'vertical', outline: 'none', tabSize: 4
            }}
            spellCheck={false}
            data-testid="mermaid-editor"
          />

          {errore && (
            <div style={{
              background: '#450a0a', border: '1px solid #dc2626', borderRadius: 6,
              padding: '8px 12px', color: '#fca5a5', fontSize: 12
            }}>
              ⚠️ {errore}
            </div>
          )}

          {/* Legenda sezioni */}
          <div style={{ color: '#64748b', fontSize: 11, lineHeight: 1.5 }}>
            <div style={{ color: '#94a3b8', fontWeight: 600, marginBottom: 6, fontSize: 11, textTransform: 'uppercase', letterSpacing: 1 }}>
              Sezioni rilevate nel diagramma
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {sezioniAttive.map(k => {
                const s = SEZIONI_DICT[k];
                return s ? (
                  <button
                    key={k}
                    onClick={() => setActiveSezione(k)}
                    style={{
                      padding: '3px 8px',
                      background: activeSezione === k ? s.colore : '#1e293b',
                      color: activeSezione === k ? 'white' : '#94a3b8',
                      border: `1px solid ${activeSezione === k ? s.colore : '#334155'}`,
                      borderRadius: 4, cursor: 'pointer', fontSize: 11,
                      transition: 'all 0.2s'
                    }}
                  >
                    {s.icona} {s.titolo.split('—')[0].trim()}
                  </button>
                ) : null;
              })}
            </div>
          </div>

          {/* Suggerimenti sintassi */}
          <div style={{
            background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6,
            padding: '10px 12px', color: '#64748b', fontSize: 11, lineHeight: 1.6
          }}>
            <div style={{ color: '#475569', fontWeight: 600, marginBottom: 4 }}>Sintassi Mermaid:</div>
            <code style={{ color: '#38bdf8' }}>A[Testo nodo] --&gt; B[Altro nodo]</code><br />
            <code style={{ color: '#a78bfa' }}>A{{"{Decisione}"}}</code><br />
            <code style={{ color: '#34d399' }}>style A fill:#colore,color:#fff</code>
          </div>
        </div>

        {/* ── Colonna destra: diagramma + descrizione ── */}
        <div style={{ display: 'flex', flexDirection: 'column' }}>

          {/* Diagramma */}
          <div style={{
            flex: '0 0 auto', padding: 24, background: 'white',
            borderBottom: '1px solid #e2e8f0', minHeight: 420,
            overflow: 'auto'
          }}>
            <div
              ref={diagramRef}
              key={renderKey}
              style={{ display: 'flex', justifyContent: 'center', alignItems: 'flex-start' }}
            />
          </div>

          {/* Descrizione umanizzata */}
          <div style={{ flex: 1, padding: 24, background: '#f8fafc' }}>
            <h2 style={{ margin: '0 0 16px', fontSize: 18, fontWeight: 700, color: '#1e293b' }}>
              Descrizione in parole del Gestionale
            </h2>

            {sezioniAttive.length === 0 ? (
              <div style={{
                textAlign: 'center', color: '#94a3b8', padding: 40, fontSize: 15
              }}>
                Modifica il diagramma a sinistra e le sezioni rilevate appariranno qui.
              </div>
            ) : (
              <>
                {/* Tabs sezioni */}
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
                  {sezioniAttive.map(k => {
                    const s = SEZIONI_DICT[k];
                    return s ? (
                      <button
                        key={k}
                        onClick={() => setActiveSezione(k)}
                        data-testid={`tab-sezione-${k}`}
                        style={{
                          padding: '8px 14px',
                          background: activeSezione === k ? s.colore : 'white',
                          color: activeSezione === k ? 'white' : '#475569',
                          border: `2px solid ${activeSezione === k ? s.colore : '#e2e8f0'}`,
                          borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 600,
                          transition: 'all 0.2s',
                          boxShadow: activeSezione === k ? `0 4px 12px ${s.colore}40` : 'none'
                        }}
                      >
                        {s.icona} {s.titolo.split('—')[0].trim()}
                      </button>
                    ) : null;
                  })}
                </div>

                {/* Card descrizione sezione attiva */}
                {sezioneInfo && (
                  <div
                    data-testid="sezione-descrizione"
                    style={{
                      background: 'white', borderRadius: 16, padding: 28,
                      border: `2px solid ${sezioneInfo.colore}30`,
                      boxShadow: `0 4px 24px ${sezioneInfo.colore}15`,
                      transition: 'all 0.3s'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
                      <div style={{
                        width: 52, height: 52, borderRadius: 14,
                        background: sezioneInfo.colore, display: 'flex',
                        alignItems: 'center', justifyContent: 'center', fontSize: 24,
                        boxShadow: `0 4px 12px ${sezioneInfo.colore}40`
                      }}>
                        {sezioneInfo.icona}
                      </div>
                      <div>
                        <h3 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: '#1e293b' }}>
                          {sezioneInfo.titolo}
                        </h3>
                      </div>
                    </div>

                    <p style={{
                      margin: '0 0 20px', fontSize: 15, lineHeight: 1.8,
                      color: '#374151', fontStyle: 'italic'
                    }}>
                      {sezioneInfo.descrizione}
                    </p>

                    <div>
                      <div style={{ fontWeight: 700, fontSize: 13, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 10 }}>
                        Funzioni principali
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                        {sezioneInfo.funzioni.map((f, i) => (
                          <span
                            key={i}
                            style={{
                              padding: '6px 14px',
                              background: `${sezioneInfo.colore}15`,
                              color: sezioneInfo.colore,
                              border: `1px solid ${sezioneInfo.colore}30`,
                              borderRadius: 20, fontSize: 13, fontWeight: 600
                            }}
                          >
                            {f}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Riepilogo completo */}
                <div style={{ marginTop: 24 }}>
                  <h3 style={{ fontSize: 16, fontWeight: 700, color: '#1e293b', marginBottom: 14 }}>
                    Riepilogo completo — come funziona il gestionale
                  </h3>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
                    {sezioniAttive.map(k => {
                      const s = SEZIONI_DICT[k];
                      return s ? (
                        <div
                          key={k}
                          onClick={() => setActiveSezione(k)}
                          style={{
                            background: 'white', borderRadius: 12, padding: 16,
                            border: `1px solid ${k === activeSezione ? s.colore : '#e2e8f0'}`,
                            cursor: 'pointer', transition: 'all 0.2s',
                            boxShadow: k === activeSezione ? `0 4px 16px ${s.colore}20` : 'none'
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                            <span style={{
                              width: 36, height: 36, borderRadius: 10,
                              background: `${s.colore}15`, display: 'flex',
                              alignItems: 'center', justifyContent: 'center', fontSize: 18,
                              flexShrink: 0
                            }}>
                              {s.icona}
                            </span>
                            <span style={{ fontWeight: 700, fontSize: 13, color: '#1e293b' }}>
                              {s.titolo.split('—')[0].trim()}
                            </span>
                          </div>
                          <p style={{
                            margin: 0, fontSize: 12, color: '#64748b', lineHeight: 1.5,
                            display: '-webkit-box', WebkitLineClamp: 3,
                            WebkitBoxOrient: 'vertical', overflow: 'hidden'
                          }}>
                            {s.descrizione}
                          </p>
                        </div>
                      ) : null;
                    })}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
