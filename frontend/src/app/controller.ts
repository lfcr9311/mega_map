import { api, ApiError } from '../api/client';
import type { AirwayLevel, AnnotateOut, PointRef, RouteIn } from '../api/types';
import type { MapView } from '../map/mapView';
import { byId } from '../ui/dom';
import { clearError, showError, showWarnings } from '../ui/messages';
import type { ProcedureSelect } from '../ui/procedureSelect';
import type { RoutePanel } from '../ui/routePanel';
import type { RunwayPicker, RunwaySide } from '../ui/runwayPicker';
import { coreFallback, legKey, newRoute, type RouteState, toRef } from './state';

export interface Views {
  map: MapView;
  panel: RoutePanel;
  runways: RunwayPicker;
  sid: ProcedureSelect;
  star: ProcedureSelect;
}

/**
 * Fluxo do planejador:
 *   calcular        -> rota base (sem SID/STAR) + botoes de pista
 *   escolher pistas -> SID/STAR automaticas (melhor combinacao) + dropdowns
 *   trocar SID/STAR -> recalcula; se a rota foi editada, preserva o miolo
 *   editar a tabela -> /route/annotate (sem re-rotear)
 */
export class PlannerController {
  private route: RouteState | null = null;
  /** descarta respostas de pedidos que ja foram superados */
  private seq = 0;
  views!: Views;

  async calculate(origin: string, destination: string, level: AirwayLevel | null) {
    clearError();
    showWarnings([]);
    origin = origin.trim().toUpperCase();
    destination = destination.trim().toUpperCase();
    if (!origin || !destination) return showError('Informe origem e destino.');

    const { runways, sid, star, panel } = this.views;
    runways.hide();
    sid.hide();
    star.hide();
    this.route = newRoute(origin, destination, level);
    if (!(await this.requestRoute())) return;

    try {
      const [dep, arr] = await Promise.all([api.airport(origin), api.airport(destination)]);
      runways.render(dep.runways, arr.runways);
      panel.renderDestinationRunways(arr.runways);
    } catch (e) {
      this.fail(e);
    }
  }

  async pickRunway(side: RunwaySide, runway: string) {
    const r = this.route;
    if (!r) return;
    if (side === 'dep') r.runwayDep = runway;
    else r.runwayArr = runway;
    if (!r.runwayDep || !r.runwayArr) return;

    r.sid = r.star = 'auto';
    r.edited = false;
    if (!(await this.requestRoute())) return;
    try {
      const [sids, stars] = await Promise.all([
        api.procedures(r.origin, 'SID'),
        api.procedures(r.destination, 'STAR'),
      ]);
      this.views.sid.fill(sids, r.sid);
      this.views.star.fill(stars, r.star);
    } catch (e) {
      this.fail(e);
    }
  }

  /** troca o nivel de aerovia e refaz o en-route (descarta edicoes manuais) */
  async setLevel(level: AirwayLevel | null) {
    const r = this.route;
    if (!r) return;
    r.level = level;
    r.edited = false;
    r.dct.clear();
    await this.requestRoute();
  }

  async setProcedure(kind: 'sid' | 'star', key: string | null) {
    if (!this.route) return;
    this.route[kind] = key;
    await this.requestRoute();
  }

  // ------------------------------------------------------------ edicao

  async replaceFix(k: number, ident: string, input: HTMLInputElement) {
    const r = this.route;
    if (!r) return;
    const refs = r.points.map(toRef);
    refs[k + 1] = { ident: ident.trim() };
    const out = await this.annotate(refs, input);
    if (!out) return;
    input.classList.remove('bad');
    // a troca desfaz DCT das duas pernas afetadas (agora sao outros pares)
    const old = r.points[k + 1];
    r.dct.delete(legKey(r.points[k], old));
    if (r.points[k + 2]) r.dct.delete(legKey(old, r.points[k + 2]));
    this.applyEdit(out);
  }

