import pytest

from commerce_support.return_workflow import strict_checkpoint_serializer


class ForeignPayload:
    pass


def test_checkpoint_serializer_disables_pickle_and_foreign_modules() -> None:
    serializer = strict_checkpoint_serializer()
    assert serializer.pickle_fallback is False
    with pytest.raises(TypeError):
        serializer.dumps_typed(ForeignPayload())
