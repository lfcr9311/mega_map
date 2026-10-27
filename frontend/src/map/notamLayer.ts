import L from 'leaflet';
import type { NotamArea } from '../api/types';

const STYLE: L.PathOptions = {
  color: '#ff0000', weight: 2, opacity: 0.7, fillColor: '#ff0000', fillOpacity: 0.2, dashArray: '5, 5',
};

const escapeHtml = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

export class NotamLayer {
  private readonly group = L.layerGroup();

  constructor(map: L.Map) {
    this.group.addTo(map);
  }

  set(areas: NotamArea[]) {
    this.group.clearLayers();
    for (const a of areas) {
      L.polygon(a.polygon, STYLE)
        .bindPopup(
          `<strong>${escapeHtml(a.number)}</strong><br>FIR: ${escapeHtml(a.fir)}<br>` +
          `Status: ${escapeHtml(a.status)}<br>${escapeHtml(a.text.slice(0, 100))}`,
        )
        .addTo(this.group);
    }
  }
}