  async insertAfter(k: number) {
    const r = this.route;
    if (!r) return;
    // copia do fixo de chegada como ponto novo, pronto para editar
    const refs = r.points.map(toRef);
    refs.splice(k + 1, 0, refs[k + 1]);
    const out = await this.annotate(refs);
    if (!out) return;
    this.applyEdit(out);
    this.views.panel.focusFix(k + 1);
  }

  async remove(k: number) {
    const r = this.route;
    if (!r || r.points.length <= 2 || k + 1 >= r.points.length - 1) return;
    const removed = r.points[k + 1];
    r.dct.delete(legKey(r.points[k], removed));
    if (r.points[k + 2]) r.dct.delete(legKey(removed, r.points[k + 2]));
    const refs = r.points.map(toRef);
    refs.splice(k + 1, 1);
    const out = await this.annotate(refs);
    if (out) this.applyEdit(out);
  }

  toggleDct(k: number) {
    const r = this.route;
    if (!r) return;
    const key = legKey(r.points[k], r.points[k + 1]);
    if (!r.dct.delete(key)) r.dct.add(key);
    this.render();
  }

  hoverLeg(k: number | null) {
    this.views.map.highlightLeg(k);
  }

  // ---------------------------------------------------------- internos

  private isDct = (k: number) => {
    const r = this.route;
    return !!r && k + 1 < r.points.length && r.dct.has(legKey(r.points[k], r.points[k + 1]));
  };

  private async requestRoute(): Promise<boolean> {
    const r = this.route!;
    const mine = ++this.seq;
    const body: RouteIn = {
      origin: r.origin,
      destination: r.destination,
      runway_dep: r.runwayDep,
      runway_arr: r.runwayArr,
      sid: r.sid,
      star: r.star,
      avoid_notams: true,
      level: r.level,
      edited: r.edited ? { path: r.points.map(toRef), fallback: coreFallback(r) } : null,
    };
    const go = byId<HTMLButtonElement>('go');
    go.disabled = true;
    try {
      const res = await api.route(body);
      if (mine !== this.seq) return false;
      clearError();
      r.points = res.points;
      r.legs = res.legs;
      r.km = res.km;
      r.directKm = res.direct_km;
      r.sidChain = res.sid?.chain ?? [];
      r.starChain = res.star?.chain ?? [];
      r.altitudes = new Map(res.points.filter((p) => p.id != null && p.altitude).map((p) => [p.id!, p.altitude!]));
      // "auto" vira a escolha concreta, para os dropdowns e as proximas trocas
      if (r.sid === 'auto') r.sid = res.sid?.key ?? null;
      if (r.star === 'auto') r.star = res.star?.key ?? null;
      showWarnings(res.warnings);
      this.render();
      this.views.map.fitRoute();
      return true;
    } catch (e) {
      if (mine === this.seq) this.fail(e);
      return false;
    } finally {
      if (mine === this.seq) go.disabled = false;
    }
  }

  private async annotate(refs: PointRef[], input?: HTMLInputElement): Promise<AnnotateOut | null> {
    try {
      clearError();
      return await api.annotate(refs, this.route?.level ?? null);
    } catch (e) {
      input?.classList.add('bad');
      showError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }

  private applyEdit(out: AnnotateOut) {
    const r = this.route!;
    r.points = out.points.map((p) => ({ ...p, altitude: p.id != null ? r.altitudes.get(p.id) ?? null : null }));
    r.legs = out.legs;
    r.km = out.km;
    r.edited = true;
    this.render();
    this.views.map.fitRoute();
  }

  private render() {
    const r = this.route!;
    this.views.panel.render(r, this.isDct);
    this.views.map.setRoute({ points: r.points, sidChain: r.sidChain, starChain: r.starChain, isDct: this.isDct });
    byId('legend').classList.add('on');
    byId('hint').hidden = true;
  }

  private fail(e: unknown) {
    showError(e instanceof ApiError || e instanceof Error ? e.message : String(e));
    if (!this.route?.points.length) {
      this.views.panel.hide();
      this.views.map.setRoute(null);
    }
  }
}
