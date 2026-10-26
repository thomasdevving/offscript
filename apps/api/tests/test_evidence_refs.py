from app.models.verification import EvidenceItem
from app.verification.checks import split_evidence_refs


def _item(ref: str) -> EvidenceItem:
    return EvidenceItem(ref=ref, label=ref, value=0.02, unit="%", display="2.0%")


def test_unknown_citations_are_split_off():
    known, unknown = split_evidence_refs(["results.alt1.p_goal", "results.alt1.verdict"], [_item("results.alt1.p_goal")])
    assert known == ["results.alt1.p_goal"]
    assert unknown == ["results.alt1.verdict"]


def test_internal_player_ids_are_rejected():
    from app.models.narrative import Narrative
    from app.verification.checks import verify_narrative

    class P:
        name = "Ravi Castellane"
        short_name = "Castellane"

    n = Narrative(narrative_id="n", analysis_id="a", audience="broadcaster", language="en", headline="H10 SHOT BLOCKED",
                  body="", caption="Castellane's shot was blocked.", generated_by="t", is_live_model_output=False, created_at="")
    issues = verify_narrative(n, [], {"H10": P()}, {"H10"})
    assert any("internal player id H10" in i for i in issues)


def test_internal_identifiers_are_rejected_but_formations_are_not():
    from app.verification.checks import _INTERNAL_ID

    assert _INTERNAL_ID.findall("the same snapshot (demo-match-073-snap-0002)") == ["demo-match-073-snap-0002"]
    assert _INTERNAL_ID.findall("measured as p_goal_within_horizon") == ["p_goal_within_horizon"]
    assert _INTERNAL_ID.findall("a 4-3-3 shape, a 2-on-1, a 10-second horizon, Mbeki-Larsen") == []


def test_identifiers_shown_in_the_evidence_table_are_allowed():
    from app.models.narrative import Narrative
    from app.verification.checks import verify_narrative

    ev = [EvidenceItem(ref="sim.simulator_version", label="Simulator", value="offscript-sim-1.0.0",
                       display="offscript-sim-1.0.0")]
    n = Narrative(narrative_id="n", analysis_id="a", audience="broadcaster", language="en", headline="H",
                  body="Simulated with offscript-sim-1.0.0; snapshot demo-match-073-snap-0002.", generated_by="t",
                  is_live_model_output=False, created_at="")
    issues = [i for i in verify_narrative(n, ev, {}, set()) if "internal identifier" in i]
    assert issues == ["Uses an internal identifier (demo-match-073-snap-0002) that viewers would not understand"]
