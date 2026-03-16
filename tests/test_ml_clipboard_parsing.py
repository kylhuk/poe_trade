from __future__ import annotations

import sys

sys.path.insert(0, '/mnt/data/devrepo')

from poe_trade.ml.workflows import _parse_clipboard_item


RARE_HELM = '''Rarity: Rare
Grim Bane
Hubris Circlet
--------
Quality: +20%
Item Level: 86
--------
+2 to Level of Socketed Minion Gems
+93 to maximum Life
'''

UNIQUE_HELM = '''Item Class: Helmets
Rarity: Unique
Crown of the Inward Eye
Prophet Crown
--------
Quality: +20%
Item Level: 84
--------
Has 1 Socket
'''


def test_parse_clipboard_item_extracts_generated_name_and_base_type_for_rare_item() -> None:
    parsed = _parse_clipboard_item(RARE_HELM)

    assert parsed['item_name'] == 'Grim Bane'
    assert parsed['base_type'] == 'Hubris Circlet'
    assert parsed['rarity'] == 'Rare'


def test_parse_clipboard_item_extracts_unique_name_and_base_type_separately() -> None:
    parsed = _parse_clipboard_item(UNIQUE_HELM)

    assert parsed['item_name'] == 'Crown of the Inward Eye'
    assert parsed['base_type'] == 'Prophet Crown'
    assert parsed['item_class'] == 'Helmets'
    assert parsed['rarity'] == 'Unique'
