import { ReactNode, CSSProperties } from 'react';

/**
 * Riquadro KPI con icona, etichetta e valore.
 * @startingPoint section="Core" subtitle="Riquadri KPI con bordo-accento" viewport="700x440"
 */
export interface StatCardProps {
  /** Icona Lucide opzionale. */
  icon?: ReactNode;
  /** Etichetta in uppercase. */
  label: string;
  /** Valore principale (es. importo formattato). */
  value: ReactNode;
  /** Riga di dettaglio sotto al valore. */
  subtext?: ReactNode;
  /** Colore del bordo-accento sinistro. Default 'primary'. */
  accent?: 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'accent' | 'none';
  onClick?: () => void;
  style?: CSSProperties;
}

export function StatCard(props: StatCardProps): JSX.Element;
export default StatCard;
