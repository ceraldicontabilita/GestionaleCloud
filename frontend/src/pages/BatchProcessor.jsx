/**
 * BatchProcessor.jsx - Riprocessamento Automatico Documenti
 *
 * MIGLIORAMENTI:
 * - Processo AUTOMATICO all'apertura della pagina
 * - Design uniforme con il resto dell'app (STYLES, COLORS)
 * - Progress tracking in tempo reale
 * - Nessun click manuale richiesto
 *
 * @author Ceraldi ERP
 * @version 2.0.0
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { PageLayout } from '../components/PageLayout';
import api from '../api';
import { STYLES, COLORS, formatEuro, formatDateIT, button, badge } from '../lib/utils';
import {
  RefreshCw,
  Play,
  CheckCircle,
  XCircle,
  Loader2,
  FileText,
  Mail,
  AlertTriangle,
  Clock,
  Zap,
  Download,
  Upload,
  Database,
  Settings,
  BarChart3,
} from 'lucide-react';

// ============================================================================
// STILI COMPONENTE (Design System Ceraldi)
// ============================================================================

const styles = {
  container: {
    ...STYLES.page,
    display: 'flex',
    flexDirection: 'column',
    gap: 24,
  },

  header: {
    ...STYLES.header,
    marginBottom: 0,
  },

  headerTitle: {
    fontSize: 24,
    fontWeight: 700,
    margin: 0,
  },

  headerSubtitle: {
    fontSize: 14,
    opacity: 0.9,
    marginTop: 4,
  },

  card: {
    ...STYLES.card,
    overflow: 'hidden',
  },

  cardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
    paddingBottom: 16,
    borderBottom: `1px solid ${COLORS.grayLight}`,
  },

  cardTitle: {
    fontSize: 18,
    fontWeight: 600,
    color: COLORS.primary,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },

  statsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: 16,
  },

  statCard: {
    background: COLORS.grayBg,
    borderRadius: 12,
    padding: 20,
    textAlign: 'center',
    border: `1px solid ${COLORS.grayLight}`,
    transition: 'all 0.2s ease',
  },

  statValue: {
    fontSize: 32,
    fontWeight: 700,
    color: COLORS.primary,
  },

  statLabel: {
    fontSize: 14,
    color: COLORS.gray,
    marginTop: 4,
  },

  progressContainer: {
    background: COLORS.grayBg,
    borderRadius: 12,
    padding: 24,
    marginBottom: 24,
  },

  progressBar: {
    height: 12,
    background: COLORS.grayLight,
    borderRadius: 6,
    overflow: 'hidden',
    marginTop: 12,
  },

  progressFill: {
    height: '100%',
    background: `linear-gradient(90deg, ${COLORS.primary} 0%, ${COLORS.success} 100%)`,
    borderRadius: 6,
    transition: 'width 0.5s ease',
  },

  logContainer: {
    background: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    maxHeight: 300,
    overflowY: 'auto',
    fontFamily: 'Monaco, Consolas, monospace',
    fontSize: 12,
  },

  logEntry: {
    padding: '4px 0',
    borderBottom: '1px solid rgba(255,255,255,0.1)',
  },

  logTime: {
    color: '#888',
    marginRight: 8,
  },

  logSuccess: {
    color: '#4ade80',
  },

  logError: {
    color: '#f87171',
  },

  logInfo: {
    color: '#60a5fa',
  },

  logWarning: {
    color: '#fbbf24',
  },

  taskList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
  },

  taskItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: 16,
    background: COLORS.grayBg,
    borderRadius: 10,
    border: `1px solid ${COLORS.grayLight}`,
  },

  taskIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },

  taskInfo: {
    flex: 1,
  },

  taskTitle: {
    fontWeight: 600,
    color: COLORS.primary,
  },

  taskSubtitle: {
    fontSize: 13,
    color: COLORS.gray,
  },

  taskStatus: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    fontSize: 13,
    fontWeight: 500,
  },

  autoModeIndicator: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 16px',
    background: 'rgba(255,255,255,0.2)',
    borderRadius: 20,
    fontSize: 13,
    fontWeight: 500,
  },

  pulseDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    background: '#4ade80',
    animation: 'pulse 2s infinite',
  },
};

// ============================================================================
// CONFIGURAZIONE TASK AUTOMATICI
// ============================================================================

const AUTO_TASKS = [
  {
    id: 'email_download',
    name: 'Download Email',
    description: 'Scarica nuove email con allegati PDF',
    icon: Mail,
    color: COLORS.info,
    endpoint: '/api/email-download/start-full-download?days_back=30',
    method: 'POST',
    autoRun: true,
  },
  {
    id: 'aruba_sync',
    name: 'Sync Fatture Aruba',
    description: 'Importa fatture da noreply@fatturazioneelettronica.aruba.it',
    icon: Download,
    color: COLORS.success,
    endpoint: '/api/documenti/scarica-fatture-aruba?since_days=30',
    method: 'POST',
    autoRun: true,
  },
  {
    id: 'ai_process',
    name: 'Elaborazione AI',
    description: 'Classifica e processa documenti con intelligenza artificiale',
    icon: Zap,
    color: COLORS.warning,
    endpoint: '/api/ai-parser/process-email-batch?limit=100',
    method: 'POST',
    autoRun: true,
  },
  {
    id: 'auto_associate',
    name: 'Auto-Associazione',
    description: 'Collega PDF a fatture, F24, cedolini esistenti',
    icon: Database,
    color: COLORS.purple,
    endpoint: '/api/email-download/auto-associa',
    method: 'POST',
    autoRun: true,
  },
  {
    id: 'f24_reconcile',
    name: 'Riconciliazione F24',
    description: 'Associa F24 in banca con quietanze nel sistema',
    icon: FileText,
    color: COLORS.primary,
    endpoint: '/api/f24-riconciliazione/riconcilia-tutto',
    method: 'POST',
    autoRun: true,
  },
  {
    id: 'categorize',
    name: 'Categorizzazione',
    description: 'Classifica movimenti bancari (stipendi, fornitori, tributi)',
    icon: BarChart3,
    color: '#9c27b0',
    endpoint: '/api/estratto-conto-movimenti/ricategorizza-batch',
    method: 'POST',
    autoRun: true,
  },
];

// ============================================================================
// COMPONENTE PRINCIPALE
// ============================================================================

export default function BatchProcessor() {
  // Stati
  const [isRunning, setIsRunning] = useState(false);
  const [autoMode, setAutoMode] = useState(true);
  const [currentTask, setCurrentTask] = useState(null);
  const [taskResults, setTaskResults] = useState({});
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState({
    totalProcessed: 0,
    documentsCreated: 0,
    errorsCount: 0,
    lastRunTime: null,
  });
  const [progress, setProgress] = useState(0);

  const hasRunRef = useRef(false);
  const logContainerRef = useRef(null);

  // Aggiungi log
  const addLog = useCallback((message, type = 'info') => {
    const timestamp = new Date().toLocaleTimeString('it-IT');
    setLogs(prev => [...prev, { timestamp, message, type }].slice(-100));

    // Auto-scroll
    setTimeout(() => {
      if (logContainerRef.current) {
        logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
      }
    }, 100);
  }, []);

  // Esegui singolo task
  const executeTask = useCallback(
    async task => {
      setCurrentTask(task.id);
      addLog(`▶ Avvio: ${task.name}`, 'info');

      try {
        const response =
          task.method === 'POST' ? await api.post(task.endpoint) : await api.get(task.endpoint);

        const result = response.data;

        setTaskResults(prev => ({
          ...prev,
          [task.id]: { success: true, data: result },
        }));

        // Aggiorna stats
        setStats(prev => ({
          ...prev,
          totalProcessed:
            prev.totalProcessed +
            (result.processed || result.emails_processate || result.riconciliati || 0),
          documentsCreated: prev.documentsCreated + (result.fatture_create || result.created || 0),
          errorsCount: prev.errorsCount + (result.errors?.length || 0),
        }));

        addLog(`✓ ${task.name}: completato`, 'success');

        // Log dettagli
        if (result.processed) addLog(`  → Processati: ${result.processed}`, 'info');
        if (result.fatture_create)
          addLog(`  → Fatture create: ${result.fatture_create}`, 'success');
        if (result.riconciliati) addLog(`  → Riconciliati: ${result.riconciliati}`, 'success');
        if (result.errors?.length) addLog(`  → Errori: ${result.errors.length}`, 'warning');

        return true;
      } catch (error) {
        const errorMsg = error.response?.data?.detail || error.message;

        setTaskResults(prev => ({
          ...prev,
          [task.id]: { success: false, error: errorMsg },
        }));

        addLog(`✗ ${task.name}: ${errorMsg}`, 'error');

        setStats(prev => ({
          ...prev,
          errorsCount: prev.errorsCount + 1,
        }));

        return false;
      }
    },
    [addLog]
  );

  // Esegui tutti i task in sequenza
  const runAllTasks = useCallback(async () => {
    if (isRunning) return;

    setIsRunning(true);
    setProgress(0);
    setTaskResults({});
    setLogs([]);

    addLog('🚀 Avvio elaborazione batch automatica...', 'info');
    addLog(`📋 ${AUTO_TASKS.length} task da eseguire`, 'info');

    const tasksToRun = AUTO_TASKS.filter(t => t.autoRun);

    for (let i = 0; i < tasksToRun.length; i++) {
      const task = tasksToRun[i];
      setProgress(Math.round((i / tasksToRun.length) * 100));

      await executeTask(task);

      // Pausa tra task per non sovraccaricare
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    setProgress(100);
    setCurrentTask(null);
    setIsRunning(false);

    setStats(prev => ({
      ...prev,
      lastRunTime: new Date().toISOString(),
    }));

    addLog('✅ Elaborazione batch completata!', 'success');
  }, [isRunning, executeTask, addLog]);

  // Auto-avvio al mount (solo una volta)
  useEffect(() => {
    if (autoMode && !hasRunRef.current) {
      hasRunRef.current = true;
      // Delay per permettere al componente di renderizzare
      const timer = setTimeout(() => {
        runAllTasks();
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [autoMode, runAllTasks]);

  // Render status icon per task
  const renderTaskStatus = taskId => {
    if (currentTask === taskId) {
      return (
        <Loader2
          style={{
            width: 20,
            height: 20,
            color: COLORS.info,
            animation: 'spin 1s linear infinite',
          }}
        />
      );
    }

    const result = taskResults[taskId];
    if (!result) {
      return <Clock style={{ width: 20, height: 20, color: COLORS.gray }} />;
    }

    if (result.success) {
      return <CheckCircle style={{ width: 20, height: 20, color: COLORS.success }} />;
    }

    return <XCircle style={{ width: 20, height: 20, color: COLORS.danger }} />;
  };

  return (
    <PageLayout
      title="Elaborazione Batch Automatica"
      subtitle="Sincronizzazione automatica email, fatture, F24 e documenti"
    >
      <div style={styles.container}>
        {/* Header con controlli */}
        <div style={styles.header}>
          <div>
            <h1 style={styles.headerTitle}>Elaborazione Batch</h1>
            <p style={styles.headerSubtitle}>
              Sincronizzazione automatica di tutti i flussi documentali
            </p>
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            {/* Indicatore Auto Mode */}
            <div style={styles.autoModeIndicator}>
              <div style={styles.pulseDot} />
              <span>Auto Mode {autoMode ? 'ON' : 'OFF'}</span>
            </div>

            {/* Pulsante Avvia/Stop */}
            <button
              onClick={runAllTasks}
              disabled={isRunning}
              style={{
                ...button.primary,
                opacity: isRunning ? 0.7 : 1,
                cursor: isRunning ? 'not-allowed' : 'pointer',
              }}
            >
              {isRunning ? (
                <>
                  <Loader2
                    style={{
                      width: 18,
                      height: 18,
                      marginRight: 8,
                      animation: 'spin 1s linear infinite',
                    }}
                  />
                  Elaborazione in corso...
                </>
              ) : (
                <>
                  <Play style={{ width: 18, height: 18, marginRight: 8 }} />
                  Avvia Elaborazione
                </>
              )}
            </button>
          </div>
        </div>

        {/* Progress Bar */}
        {isRunning && (
          <div style={styles.progressContainer}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 600, color: COLORS.primary }}>
                Elaborazione in corso...
              </span>
              <span style={{ fontWeight: 700, color: COLORS.primary }}>{progress}%</span>
            </div>
            <div style={styles.progressBar}>
              <div style={{ ...styles.progressFill, width: `${progress}%` }} />
            </div>
          </div>
        )}

        {/* Statistiche */}
        <div style={styles.statsGrid}>
          <div style={styles.statCard}>
            <div style={{ ...styles.statValue, color: COLORS.primary }}>{stats.totalProcessed}</div>
            <div style={styles.statLabel}>Documenti Processati</div>
          </div>
          <div style={styles.statCard}>
            <div style={{ ...styles.statValue, color: COLORS.success }}>
              {stats.documentsCreated}
            </div>
            <div style={styles.statLabel}>Documenti Creati</div>
          </div>
          <div style={styles.statCard}>
            <div style={{ ...styles.statValue, color: COLORS.danger }}>{stats.errorsCount}</div>
            <div style={styles.statLabel}>Errori</div>
          </div>
          <div style={styles.statCard}>
            <div style={{ ...styles.statValue, color: COLORS.info, fontSize: 18 }}>
              {stats.lastRunTime
                ? new Date(stats.lastRunTime).toLocaleTimeString('it-IT')
                : '--:--'}
            </div>
            <div style={styles.statLabel}>Ultimo Aggiornamento</div>
          </div>
        </div>

        {/* Lista Task */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardTitle}>
              <Settings style={{ width: 20, height: 20 }} />
              Task Automatici
            </div>
          </div>

          <div style={styles.taskList}>
            {AUTO_TASKS.map(task => {
              const Icon = task.icon;
              const result = taskResults[task.id];

              return (
                <div
                  key={task.id}
                  style={{
                    ...styles.taskItem,
                    background:
                      currentTask === task.id
                        ? `linear-gradient(90deg, ${task.color}10 0%, transparent 100%)`
                        : result?.success
                          ? `${COLORS.success}08`
                          : result?.error
                            ? `${COLORS.danger}08`
                            : COLORS.grayBg,
                  }}
                >
                  <div style={{ ...styles.taskIcon, background: `${task.color}15` }}>
                    <Icon style={{ width: 20, height: 20, color: task.color }} />
                  </div>

                  <div style={styles.taskInfo}>
                    <div style={styles.taskTitle}>{task.name}</div>
                    <div style={styles.taskSubtitle}>{task.description}</div>
                    {result?.data && (
                      <div style={{ fontSize: 12, color: COLORS.gray, marginTop: 4 }}>
                        {result.data.processed && `Processati: ${result.data.processed}`}
                        {result.data.fatture_create && ` | Creati: ${result.data.fatture_create}`}
                        {result.data.riconciliati && ` | Riconciliati: ${result.data.riconciliati}`}
                      </div>
                    )}
                  </div>

                  <div style={styles.taskStatus}>{renderTaskStatus(task.id)}</div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Log Console */}
        <div style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardTitle}>
              <FileText style={{ width: 20, height: 20 }} />
              Log Elaborazione
            </div>
            <button
              onClick={() => setLogs([])}
              style={{ ...button.outline, padding: '6px 12px', fontSize: 13 }}
            >
              Pulisci Log
            </button>
          </div>

          <div style={styles.logContainer} ref={logContainerRef}>
            {logs.length === 0 ? (
              <div style={{ color: '#666', textAlign: 'center', padding: 24 }}>
                In attesa dell'avvio dell'elaborazione...
              </div>
            ) : (
              logs.map((log, i) => (
                <div key={i} style={styles.logEntry}>
                  <span style={styles.logTime}>[{log.timestamp}]</span>
                  <span
                    style={
                      log.type === 'success'
                        ? styles.logSuccess
                        : log.type === 'error'
                          ? styles.logError
                          : log.type === 'warning'
                            ? styles.logWarning
                            : styles.logInfo
                    }
                  >
                    {log.message}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* CSS per animazioni */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </PageLayout>
  );
}
