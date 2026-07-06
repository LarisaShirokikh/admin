# Deterministic category assignment rules.
# Input: product name + scraped attributes dict.
# Output: list of category slugs the product belongs to.
# Every product additionally goes to the default category ("vse-dveri")
# in assign_categories, so rules here only handle the specific ones.

from typing import Dict, List

# Attribute keys that describe panel finish/color on Labirint product pages.
# "Покраска металла" is intentionally excluded: nearly every door has a black
# frame ("Муар чёрный"), it says nothing about the visible color.
_FINISH_KEYS = (
    "Отделка снаружи",
    "Внутренняя отделка",
)


def _text_blob(name: str, attributes: Dict[str, str]) -> str:
    parts = [name or ""]
    for k, v in (attributes or {}).items():
        parts.append(str(k))
        parts.append(str(v))
    return " ".join(parts).lower()


def _finish_blob(attributes: Dict[str, str]) -> str:
    parts = []
    for key in _FINISH_KEYS:
        val = (attributes or {}).get(key)
        if val:
            parts.append(str(val))
    return " ".join(parts).lower()


def classify_by_rules(name: str, attributes: Dict[str, str]) -> List[str]:
    """Returns category slugs matched by explicit rules."""
    blob = _text_blob(name, attributes)
    finish = _finish_blob(attributes)
    name_l = (name or "").lower()
    slugs: List[str] = []

    # For the house: thermal break or street-use markers
    if "терморазрыв" in blob or "уличн" in blob or "морозостойк" in blob:
        slugs.append("dveri-dlya-doma")
    else:
        # Entry doors without a thermal break are apartment doors
        slugs.append("dveri-dlya-kvartiry")

    # Mirror: mentioned in the name or interior finish
    if "зеркал" in name_l or "зеркал" in finish:
        slugs.append("dveri-s-zerkalom")

    # Colors: prefer the name (what the customer sees), then finish attributes
    color_src = name_l if any(c in name_l for c in ("бел", "черн", "чёрн", "венге")) else finish
    if "бел" in color_src:
        slugs.append("belye-dveri")
    if "черн" in color_src or "чёрн" in color_src:
        slugs.append("chernye-dveri")
    if "венге" in color_src:
        slugs.append("dveri-venge")

    # Loft style: concrete/loft/graphite finishes
    if any(w in name_l or w in finish for w in ("лофт", "бетон", "графит")):
        slugs.append("dveri-loft")

    return slugs
