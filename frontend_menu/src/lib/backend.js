// Menu fa parte dello stesso servizio del gestionale, anche in sviluppo.
// Un ambiente senza override non deve produrre URL «undefined/api/...».
export const MENU_BACKEND_URL = (process.env.REACT_APP_MENU_BACKEND_URL || '/menu').replace(/\/+$/, '');
