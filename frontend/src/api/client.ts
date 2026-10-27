import type {
  Airport, AirportDetail, AirwayLevel, AnnotateOut, Bbox, Meta, Network, NotamArea, PointRef,
  Procedure, RouteIn, RouteOut, SpecialArea,
} from './types';

const BASE = import.meta.env.VITE_API_BASE ?? '/api';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** indice do ponto invalido, quando o erro vem de /route/annotate */
    readonly index: number | null = null,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    });
  } catch {
    throw new ApiError(0, 'API indisponível. O backend está rodando? (fmsnav serve)');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    if (detail && typeof detail === 'object' && 'message' in detail) {
      throw new ApiError(res.status, String(detail.message), detail.index ?? null);
    }
    throw new ApiError(res.status, typeof detail === 'string' ? detail : `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

const qs = (params: Record<string, string | number | boolean | null | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v != null) p.set(k, String(v));
  return p.toString();
};

const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) });

export const api = {
  meta: () => request<Meta>('/meta'),

  searchAirports: (q: string, limit = 8) =>
    request<Airport[]>(`/airports?${qs({ q, limit })}`),

  airport: (icao: string) => request<AirportDetail>(`/airports/${encodeURIComponent(icao)}`),

  procedures: (icao: string, kind: 'SID' | 'STAR', runway?: string | null) =>
    request<Procedure[]>(`/airports/${encodeURIComponent(icao)}/procedures?${qs({ kind, runway })}`),

  network: (bbox: Bbox, fixes: boolean, level: AirwayLevel | null, signal?: AbortSignal) =>
    request<Network>(`/network?${qs({ ...bbox, fixes, level })}`, { signal }),

  route: (body: RouteIn) => request<RouteOut>('/route', post(body)),

  annotate: (points: PointRef[], level: AirwayLevel | null) =>
    request<AnnotateOut>('/route/annotate', post({ points, level })),

  notams: () => request<NotamArea[]>('/notams'),

  specialAreas: () => request<SpecialArea[]>('/special-areas'),
};
