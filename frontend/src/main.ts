import 'leaflet/dist/leaflet.css';
import './styles/base.css';
import './styles/sidebar.css';
import './styles/map.css';

import { api } from './api/client';
import type { AirwayLevel } from './api/types';
import { PlannerController } from './app/controller';
import { BASEMAPS, DEFAULT_BASEMAP } from './map/basemaps';
import { MapView } from './map/mapView';
import { NetworkLoader } from './map/networkLoader';
import { NotamLayer } from './map/notamLayer';
import { attachAirportAutocomplete, isSuggesting } from './ui/autocomplete';
import { byId, escapeHtml } from './ui/dom';
import { showError } from './ui/messages';
import { ProcedureSelect } from './ui/procedureSelect';
import { RoutePanel } from './ui/routePanel';
import { RunwayPicker } from './ui/runwayPicker';

const ctl = new PlannerController();

// ---- mapa
const map = new MapView(byId('map'), byId('svg') as unknown as SVGSVGElement);
const network = new NetworkLoader(map);
const notams = new NotamLayer(map.map);

const tiles = byId<HTMLSelectElement>('tiles');
tiles.innerHTML = Object.entries(BASEMAPS)
  .map(([k, b]) => `<option value="${k}">${escapeHtml(b.label)}</option>`).join('');
tiles.value = DEFAULT_BASEMAP;
tiles.addEventListener('change', () => map.setBasemap(tiles.value));

byId('lbl-toggle').addEventListener('click', (e) => {
  const on = !map.labelsOn;
  (e.currentTarget as HTMLElement).setAttribute('aria-pressed', String(on));
  map.setLabels(on);
  network.refresh();
});

// ---- painel
ctl.views = {
  map,
  panel: new RoutePanel({
    replaceFix: (k, ident, input) => void ctl.replaceFix(k, ident, input),
    insertAfter: (k) => void ctl.insertAfter(k),
    remove: (k) => void ctl.remove(k),
    toggleDct: (k) => ctl.toggleDct(k),
    hover: (k) => ctl.hoverLeg(k),
  }),
  runways: new RunwayPicker((side, rwy) => void ctl.pickRunway(side, rwy)),
  sid: new ProcedureSelect('sid', 'sid-box', (key) => void ctl.setProcedure('sid', key)),
  star: new ProcedureSelect('star', 'star-box', (key) => void ctl.setProcedure('star', key)),
};

// ---- formulario
const origin = byId<HTMLInputElement>('o');
const destination = byId<HTMLInputElement>('d');
const levelSel = byId<HTMLSelectElement>('level');
const level = () => (levelSel.value || null) as AirwayLevel | null;
levelSel.addEventListener('change', () => {
  network.level = level();
  network.refresh();
  void ctl.setLevel(level());
});
attachAirportAutocomplete(origin, byId('aco'));
attachAirportAutocomplete(destination, byId('acd'));

byId('route-form').addEventListener('submit', (e) => {
  e.preventDefault();
  if (isSuggesting()) return;
  void ctl.calculate(origin.value, destination.value, level());
});
byId('swap').addEventListener('click', () => {
  [origin.value, destination.value] = [destination.value, origin.value];
});
// fecha as sugestoes ao interagir fora do campo, senao o painel cobre o botao
document.addEventListener('pointerdown', (e) => {
  if ((e.target as HTMLElement).closest('.field')) return;
  document.querySelectorAll('.ac.on').forEach((x) => x.classList.remove('on'));
}, true);

// link direto: ?o=SBGR&d=SBBR[&level=H|L]
const params = new URLSearchParams(location.search);
if (params.get('level') === 'H' || params.get('level') === 'L') {
  levelSel.value = params.get('level')!;
  network.level = level();
}
if (params.get('o') && params.get('d')) {
  origin.value = params.get('o')!;
  destination.value = params.get('d')!;
  void ctl.calculate(origin.value, destination.value, level());
}

// ---- dados de apoio
api.meta()
  .then((m) => { byId('cyc').textContent = m.cycle ?? '—'; })
  .catch((e) => showError(e.message));
api.notams().then((a) => notams.set(a)).catch(() => {});
api.specialAreas().then((a) => map.setSpecialAreas(a)).catch(() => {});
