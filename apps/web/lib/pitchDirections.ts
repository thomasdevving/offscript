import type { CandidateAction, MatchStateSnapshot } from "@offscript/contracts";

export type Point = [number, number];
export type Motion = "pass" | "dribble" | "shoot" | "run";

/** Stable option references: observed choice is ACT, alternatives follow their list order. */
export function candidateBadges(actions: readonly Pick<CandidateAction, "action_id" | "is_actual">[]) {
  let rank = 0;
  return new Map(actions.map((a) => [a.action_id, a.is_actual ? "ACT" : String(++rank)]));
}

/** All coordinates stay in the world frame, including when the team attacks left. */
export function actionDirection(action: CandidateAction, snapshot: MatchStateSnapshot) {
  const actor = snapshot.players.find((p) => p.player_id === action.actor_id);
  if (!actor) return null;
  const receiver = snapshot.players.find((p) => p.player_id === action.target_player_id);
  const attack = snapshot.attack_direction[actor.team_id] === -1 ? -1 : 1;
  const from: Point = [actor.x, actor.y];
  const to: Point | null = action.action_type === "shoot" ? [attack === 1 ? 105 : 0, 34]
    : action.target_x != null && action.target_y != null ? [action.target_x, action.target_y]
      : receiver ? [receiver.x, receiver.y] : null;
  if (!to) return null;
  const dx = to[0] - from[0], dy = to[1] - from[1];
  const distance = Math.hypot(dx, dy);
  if (distance < 0.2) return null;
  const longitudinal = dx * attack;
  // Left/right in generated action names is player-relative. The icon shows the
  // precise screen direction; the caption only describes progress towards goal.
  const progress = Math.abs(longitudinal) > distance * 0.25 ? longitudinal > 0 ? "Forward" : "Back" : "Across";
  return { from, to, distance, angle: Math.atan2(dy, dx) * 180 / Math.PI,
    description: `${progress} · ${Math.round(distance)} m` };
}

/** Shared by 2D and 3D: the line pattern describes the action, colour describes its role. */
export function directionStyle(kind: string, motion?: Motion) {
  const color = kind === "actual" ? "#f8fafc" : kind === "defense" ? "#fb923c"
    : kind === "recommended" ? "#8fca7c" : kind === "selected" ? "#d4ee8f" : "#cfe2b4";
  const dash: [number, number] | undefined = kind === "actual" ? [1.2, 1]
    : kind === "defense" || motion === "run" ? [0.6, 1]
      : motion === "pass" ? [2.1, 1.1] : motion === "dribble" ? [0.35, 0.85]
        : kind === "alternative" ? [1, 1] : undefined;
  return { color, dash };
}
