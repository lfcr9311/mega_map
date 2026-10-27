import L from 'leaflet';
import type { Bbox, Network, Point, SpecialArea } from '../api/types';
import { BASEMAPS, DEFAULT_BASEMAP } from './basemaps';

const NS = 'http://www.w3.org/2000/svg';
/** zoom minimo para desenhar a malha de aerovias e os nomes dos fixos */
export const NETWORK_MIN_ZOOM = 5;
export const LABELS_MIN_ZOOM = 7;

const AREA_COLORS: Record<string, string> = { D: '#ff4444', P: '#ffaa00', R: '#ff00ff', A: '#00ffff' };

export interface RouteView {
  points: Point[];
  sidChain: Point[];
  starChain: Point[];
  isDct: (k: number) => boolean;
}

function svgEl(tag: string, attrs: Record<string, string | number>): SVGElement {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, String(attrs[k]));
  return e;
}

/**
 * Mapa Leaflet + overlay SVG redesenhado a cada movimento. O overlay (em vez de
 * camadas Leaflet) permite rotulos com anticolisao e a malha inteira num unico path.
 */
export class MapView {
  readonly map: L.Map;
  private tiles: L.TileLayer | null = null;
  private route: RouteView | null = null;
  private network: Network | null = null;
  private specialAreas: SpecialArea[] = [];
  private showLabels = false;
  private highlighted: number | null = null;

  constructor(mapEl: HTMLElement, private readonly svg: SVGSVGElement) {
    this.map = L.map(mapEl, { worldCopyJump: false }).setView([-15, -52], 4);
    this.setBasemap(DEFAULT_BASEMAP);
    this.map.on('move zoom viewreset resize', () => this.paint());
    addEventListener('resize', () => setTimeout(() => this.paint(), 80));
  }

  setBasemap(key: string) {
    const b = BASEMAPS[key] ?? BASEMAPS[DEFAULT_BASEMAP];
    if (this.tiles) this.map.removeLayer(this.tiles);
    this.tiles = L.tileLayer(b.url, { maxZoom: b.maxZoom, attribution: b.attribution }).addTo(this.map);
    this.map.getPane('tilePane')?.classList.toggle('dark', b.dark);
  }

  setRoute(route: RouteView | null) {
    this.route = route;
    this.highlighted = null;
    this.paint();
  }

  setNetwork(network: Network | null) {
    this.network = network;
    this.paint();
  }

  setSpecialAreas(areas: SpecialArea[]) {
    this.specialAreas = areas;
    this.paint();
  }

  setLabels(on: boolean) {
    this.showLabels = on;
    this.paint();
  }

  get labelsOn() {
    return this.showLabels;
  }

  highlightLeg(k: number | null) {
    this.highlighted = k;
    this.svg.querySelectorAll('.leg.hi').forEach((p) => p.classList.remove('hi'));
    if (k != null) this.svg.querySelector(`.leg[data-k="${k}"]`)?.classList.add('hi');
  }

  fitRoute() {
    if (!this.route?.points.length) return;
    const bounds = L.latLngBounds(this.route.points.map((p) => [p.lat, p.lon] as L.LatLngTuple));
    this.map.fitBounds(bounds.pad(0.15), { animate: false });
    this.paint();
  }

  bbox(padDeg: number): Bbox {
    const b = this.map.getBounds();
    return {
      south: b.getSouth() - padDeg, west: b.getWest() - padDeg,
      north: b.getNorth() + padDeg, east: b.getEast() + padDeg,
    };
  }

