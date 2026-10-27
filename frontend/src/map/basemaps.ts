// Tiles gratuitos e sem chave. tile.openstreetmap.org bloqueia (403) uso fora
// de sites cadastrados e o Carto passou a exigir chave — por isso Esri.
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/';
const ESRI_ATTR = '&copy; Esri, HERE, Garmin, OpenStreetMap';

export interface Basemap {
  label: string;
  url: string;
  attribution: string;
  maxZoom: number;
  /** mapa ja escuro: nao inverte as cores */
  dark: boolean;
}

export const BASEMAPS: Record<string, Basemap> = {
  streets: { label: 'Esri Ruas', url: `${ESRI}World_Street_Map/MapServer/tile/{z}/{y}/{x}`, attribution: ESRI_ATTR, maxZoom: 19, dark: false },
  dark: { label: 'Esri Escuro', url: `${ESRI}Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`, attribution: ESRI_ATTR, maxZoom: 16, dark: true },
  topo: { label: 'Esri Topográfico', url: `${ESRI}World_Topo_Map/MapServer/tile/{z}/{y}/{x}`, attribution: ESRI_ATTR, maxZoom: 19, dark: false },
  sat: { label: 'Satélite (Esri)', url: `${ESRI}World_Imagery/MapServer/tile/{z}/{y}/{x}`, attribution: '&copy; Esri, Maxar', maxZoom: 18, dark: true },
};

export const DEFAULT_BASEMAP = 'streets';
