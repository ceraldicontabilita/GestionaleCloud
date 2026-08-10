import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  Bot,
  CalendarClock,
  CheckCircle2,
  FileWarning,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';

import api from '../api';
import {
  PageEmpty,
  PageError,
  PageGrid,
  PageLayout,
  PageLoading,
  PageSection,
} from '../components/PageLayout';
import { Button, PageHeader, StatCard } from '../components/ds';
import { BORDER_RADIUS, COLORS, FONT, SHADOWS, SPACING } from '../lib/utils';

const severityColors = {
  critical: { color: COLORS.danger, background: COLORS.dangerLight },
  high: { color: COLORS.warning, background: COLORS.warningLight },
  medium: { color: COLORS.info, background: COLORS.infoLight },
  low: { color: COLORS.textMuted, background: COLORS.bg },
  info: { color: COLORS.textMuted, background: COLORS.bg },
};

function apiError(error, fallback) {
  return error?.response?.data?.detail || error?.message || fallback;
}

function formatDate(value) {
  if (!value) return 'Data non disponibile';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('it-IT');
}

function formatMoney(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 'Importo non disponibile';
  return number.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' });
}

function StatusBadge({ severity = 'info', children }) {
  const palette = severityColors[severity] || severityColors.info;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '4px 8px',
        borderRadius: BORDER_RADIUS.full,
        background: palette.background,
        color: palette.color,
        fontSize: 11,
        fontWeight: 700,
        textTransform: 'uppercase',
      }}
    >
      {children || severity}
    </span>
  );
}

