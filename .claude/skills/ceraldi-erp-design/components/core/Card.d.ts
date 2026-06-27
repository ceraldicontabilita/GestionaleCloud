import { CSSProperties, ReactNode } from 'react';

/**
 * Contenitore card bianco con bordo e ombra leggera.
 * @startingPoint section="Core" subtitle="Card contenitore con header opzionale" viewport="700x440"
 */
export interface CardProps {
  /** Titolo opzionale; se presente disegna l'intestazione. */
  title?: ReactNode;
  /** Icona Lucide accanto al titolo. */
  icon?: ReactNode;
  /** Azioni allineate a destra nell'intestazione. */
  actions?: ReactNode;
  children?: ReactNode;
  style?: CSSProperties;
  bodyStyle?: CSSProperties;
}

export function Card(props: CardProps): JSX.Element;
export default Card;
