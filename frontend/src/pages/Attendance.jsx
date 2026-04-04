/**
 * Attendance.jsx
 * 
 * Sistema di gestione presenze dipendenti con vista calendario.
 * Features:
 * - Vista calendario mensile/settimanale
 * - Click rapido per cambiare stato presenza
 * - Gestione ferie, permessi, malattie
 * - Storico ore lavorate
 */

import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { 
  ChevronLeft, ChevronRight, RefreshCw, Plus, Calendar,
  Users, Clock, FileText, History, Settings, Check, X, FileDown
} from 'lucide-react';
import { toast } from 'sonner';
import { STYLES, COLORS, button, badge, formatEuro, formatDateIT } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';

// Importa costanti e helpers dal modulo attendance
import { 
  STATI_PRESENZA, 
  GIORNI_SETTIMANA, 
  MESI, 
  MANSIONI_DEFAULT 
} from '../components/attendance/constants';
import { 
  isDipendenteCessato, 
  isDipendenteVisibileNelMese, 
  formatDate 
} from '../components/attendance/helpers';

// Importa componenti estratti


export default function Attendance() {
  const { anno: annoGlobale } = useAnnoGlobale();
  const [loading, setLoading] = useState(true);
  const [employees, setEmployees] = useState([]);
  const [presenze, setPresenze] = useState({}); // { "employeeId_YYYY-MM-DD": "presente" }
  const [activeTab, setActiveTab] = useState('calendario');
  const [viewMode, setViewMode] = useState('mensile'); // mensile | settimanale
  
  // Data corrente per calendario - usa anno dal context
  const [currentDate, setCurrentDate] = useState(() => new Date(annoGlobale, new Date().getMonth(), 1));
  const currentYear = currentDate.getFullYear();
  const currentMonth = currentDate.getMonth();
  
  // Storico Ore
  const [storicoEmployee, setStoricoEmployee] = useState('');
  const [storicoData, setStoricoData] = useState(null);
  const [loadingStorico, setLoadingStorico] = useState(false);
  
  // Richieste pending
  const [richiestePending, setRichiestePending] = useState([]);
  
  // === SELEZIONE MULTIPLA ===
  const [selectedStato, setSelectedStato] = useState(null); // Stato selezionato per inserimento rapido
  const [multiSelectMode, setMultiSelectMode] = useState(false);
  const [selectedCells, setSelectedCells] = useState(new Set()); // Celle selezionate
  const [rangeStart, setRangeStart] = useState(null); // Inizio selezione range
  const [rangeSelectMode, setRangeSelectMode] = useState(false); // Modalità selezione range
  
  // Note presenze (protocolli malattia, etc.)
  const [notePresenze, setNotePresenze] = useState({}); // { "employeeId_YYYY-MM-DD": { protocollo: "xxx", note: "..." } }
  
  // Generazione PDF
  const [generatingPdf, setGeneratingPdf] = useState(false);

  // === MENU CONTESTUALE PER CAMBIO GIUSTIFICATIVO ===
  const [menuCella, setMenuCella] = useState({ open: false, x: 0, y: 0, employeeId: null, dateStr: null });

  // === FORM INSERIMENTO RAPIDO CON RANGE ===
  const [formRapido, setFormRapido] = useState({
    dipendente: '',
    dataDa: '',
    dataA: '',
    giustificativo: ''
  });
  const [inserendoRapido, setInserendoRapido] = useState(false);

  // Calcola giorni del mese
  const getDaysInMonth = (year, month) => {
    return new Date(year, month + 1, 0).getDate();
  };
  
  const daysInMonth = getDaysInMonth(currentYear, currentMonth);
  
  // Genera array di giorni
  const days = Array.from({ length: daysInMonth }, (_, i) => {
    const date = new Date(currentYear, currentMonth, i + 1);
    return {
      day: i + 1,
      dayOfWeek: date.getDay(),
      isWeekend: date.getDay() === 0, // Solo domenica è weekend (sabato lavorativo)
      isSabato: date.getDay() === 6, // Sabato è lavorativo ma evidenziato
      dateStr: `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(i + 1).padStart(2, '0')}`
    };
  });

  // Carica dati
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      
      const [empRes, presenzeRes, pendingRes] = await Promise.all([
        api.get('/api/employees?limit=200'),
        api.get(`/api/attendance/presenze-mese?anno=${currentYear}&mese=${currentMonth + 1}`),
        api.get('/api/attendance/richieste-pending')
      ]);
      
      // Normalizza employees - filtra solo attivi E in_carico E visibili nel mese corrente
      const emps = (empRes.data.employees || empRes.data || [])
        .filter(e => (e.status === 'attivo' || !e.status) && (e.in_carico !== false))
        .filter(e => isDipendenteVisibileNelMese(e, currentYear, currentMonth))
        .map(e => ({
          ...e,
          nome_completo: e.nome_completo || e.name || `${e.nome || ''} ${e.cognome || ''}`.trim()
        }));
      setEmployees(emps);
      
      // Carica presenze del mese
      if (presenzeRes.data.presenze) {
        setPresenze(presenzeRes.data.presenze);
      }
      
      setRichiestePending(pendingRes.data.richieste || []);
      
    } catch (error) {
      console.error('Errore caricamento:', error);
      // Se l'endpoint presenze-mese non esiste, ignora
    } finally {
      setLoading(false);
    }
  }, [currentYear, currentMonth]);

  // Quando l'anno globale cambia, aggiorna currentDate
  useEffect(() => {
    setCurrentDate(new Date(annoGlobale, currentMonth, 1));
  }, [annoGlobale]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Cambia stato presenza (click su cella)
  const handleCellClick = async (employeeId, dateStr, currentState, event) => {
    // Apre il menu contestuale per selezionare il giustificativo
    const rect = event?.target?.getBoundingClientRect();
    const x = rect ? rect.left : event?.clientX || 100;
    const y = rect ? rect.bottom : event?.clientY || 100;
    
    setMenuCella({
      open: true,
      x,
      y,
      employeeId,
      dateStr,
      currentState
    });
  };

  // Funzione per applicare il giustificativo selezionato dal menu
  const applyGiustificativo = async (nuovoStato) => {
    const { employeeId, dateStr, currentState } = menuCella;
    setMenuCella({ open: false, x: 0, y: 0, employeeId: null, dateStr: null });
    
    if (nuovoStato === currentState) return;
    
    // Mappa stato presenza a codice giustificativo
    const mappaGiustificativi = {
      'ferie': 'FER',
      'permesso': 'PER',
      'malattia': 'MAL',
      'rol': 'ROL',
      'assente': 'AI'
    };
    
    const codiceGiustificativo = mappaGiustificativi[nuovoStato];
    
    // Se è un giustificativo con limite, valida prima
    if (codiceGiustificativo) {
      try {
        const validazione = await api.post('/api/giustificativi/valida-giustificativo', {
          employee_id: employeeId,
          codice_giustificativo: codiceGiustificativo,
          data: dateStr,
          ore: 8
        });
        
        if (!validazione.data.valido) {
          toast.error(`⛔ ${validazione.data.messaggio}`);
          return;
        }
        
        if (validazione.data.warnings?.length > 0) {
          toast.warning(validazione.data.warnings[0]);
        }
      } catch (err) {
        console.error('Errore validazione giustificativo:', err);
      }
    }
    
    // Aggiorna UI ottimisticamente
    const key = `${employeeId}_${dateStr}`;
    setPresenze(prev => ({ ...prev, [key]: nuovoStato }));
    
    // Salva nel backend
    try {
      await api.post('/api/attendance/set-presenza', {
        employee_id: employeeId,
        data: dateStr,
        stato: nuovoStato
      });
      
      const emp = employees.find(e => e.id === employeeId);
      const nomeStato = STATI_PRESENZA[nuovoStato]?.name || nuovoStato;
      toast.success(`✓ ${emp?.nome || ''} ${emp?.cognome || ''}: ${nomeStato}`);
    } catch (error) {
      setPresenze(prev => ({ ...prev, [key]: currentState }));
      toast.error('Errore salvataggio');
    }
  };

  // === SELEZIONE MULTIPLA: Click su cella in modalità selezione rapida ===
  const handleMultiSelectClick = async (employeeId, dateStr, event) => {
    if (!selectedStato) return;
    
    // Se SHIFT è premuto e c'è un range start, applica a tutto il range
    if (event?.shiftKey && rangeStart) {
      const startDay = parseInt(rangeStart.split('-')[2]);
      const endDay = parseInt(dateStr.split('-')[2]);
      const minDay = Math.min(startDay, endDay);
      const maxDay = Math.max(startDay, endDay);
      
      toast.info(`Applico ${STATI_PRESENZA[selectedStato]?.name} dal ${minDay} al ${maxDay}...`);
      
      for (let d = minDay; d <= maxDay; d++) {
        const dayDateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
        const dayOfWeek = new Date(currentYear, currentMonth, d).getDay();
        
        // Salta domeniche (0) ma includi sabato (6)
        if (dayOfWeek === 0) continue;
        
        const key = `${employeeId}_${dayDateStr}`;
        setPresenze(prev => ({ ...prev, [key]: selectedStato }));
        
        // Salva nel backend
        try {
          await api.post('/api/attendance/set-presenza', {
            employee_id: employeeId,
            data: dayDateStr,
            stato: selectedStato
          });
        } catch (err) {
          console.error('Errore salvataggio:', err);
        }
      }
      
      toast.success(`✅ Applicato a ${maxDay - minDay + 1} giorni`);
      setRangeStart(null);
      return;
    }
    
    // Imposta come inizio range per prossimo click con SHIFT
    setRangeStart(dateStr);
    
    const key = `${employeeId}_${dateStr}`;
    const currentState = presenze[key];
    
    // Se lo stato è già quello selezionato, rimuovi (torna a riposo)
    const newState = currentState === selectedStato ? 'riposo' : selectedStato;
    
    // Mappa stato presenza a codice giustificativo per validazione
    const mappaGiustificativi = {
      'ferie': 'FER',
      'permesso': 'PER',
      'malattia': 'MAL',
      'rol': 'ROL',
      'assente': 'AI'
    };
    
    const codiceGiustificativo = mappaGiustificativi[newState];
    
    // Se è un giustificativo con limite, valida prima
    if (codiceGiustificativo && newState !== 'riposo') {
      try {
        const validazione = await api.post('/api/giustificativi/valida-giustificativo', {
          employee_id: employeeId,
          codice_giustificativo: codiceGiustificativo,
          data: dateStr,
          ore: 8
        });
        
        if (!validazione.data.valido) {
          toast.error(`⛔ ${validazione.data.messaggio}`);
          return;
        }
      } catch (err) {
        console.error('Errore validazione:', err);
      }
    }
    
    // Aggiorna UI
    setPresenze(prev => ({ ...prev, [key]: newState }));
    
    // Salva nel backend
    try {
      await api.post('/api/attendance/set-presenza', {
        employee_id: employeeId,
        data: dateStr,
        stato: newState
      });
      
      // Se è malattia, apri dialog per protocollo
      if (newState === 'malattia') {
        const protocollo = prompt('Inserisci numero protocollo certificato medico (opzionale):');
        if (protocollo) {
          setNotePresenze(prev => ({
            ...prev,
            [key]: { ...prev[key], protocollo_malattia: protocollo }
          }));
          // Salva nota nel backend
          await api.post('/api/attendance/set-nota-presenza', {
            employee_id: employeeId,
            data: dateStr,
            protocollo_malattia: protocollo
          }).catch(() => {});
        }
      }
    } catch (error) {
      setPresenze(prev => ({ ...prev, [key]: currentState }));
      toast.error('Errore salvataggio');
    }
  };

  // Attiva/disattiva modalità selezione rapida
  const toggleMultiSelectMode = (stato) => {
    if (selectedStato === stato) {
      // Disattiva
      setSelectedStato(null);
      setMultiSelectMode(false);
      toast.info('Modalità selezione rapida disattivata');
    } else {
      // Attiva
      setSelectedStato(stato);
      setMultiSelectMode(true);
      toast.success(`Modalità ${STATI_PRESENZA[stato]?.name} attivata - Clicca sulle celle per applicare`);
    }
  };

  // === INSERIMENTO RAPIDO CON RANGE DATE ===
  const handleInserimentoRapido = async () => {
    const { dipendente, dataDa, dataA, giustificativo } = formRapido;
    
    if (!dipendente || !dataDa || !dataA || !giustificativo) {
      toast.error('Compila tutti i campi');
      return;
    }
    
    const from = new Date(dataDa);
    const to = new Date(dataA);
    
    if (from > to) {
      toast.error('La data "Da" deve essere precedente a "A"');
      return;
    }
    
    setInserendoRapido(true);
    
    try {
      // Trova il dipendente per controllare i giorni lavorativi
      const emp = employees.find(e => e.id === dipendente);
      // Giorni lavorativi: array di numeri (0=dom, 1=lun, ..., 6=sab)
      // Default: lun-ven (1,2,3,4,5), ma se ha giorni_lavoro usa quelli
      let giorniLavorativi = [1, 2, 3, 4, 5]; // Default lun-ven
      
      if (emp?.giorni_lavoro && Array.isArray(emp.giorni_lavoro)) {
        // Converte array di stringhe in numeri
        const mapGiorni = { 'dom': 0, 'lun': 1, 'mar': 2, 'mer': 3, 'gio': 4, 'ven': 5, 'sab': 6 };
        giorniLavorativi = emp.giorni_lavoro.map(g => mapGiorni[g.toLowerCase()] ?? -1).filter(n => n >= 0);
      } else if (emp?.lavora_sabato || emp?.sabato) {
        // Se ha flag lavora_sabato, aggiungi sabato
        giorniLavorativi = [1, 2, 3, 4, 5, 6];
      } else if (emp?.lavora_domenica || emp?.domenica) {
        giorniLavorativi = [0, 1, 2, 3, 4, 5];
      }
      
      const giorniDaInserire = [];
      let current = new Date(from);
      
      while (current <= to) {
        const dow = current.getDay();
        // Inserisce solo se è un giorno lavorativo per questo dipendente
        if (giorniLavorativi.includes(dow)) {
          giorniDaInserire.push(current.toISOString().slice(0, 10));
        }
        current.setDate(current.getDate() + 1);
      }
      
      if (giorniDaInserire.length === 0) {
        toast.warning('Nessun giorno lavorativo nel range selezionato');
        setInserendoRapido(false);
        return;
      }
      
      // Aggiorna UI
      for (const dateStr of giorniDaInserire) {
        const key = `${dipendente}_${dateStr}`;
        setPresenze(prev => ({ ...prev, [key]: giustificativo }));
      }
      
      // Salva nel backend con batch
      await api.post('/api/attendance/batch-insert', {
        employee_id: dipendente,
        giorni: giorniDaInserire,
        stato: giustificativo
      });
      
      const nomeCompleto = emp ? `${emp.nome || ''} ${emp.cognome || ''}`.trim() : 'dipendente';
      toast.success(`✅ Inserite ${giorniDaInserire.length} ${STATI_PRESENZA[giustificativo]?.name || giustificativo} per ${nomeCompleto}`);
      
      // Reset form
      setFormRapido({ dipendente: '', dataDa: '', dataA: '', giustificativo: '' });
      
    } catch (error) {
      console.error('Errore inserimento rapido:', error);
      toast.error('Errore inserimento. I dati sono stati salvati localmente.');
    } finally {
      setInserendoRapido(false);
    }
  };

  // === GENERAZIONE PDF PER CONSULENTE ===
  const generatePdfConsulente = async () => {
    try {
      setGeneratingPdf(true);
      toast.info('Generazione PDF in corso...');
      
      const response = await api.post('/api/attendance/genera-pdf-consulente', {
        anno: currentYear,
        mese: currentMonth + 1
      }, { responseType: 'blob' });
      
      // Download file
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `Presenze_${MESI[currentMonth]}_${currentYear}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      
      toast.success('PDF generato con successo!');
    } catch (error) {
      console.error('Errore generazione PDF:', error);
      toast.error('Errore nella generazione del PDF');
    } finally {
      setGeneratingPdf(false);
    }
  };

  // Naviga mese
  const navigateMonth = (delta) => {
    setCurrentDate(prev => new Date(prev.getFullYear(), prev.getMonth() + delta, 1));
  };

  // Carica storico ore
  const loadStoricoOre = async () => {
    if (!storicoEmployee) {
      toast.error('Seleziona un dipendente');
      return;
    }
    
    try {
      setLoadingStorico(true);
      const res = await api.get(`/api/attendance/ore-lavorate/${storicoEmployee}?mese=${currentMonth + 1}&anno=${currentYear}`);
      setStoricoData(res.data);
    } catch (error) {
      console.error('Errore caricamento storico:', error);
      toast.error('Errore caricamento storico ore');
    } finally {
      setLoadingStorico(false);
    }
  };

  // Approva richiesta
  const handleApprova = async (richiestaId) => {
    try {
      const res = await api.put(`/api/attendance/richiesta-assenza/${richiestaId}/approva`);
      if (res.data.success) {
        toast.success('Richiesta approvata');
        loadData();
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Errore approvazione');
    }
  };

  // Rifiuta richiesta
  const handleRifiuta = async (richiestaId) => {
    const motivo = prompt('Motivo del rifiuto:');
    if (!motivo) return;
    
    try {
      const res = await api.put(`/api/attendance/richiesta-assenza/${richiestaId}/rifiuta`, { motivo });
      if (res.data.success) {
        toast.success('Richiesta rifiutata');
        loadData();
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Errore');
    }
  };

  // Calcola statistiche dipendente - conta ogni stato e giorni retribuiti
  const getEmployeeStats = (employeeId) => {
    // Contatori per ogni stato
    const counts = {
      presente: 0,
      assente: 0,
      ferie: 0,
      permesso: 0,
      malattia: 0,
      rol: 0,
      chiuso: 0,
      riposo_settimanale: 0,
      trasferta: 0,
      cessato: 0,
      riposo: 0,
      festivita_lavorata: 0,
      festivita_non_lavorata: 0
    };
    
    days.forEach(d => {
      const key = `${employeeId}_${d.dateStr}`;
      const stato = presenze[key];
      if (stato && counts.hasOwnProperty(stato)) {
        counts[stato]++;
      }
    });
    
    // Giorni RETRIBUITI: Presente, Ferie, Permesso, Malattia, ROL, Trasferta, Festività Lavorata, Festività Non Lavorata
    // NON retribuiti: Assente (ingiustificato), Chiuso, Riposo Sett., Riposo, Cessato
    const giorniRetribuiti = counts.presente + counts.ferie + counts.permesso + 
                             counts.malattia + counts.rol + counts.trasferta + 
                             counts.festivita_lavorata + counts.festivita_non_lavorata;
    
    return { ...counts, giorniRetribuiti };
  };

  // Rendering cella - versione compatta
  const renderCell = (employee, day) => {
    const key = `${employee.id}_${day.dateStr}`;
    
    // Verifica se il dipendente è cessato in questa data
    const cessato = isDipendenteCessato(employee, day.dateStr);
    
    // Se cessato, mostra "X" e non permette modifica
    if (cessato) {
      const cessatoConfig = STATI_PRESENZA.cessato;
      return (
        <td
          key={day.day}
          style={{
            width: 22,
            height: 20,
            padding: 0,
            textAlign: 'center',
            cursor: 'not-allowed',
            background: cessatoConfig.bg,
            borderRight: '1px solid #e5e7eb',
            borderBottom: '1px solid #e5e7eb',
            fontSize: 8,
            fontWeight: 600,
            color: cessatoConfig.color,
          }}
          title={`${employee.nome_completo} - Contratto cessato`}
          data-testid={`cell-${employee.id}-${day.day}`}
        >
          {cessatoConfig.label}
        </td>
      );
    }
    
    const stato = presenze[key] || (day.isWeekend ? 'riposo' : null);
    const config = stato ? STATI_PRESENZA[stato] : null;
    const nota = notePresenze[key];
    
    // Determina se la cella è selezionata (in modalità multi-select)
    const isHighlighted = multiSelectMode && selectedStato && stato === selectedStato;
    
    return (
      <td
        key={day.day}
        onClick={(e) => multiSelectMode ? handleMultiSelectClick(employee.id, day.dateStr, e) : handleCellClick(employee.id, day.dateStr, stato, e)}
        style={{
          width: 22,
          height: 20,
          padding: 0,
          textAlign: 'center',
          cursor: multiSelectMode ? 'crosshair' : 'pointer',
          background: config ? config.bg : (day.isWeekend ? '#f3f4f6' : 'white'),
          borderRight: '1px solid #e5e7eb',
          borderBottom: '1px solid #e5e7eb',
          fontSize: 8,
          fontWeight: 600,
          color: config ? config.color : '#d1d5db',
          transition: 'all 0.1s ease',
          userSelect: 'none',
          outline: isHighlighted ? '2px solid #3b82f6' : 'none',
          outlineOffset: '-2px',
          position: 'relative'
        }}
        title={`${employee.nome_completo} - ${day.day}/${currentMonth + 1}: ${config?.name || 'Non definito'}${nota?.protocollo_malattia ? ` (Prot: ${nota.protocollo_malattia})` : ''}`}
        data-testid={`cell-${employee.id}-${day.day}`}
      >
        {config?.label || '-'}
        {nota?.protocollo_malattia && (
          <span style={{
            position: 'absolute',
            top: -2,
            right: -2,
            width: 6,
            height: 6,
            background: '#ef4444',
            borderRadius: '50%'
          }} title={`Prot: ${nota.protocollo_malattia}`} />
        )}
      </td>
    );
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        <RefreshCw style={{ width: 32, height: 32, animation: 'spin 1s linear infinite', color: '#3b82f6' }} />
      </div>
    );
  }

  return (
    <PageLayout title="Gestione Presenze" subtitle="Calendario presenze e assenze dipendenti">
    <div style={{ maxWidth: 1600, margin: '0 auto' }} data-testid="attendance-page">
      {/* Header con controlli */}
      <div style={{ 
        display: 'flex', 
        justifyContent: 'flex-end', 
        alignItems: 'center', 
        marginBottom: 20,
        gap: 10,
        flexWrap: 'wrap'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button 
            onClick={loadData}
            style={{ 
              padding: '10px 20px',
              background: '#1e3a5f',
              color: 'white',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontWeight: '600'
            }}
            data-testid="btn-refresh"
          >
            🔄 Aggiorna
          </button>
        </div>
      </div>

      {/* Tabs - Solo Calendario */}
      <div style={{ display: 'flex', gap: 8, borderBottom: '2px solid #e5e7eb', paddingBottom: 8, marginBottom: 20 }}>
        <button
          style={{
            padding: '10px 16px',
            fontSize: 14,
            fontWeight: 'bold',
            borderRadius: '8px 8px 0 0',
            border: 'none',
            background: '#1e3a5f',
            color: 'white',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 6
          }}
          data-testid="tab-calendario"
        >
          📅 Calendario Presenze
        </button>
      </div>

      {/* Tab Calendario */}
      {true && (
        <div style={{ 
          background: 'white', 
          borderRadius: 12, 
          boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
          overflow: 'hidden'
        }}>
          {/* Toolbar Calendario */}
          <div style={{ 
            padding: '12px 16px', 
            background: '#f8fafc', 
            borderBottom: '1px solid #e5e7eb',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12
          }}>
            {/* Vista */}
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                onClick={() => setViewMode('mensile')}
                style={{
                  padding: '8px 16px',
                  background: viewMode === 'mensile' ? '#1e3a5f' : 'white',
                  color: viewMode === 'mensile' ? 'white' : '#6b7280',
                  border: '1px solid #e5e7eb',
                  borderRadius: '6px 0 0 6px',
                  cursor: 'pointer',
                  fontWeight: 500,
                  fontSize: 13
                }}
              >
                Mensile
              </button>
              <button
                onClick={() => setViewMode('settimanale')}
                style={{
                  padding: '8px 16px',
                  background: viewMode === 'settimanale' ? '#1e3a5f' : 'white',
                  color: viewMode === 'settimanale' ? 'white' : '#6b7280',
                  border: '1px solid #e5e7eb',
                  borderRadius: '0 6px 6px 0',
                  cursor: 'pointer',
                  fontWeight: 500,
                  fontSize: 13
                }}
              >
                Settimanale
              </button>
            </div>

            {/* Navigazione Mese */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button
                onClick={() => navigateMonth(-1)}
                style={{
                  padding: '8px 12px',
                  background: 'white',
                  border: '1px solid #e5e7eb',
                  borderRadius: 6,
                  cursor: 'pointer'
                }}
              >
                <ChevronLeft style={{ width: 16, height: 16 }} />
              </button>
              <div style={{ 
                padding: '8px 20px', 
                background: 'white', 
                border: '1px solid #e5e7eb', 
                borderRadius: 6,
                fontWeight: 600,
                minWidth: 150,
                textAlign: 'center'
              }}>
                📅 {MESI[currentMonth]} {currentYear}
              </div>
              <button
                onClick={() => navigateMonth(1)}
                style={{
                  padding: '8px 12px',
                  background: 'white',
                  border: '1px solid #e5e7eb',
                  borderRadius: 6,
                  cursor: 'pointer'
                }}
              >
                <ChevronRight style={{ width: 16, height: 16 }} />
              </button>
            </div>

            {/* Info dipendenti */}
            <div style={{ fontSize: 13, color: '#6b7280' }}>
              👥 {employees.length} dipendenti
            </div>
          </div>

          {/* === FORM INSERIMENTO RAPIDO CON RANGE === */}
          <div style={{ 
            padding: '16px', 
            background: '#eff6ff', 
            borderBottom: '1px solid #bfdbfe',
            display: 'flex',
            alignItems: 'flex-end',
            gap: 12,
            flexWrap: 'wrap'
          }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#1e40af', marginRight: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
              📝 Inserimento Rapido:
            </div>
            
            {/* Dipendente */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label style={{ fontSize: 10, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Dipendente</label>
              <select 
                value={formRapido.dipendente}
                onChange={e => setFormRapido(f => ({ ...f, dipendente: e.target.value }))}
                style={{
                  padding: '8px 12px',
                  border: '1px solid #93c5fd',
                  borderRadius: 6,
                  fontSize: 13,
                  minWidth: 180,
                  background: 'white'
                }}
              >
                <option value="">-- Seleziona --</option>
                {employees.map(e => (
                  <option key={e.id} value={e.id}>{e.nome} {e.cognome}</option>
                ))}
              </select>
            </div>
            
            {/* Data Da */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label style={{ fontSize: 10, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Da</label>
              <input 
                type="date"
                value={formRapido.dataDa}
                onChange={e => setFormRapido(f => ({ ...f, dataDa: e.target.value }))}
                style={{
                  padding: '8px 12px',
                  border: '1px solid #93c5fd',
                  borderRadius: 6,
                  fontSize: 13,
                  background: 'white'
                }}
              />
            </div>
            
            {/* Data A */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label style={{ fontSize: 10, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>A</label>
              <input 
                type="date"
                value={formRapido.dataA}
                onChange={e => setFormRapido(f => ({ ...f, dataA: e.target.value }))}
                style={{
                  padding: '8px 12px',
                  border: '1px solid #93c5fd',
                  borderRadius: 6,
                  fontSize: 13,
                  background: 'white'
                }}
              />
            </div>
            
            {/* Giustificativo */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label style={{ fontSize: 10, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Giustificativo</label>
              <select 
                value={formRapido.giustificativo}
                onChange={e => setFormRapido(f => ({ ...f, giustificativo: e.target.value }))}
                style={{
                  padding: '8px 12px',
                  border: '1px solid #93c5fd',
                  borderRadius: 6,
                  fontSize: 13,
                  minWidth: 140,
                  background: 'white'
                }}
              >
                <option value="">-- Seleziona --</option>
                {Object.entries(STATI_PRESENZA).map(([key, config]) => (
                  <option key={key} value={key}>{config.label} {config.name}</option>
                ))}
              </select>
            </div>
            
            {/* Pulsante Inserisci */}
            <button
              onClick={handleInserimentoRapido}
              disabled={inserendoRapido}
              style={{
                padding: '8px 20px',
                background: inserendoRapido ? '#9ca3af' : '#2563eb',
                color: 'white',
                border: 'none',
                borderRadius: 6,
                fontWeight: 600,
                fontSize: 13,
                cursor: inserendoRapido ? 'wait' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6
              }}
            >
              {inserendoRapido ? '⏳' : '✓'} Inserisci
            </button>
          </div>

          {/* === TOOLBAR SELEZIONE RAPIDA === */}
          <div style={{ 
            padding: '10px 16px', 
            background: multiSelectMode ? '#fef3c7' : '#f1f5f9', 
            borderBottom: '1px solid #e5e7eb',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flexWrap: 'wrap'
          }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginRight: 4 }}>
              ⚡ Selezione Rapida:
            </span>
            
            {/* Bottone Tutti Presenti */}
            <button
              onClick={async () => {
                if (!confirm('Vuoi impostare TUTTI i giorni lavorativi come "Presente" per tutti i dipendenti? Potrai poi modificare singolarmente.')) return;
                
                toast.info('Impostazione presenze in corso...');
                let count = 0;
                
                for (const emp of employees) {
                  for (const day of days) {
                    if (day.isWeekend) continue; // Salta weekend
                    
                    const key = `${emp.id}_${day.dateStr}`;
                    const currentState = presenze[key];
                    
                    // Salta se già ha uno stato diverso da vuoto/riposo
                    if (currentState && currentState !== 'riposo') continue;
                    
                    setPresenze(prev => ({ ...prev, [key]: 'presente' }));
                    count++;
                  }
                }
                
                // Salva tutto in batch
                try {
                  await api.post('/api/attendance/imposta-tutti-presenti', {
                    anno: currentYear,
                    mese: currentMonth + 1,
                    employees: employees.map(e => e.id)
                  });
                  toast.success(`✅ ${count} giorni impostati come "Presente"`);
                } catch (err) {
                  console.error('Errore batch:', err);
                  toast.warning('Presenze impostate localmente, alcune potrebbero non essere salvate');
                }
              }}
              style={{
                padding: '6px 12px',
                background: '#22c55e',
                color: 'white',
                border: 'none',
                borderRadius: 6,
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: 11,
                display: 'flex',
                alignItems: 'center',
                gap: 4
              }}
              data-testid="btn-tutti-presenti"
            >
              ✓ Tutti Presenti
            </button>
            
            <div style={{ width: 1, height: 24, background: '#d1d5db', margin: '0 4px' }} />
            
            {Object.entries(STATI_PRESENZA).filter(([key]) => key !== 'riposo').map(([key, config]) => (
              <button
                key={key}
                onClick={() => toggleMultiSelectMode(key)}
                style={{
                  padding: '6px 12px',
                  background: selectedStato === key ? config.color : config.bg,
                  color: selectedStato === key ? 'white' : config.color,
                  border: selectedStato === key ? `2px solid ${config.color}` : `1px solid ${config.color}40`,
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: 11,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  transition: 'all 0.15s ease',
                  boxShadow: selectedStato === key ? '0 2px 8px rgba(0,0,0,0.15)' : 'none'
                }}
                data-testid={`btn-select-${key}`}
              >
                <span style={{ 
                  width: 16, 
                  height: 16, 
                  borderRadius: 3, 
                  background: selectedStato === key ? 'white' : config.bg,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 9,
                  fontWeight: 700,
                  color: config.color
                }}>
                  {config.label}
                </span>
                {config.name}
              </button>
            ))}
            
            {multiSelectMode && (
              <>
                <div style={{ 
                  padding: '6px 12px', 
                  background: '#fef3c7', 
                  borderRadius: 6, 
                  fontSize: 11, 
                  color: '#92400e',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4
                }}>
                  💡 SHIFT+Click per range
                  {rangeStart && (
                    <span style={{ fontWeight: 'bold' }}>
                      (dal giorno {rangeStart.split('-')[2]})
                    </span>
                  )}
                </div>
                <button
                  onClick={() => { setSelectedStato(null); setMultiSelectMode(false); setRangeStart(null); }}
                  style={{
                    padding: '6px 12px',
                    background: '#ef4444',
                    color: 'white',
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'pointer',
                    fontWeight: 600,
                    fontSize: 11,
                    marginLeft: 'auto'
                  }}
                >
                  ✕ Disattiva
                </button>
              </>
            )}
            
            {/* Pulsante PDF */}
            <button
              onClick={generatePdfConsulente}
              disabled={generatingPdf}
              style={{
                padding: '6px 12px',
                background: '#1e3a5f',
                color: 'white',
                border: 'none',
                borderRadius: 6,
                cursor: generatingPdf ? 'wait' : 'pointer',
                fontWeight: 600,
                fontSize: 11,
                marginLeft: multiSelectMode ? 8 : 'auto',
                opacity: generatingPdf ? 0.7 : 1
              }}
              data-testid="btn-genera-pdf"
            >
              📄 {generatingPdf ? 'Generando...' : 'PDF Consulente'}
            </button>
          </div>

          {multiSelectMode && (
            <div style={{ 
              padding: '8px 16px', 
              background: '#fef9c3', 
              borderBottom: '1px solid #fcd34d',
              fontSize: 12,
              color: '#854d0e',
              display: 'flex',
              alignItems: 'center',
              gap: 6
            }}>
              <span style={{ fontSize: 16 }}>👆</span>
              <strong>Modalità {STATI_PRESENZA[selectedStato]?.name} attiva</strong> - 
              Clicca sulle celle per applicare &quot;{STATI_PRESENZA[selectedStato]?.label}&quot; a più giorni/dipendenti
            </div>
          )}

          {/* Tabella Calendario - Layout compatto senza scroll */}
          <div style={{ overflow: 'hidden' }}>
            <table style={{ 
              width: '100%', 
              borderCollapse: 'collapse',
              fontSize: 11,
              tableLayout: 'fixed'
            }}>
              <thead>
                <tr style={{ background: '#f9fafb' }}>
                  <th style={{ 
                    position: 'sticky', 
                    left: 0, 
                    background: '#f9fafb',
                    padding: '4px 6px', 
                    textAlign: 'left',
                    borderRight: '2px solid #e5e7eb',
                    borderBottom: '2px solid #e5e7eb',
                    width: 120,
                    fontSize: 10,
                    zIndex: 10
                  }}>
                    Dipendente
                  </th>
                  {days.map(d => (
                    <th 
                      key={d.day}
                      style={{ 
                        width: 22,
                        padding: '2px 1px',
                        textAlign: 'center',
                        borderRight: '1px solid #e5e7eb',
                        borderBottom: '2px solid #e5e7eb',
                        background: d.isWeekend ? '#fef2f2' : (d.isSabato ? '#fefce8' : '#f9fafb'),
                        fontSize: 8
                      }}
                    >
                      <div style={{ color: d.isWeekend ? '#ef4444' : (d.isSabato ? '#ca8a04' : '#6b7280'), lineHeight: 1 }}>
                        {GIORNI_SETTIMANA[d.dayOfWeek]}
                      </div>
                      <div style={{ fontWeight: 700, color: d.isWeekend ? '#ef4444' : '#1f2937', lineHeight: 1.2 }}>
                        {d.day}
                      </div>
                    </th>
                  ))}
                  {/* Colonne riepilogo per ogni stato */}
                  {Object.entries(STATI_PRESENZA).map(([key, config]) => (
                    <th 
                      key={`header-${key}`}
                      style={{ 
                        padding: '2px 1px', 
                        textAlign: 'center',
                        borderBottom: '2px solid #e5e7eb',
                        background: config.bg,
                        color: config.color,
                        width: 22,
                        fontSize: 7,
                        fontWeight: 700,
                        borderLeft: '1px solid #e5e7eb'
                      }}
                      title={config.name}
                    >
                      {config.label}
                    </th>
                  ))}
                  <th style={{ 
                    padding: '4px 2px', 
                    textAlign: 'center',
                    borderBottom: '2px solid #e5e7eb',
                    background: '#1e3a5f',
                    color: 'white',
                    width: 30,
                    fontSize: 7,
                    borderLeft: '2px solid #1e3a5f'
                  }}
                  title="Giorni Retribuiti (P+F+PE+M+R+T+FL+FNL)">
                    TOT
                  </th>
                </tr>
              </thead>
              <tbody>
                {employees.map((emp, idx) => {
                  const stats = getEmployeeStats(emp.id);
                  return (
                    <tr key={emp.id} style={{ background: idx % 2 === 0 ? 'white' : '#fafafa', height: 24 }}>
                      <td style={{ 
                        position: 'sticky', 
                        left: 0, 
                        background: idx % 2 === 0 ? 'white' : '#fafafa',
                        padding: '2px 4px', 
                        borderRight: '2px solid #e5e7eb',
                        borderBottom: '1px solid #e5e7eb',
                        fontWeight: 500,
                        fontSize: 10,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        maxWidth: 120,
                        zIndex: 5
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          <div style={{ 
                            width: 18, 
                            height: 18, 
                            borderRadius: '50%', 
                            background: '#e0e7ff', 
                            display: 'flex', 
                            alignItems: 'center', 
                            justifyContent: 'center',
                            fontSize: 8,
                            fontWeight: 600,
                            color: '#4338ca',
                            flexShrink: 0
                          }}>
                            {emp.nome_completo?.substring(0, 2).toUpperCase() || '??'}
                          </div>
                          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', fontSize: 9 }}>
                            {emp.nome_completo || emp.name || 'N/D'}
                          </span>
                        </div>
                      </td>
                      {days.map(d => renderCell(emp, d))}
                      {/* Colonne conteggio per ogni stato */}
                      {Object.entries(STATI_PRESENZA).map(([key, config]) => (
                        <td 
                          key={`count-${emp.id}-${key}`}
                          style={{ 
                            padding: '1px', 
                            textAlign: 'center',
                            borderBottom: '1px solid #e5e7eb',
                            background: stats[key] > 0 ? config.bg : (idx % 2 === 0 ? 'white' : '#fafafa'),
                            fontSize: 8,
                            fontWeight: stats[key] > 0 ? 700 : 400,
                            color: stats[key] > 0 ? config.color : '#d1d5db',
                            borderLeft: '1px solid #e5e7eb'
                          }}
                        >
                          {stats[key] || '-'}
                        </td>
                      ))}
                      {/* Totale Giorni Retribuiti */}
                      <td style={{ 
                        padding: '1px 2px', 
                        textAlign: 'center',
                        borderBottom: '1px solid #e5e7eb',
                        background: '#dcfce7',
                        fontWeight: 700,
                        fontSize: 9,
                        color: '#166534',
                        borderLeft: '2px solid #1e3a5f'
                      }}>
                        {stats.giorniRetribuiti}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Legenda */}
          <div style={{ 
            padding: '12px 16px', 
            background: '#f8fafc', 
            borderTop: '1px solid #e5e7eb',
            display: 'flex',
            flexWrap: 'wrap',
            gap: 12,
            justifyContent: 'center'
          }}>
            <span style={{ fontSize: 12, color: '#6b7280', marginRight: 8 }}>Legenda:</span>
            {Object.entries(STATI_PRESENZA).map(([key, config]) => (
              <div 
                key={key}
                style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: 4,
                  fontSize: 11
                }}
              >
                <span style={{ 
                  width: 20, 
                  height: 20, 
                  borderRadius: 4, 
                  background: config.bg, 
                  color: config.color,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 600,
                  fontSize: 9
                }}>
                  {config.label}
                </span>
                <span style={{ color: '#6b7280' }}>{config.name}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* === MENU CONTESTUALE DROPDOWN === */}
      {menuCella.open && (
        <div 
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 999
          }}
          onClick={() => setMenuCella({ open: false, x: 0, y: 0, employeeId: null, dateStr: null })}
        >
          <div 
            style={{
              position: 'absolute',
              left: Math.min(menuCella.x, window.innerWidth - 200),
              top: Math.min(menuCella.y, window.innerHeight - 300),
              background: 'white',
              borderRadius: 10,
              boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
              border: '1px solid #e5e7eb',
              overflow: 'hidden',
              minWidth: 180,
              zIndex: 1000
            }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ 
              padding: '10px 14px', 
              background: '#f8fafc', 
              borderBottom: '1px solid #e5e7eb',
              fontSize: 11,
              fontWeight: 700,
              color: '#374151',
              textTransform: 'uppercase'
            }}>
              Seleziona giustificativo
            </div>
            <div style={{ padding: 6 }}>
              {Object.entries(STATI_PRESENZA).map(([key, config]) => (
                <button
                  key={key}
                  onClick={() => applyGiustificativo(key)}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '10px 12px',
                    background: menuCella.currentState === key ? config.bg : 'transparent',
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'pointer',
                    textAlign: 'left',
                    fontSize: 13,
                    fontWeight: menuCella.currentState === key ? 600 : 400,
                    color: '#1f2937',
                    transition: 'background 0.1s'
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = config.bg}
                  onMouseLeave={e => e.currentTarget.style.background = menuCella.currentState === key ? config.bg : 'transparent'}
                  data-testid={`menu-option-${key}`}
                >
                  <span style={{ 
                    width: 26, 
                    height: 26, 
                    borderRadius: 6, 
                    background: config.bg, 
                    color: config.color,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 700,
                    fontSize: 11,
                    border: `1px solid ${config.color}30`
                  }}>
                    {config.label}
                  </span>
                  <span>{config.name}</span>
                  {menuCella.currentState === key && (
                    <span style={{ marginLeft: 'auto', color: '#10b981', fontSize: 16 }}>✓</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
    </PageLayout>
  );
}
