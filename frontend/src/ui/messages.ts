import { byId, escapeHtml } from './dom';

const err = () => byId('err');
const warn = () => byId('warn');

export function showError(message: string) {
  err().textContent = message;
  err().classList.add('on');
}

export function clearError() {
  err().classList.remove('on');
}

export function showWarnings(messages: string[]) {
  warn().innerHTML = messages.map((m) => `<div>${escapeHtml(m)}</div>`).join('');
  warn().classList.toggle('on', messages.length > 0);
}
