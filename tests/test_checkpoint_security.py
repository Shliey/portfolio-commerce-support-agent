import ormsgpack
import pytest

from commerce_support.return_workflow import strict_checkpoint_serializer


class ForeignPayload:
    pass


def test_checkpoint_serializer_disables_pickle_and_foreign_modules() -> None:
    serializer = strict_checkpoint_serializer()
    assert serializer.pickle_fallback is False
    with pytest.raises(TypeError):
        serializer.dumps_typed(ForeignPayload())


def test_foreign_constructor_payload_is_not_executed(tmp_path) -> None:
    marker = tmp_path / "must-not-exist.txt"
    command = f'type nul > "{marker}"'
    constructor = ormsgpack.packb(("os", "system", command))
    malicious = ormsgpack.packb(ormsgpack.Ext(0, constructor))
    serializer = strict_checkpoint_serializer()
    with pytest.raises(ValueError, match="ext_hook failed"):
        serializer.loads_typed(("msgpack", malicious))
    assert not marker.exists()
