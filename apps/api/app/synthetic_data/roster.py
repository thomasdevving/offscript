"""Fictional teams and players. Every name and colour here is invented for PARALLEL."""

from __future__ import annotations

from ..models.match import Player, Team

HOME = Team(
    team_id="HCF",
    name="Harbour City FC",
    short_name="HCF",
    color_primary="#38BDF8",
    color_secondary="#0B1220",
    formation="4-2-3-1",
)
AWAY = Team(
    team_id="NVA",
    name="Northvale Athletic",
    short_name="NVA",
    color_primary="#F59E0B",
    color_secondary="#1C1917",
    formation="4-3-3",
)

# (id, name, short, number, role, max_speed, accel, reaction, technique, finishing, dribbling, starting)
_HOME = [
    ("H01", "Elias Brandvold", "Brandvold", 1, "GK", 7.4, 4.5, 0.24, 0.62, 0.10, 0.25, True),
    ("H02", "Kofi Annerud", "Annerud", 2, "RB", 9.1, 6.0, 0.27, 0.68, 0.30, 0.58, True),
    ("H04", "Mateo Lindqvist-Sa", "Lindqvist-Sa", 4, "CB", 8.4, 5.2, 0.26, 0.66, 0.28, 0.40, True),
    ("H05", "Jonah Okereke-Voss", "Okereke-Voss", 5, "CB", 8.6, 5.3, 0.25, 0.62, 0.32, 0.38, True),
    ("H03", "Ilias Marchetti", "Marchetti", 3, "LB", 9.0, 6.1, 0.27, 0.70, 0.30, 0.60, True),
    ("H06", "Sander Quist", "Quist", 6, "DM", 8.3, 5.5, 0.24, 0.80, 0.40, 0.55, True),
    ("H08", "Luca Ferreira-Holm", "Ferreira-Holm", 8, "CM", 8.7, 5.8, 0.25, 0.84, 0.52, 0.68, True),
    ("H10", "Ravi Castellane", "Castellane", 10, "AM", 8.9, 6.2, 0.23, 0.86, 0.70, 0.82, True),
    ("H07", "Theo Mbeki-Larsen", "Mbeki-Larsen", 7, "RW", 9.6, 6.6, 0.25, 0.76, 0.66, 0.80, True),
    ("H11", "Dario Kestrel", "Kestrel", 11, "LW", 9.4, 6.4, 0.26, 0.74, 0.64, 0.78, True),
    ("H09", "Ade Valcourt", "Valcourt", 9, "ST", 9.0, 6.0, 0.24, 0.70, 0.82, 0.66, True),
    ("H14", "Milo Arendt", "Arendt", 14, "CM", 8.5, 5.6, 0.26, 0.76, 0.48, 0.62, False),
    ("H16", "Yusuf Tanaka-Reid", "Tanaka-Reid", 16, "ST", 9.2, 6.1, 0.25, 0.66, 0.74, 0.70, False),
    ("H18", "Pim Oosterhuis", "Oosterhuis", 18, "RW", 9.3, 6.3, 0.26, 0.70, 0.60, 0.74, False),
]
_AWAY = [
    ("A01", "Bram Hollister", "Hollister", 1, "GK", 7.3, 4.4, 0.23, 0.60, 0.10, 0.22, True),
    ("A02", "Caius Wendt", "Wendt", 2, "RB", 9.0, 6.0, 0.27, 0.66, 0.28, 0.56, True),
    ("A04", "Oskar Renner", "Renner", 4, "CB", 8.5, 5.2, 0.25, 0.64, 0.30, 0.36, True),
    ("A05", "Malik Durand-Sowe", "Durand-Sowe", 5, "CB", 8.8, 5.4, 0.24, 0.60, 0.26, 0.38, True),
    ("A03", "Finn Achterberg", "Achterberg", 3, "LB", 8.9, 6.0, 0.27, 0.68, 0.28, 0.58, True),
    ("A06", "Leon Varga", "Varga", 6, "DM", 8.4, 5.6, 0.24, 0.78, 0.38, 0.52, True),
    ("A08", "Nico Albescu", "Albescu", 8, "CM", 8.6, 5.7, 0.25, 0.82, 0.50, 0.64, True),
    ("A10", "Samir El-Haddou", "El-Haddou", 10, "CM", 8.8, 6.0, 0.24, 0.85, 0.62, 0.80, True),
    ("A07", "Jasper Thornquist", "Thornquist", 7, "RW", 9.5, 6.5, 0.25, 0.74, 0.64, 0.78, True),
    ("A11", "Emeka Rossi-Blane", "Rossi-Blane", 11, "LW", 9.4, 6.4, 0.26, 0.72, 0.62, 0.76, True),
    ("A09", "Viktor Saelens", "Saelens", 9, "ST", 9.1, 6.1, 0.24, 0.68, 0.80, 0.64, True),
    ("A12", "Ruben Ilic-Moor", "Ilic-Moor", 12, "CB", 8.3, 5.0, 0.26, 0.60, 0.24, 0.34, False),
    ("A15", "Dean Kowalczyk-Ames", "Kowalczyk-Ames", 15, "CM", 8.6, 5.7, 0.25, 0.76, 0.46, 0.60, False),
]


