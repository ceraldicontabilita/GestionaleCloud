/**
 * Helper functions per il modulo Attendance
 */

/**
 * Verifica se dipendente è cessato in una data
 */
export const isDipendenteCessato = (employee, dateStr) => {
  const dataFineContratto = employee.data_fine_contratto || employee.contratto?.data_fine;
  if (!dataFineContratto) return false;

  const dataFine = new Date(dataFineContratto);
  const dataCorrente = new Date(dateStr);

  return dataCorrente > dataFine;
};

/**
 * Verifica se dipendente deve essere visibile nel mese
 */
export const isDipendenteVisibileNelMese = (employee, anno, mese) => {
  const dataFineContratto = employee.data_fine_contratto || employee.contratto?.data_fine;
  if (!dataFineContratto) return true;

  const dataFine = new Date(dataFineContratto);
  const inizioMese = new Date(anno, mese, 1);

  // Se il contratto è scaduto prima dell'inizio del mese, non mostrare
  return dataFine >= inizioMese;
};

/**
 * Formatta data in formato italiano
 */
export const formatDate = dateStr => {
  if (!dateStr) return '-';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('it-IT').replaceAll('/', '-');
  } catch {
    return dateStr;
  }
};

/**
 * Genera array di giorni per un mese
 */
export const getDaysInMonth = (year, month) => {
  const days = [];
  const lastDay = new Date(year, month + 1, 0).getDate();

  for (let day = 1; day <= lastDay; day++) {
    const date = new Date(year, month, day);
    days.push({
      day,
      date: date.toISOString().split('T')[0],
      dayOfWeek: date.getDay(),
      isWeekend: date.getDay() === 0 || date.getDay() === 6,
    });
  }

  return days;
};

/**
 * Calcola le ore totali lavorate per un dipendente in un mese
 */
export const calcolaOreMensili = (presenze, employeeId, anno, mese) => {
  let oreTotali = 0;
  const daysInMonth = new Date(anno, mese + 1, 0).getDate();

  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${anno}-${String(mese + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const presenza = presenze[`${employeeId}_${dateStr}`];

    if (presenza?.stato === 'presente') {
      oreTotali += presenza.ore || 8;
    }
  }

  return oreTotali;
};

/**
 * Filtra dipendenti visibili nel mese corrente
 */
export const filtraDipendentiVisibili = (employees, anno, mese) => {
  return employees.filter(emp => isDipendenteVisibileNelMese(emp, anno, mese));
};
