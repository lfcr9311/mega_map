import type { Runway } from '../api/types';
import { byId } from './dom';

export type RunwaySide = 'dep' | 'arr';

/** Botoes de pista de saida e chegada. Escolher as duas dispara SID/STAR automaticas. */
export class RunwayPicker {
  private readonly box = byId('rwy-select-box');
  private readonly cols: Record<RunwaySide, HTMLElement> = { dep: byId('rwy-dep'), arr: byId('rwy-arr') };

  constructor(private readonly onPick: (side: RunwaySide, runway: string) => void) {}

  render(dep: Runway[], arr: Runway[]) {
    this.box.hidden = !dep.length && !arr.length;
    this.fill('dep', dep);
    this.fill('arr', arr);
  }

  hide() {
    this.box.hidden = true;
  }

  private fill(side: RunwaySide, runways: Runway[]) {
    const col = this.cols[side];
    col.replaceChildren();
    for (const r of runways) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.setAttribute('aria-pressed', 'false');
      btn.textContent = `RW${r.ident} · ${r.bearing.toFixed(0)}° · ${r.length_ft.toLocaleString('pt-BR')}ft`;
      btn.addEventListener('click', () => {
        col.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', 'false'));
        btn.setAttribute('aria-pressed', 'true');
        this.onPick(side, r.ident);
      });
      col.appendChild(btn);
    }
  }
}