def _build(rows: list[tuple], team_id: str) -> list[Player]:
    return [
        Player(
            player_id=r[0], team_id=team_id, name=r[1], short_name=r[2], shirt_number=r[3], role=r[4],
            max_speed_mps=r[5], acceleration_mps2=r[6], reaction_time_s=r[7], technique=r[8], finishing=r[9],
            dribbling=r[10], starting=r[11],
        )
        for r in rows
    ]


PLAYERS: list[Player] = _build(_HOME, HOME.team_id) + _build(_AWAY, AWAY.team_id)
ROSTER: dict[str, Player] = {p.player_id: p for p in PLAYERS}
TEAMS = {HOME.team_id: HOME, AWAY.team_id: AWAY}


def starters(team_id: str) -> list[Player]:
    return [p for p in PLAYERS if p.team_id == team_id and p.starting]


# Formation templates in each team's *own* attack frame (attacking towards x = 105),
# for a ball at the centre spot. "Right" is the high-y side.
IN_POSSESSION = {
    "GK": [(7, 34)],
    "LB": [(42, 9)],
    "CB": [(30, 25), (30, 43)],
    "RB": [(42, 59)],
    "DM": [(46, 34)],
    "CM": [(56, 26), (58, 44)],
    "AM": [(64, 40)],
    "LW": [(72, 11)],
    "RW": [(72, 57)],
    "ST": [(78, 34)],
}
OUT_OF_POSSESSION = {
    "GK": [(4, 34)],
    "LB": [(22, 12)],
    "CB": [(18, 28), (18, 40)],
    "RB": [(22, 56)],
    "DM": [(30, 34)],
    "CM": [(37, 24), (37, 44)],
    "AM": [(42, 40)],
    "LW": [(46, 12)],
    "RW": [(46, 56)],
    "ST": [(54, 34)],
}
KICKOFF = {
    "GK": [(5, 34)],
    "LB": [(30, 12)],
    "CB": [(25, 27), (25, 41)],
    "RB": [(30, 56)],
    "DM": [(38, 34)],
    "CM": [(44, 26), (44, 42)],
    "AM": [(48, 40)],
    "LW": [(48, 10)],
    "RW": [(48, 58)],
    "ST": [(51.5, 34)],
}


def template_positions(players: list[Player], template: dict[str, list[tuple[float, float]]]) -> dict[str, tuple[float, float]]:
    """Assign template slots by role; overflow players of a role reuse the role's last slot with an offset."""
    used: dict[str, int] = {}
    out: dict[str, tuple[float, float]] = {}
    fallback = {"AM": "CM", "CM": "DM", "DM": "CM"}
    for p in players:
        role = p.role if p.role in template else fallback.get(p.role, "CM")
        k = used.get(role, 0)
        slots = template[role]
        if k < len(slots):
            out[p.player_id] = slots[k]
        else:
            x, y = slots[-1]
            out[p.player_id] = (x, min(64.0, y + 8.0 * (k - len(slots) + 1)))
        used[role] = k + 1
    return out
