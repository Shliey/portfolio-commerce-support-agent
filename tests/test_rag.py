from commerce_support.rag import OfflinePolicyRetriever


def test_answer_citations_are_retrieved_sources() -> None:
    answer = OfflinePolicyRetriever().answer("How many days can I return a delivered item?")
    assert not answer.insufficient_evidence
    assert answer.citations[0].source == "policy/returns.md"


def test_unknown_policy_is_refused_without_citations() -> None:
    answer = OfflinePolicyRetriever().answer("Can I teleport my purchase to Mars?")
    assert answer.insufficient_evidence
    assert answer.citations == []
