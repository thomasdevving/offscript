from app.models.verification import EvidenceItem
from app.verification.checks import split_evidence_refs


def _item(ref: str) -> EvidenceItem:
    return EvidenceItem(ref=ref, label=ref, value=0.02, unit="%", display="2.0%")


def test_unknown_citations_are_split_off():
    known, unknown = split_evidence_refs(["results.alt1.p_goal", "results.alt1.verdict"], [_item("results.alt1.p_goal")])
    assert known == ["results.alt1.p_goal"]
    assert unknown == ["results.alt1.verdict"]
