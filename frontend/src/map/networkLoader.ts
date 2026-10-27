import { api } from '../api/client';
import type { AirwayLevel } from '../api/types';
import { LABELS_MIN_ZOOM, MapView, NETWORK_MIN_ZOOM } from './mapView';

const PAD_DEG = 0.6;
const DEBOUNCE_MS = 150;

/** Busca a malha visivel (e os fixos, com nomes ligados) a cada fim de movimento. */
export class NetworkLoader {
  private ctrl: AbortController | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  /** malha desenhada so com as aerovias do nivel escolhido */
  level: AirwayLevel | null = null;

  constructor(private readonly view: MapView) {
    view.map.on('moveend', () => this.refresh());
  }

  refresh() {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.load(), DEBOUNCE_MS);
  }

  private async load() {
    this.ctrl?.abort();
    const zoom = this.view.map.getZoom();
    if (zoom < NETWORK_MIN_ZOOM) {
      this.view.setNetwork(null);
      return;
    }
    const ctrl = (this.ctrl = new AbortController());
    const fixes = this.view.labelsOn && zoom >= LABELS_MIN_ZOOM;
    try {
      const net = await api.network(this.view.bbox(PAD_DEG), fixes, this.level, ctrl.signal);
      if (!ctrl.signal.aborted) this.view.setNetwork(net);
    } catch {
      // malha e decorativa: falha (ou abort) nao interrompe o planejador
    }
  }
}
