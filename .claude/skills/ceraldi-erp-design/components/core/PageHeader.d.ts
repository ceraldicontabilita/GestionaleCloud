import { CSSProperties, ReactNode } from 'react';

/**
 * Intestazione di pagina con bordo-accento navy a sinistra.
 * @startingPoint section="Core" subtitle="Header pagina con titolo + azioni" viewport="700x440"
 */
export interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Icona Lucide (o emoji) accanto al titolo. */
  icon?: ReactNode;
  /** Bottoni allineati a destra. */
  actions?: ReactNode;
  style?: CSSProperties;
}

export function PageHeader(props: PageHeaderProps): JSX.Element;
export default PageHeader;
