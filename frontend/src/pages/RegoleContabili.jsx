import React, { useState } from "react";
import { STYLES, COLORS, button, badge, formatEuro, formatDateIT } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

/**
 * DIZIONARIO DELLE REGOLE CONTABILI
 * 
 * Questa pagina documenta tutte le logiche di business implementate
 * nel sistema gestionale per la contabilità.
 */

export default function RegoleContabili() {
  const [expandedSection, setExpandedSection] = useState(null);

  const toggleSection = (section) => {
    setExpandedSection(expandedSection === section ? null : section);
  };

  const regole = [
    {
      id: 'ciclo-passivo',
      titolo: '📥 Ciclo Passivo (Fatture Fornitori)',
      icona: '📥',
      colore: '#1535a8',
      sottosezioni: [
        {
          titolo: 'Determinazione Metodo Pagamento Effettivo',
          regole: [
            {
              nome: 'Priorità Identificazione Metodo',
              descrizione: 'Per determinare DOVE è stata pagata una fattura, il sistema usa questa priorità: 1) prima_nota_cassa_id o prima_nota_banca_id (fonte primaria - ID del movimento in Prima Nota). 2) metodo_pagamento_effettivo o metodo_pagamento salvato (fallback per dati legacy). 3) Se nessuno dei precedenti è disponibile, permette all\'utente di scegliere.',
              campi: ['prima_nota_cassa_id (priorità 1)', 'prima_nota_banca_id (priorità 1)', 'metodo_pagamento_effettivo (priorità 2)', 'metodo_pagamento (priorità 2)']
            },
            {
              nome: 'Mapping Metodo → Cassa',
              descrizione: 'Il sistema identifica come "CASSA" i seguenti valori nel campo metodo_pagamento: contanti, cassa, cash, contante.',
              campi: ['contanti → cassa', 'cassa → cassa', 'cash → cassa']
            },
            {
              nome: 'Mapping Metodo → Banca',
              descrizione: 'Il sistema identifica come "BANCA" i seguenti valori nel campo metodo_pagamento: bonifico, banca, bank, sepa, rid, sdd.',
              campi: ['bonifico → banca', 'banca → banca', 'sepa → banca', 'rid → banca']
            },
            {
              nome: 'Dati Legacy senza ID Prima Nota',
              descrizione: 'Le fatture importate prima dell\'implementazione completa potrebbero avere pagato=true ma senza prima_nota_cassa_id/prima_nota_banca_id. In questo caso il sistema usa il campo metodo_pagamento per determinare il metodo effettivo.',
              campi: ['pagato: true', 'prima_nota_*_id: null', 'metodo_pagamento: usato come fallback']
            }
          ]
        },
        {
          titolo: 'Flusso Dati Fatture',
          regole: [
            {
              nome: 'Email → Dato Provvisorio',
              descrizione: 'Quando il sistema scarica email con fatture, estrae: Fornitore, Numero Fattura, Importo, Data. Questi dati vengono salvati come record PROVVISORIO in Archivio Fatture.',
              campi: ['is_bozza_email: true', 'source: "email"', 'provvisorio: true']
            },
            {
              nome: 'XML Sovrascrive Email (mantenendo scelta utente)',
              descrizione: 'Quando viene caricata la fattura XML, questa SOVRASCRIVE il dato provvisorio da email. Il match avviene su P.IVA + Numero Fattura. Se l\'utente ha già scelto un metodo di pagamento, questo viene MANTENUTO.',
              campi: ['metodo_pagamento_modificato_manualmente: true → viene preservato']
            },
            {
              nome: 'Metodo Pagamento Iniziale',
              descrizione: 'Il metodo di pagamento iniziale viene preso dal fornitore (metodo_pagamento_predefinito). L\'utente può sempre modificarlo manualmente.',
              campi: ['metodo_pagamento', 'metodo_pagamento_predefinito']
            }
          ]
        },
        {
          titolo: '4 Casi del Flusso Pagamento',
          regole: [
            {
              nome: 'CASO 1: Sistema registra, utente conferma',
              descrizione: 'Il sistema scarica la fattura, trova il metodo pagamento associato al fornitore, registra il movimento. L\'utente NON interviene → il sistema CONFERMA automaticamente l\'operazione.',
              campi: ['metodo_pagamento = fornitore.metodo_predefinito', 'provvisorio: true']
            },
            {
              nome: 'CASO 2: Sistema registra, utente cambia metodo',
              descrizione: 'Il sistema scarica la fattura, trova il metodo pagamento, registra. L\'utente INTERVIENE cambiando metodo (es. da Cassa a Banca). Il sistema sposta il movimento e CONFERMA l\'operazione.',
              campi: ['metodo_pagamento_modificato_manualmente: true', 'provvisorio: true']
            },
            {
              nome: 'CASO 3: Riconciliazione automatica con estratto conto',
              descrizione: 'L\'utente ha già modificato il metodo (magari messo "cassa" per errore). Successivamente viene caricato l\'estratto conto bancario. Il sistema trova l\'operazione in banca, la SPOSTA automaticamente da cassa a banca, e la rende NON MODIFICABILE (riconciliata).',
              campi: ['riconciliato: true', 'provvisorio: false', 'movimento_banca_riconciliato_id']
            },
            {
              nome: 'CASO 4: Forzatura con autorizzazione + avvisi incoerenza',
              descrizione: 'Se l\'utente tenta di modificare una fattura già riconciliata, il sistema BLOCCA l\'operazione. È possibile forzare la modifica con autorizzazione (viene loggata). Ogni volta che si legge l\'estratto conto, il sistema dà AVVISO se trova incoerenze (es. fattura in cassa ma pagamento trovato in banca).',
              campi: ['forza_modifica: true', 'motivo_forzatura', 'log_forzature', 'avvisi_incoerenza']
            }
          ]
        },
        {
          titolo: 'Blocchi e Autorizzazioni',
          regole: [
            {
              nome: 'Blocco Modifica Post-Riconciliazione',
              descrizione: 'Una volta riconciliata con l\'estratto conto, la fattura NON può più essere modificata. I pulsanti Cassa/Banca vengono disabilitati e mostrano badge "RICONCILIATA".',
              campi: ['riconciliato: true → pulsanti disabilitati']
            },
            {
              nome: 'Forzatura con Log',
              descrizione: 'In casi eccezionali, è possibile forzare la modifica fornendo una motivazione. L\'operazione viene loggata nella collection "log_forzature" per audit.',
              campi: ['forza_modifica: true', 'motivo_forzatura', 'timestamp']
            }
          ]
        }
      ]
    },
    {
      id: 'riconciliazione',
      titolo: '🔄 Riconciliazione Bancaria',
      icona: '🔄',
      colore: '#10b981',
      sottosezioni: [
        {
          titolo: 'Criteri di Match',
          regole: [
            {
              nome: 'Match per Importo + Beneficiario',
              descrizione: 'Il match bancario si basa PRINCIPALMENTE su: Nome fornitore/beneficiario e Importo. La DATA NON È OBBLIGATORIA perché un bonifico può essere emesso contestualmente, in anticipo o in differita rispetto alla fattura.',
              campi: ['importo (obbligatorio)', 'beneficiario/fornitore (obbligatorio)', 'data (opzionale)']
            },
            {
              nome: 'Match per Numero Fattura in Causale',
              descrizione: 'Se nella causale del bonifico è presente il numero della fattura, questo viene usato come criterio aggiuntivo per il match.',
              campi: ['causale → numero_fattura']
            },
            {
              nome: 'Tolleranza Importo',
              descrizione: 'È prevista una tolleranza sull\'importo per gestire piccole differenze (es. arrotondamenti, commissioni bancarie). Tolleranza: ±1€ o ±1% (il maggiore dei due).',
              campi: ['tolleranza_importo: max(1€, importo*1%)']
            }
          ]
        },
        {
          titolo: 'Verifica Incoerenze',
          regole: [
            {
              nome: 'Avvisi Automatici',
              descrizione: 'Ogni volta che viene caricato l\'estratto conto, il sistema verifica se ci sono incoerenze: fatture marcate "cassa" ma con pagamento trovato in banca, importi discordanti, ecc.',
              campi: ['GET /api/fatture-ricevute/verifica-incoerenze-estratto-conto']
            },
            {
              nome: 'Tipi di Incoerenza',
              descrizione: '1) Fattura in cassa ma trovata in estratto conto banca. 2) Importo fattura diverso da importo movimento banca. 3) Fattura non pagata ma movimento trovato in banca.',
              campi: ['INCOERENZA_METODO', 'INCOERENZA_IMPORTO', 'INCOERENZA_STATO']
            }
          ]
        },
        {
          titolo: 'Stato Post-Riconciliazione',
          regole: [
            {
              nome: 'Pagamento Definitivo',
              descrizione: 'Dopo la riconciliazione, il pagamento diventa DEFINITIVO e NON MODIFICABILE. I pulsanti Cassa/Banca vengono disabilitati.',
              campi: ['riconciliato: true', 'provvisorio: false', 'stato: "riconciliato"']
            },
            {
              nome: 'Collegamento Movimento Bancario',
              descrizione: 'Il pagamento viene collegato al movimento specifico dell\'estratto conto bancario.',
              campi: ['movimento_bancario_id', 'data_riconciliazione']
            }
          ]
        }
      ]
    },
    {
      id: 'corrispettivi',
      titolo: '🧾 Corrispettivi e POS',
      icona: '🧾',
      colore: '#f59e0b',
      sottosezioni: [
        {
          titolo: 'Dati Provvisori vs XML',
          regole: [
            {
              nome: 'Inserimento Manuale = Provvisorio',
              descrizione: 'Quando l\'utente inserisce manualmente i corrispettivi giornalieri e il POS, questi sono dati PROVVISORI per avere una stima anticipata del saldo cassa.',
              campi: ['source: "manual_entry"', 'source: "manual_pos"', 'provvisorio: true']
            },
            {
              nome: 'XML Sovrascrive per DATA',
              descrizione: 'Quando viene caricato il file XML dei corrispettivi telematici, questo SOVRASCRIVE i dati manuali. Il match avviene per DATA (non per matricola, che i dati manuali non hanno).',
              campi: ['data (chiave di match)', 'source: "xml"', 'provvisorio: false']
            },
            {
              nome: 'Unificazione POS',
              descrizione: 'Il dato POS è unificato in un solo campo (non più 3 campi separati). Rappresenta il totale incassi elettronici della giornata.',
              campi: ['pagato_elettronico', 'pos_totale']
            }
          ]
        }
      ]
    },
    {
      id: 'prima-nota',
      titolo: '📒 Prima Nota',
      icona: '📒',
      colore: '#8b5cf6',
      sottosezioni: [
        {
          titolo: '📚 REGOLE DI RAGIONERIA GENERALE',
          regole: [
            {
              nome: 'Principio della Partita Doppia',
              descrizione: 'Ogni operazione contabile deve essere registrata in DUE conti: uno in DARE e uno in AVERE. La somma dei DARE deve sempre essere uguale alla somma degli AVERE.',
              campi: ['DARE = AVERE (sempre)', 'Tolleranza: ±0.01€ per arrotondamenti']
            },
            {
              nome: 'Data del Movimento',
              descrizione: 'La data da usare è la DATA DOCUMENTO (data della fattura/verbale), NON la data di ricezione. Questo perché la competenza contabile è determinata dalla data dell\'operazione economica.',
              campi: ['✅ Data documento (corretta)', '❌ Data ricezione (ERRORE)']
            },
            {
              nome: 'DARE vs AVERE - Regola Base',
              descrizione: 'DARE = Entrate di denaro (incassi, rimborsi ricevuti, vendite). AVERE = Uscite di denaro (pagamenti, acquisti, spese). Un RIMBORSO RICEVUTO è un\'entrata → va in DARE!',
              campi: ['DARE: +Cassa, +Banca, +Crediti', 'AVERE: +Debiti, +Costi, -Cassa']
            },
            {
              nome: 'Tipi di Conti',
              descrizione: 'ATTIVO (aumenta in DARE): Cassa, Banca, Crediti. PASSIVO (aumenta in AVERE): Debiti, Capitale. COSTO (aumenta in DARE): Acquisti, Spese. RICAVO (aumenta in AVERE): Vendite, Prestazioni.',
              campi: ['Attivo: 1.x.x', 'Passivo: 3.x.x', 'Costo: 6.x.x', 'Ricavo: 7.x.x']
            }
          ]
        },
        {
          titolo: 'Struttura',
          regole: [
            {
              nome: 'Prima Nota Cassa',
              descrizione: 'Registra SOLO movimenti in contanti: Corrispettivi giornalieri, Incassi POS. NON inserire bonifici o operazioni bancarie!',
              campi: ['collection: prima_nota_cassa', 'tipo: entrata/uscita', 'Solo: Corrispettivi, POS']
            },
            {
              nome: 'Prima Nota Banca',
              descrizione: 'Registra tutti i movimenti bancari: bonifici in uscita (fornitori), bonifici in entrata, addebiti diretti, F24, stipendi. I dati provengono dall\'estratto conto importato.',
              campi: ['collection: estratto_conto_movimenti', 'tipo: entrata/uscita']
            },
            {
              nome: 'Collegamento Documenti',
              descrizione: 'Ogni movimento può essere collegato al documento di origine: Fattura, Corrispettivo XML, F24, Bonifico PDF.',
              campi: ['fattura_id', 'corrispettivo_id', 'f24_id', 'bonifico_pdf_id', 'xml_filename']
            }
          ]
        },
        {
          titolo: '⚠️ REGOLA IMPORTAZIONE ESTRATTO CONTO',
          regole: [
            {
              nome: 'Estratto Conto → SOLO Prima Nota Banca',
              descrizione: 'L\'estratto conto bancario deve essere importato ESCLUSIVAMENTE nella collection estratto_conto_movimenti, che alimenta la Prima Nota Banca. NON deve MAI essere importato in Prima Nota Cassa.',
              campi: ['✅ estratto_conto_movimenti (corretto)', '❌ prima_nota_cassa (ERRORE)']
            },
            {
              nome: 'Prima Nota Cassa - Contenuto Corretto',
              descrizione: 'Prima Nota Cassa deve contenere SOLO: Corrispettivi XML (incassi giornalieri), POS (incassi elettronici). I pagamenti fornitori in contanti sono rari e da inserire manualmente.',
              campi: ['✅ Corrispettivi', '✅ POS', '❌ Bonifici', '❌ F24', '❌ Stipendi']
            },
            {
              nome: 'Correzione Errori',
              descrizione: 'Se sono stati importati erroneamente movimenti bancari in Prima Nota Cassa, usare l\'endpoint: DELETE /api/prima-nota/cassa/elimina-movimenti-bancari-errati',
              campi: ['DELETE /api/prima-nota/cassa/elimina-movimenti-bancari-errati']
            }
          ]
        },
        {
          titolo: '🔄 Motore Contabile (Partita Doppia)',
          regole: [
            {
              nome: 'Piano dei Conti Italiano',
              descrizione: 'Il sistema usa un piano dei conti semplificato per PMI conforme alla normativa italiana. Ogni conto ha un codice (es. 1.1.1 = Cassa contanti) e un tipo (attivo/passivo/costo/ricavo).',
              campi: ['GET /api/accounting-engine/piano-conti']
            },
            {
              nome: 'Validazione Automatica',
              descrizione: 'Ogni operazione viene validata automaticamente: verifica DARE=AVERE, verifica data documento, verifica conto corretto per il tipo di operazione.',
              campi: ['POST /api/accounting-engine/valida-operazione']
            },
            {
              nome: 'Storno Operazioni',
              descrizione: 'Le operazioni sono REVERSIBILI tramite storno. Invece di cancellare, si crea una scrittura inversa che annulla l\'effetto contabile. Questo garantisce la tracciabilità completa.',
              campi: ['POST /api/accounting-engine/storna-operazione/{id}']
            }
          ]
        },
        {
          titolo: 'Visualizzazione Documenti',
          regole: [
            {
              nome: 'Pulsante Documento',
              descrizione: 'Ogni movimento mostra un pulsante per visualizzare il documento collegato in formato leggibile.',
              campi: ['📄 Fattura (blu)', '🧾 Corrispettivo (verde)', '📎 Bonifico (viola)', '🏛️ F24 (rosso)']
            }
          ]
        }
      ]
    },
    {
      id: 'fornitori',
      titolo: '👥 Anagrafica Fornitori',
      icona: '👥',
      colore: '#ec4899',
      sottosezioni: [
        {
          titolo: 'Dizionario Metodi Pagamento',
          regole: [
            {
              nome: 'Quando SI AGGIORNA il dizionario',
              descrizione: 'Il metodo di pagamento del fornitore viene aggiornato SOLO in questi casi: 1) Riconciliazione pagamenti 2) Caricamento nuovo estratto conto 3) Creazione nuovo fornitore 4) Aggiornamento diretto fornitore 5) Eliminazione fornitore senza fatture.',
              campi: ['source: riconciliazione', 'source: estratto_conto', 'source: nuovo_fornitore', 'source: aggiornamento_fornitore']
            },
            {
              nome: 'Quando NON SI AGGIORNA il dizionario',
              descrizione: 'Il metodo di pagamento cambiato su una singola fattura (da Prima Nota Cassa, Prima Nota Banca o Ciclo Passivo) NON modifica MAI il dizionario e NON modifica MAI il fornitore. La modifica resta solo sulla fattura specifica.',
              campi: ['Prima Nota Cassa → NO UPDATE', 'Prima Nota Banca → NO UPDATE', 'Ciclo Passivo → NO UPDATE']
            }
          ]
        },
        {
          titolo: 'Estratto Fatture Fornitore',
          regole: [
            {
              nome: 'Visualizzazione dalla Scheda Fornitore',
              descrizione: 'Cliccando su "Fatture" nella scheda fornitore si apre un modale con l\'estratto completo delle fatture ricevute e note credito. Include il metodo di pagamento per ogni documento (per controllo cartaceo).',
              campi: ['GET /api/suppliers/{id}/fatture']
            },
            {
              nome: 'Filtri Disponibili',
              descrizione: 'L\'estratto può essere filtrato per: Anno, Data Da/A, Importo Min/Max, Tipo documento (Fatture, Note Credito, Tutti).',
              campi: ['anno', 'data_da', 'data_a', 'importo_min', 'importo_max', 'tipo']
            }
          ]
        },
        {
          titolo: 'Configurazione',
          regole: [
            {
              nome: 'Metodo Pagamento Predefinito',
              descrizione: 'Ogni fornitore ha un metodo di pagamento predefinito (bonifico, cassa, rid, assegno, ecc.). Questo viene usato come default quando si importa una nuova fattura.',
              campi: ['metodo_pagamento_predefinito', 'iban', 'termini_pagamento']
            },
            {
              nome: 'IBAN Obbligatorio per Bonifici',
              descrizione: 'Se il metodo predefinito è "bonifico" o simile, l\'IBAN del fornitore è obbligatorio per poter emettere il pagamento.',
              campi: ['iban', 'bic_swift']
            },
            {
              nome: 'Creazione Automatica',
              descrizione: 'Quando si importa una fattura XML con un fornitore sconosciuto, questo viene creato automaticamente in anagrafica con i dati estratti dalla fattura.',
              campi: ['fornitore_nuovo: true']
            }
          ]
        }
      ]
    },
    {
      id: 'scadenziario',
      titolo: '📅 Scadenziario',
      icona: '📅',
      colore: '#06b6d4',
      sottosezioni: [
        {
          titolo: 'Gestione Scadenze',
          regole: [
            {
              nome: 'Calcolo Data Scadenza',
              descrizione: 'La data di scadenza viene calcolata dalla data fattura + termini di pagamento del fornitore (es. 30gg, 60gg, fine mese).',
              campi: ['data_fattura + termini_pagamento = data_scadenza']
            },
            {
              nome: 'Stati Scadenza',
              descrizione: 'Una scadenza può essere: in_attesa, in_scadenza (prossimi 7gg), scaduta, pagata.',
              campi: ['stato: in_attesa | in_scadenza | scaduta | pagato']
            },
            {
              nome: 'Collegamento Pagamento',
              descrizione: 'Quando la fattura viene pagata, la scadenza viene marcata come "pagato" con riferimento al movimento di pagamento.',
              campi: ['stato: pagato', 'movimento_id', 'data_pagamento']
            }
          ]
        }
      ]
    },
    {
      id: 'verbali',
      titolo: '🚗 Verbali Noleggio (Multas)',
      icona: '🚗',
      colore: '#dc2626',
      sottosezioni: [
        {
          titolo: 'Flusso Riconciliazione Verbali',
          regole: [
            {
              nome: 'Scenario A: Pago Prima della Fattura',
              descrizione: '1) Driver trova verbale sul parabrezza. 2) Pago subito (prima che arrivi la fattura dal noleggiatore). 3) Scarico il verbale da email/posta → Salvo. 4) Arriva fattura noleggiatore (es. ALD) con numero verbale → Associo. 5) Riconcilio: Verbale + Fattura + Pagamento.',
              campi: ['stato: pagato → fattura_ricevuta → riconciliato']
            },
            {
              nome: 'Scenario B: Fattura Prima del Pagamento',
              descrizione: '1) Arriva fattura noleggiatore (es. ALD €35 spese notifica). 2) Estraggo numero verbale dalla descrizione fattura. 3) Cerco/scarico verbale originale da email. 4) Pago il verbale. 5) Riconcilio: Fattura + Verbale + Pagamento.',
              campi: ['stato: fattura_ricevuta → pagato → riconciliato']
            },
            {
              nome: 'Differenza Multa vs Spese Notifica',
              descrizione: 'IMPORTANTE: La fattura del noleggiatore (es. €35) NON è la multa! È solo il costo di "rinotifica" che il noleggiatore addebita. Il verbale vero è un documento separato con importo diverso (es. €80, €150, ecc.).',
              campi: ['Fattura noleggiatore = spese notifica (€35)', 'Verbale = multa vera (importo variabile)']
            }
          ]
        },
        {
          titolo: 'Stati del Verbale',
          regole: [
            {
              nome: 'Stati Progressivi',
              descrizione: 'Un verbale passa attraverso questi stati durante il suo ciclo di vita.',
              campi: ['da_scaricare → salvato → fattura_ricevuta → pagato → riconciliato']
            },
            {
              nome: 'da_scaricare',
              descrizione: 'Verbale identificato (es. da email) ma PDF non ancora scaricato/salvato nel sistema.',
              campi: ['stato: da_scaricare']
            },
            {
              nome: 'salvato',
              descrizione: 'PDF del verbale scaricato e salvato. In attesa di fattura noleggiatore o pagamento.',
              campi: ['stato: salvato', 'pdf_id']
            },
            {
              nome: 'fattura_ricevuta',
              descrizione: 'Fattura del noleggiatore associata. Il numero verbale è stato estratto dalla descrizione fattura.',
              campi: ['stato: fattura_ricevuta', 'fattura_id', 'fattura_numero']
            },
            {
              nome: 'pagato',
              descrizione: 'Pagamento del verbale registrato (trovato in estratto conto o registrato manualmente).',
              campi: ['stato: pagato', 'pagamento_id', 'data_pagamento', 'importo']
            },
            {
              nome: 'riconciliato',
              descrizione: 'Ciclo completo: Verbale + Fattura noleggiatore + Pagamento + Veicolo + Driver tutti collegati.',
              campi: ['stato: riconciliato', 'driver_id', 'veicolo_id', 'targa']
            }
          ]
        },
        {
          titolo: 'Catena di Associazione',
          regole: [
            {
              nome: 'Verbale → Fattura → Veicolo → Driver',
              descrizione: 'La riconciliazione completa collega: 1) Numero verbale nella fattura. 2) Targa veicolo nella fattura. 3) Veicolo in anagrafica noleggio. 4) Driver assegnato al veicolo alla data del verbale.',
              campi: ['numero_verbale', 'targa', 'veicolo_id', 'driver_id', 'driver_nome']
            },
            {
              nome: 'Estrazione Automatica',
              descrizione: 'Il sistema estrae automaticamente: numero verbale e targa dalla descrizione delle fatture noleggiatori (ALD, ARVAL, LEASYS, ecc.).',
              campi: ['Pattern verbale: A25111540620, B23123049750', 'Pattern targa: GE911SC, GX037HJ']
            }
          ]
        },
        {
          titolo: 'Collections MongoDB',
          regole: [
            {
              nome: 'verbali_noleggio',
              descrizione: 'Collection principale con tutti i verbali e il loro stato di riconciliazione.',
              campi: ['collection: verbali_noleggio']
            },
            {
              nome: 'verbali_noleggio_completi',
              descrizione: 'Collection di staging con verbali completi scaricati da email. Deve essere sincronizzata con verbali_noleggio.',
              campi: ['collection: verbali_noleggio_completi', 'sync → verbali_noleggio']
            }
          ]
        }
      ]
    }
  ];

  const cardStyle = {
    background: 'white',
    borderRadius: 12,
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    overflow: 'hidden',
    marginBottom: 16
  };

  const headerStyle = (colore) => ({
    padding: '16px 20px',
    background: `linear-gradient(135deg, ${colore}, ${colore}dd)`,
    color: 'white',
    cursor: 'pointer',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    transition: 'all 0.2s'
  });

  const contentStyle = {
    padding: 20,
    background: '#f8fafc'
  };

  const sottosezioneStyle = {
    background: 'white',
    borderRadius: 8,
    padding: 16,
    marginBottom: 12,
    border: '1px solid #e2e8f0'
  };

  const regolaStyle = {
    padding: '12px 0',
    borderBottom: '1px solid #f1f5f9'
  };

  const badgeStyle = (bg) => ({
    display: 'inline-block',
    padding: '2px 8px',
    background: bg,
    color: '#374151',
    borderRadius: 4,
    fontSize: 11,
    fontFamily: 'monospace',
    marginRight: 6,
    marginTop: 4
  });

  return (
    <PageLayout title="Dizionario Regole Contabili" subtitle="Documentazione completa delle logiche di business implementate nel sistema gestionale">
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, color: '#1535a8', marginBottom: 8 }}>
          📚 Dizionario Regole Contabili
        </h1>
        <p style={{ color: '#64748b', fontSize: 14, lineHeight: 1.6 }}>
          Documentazione completa delle logiche di business implementate nel sistema gestionale.
          Clicca su una sezione per espanderla.
        </p>
      </div>

      {/* Info Box */}
      <div style={{ 
        background: 'linear-gradient(135deg, #dbeafe, #ede9fe)', 
        padding: 16, 
        borderRadius: 12, 
        marginBottom: 24,
        border: '1px solid #c7d2fe'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 24 }}>💡</span>
          <div>
            <strong style={{ color: '#4338ca' }}>Principio Fondamentale</strong>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: '#4f46e5' }}>
              I dati manuali o da email sono sempre <strong>PROVVISORI</strong>. 
              La <strong>fonte di verità</strong> è sempre il documento ufficiale (XML fattura, estratto conto).
              La scelta dell'utente sul metodo di pagamento viene sempre <strong>preservata</strong>.
            </p>
          </div>
        </div>
      </div>

      {/* Sezioni */}
      {regole.map((sezione) => (
        <div key={sezione.id} style={cardStyle}>
          <div 
            style={headerStyle(sezione.colore)}
            onClick={() => toggleSection(sezione.id)}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ fontSize: 24 }}>{sezione.icona}</span>
              <span style={{ fontSize: 18, fontWeight: 600 }}>{sezione.titolo}</span>
            </div>
            <span style={{ fontSize: 20, transition: 'transform 0.2s', transform: expandedSection === sezione.id ? 'rotate(180deg)' : 'rotate(0deg)' }}>
              ▼
            </span>
          </div>

          {expandedSection === sezione.id && (
            <div style={contentStyle}>
              {sezione.sottosezioni.map((sotto, idx) => (
                <div key={idx} style={sottosezioneStyle}>
                  <h3 style={{ fontSize: 14, fontWeight: 600, color: '#475569', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    {sotto.titolo}
                  </h3>
                  {sotto.regole.map((regola, ridx) => (
                    <div key={ridx} style={regolaStyle}>
                      <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: 4 }}>
                        {regola.nome}
                      </div>
                      <p style={{ fontSize: 13, color: '#64748b', lineHeight: 1.5, marginBottom: 8 }}>
                        {regola.descrizione}
                      </p>
                      <div>
                        {regola.campi.map((campo, cidx) => (
                          <span key={cidx} style={badgeStyle('#f1f5f9')}>
                            {campo}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {/* Footer Note */}
      <div style={{ 
        marginTop: 32, 
        padding: 16, 
        background: '#fefce8', 
        borderRadius: 12,
        border: '1px solid #fef08a'
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <span style={{ fontSize: 20 }}>📝</span>
          <div style={{ fontSize: 13, color: '#854d0e', lineHeight: 1.6 }}>
            <strong>Note per lo sviluppo:</strong><br/>
            Questa documentazione viene aggiornata man mano che nuove funzionalità vengono implementate.
            Per modifiche alle regole di business, contattare l'amministratore del sistema.
          </div>
        </div>
      </div>
    </div>
    </PageLayout>
  );
}
