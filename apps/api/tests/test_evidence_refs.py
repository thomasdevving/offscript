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
