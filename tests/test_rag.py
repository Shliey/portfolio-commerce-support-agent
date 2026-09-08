from commerce_support.rag import (
    HashEmbedding,
    OfflinePolicyRetriever,
    SemanticPolicyRetriever,
    load_policy_corpus,
)


def test_policy_corpus_has_required_topics_and_metadata() -> None:
    chunks = load_policy_corpus()
    assert {chunk.topic for chunk in chunks} == {
        "returns",
        "electronics_warranty",
        "logistics_exceptions",
        "promotion_refunds",
    }
    assert all(chunk.source and chunk.title and chunk.section for chunk in chunks)
    assert all(chunk.position >= 0 for chunk in chunks)


def test_answer_citations_are_retrieved_sources() -> None:
    answer = OfflinePolicyRetriever().answer("How many days can I return a delivered item?")
    assert not answer.insufficient_evidence
    assert answer.citations[0].source == "policy/returns.md"


def test_unknown_policy_is_refused_without_citations() -> None:
    answer = OfflinePolicyRetriever().answer("Can I teleport my purchase to Mars?")
    assert answer.insufficient_evidence
    assert answer.citations == []


def test_vector_store_can_be_swapped_without_changing_answer_contract() -> None:
    class FakeStore:
        def __init__(self) -> None:
            self.indexed = False

        def index(self, vectors: list[list[float]]) -> None:
            self.indexed = bool(vectors)

        def search(self, query: list[float], limit: int) -> list[tuple[int, float]]:
            assert query
            assert limit == 3
            return [(2, 0.9)]

    store = FakeStore()
    retriever = SemanticPolicyRetriever(HashEmbedding(), vector_store=store)
    answer = retriever.answer("coverage question")
    assert store.indexed
    assert answer.citations[0].source == "policy/warranty.md"
