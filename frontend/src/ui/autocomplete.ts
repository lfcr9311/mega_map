import { api } from '../api/client';
import type { Airport } from '../api/types';
import { escapeHtml } from './dom';

const DEBOUNCE_MS = 120;

/** Sugestoes de aeroporto sob um campo de texto (setas, Enter, Esc). */
export function attachAirportAutocomplete(input: HTMLInputElement, box: HTMLElement) {
  let items: Airport[] = [];
  let sel = -1;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let seq = 0;

  const close = () => {
    box.classList.remove('on');
    sel = -1;
  };
  const draw = () => {
    if (!items.length) return close();
    box.innerHTML = items.map((a, k) =>
      `<div data-k="${k}" class="${k === sel ? 'sel' : ''}"><b>${escapeHtml(a.icao)}</b>` +
      `<small>${a.procedures ? `${a.procedures} procedimentos` : 'aeródromo'}</small></div>`,
    ).join('');
    box.classList.add('on');
  };
  const search = () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) {
      items = [];
      return close();
    }
    timer = setTimeout(async () => {
      const mine = ++seq;
      try {
        const res = await api.searchAirports(q);
        if (mine !== seq) return;
        items = res;
        draw();
      } catch {
        close();
      }
    }, DEBOUNCE_MS);
  };
  const pick = (k: number) => {
    input.value = items[k].icao;
    close();
  };

  input.addEventListener('input', () => {
    sel = -1;
    search();
  });
  input.addEventListener('focus', search);
  input.addEventListener('blur', () => setTimeout(close, 120));
  input.addEventListener('keydown', (e) => {
    if (!box.classList.contains('on')) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      sel = Math.min(sel + 1, items.length - 1);
      draw();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      sel = Math.max(sel - 1, 0);
      draw();
    } else if (e.key === 'Enter' && sel >= 0) {
      e.preventDefault();
      pick(sel);
    } else if (e.key === 'Escape') {
      close();
    }
  });
  box.addEventListener('mousedown', (e) => {
    const d = (e.target as HTMLElement).closest<HTMLElement>('[data-k]');
    if (d) pick(Number(d.dataset.k));
  });
}

export const isSuggesting = () => document.querySelector('.ac.on') != null;
