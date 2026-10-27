import type { Altitude, Runway } from '../api/types';
import type { RouteState } from '../app/state';
import { byId, escapeHtml, fmtInt } from './dom';

export interface RouteEditHandlers {
  /** troca o fixo de chegada da perna k (ponto k+1) pelo ident digitado */
  replaceFix(k: number, ident: string, input: HTMLInputElement): void;
  insertAfter(k: number): void;
  remove(k: number): void;
  toggleDct(k: number): void;
  hover(k: number | null): void;
}

function fmtAlt(a: Altitude | null | undefined): string {
  if (!a?.ft) return '·';
  const v = a.ft.toLocaleString('pt-BR');
  if (a.desc === '+') return '≥' + v;     // no ou acima
  if (a.desc === '-') return '≤' + v;     // no ou abaixo
  if (a.desc === 'B') return '~' + v;     // janela (limite principal)
  return v;
}

/** Estatisticas, tabela editavel de pernas e pistas do destino. */
export class RoutePanel {
  private readonly res = byId('res');
  private readonly legs = byId('legs');

  constructor(h: RouteEditHandlers) {
    this.legs.addEventListener('change', (e) => {
      const inp = (e.target as HTMLElement).closest<HTMLInputElement>('input.fx');
      if (inp) h.replaceFix(Number(inp.dataset.k), inp.value, inp);
    });
    this.legs.addEventListener('click', (e) => {
      const t = e.target as HTMLElement;
      const ins = t.closest<HTMLElement>('button.ins');
      const del = t.closest<HTMLElement>('button.del');
      const tg = t.closest<HTMLElement>('td.awy');
      if (ins) h.insertAfter(Number(ins.dataset.k));
      else if (del) h.remove(Number(del.dataset.k));
      else if (tg) h.toggleDct(Number(tg.dataset.k));
    });
    this.legs.addEventListener('mouseover', (e) => {
      const tr = (e.target as HTMLElement).closest<HTMLElement>('tr[data-k]');
      if (!tr) return;
      this.legs.querySelectorAll('tr.hov').forEach((r) => r.classList.remove('hov'));
      tr.classList.add('hov');
      h.hover(Number(tr.dataset.k));
    });
    this.legs.addEventListener('mouseleave', () => {
      this.legs.querySelectorAll('tr.hov').forEach((r) => r.classList.remove('hov'));
      h.hover(null);
    });
  }

  render(r: RouteState, isDct: (k: number) => boolean) {
    const n = r.points.length;
    byId('s-km').textContent = fmtInt(r.km);
    byId('s-dir').textContent = (r.directKm > 0 ? '+' + ((r.km / r.directKm - 1) * 100).toFixed(1) : '0.0') + '%';
    byId('s-hop').textContent = String(Math.max(n - 1, 0));
    byId('s-fix').textContent = String(n);

    this.legs.innerHTML = r.legs.map((leg, k) => {
      const a = r.points[k], b = r.points[k + 1];
      const dct = isDct(k);
      const alt = b.altitude ?? (b.id != null ? r.altitudes.get(b.id) : null);
      const last = k + 1 === n - 1;
      return `<tr data-k="${k}"><td class="${a.kind === 'V' ? 'dev' : ''}">${escapeHtml(a.ident)}</td>` +
        `<td><input class="fx${b.kind === 'V' ? ' dev' : ''}" data-k="${k}" value="${escapeHtml(b.ident)}" spellcheck="false"${last ? ' disabled' : ''}></td>` +
        `<td class="awy${dct ? ' dct' : ''}" data-k="${k}" title="clique p/ alternar DCT">${dct ? 'DCT' : escapeHtml(leg.airway || '·')}</td>` +
        `<td class="alt">${fmtAlt(alt)}</td>` +
        `<td class="n">${leg.km.toFixed(1)}</td>` +
        `<td class="ed"><button type="button" class="ins" data-k="${k}" title="inserir fixo depois">+</button>` +
        (last ? '' : `<button type="button" class="del" data-k="${k}" title="remover ${escapeHtml(b.ident)}">×</button>`) +
        `</td></tr>`;
    }).join('');
    this.res.classList.add('on');
  }

  renderDestinationRunways(runways: Runway[]) {
    const box = byId('rwy-box');
    box.hidden = !runways.length;
    byId('rwys').innerHTML = runways.map((r) =>
      `<div><b>${r.ident}</b> · ${r.bearing.toFixed(0)}° · ${r.length_ft.toLocaleString('pt-BR')} ft · elev ${r.elevation_ft} ft</div>`,
    ).join('');
  }

  hide() {
    this.res.classList.remove('on');
  }

  focusFix(k: number) {
    const inp = this.legs.querySelector<HTMLInputElement>(`input.fx[data-k="${k}"]`);
    inp?.focus();
    inp?.select();
  }
}
