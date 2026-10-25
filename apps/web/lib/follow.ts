import type { DecisionPoint, MatchInfo } from "@offscript/contracts";

/** Optional personalisation: the team or player a fan follows. null = follow everyone (the default). */
export type Follow = { kind: "team" | "player"; id: string } | null;

export const FOLLOW_KEY = "offscript.follow";

export function encodeFollow(f: Follow): string {
  return f ? `${f.kind}:${f.id}` : "";
}

export function decodeFollow(v: string | null | undefined): Follow {
  const m = /^(team|player):(.+)$/.exec(v ?? "");
  return m ? { kind: m[1] as "team" | "player", id: m[2] } : null;
}

/** The follow choice only applies when its team or player is part of this match. */
export function activeFollow(f: Follow, match: MatchInfo | null): Follow {
  if (!f || !match) return null;
  if (f.kind === "team") return [match.home.team_id, match.away.team_id].includes(f.id) ? f : null;
  return match.players.some((p) => p.player_id === f.id) ? f : null;
}

export function teamOf(playerId: string, match: MatchInfo | null): string | undefined {
  return match?.players.find((p) => p.player_id === playerId)?.team_id;
}

/** How a decision relates to the fan's choice: their team/player, the opponent, or not followed. */
export function followRelation(f: Follow, d: DecisionPoint, match: MatchInfo | null): "team" | "player" | "opponent" | null {
  const a = activeFollow(f, match);
  if (!a) return null;
  if (a.kind === "player") return d.actor_id === a.id ? "player" : null;
  const team = teamOf(d.actor_id, match);
  if (!team) return null;
  return team === a.id ? "team" : "opponent";
}

/** Whether a decision should pause the match for this fan: every decision unless they follow someone. */
export function pausesFor(f: Follow, d: DecisionPoint, match: MatchInfo | null): boolean {
  const a = activeFollow(f, match);
  if (!a) return true;
  const r = followRelation(a, d, match);
  return r === "team" || r === "player";
}

export function followLabel(f: Follow, match: MatchInfo | null): string | null {
  const a = activeFollow(f, match);
  if (!a || !match) return null;
  if (a.kind === "team") return [match.home, match.away].find((t) => t.team_id === a.id)?.name ?? null;
  return match.players.find((p) => p.player_id === a.id)?.name ?? null;
}
