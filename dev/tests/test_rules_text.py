"""Start-page rules take their numbers from the active balance profile."""

from pathlib import Path

from sixtyfivekmconvoy.core.card_display import fill_rules_html
from sixtyfivekmconvoy.core.configs import get_config, load_config

_TEMPLATE = Path(__file__).resolve().parents[1] / "web" / "index.html"


def _filled(name: str) -> str:
    previous = get_config().CONFIG_NAME
    try:
        load_config(name)
        return fill_rules_html(_TEMPLATE.read_text(encoding="utf-8"))
    finally:
        load_config(previous)


def test_rules_template_keeps_placeholders():
    raw = _TEMPLATE.read_text(encoding="utf-8")
    for token in (
        "{cards_to_deal}",
        "{cash_in_sentence}",
        "{cash_to_win}",
        "{promotions_to_win}",
        "{attack_cash}",
        "{service_cash}",
        "{soak_air_cash}",
        "{soak_air_atrocities}",
        "{soak_sabotage_cash}",
        "{reveal_mauling_cash}",
        "{reveal_resistance_cash}",
    ):
        assert token in raw


def test_default_rules_use_discard_cash_in_and_win_threshold():
    html = _filled("default")
    assert "{cash_to_win}" not in html
    assert "edellyttämän 25 MMk tai 6 ylennyspistettä" in html
    assert "nostaa 5 korttia" in html
    assert "Maksaa 4 korttia. Kortit menevät poistopakkaan ja saat 1 MMk." in html
    assert "Pelaajalla on mahdollisuus laittaa 4 korttia" not in html
    assert "tuo 2 MMk" in html
    assert "saat 2 MMk ja 1 hirmutekopisteen" in html
    assert "antaa 1 MMk ja vähintään yksi vastarintakortti 1 MMk" in html
    assert "saa 1 MMk." in html


def test_retire_rules_remove_cards_and_pay_one():
    html = _filled("retire")
    assert "edellyttämän 25 MMk tai 6 ylennyspistettä" in html
    assert (
        "Maksaa 4 korttia. Kortit poistuvat pelistä eivätkä palaa pakkaan, "
        "ja saat 1 MMk."
    ) in html
    assert "laittaa 4 korttia poistopakkaan" not in html
