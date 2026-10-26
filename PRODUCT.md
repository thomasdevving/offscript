# OFFSCRIPT

OFFSCRIPT lets football fans, analysts and broadcasters explore whether a different
decision could have produced a better outcome. It uses synthetic matches and an
explicit simulation model. Existing product detail lives in [README.md](README.md),
[Multiverse](docs/multiverse.md) and [limitations](docs/limitations.md).

## Product constraints

- Observed synthetic events and simulated alternatives remain distinguishable.
- Estimates are model outputs, not predictions validated against real football.
- A displayed continuation is one sample, never a claim about what would have happened.
- Alternatives start from the same frozen decision state. Rewinding restores that state.
- Microsoft Foundry agents and the deterministic policy planner are labelled accurately.
- The frontend must preserve existing simulation, validation and comparison behavior.

## Football Multiverse

The user chooses an action, or asks the agents to recommend or play actions. An
attacking agent and defending agent evaluate alternatives. The user can watch a
continuation, rewind, create another branch and compare branches.

This is an operating interface: the pitch and the available decision lead. Action
directions must remain clear in 2D and 3D, including when a team attacks left.
Route patterns distinguish passes, dribbles, shots and defensive movement without
depending on colour alone. Option previews must not submit a decision.

## Interface commitments

- Preserve the existing OFFSCRIPT logo, green palette, typography and light/dark themes.
- On desktop, place the pitch beside the decision panel, with playback and the
  branch map directly below the pitch in the left column. Keep a 14px gap between
  playback and the branch map.
- On mobile, use one column with the decision and analysis panel before the branch
  map, and contain branch-map scrolling within its viewport.
- Keep language and theme controls at the right of the Live match / Multiverse row.
- Keep playback directly below the pitch legend; a taller analysis panel must not
  push playback away from the pitch.
- Draw route labels above every route line, with opaque backgrounds, so crossing
  directions cannot obscure another action's text.
- In Multiverse decisions, use compact numbered route markers connected to their
  endpoints. Match each number to the corresponding option; keep full action
  names in the option list so text blocks do not obscure neighbouring routes.
- Derive attack direction from the acting player's team and keep its cue below the
  field, outside the outcome overlay, so it remains visible when an outcome card is
  present.

The image-generated Multiverse sketch guides composition. It does not authorize
invented features, player information, metrics or model-validation claims.

Live match decision analysis uses the same route patterns, intermediate chevrons,
numbered endpoint markers, direction icons and legend as Multiverse. Its numbered
options preview routes on hover or focus without requesting a trajectory; choosing
an option still opens the existing simulated continuation. ACT identifies the
observed choice. The full pitch and playback remain together in the left column.

The landing hero field moves only while a mouse moves over its scene and holds
its last pose when the pointer leaves. Keep the field, routes and decision marker
still at rest; touch input and reduced-motion preferences do not trigger its tilt.
