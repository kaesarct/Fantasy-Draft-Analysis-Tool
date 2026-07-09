import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private base = environment.apiUrl;

  constructor(private http: HttpClient) {}

  // ── Players ────────────────────────────────────────────────
  getPlayers(search?: string, role?: string, teamId?: number, seasonId?: number): Observable<any[]> {
    let params = new HttpParams();
    if (search) params = params.set('search', search);
    if (role) params = params.set('role', role);
    if (teamId) params = params.set('team_id', teamId);
    if (seasonId) params = params.set('season_id', seasonId);
    return this.http.get<any[]>(`${this.base}/players`, { params });
  }

  getPlayer(id: number): Observable<any> {
    return this.http.get<any>(`${this.base}/players/${id}`);
  }

  getPlayerHistory(id: number, seasonId?: number): Observable<any[]> {
    let params = new HttpParams();
    if (seasonId) params = params.set('season_id', seasonId);
    return this.http.get<any[]>(`${this.base}/players/${id}/history`, { params });
  }

  getPlayerScores(id: number, seasonId?: number): Observable<any[]> {
    let params = new HttpParams();
    if (seasonId) params = params.set('season_id', seasonId);
    return this.http.get<any[]>(`${this.base}/players/${id}/scores`, { params });
  }

  // ── Allenatori ─────────────────────────────────────────────
  getAllenatori(): Observable<any[]> {
    return this.http.get<any[]>(`${this.base}/allenatori`);
  }

  getAllenatore(id: number): Observable<any> {
    return this.http.get<any>(`${this.base}/allenatori/${id}`);
  }

  createAllenatore(data: { username: string; display_name: string; email?: string }): Observable<any> {
    return this.http.post(`${this.base}/allenatori`, data);
  }

  updateAllenatore(id: number, data: { display_name?: string; email?: string; is_active?: boolean }): Observable<any> {
    return this.http.patch(`${this.base}/allenatori/${id}`, data);
  }

  assignCoach(teamId: number, allenatoreId: number, isPrimary = true): Observable<any> {
    return this.http.post(`${this.base}/fanta-teams/${teamId}/coaches`, {
      allenatore_id: allenatoreId,
      is_primary: isPrimary,
    });
  }

  removeCoach(teamId: number, allenatoreId: number): Observable<any> {
    return this.http.delete(`${this.base}/fanta-teams/${teamId}/coaches/${allenatoreId}`);
  }

  // ── FantaTeams ─────────────────────────────────────────────
  getFantaTeams(seasonId?: number, leagueLevel?: string): Observable<any[]> {
    let params = new HttpParams();
    if (seasonId) params = params.set('season_id', seasonId);
    if (leagueLevel) params = params.set('league_level', leagueLevel);
    return this.http.get<any[]>(`${this.base}/fanta-teams`, { params });
  }

  getFantaTeam(id: number): Observable<any> {
    return this.http.get<any>(`${this.base}/fanta-teams/${id}`);
  }

  // ── League / Seasons ───────────────────────────────────────
  getSeasons(): Observable<any[]> {
    return this.http.get<any[]>(`${this.base}/seasons`);
  }

  setCurrentSeason(seasonId: number): Observable<any> {
    return this.http.patch(`${this.base}/seasons/${seasonId}/set-current`, null);
  }

  getSeasonCompetitions(seasonId: number): Observable<any[]> {
    return this.http.get<any[]>(`${this.base}/seasons/${seasonId}/competitions`);
  }

  getSeasonStandings(seasonId: number, compType?: string, matchDay?: number): Observable<any[]> {
    let params = new HttpParams();
    if (compType) params = params.set('comp_type', compType);
    if (matchDay) params = params.set('match_day', matchDay);
    return this.http.get<any[]>(`${this.base}/seasons/${seasonId}/standings`, { params });
  }

  getCompetitionStandings(compId: number, matchDay?: number): Observable<any[]> {
    let params = new HttpParams();
    if (matchDay) params = params.set('match_day', matchDay);
    return this.http.get<any[]>(`${this.base}/competitions/${compId}/standings`, { params });
  }

  getCompetitionMatches(compId: number, matchDay?: number): Observable<any[]> {
    let params = new HttpParams();
    if (matchDay) params = params.set('match_day', matchDay);
    return this.http.get<any[]>(`${this.base}/competitions/${compId}/matches`, { params });
  }

  // ── Matches ────────────────────────────────────────────────
  getNextMatches(): Observable<any[]> {
    return this.http.get<any[]>(`${this.base}/matches`);
  }

  // ── Injuries ───────────────────────────────────────────────
  getInjuries(seasonId?: number, activeOnly: boolean = true): Observable<any[]> {
    let params = new HttpParams().set('active_only', activeOnly);
    if (seasonId) params = params.set('season_id', seasonId);
    return this.http.get<any[]>(`${this.base}/injuries`, { params });
  }

  createInjury(data: any): Observable<any> {
    return this.http.post(`${this.base}/injuries`, data);
  }

  recoverPlayer(injuryId: number, confirmedReturn: string): Observable<any> {
    return this.http.patch(`${this.base}/injuries/${injuryId}/recover`, null, {
      params: new HttpParams().set('confirmed_return', confirmedReturn),
    });
  }

  deleteInjury(id: number): Observable<any> {
    return this.http.delete(`${this.base}/injuries/${id}`);
  }

  checkInjuryRecovery(seasonId: number, matchDay?: number): Observable<any> {
    let params = new HttpParams().set('season_id', seasonId);
    if (matchDay !== undefined && matchDay !== null) params = params.set('match_day', matchDay);
    return this.http.post(`${this.base}/injuries/check-recovery`, null, { params });
  }

  // ── Sync ───────────────────────────────────────────────────
  syncPrices(seasonId: number): Observable<any> {
    return this.http.post(`${this.base}/sync/prices`, null, {
      params: new HttpParams().set('season_id', seasonId),
    });
  }

  syncVotes(seasonId: number, matchDay?: number): Observable<any> {
    let params = new HttpParams().set('season_id', seasonId);
    if (matchDay) params = params.set('match_day', matchDay);
    return this.http.post(`${this.base}/sync/votes`, null, { params });
  }

  syncFormazioni(seasonId: number): Observable<any> {
    return this.http.post(`${this.base}/sync/formazioni`, null, {
      params: new HttpParams().set('season_id', seasonId),
    });
  }

  // ── History (storico stagioni) ─────────────────────────────
  importSeasonHistory(seasonId: number, dataType: 'stats' | 'prices', force = false): Observable<any> {
    return this.http.post(`${this.base}/history/seasons/${seasonId}/import`, null, {
      params: new HttpParams().set('data_type', dataType).set('force', force),
    });
  }

  getSeasonStats(seasonId: number, search?: string): Observable<any[]> {
    let params = new HttpParams();
    if (search) params = params.set('search', search);
    return this.http.get<any[]>(`${this.base}/history/seasons/${seasonId}/stats`, { params });
  }

  getSeasonPrices(seasonId: number, search?: string): Observable<any[]> {
    let params = new HttpParams();
    if (search) params = params.set('search', search);
    return this.http.get<any[]>(`${this.base}/history/seasons/${seasonId}/prices`, { params });
  }

  getSeasonHistoryCsvUrl(seasonId: number, dataType: 'stats' | 'prices'): string {
    return `${this.base}/history/seasons/${seasonId}/${dataType}/csv`;
  }
}