function EvidenceList({ evidence }) {
  if (!evidence || typeof evidence !== 'object') return null;
  const entries = Object.entries(evidence).filter(([, value]) => value !== null && value !== '');
  if (!entries.length) return null;
  return (
    <dl
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(min(180px, 100%), 1fr))',
        gap: 8,
        margin: '12px 0 0',
      }}
    >
      {entries.map(([key, value]) => (
        <div key={key} style={{ minWidth: 0 }}>
          <dt style={{ fontSize: 10, color: COLORS.textMuted, textTransform: 'uppercase' }}>
            {key.replaceAll('_', ' ')}
          </dt>
          <dd
            style={{
              margin: '2px 0 0',
              color: COLORS.text,
              fontSize: 12,
              overflowWrap: 'anywhere',
            }}
          >
            {typeof value === 'boolean'
              ? value
                ? 'Sì'
                : 'No'
              : typeof value === 'object'
                ? JSON.stringify(value)
                : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function QuestionCard({ item, answering, onAnswer }) {
  return (
    <article style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <StatusBadge severity={item.severity}>{item.severity || 'da verificare'}</StatusBadge>
          <h3 style={cardTitleStyle}>{item.title || 'Domanda amministrativa'}</h3>
        </div>
        <span style={sourceStyle}>{item.subject?.type || item.question_type}</span>
      </div>
      <p style={bodyStyle}>{item.question}</p>
      <EvidenceList evidence={item.evidence} />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 14 }}>
        {(item.options || []).map(option => (
          <Button
            key={option.id}
            size="sm"
            variant={option.action === 'confirm_outcome' ? 'success' : 'secondary'}
            disabled={answering}
            onClick={() => onAnswer(item.id, option.id)}
          >
            {option.label}
          </Button>
        ))}
      </div>
    </article>
  );
}

function AnomalyCard({ item }) {
  const assessment = item.assessment || {};
  const supportedCounters = (assessment.counter_hypotheses || []).filter(counter => counter.supported);
  return (
    <article style={{ ...cardStyle, borderLeft: `4px solid ${COLORS.warning}` }}>
      <div style={cardHeaderStyle}>
        <div>
          <StatusBadge severity={item.severity}>{item.severity || 'anomalia'}</StatusBadge>
          <h3 style={cardTitleStyle}>{item.title || item.anomaly_type}</h3>
        </div>
        <span style={sourceStyle}>
          Confidenza {Math.round(Number(assessment.confidence || 0) * 100)}%
        </span>
      </div>
      <p style={bodyStyle}>
        Conclusione: <strong>{assessment.conclusion || 'da verificare'}</strong>
      </p>
      {item.must_not_auto_pay_again && (
        <div style={blockingStyle}>
          <ShieldCheck size={16} /> Secondo pagamento automatico bloccato fino alla verifica umana.
        </div>
      )}
      {supportedCounters.length > 0 && (
        <div style={counterStyle}>
          <strong>Contro-ipotesi attiva:</strong>{' '}
          {supportedCounters.map(counter => counter.description).join(' ')}
        </div>
      )}
      <EvidenceList evidence={assessment.evidence} />
    </article>
  );
}

function ExpectedEventCard({ item }) {
  const statusSeverity =
    item.status === 'overdue' ? 'critical' : item.status === 'ambiguous' ? 'high' : 'medium';
  return (
    <article style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <StatusBadge severity={statusSeverity}>{item.status}</StatusBadge>
          <h3 style={cardTitleStyle}>{item.event_type || 'Evento atteso'}</h3>
        </div>
        <span style={sourceStyle}>{item.key}</span>
      </div>
      <p style={bodyStyle}>
        Periodo {String(item.month || '').padStart(2, '0')}/{item.year} · giorni attesi{' '}
        {item.expected_day_from || '?'}–{item.expected_day_to || '?'} ·{' '}
        {formatMoney(item.expected_amount)}
      </p>
      <p style={mutedStyle}>Confidenza {Math.round(Number(item.confidence || 0) * 100)}%</p>
    </article>
  );
}

function PatternCard({ item }) {
  return (
    <article style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <StatusBadge severity="info">{item.learning_level || 'osservazione'}</StatusBadge>
          <h3 style={cardTitleStyle}>{item.pattern_type || 'Schema operativo'}</h3>
        </div>
        <span style={sourceStyle}>{item.key}</span>
      </div>
      <p style={bodyStyle}>
        {item.distinct_months || 0} mesi distinti · frequenza {item.frequency || 'non definita'} ·
        importo mediano {formatMoney(item.median_amount)}
      </p>
      <p style={mutedStyle}>
        Confidenza {Math.round(Number(item.confidence || 0) * 100)}%: resta una proposta finché non
        è confermata.
      </p>
    </article>
  );
}

export default function AssistenteCeraldi() {
  const queryClient = useQueryClient();
  const dashboard = useQuery({
    queryKey: ['assistente-ceraldi', 'dashboard'],
    queryFn: async () => (await api.get('/api/assistente/dashboard')).data,
  });

  const scan = useMutation({
    mutationFn: async () => (await api.post('/api/assistente/scan/all')).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['assistente-ceraldi'] }),
  });

  const answer = useMutation({
    mutationFn: async ({ questionId, optionId }) =>
      (
        await api.post(`/api/assistente/questions/${encodeURIComponent(questionId)}/answer`, {
          option_id: optionId,
          notes: '',
        })
      ).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['assistente-ceraldi'] }),
  });

  const data = dashboard.data;
  const error = dashboard.error || scan.error || answer.error;
  const answerQuestion = (questionId, optionId) => answer.mutate({ questionId, optionId });

  return (
    <PageLayout>
      <div data-testid="assistente-ceraldi" style={{ width: '100%', maxWidth: 1500 }}>
        <PageHeader
          title="Assistente Ceraldi"
          subtitle="Attese, anomalie e domande con prove verificabili. Nessuna scrittura contabile automatica."
          icon={<Bot size={20} />}
          actions={
            <Button
              onClick={() => scan.mutate()}
              disabled={scan.isPending}
              iconLeft={<RefreshCw size={14} className={scan.isPending ? 'spin' : undefined} />}
            >
              {scan.isPending ? 'Controllo in corso…' : 'Aggiorna controlli'}
            </Button>
          }
        />

        <div style={safetyStyle}>
          <ShieldCheck size={22} color={COLORS.success} style={{ flexShrink: 0 }} />
          <div>
            <strong>Confine di sicurezza attivo.</strong> Il motore legge i domini contabili ma scrive
            soltanto nella memoria separata dell’Assistente. Importo al centesimo e identità sono
            entrambi obbligatori; un dubbio non diventa mai pagamento, riconciliazione o verità.
          </div>
        </div>

        {error && (
          <div style={{ marginBottom: 16 }}>
            <PageError
              message={apiError(error, 'Impossibile caricare l’Assistente Ceraldi')}
              onRetry={() => dashboard.refetch()}
            />
          </div>
        )}

        {dashboard.isPending ? (
          <PageLoading message="Caricamento controlli amministrativi…" />
        ) : (
          <>
            <PageGrid cols={4} gap={12} minWidth={190}>
              <StatCard
                label="Domande da decidere"
                value={data?.counts?.questions || 0}
                icon={<FileWarning size={18} />}
                accent="warning"
              />
              <StatCard
                label="Anomalie da verificare"
                value={data?.counts?.anomalies || 0}
                icon={<AlertTriangle size={18} />}
                accent="danger"
              />
              <StatCard
                label="Eventi attesi"
                value={data?.counts?.expected_events || 0}
                icon={<CalendarClock size={18} />}
                accent="info"
              />
              <StatCard
                label="Schemi appresi"
                value={data?.counts?.learned_patterns || 0}
                icon={<CheckCircle2 size={18} />}
                accent="success"
              />
            </PageGrid>

            <div style={{ height: SPACING.lg }} />

            <PageSection title="Decisioni umane richieste" icon={<FileWarning size={16} />}>
              {(data?.questions || []).length ? (
                <PageGrid cols={2} gap={12} minWidth={340}>
                  {data.questions.map(item => (
                    <QuestionCard
                      key={item.id}
                      item={item}
                      answering={answer.isPending}
                      onAnswer={answerQuestion}
                    />
                  ))}
                </PageGrid>
              ) : (
                <PageEmpty icon="✓" message="Nessuna decisione amministrativa aperta." />
              )}
            </PageSection>

            <PageSection title="Anomalie amministrative" icon={<AlertTriangle size={16} />}>
              {(data?.anomalies || []).length ? (
                <PageGrid cols={2} gap={12} minWidth={340}>
                  {data.anomalies.map(item => (
                    <AnomalyCard key={item.id} item={item} />
                  ))}
                </PageGrid>
              ) : (
                <PageEmpty icon="✓" message="Nessuna anomalia amministrativa aperta." />
              )}
            </PageSection>

            <PageSection title="Eventi attesi" icon={<CalendarClock size={16} />}>
              {(data?.expected_events || []).length ? (
                <PageGrid cols={3} gap={12} minWidth={260}>
                  {data.expected_events.map(item => (
                    <ExpectedEventCard key={item.id} item={item} />
                  ))}
                </PageGrid>
              ) : (
                <PageEmpty icon="○" message="Nessun evento periodico atteso rilevato." />
              )}
            </PageSection>

            <PageSection title="Schemi appresi, non ancora regole" icon={<Bot size={16} />}>
              {(data?.learned_patterns || []).length ? (
                <PageGrid cols={3} gap={12} minWidth={260}>
                  {data.learned_patterns.map(item => (
                    <PatternCard key={item.id} item={item} />
                  ))}
                </PageGrid>
              ) : (
                <PageEmpty icon="○" message="Nessuno schema sufficientemente documentato." />
              )}
            </PageSection>

            <p style={{ ...mutedStyle, textAlign: 'right' }}>
              Ultimo aggiornamento: {formatDate(data?.generated_at)}
            </p>
          </>
        )}
      </div>
    </PageLayout>
  );
}

