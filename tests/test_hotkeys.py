import pytest

from dmnt_kobold.hotkeys import zerlegen


def test_zerlegen():
    assert zerlegen("Strg+Alt+E") == (0x3, ord("E"))
    assert zerlegen("Umschalt+Win+F9") == (0xC, 0x78)
    assert zerlegen("F12") == (0, 0x7B)


@pytest.mark.parametrize("k", ["", "E", "Strg+", "Hyper+E", "Strg+Ä"])
def test_ungueltig(k):
    with pytest.raises(ValueError):
        zerlegen(k)