  paint() {
    const svg = this.svg;
    svg.replaceChildren();
    const g = svgEl('g', {});
    svg.appendChild(g);
    const W = svg.clientWidth, H = svg.clientHeight;
    const zoom = this.map.getZoom();
    const xy = (lat: number, lon: number): [number, number] => {
      const p = this.map.latLngToContainerPoint([lat, lon]);
      return [p.x, p.y];
    };
    const seg = (a: [number, number], b: [number, number]) =>
      `M${a[0].toFixed(1)} ${a[1].toFixed(1)}L${b[0].toFixed(1)} ${b[1].toFixed(1)}`;

    // areas especiais (rpl_back)
    for (const area of this.specialAreas) {
      const coords = area.coords_latlon;
      if (!coords?.length) continue;
      const color = AREA_COLORS[area.type ?? ''] ?? '#ff0000';
      const d = coords.map(([la, lo], i) => {
        const [x, y] = xy(la, lo);
        return `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`;
      }).join('') + 'Z';
      const poly = svgEl('path', { class: 'restriction', d, stroke: color, fill: color });
      const title = svgEl('title', {});
      title.textContent = `${area.name ?? ''} (${area.typeLabel ?? area.type ?? ''})`;
      poly.appendChild(title);
      g.appendChild(poly);
    }

    // malha de aerovias
    if (this.network && zoom >= NETWORK_MIN_ZOOM) {
      let d = '';
      for (const [la1, lo1, la2, lo2] of this.network.edges) d += seg(xy(la1, lo1), xy(la2, lo2));
      if (d) g.appendChild(svgEl('path', { class: 'net', d }));
    }

    // nomes de todos os fixos visiveis (toggle)
    if (this.showLabels && this.network && zoom >= LABELS_MIN_ZOOM) {
      const placed: [number, number][] = [];
      const fits = (x: number, y: number) => placed.every((p) => Math.abs(p[0] - x) > 40 || Math.abs(p[1] - y) > 11);
      for (const [ident, la, lo] of this.network.fixes) {
        const [cx, cy] = xy(la, lo);
        if (cx < 0 || cx > W || cy < 0 || cy > H || !fits(cx + 5, cy - 5)) continue;
        g.appendChild(svgEl('circle', { class: 'node dim', cx, cy, r: 1.6 }));
        const t = svgEl('text', { class: 'lbl wp', x: cx + 5, y: cy - 5 });
        t.textContent = ident;
        g.appendChild(t);
        placed.push([cx + 5, cy - 5]);
      }
    }

    const route = this.route;
    if (!route?.points.length) return;
    const pts = route.points;

    // rota inteira na cor en-route; SID/STAR por cima onde se aplicam
    pts.forEach((p, k) => {
      if (k === pts.length - 1) return;
      const q = pts[k + 1];
      const cls = route.isDct(k) ? 'leg a dctleg' : 'leg a';
      const hi = k === this.highlighted ? ' hi' : '';
      g.appendChild(svgEl('path', { class: cls + hi, 'data-k': k, d: seg(xy(p.lat, p.lon), xy(q.lat, q.lon)) }));
    });
    const drawChain = (chain: Point[], cls: string) => {
      for (let k = 0; k < chain.length - 1; k++) {
        const a = chain[k], b = chain[k + 1];
        g.appendChild(svgEl('path', { class: `leg ${cls}`, d: seg(xy(a.lat, a.lon), xy(b.lat, b.lon)) }));
      }
    };
    drawChain(route.sidChain, 's');
    drawChain(route.starChain, 't');

    const placed: [number, number][] = [];
    const fits = (x: number, y: number) => placed.every((p) => Math.abs(p[0] - x) > 46 || Math.abs(p[1] - y) > 13);
    pts.forEach((p, k) => {
      const end = k === 0 || k === pts.length - 1;
      const dev = p.kind === 'V';
      const [cx, cy] = xy(p.lat, p.lon);
      if (cx < -50 || cx > W + 50 || cy < -50 || cy > H + 50) return;
      if (dev) {
        g.appendChild(svgEl('circle', { class: 'dev-halo', cx, cy, r: 7 }));
        g.appendChild(svgEl('circle', { class: 'node dev', cx, cy, r: 4 }));
      } else {
        g.appendChild(svgEl('circle', { class: end ? 'ap' : 'node', cx, cy, r: end ? 5 : 2.5 }));
      }
      const lx = cx + 8, ly = cy - 8;
      if (end || dev || fits(lx, ly)) {
        const t = svgEl('text', { class: dev ? 'lbl dev' : end ? 'lbl big' : 'lbl', x: lx, y: ly });
        t.textContent = p.ident;
        g.appendChild(t);
        placed.push([lx, ly]);
      }
    });
  }
}
