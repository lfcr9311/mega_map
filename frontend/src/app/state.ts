import type { AirwayLevel, Altitude, Point, PointRef, RouteLeg } from '../api/types';

/** Rota em tela. O backend calcula; edicoes manuais mudam `points` e marcam `edited`. */
export interface RouteState {
  origin: string;
  destination: string;
  runwayDep: string | null;
  runwayArr: string | null;
  /** chave da SID/STAR escolhida, "auto" ou null */
  sid: string | null;
  star: string | null;
  /** restringe o en-route a aerovias de alta ou baixa (null = todas) */
  level: AirwayLevel | null;
  points: Point[];
  legs: RouteLeg[];
  km: number;
  directKm: number;
  /** cadeias dos procedimentos para desenho: [origem, ...SID] e [...STAR, destino] */
  sidChain: Point[];
  starChain: Point[];
  /** pernas forcadas a DCT (linha reta), por legKey */
  dct: Set<string>;
  /** rota editada a mao: trocar SID/STAR preserva o miolo en-route */
  edited: boolean;
  /** restricoes de altitude dos procedimentos, por id de no */
  altitudes: Map<number, Altitude>;
}

export function newRoute(origin: string, destination: string, level: AirwayLevel | null): RouteState {
  return {
    origin, destination, runwayDep: null, runwayArr: null, sid: null, star: null, level,
    points: [], legs: [], km: 0, directKm: 0, sidChain: [], starChain: [],
    dct: new Set(), edited: false, altitudes: new Map(),
  };
}

export const pointKey = (p: Point): string =>
  p.id != null ? `n${p.id}` : `v${p.ident}@${p.lat},${p.lon}`;

export const legKey = (a: Point, b: Point): string => {
  const ka = pointKey(a), kb = pointKey(b);
  return ka < kb ? `${ka}|${kb}` : `${kb}|${ka}`;
};

export const toRef = (p: Point): PointRef =>
  p.id != null ? { id: p.id } : { ident: p.ident, lat: p.lat, lon: p.lon };

/** Intervalo [ini, fim) do miolo en-route, usado se as novas pontas nao estao na rota. */
export function coreFallback(r: RouteState): [number, number] {
  const n = r.points.length;
  const start = r.sidChain.length ? r.sidChain.length - 1 : 1;
  const end = r.starChain.length ? n - r.starChain.length : n - 1;
  return [start, end];
}

export const isVirtual = (p: Point) => p.id == null;