const cardStyle = {
  height: '100%',
  boxSizing: 'border-box',
  padding: 14,
  border: `1px solid ${COLORS.border}`,
  borderRadius: BORDER_RADIUS.md,
  background: COLORS.card,
  boxShadow: SHADOWS.sm,
  fontFamily: FONT.family,
};

const cardHeaderStyle = {
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: 12,
};

const cardTitleStyle = {
  margin: '8px 0 0',
  color: COLORS.primary,
  fontSize: 15,
  lineHeight: 1.35,
};

const bodyStyle = {
  margin: '10px 0 0',
  color: COLORS.text,
  fontSize: 13,
  lineHeight: 1.55,
};

const mutedStyle = {
  margin: '8px 0 0',
  color: COLORS.textMuted,
  fontSize: 12,
  lineHeight: 1.45,
};

const sourceStyle = {
  color: COLORS.textMuted,
  fontSize: 11,
  textAlign: 'right',
  overflowWrap: 'anywhere',
};

const blockingStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  marginTop: 12,
  padding: 10,
  borderRadius: BORDER_RADIUS.sm,
  background: COLORS.dangerLight,
  color: COLORS.danger,
  fontSize: 12,
  fontWeight: 700,
};

const counterStyle = {
  marginTop: 10,
  padding: 10,
  borderRadius: BORDER_RADIUS.sm,
  background: COLORS.infoLight,
  color: COLORS.info,
  fontSize: 12,
  lineHeight: 1.45,
};

const safetyStyle = {
  display: 'flex',
  alignItems: 'flex-start',
  gap: 12,
  marginBottom: 16,
  padding: 14,
  border: `1px solid ${COLORS.success}`,
  borderRadius: BORDER_RADIUS.md,
  background: COLORS.successLight,
  color: COLORS.text,
  fontSize: 13,
  lineHeight: 1.55,
};
