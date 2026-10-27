import type { Procedure } from '../api/types';
import { byId, escapeHtml } from './dom';

/** Dropdown de SID ou STAR. O valor e a chave do procedimento ("" = nenhum). */
export class ProcedureSelect {
  private readonly box: HTMLElement;
  private readonly select: HTMLSelectElement;

  constructor(selectId: string, boxId: string, onChange: (key: string | null) => void) {
    this.select = byId<HTMLSelectElement>(selectId);
    this.box = byId(boxId);
    this.select.addEventListener('change', () => onChange(this.select.value || null));
  }

  fill(options: Procedure[], selected: string | null) {
    this.box.hidden = !options.length;
    this.select.innerHTML = '<option value="">— nenhum —</option>' +
      options.map((o) => `<option value="${escapeHtml(o.key)}">${escapeHtml(o.label)}</option>`).join('');
    this.select.value = selected ?? '';
  }

  hide() {
    this.box.hidden = true;
    this.select.innerHTML = '';
  }
}
