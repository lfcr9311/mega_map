// Espelho de backend/src/fmsnav/api/schemas.py — mantenha os dois em sincronia.

export type AltDesc = '+' | '-' | '' | 'B';

/** H = so aerovias de alta (designador comeca com U), L = so baixa */
export type AirwayLevel = 'H' | 'L';

export interface Altitude {
  ft: number;
  desc: AltDesc;
}

/** kind: W aerovia, A aeroporto, P procedimento, V virtual (desvio) */
export interface Point {
  id: number | null;
  ident: string;
  lat: number;
  lon: number;
  kind: string;
  altitude?: Altitude | null;
}

export interface PointRef {
  id?: number | null;
  ident?: string;
  lat?: number;
  lon?: number;
}

export interface RouteLeg {
  airway: string;
  km: number;
}

export interface Procedure {
  key: string;
  name: string;
  transition: string;
  label: string;
  runway_transitions: string[];
}

export interface ChosenProcedure extends Procedure {
  chain: Point[];
}

export interface RouteIn {
  origin: string;
  destination: string;
  runway_dep?: string | null;
  runway_arr?: string | null;
  /** chave da opcao, "auto" ou null */
  sid?: string | null;
  star?: string | null;
  avoid_notams?: boolean;
  level?: AirwayLevel | null;
  edited?: { path: PointRef[]; fallback: [number, number] } | null;
}

export interface RouteOut {
  points: Point[];
  legs: RouteLeg[];
  km: number;
  direct_km: number;
  sid: ChosenProcedure | null;
  star: ChosenProcedure | null;
  avoidance_applied: boolean;
  warnings: string[];
}

export interface AnnotateOut {
  points: Point[];
  legs: RouteLeg[];
  km: number;
}

export interface Runway {
  ident: string;
  bearing: number;
  length_ft: number;
  elevation_ft: number;
}

export interface Airport {
  icao: string;
  lat: number;
  lon: number;
  procedures: number;
}

export interface AirportDetail extends Airport {
  runways: Runway[];
}

export interface Network {
  edges: [number, number, number, number][];
  fixes: [string, number, number][];
  truncated: boolean;
}

export interface NotamArea {
  number: string;
  fir: string;
  status: string;
  text: string;
  polygon: [number, number][];
}

/** repasse cru do rpl_back */
export interface SpecialArea {
  name?: string;
  type?: string;
  typeLabel?: string;
  coords_latlon?: [number, number][];
}

export interface Meta {
  cycle: string | null;
  area: string[] | null;
  built_at: string | null;
  nodes: number;
  edges: number;
  airports: number;
}

export interface Bbox {
  south: number;
  west: number;
  north: number;
  east: number;
}
