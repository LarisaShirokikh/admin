# Deterministic category assignment rules.
# Input: product name + scraped attributes dict.
# Output: list of category slugs the product belongs to.
# Every product additionally goes to the default category ("vse-dveri")
# in assign_categories, so rules here only handle the specific ones.

from typing import Dict, List, Optional

# Finish attribute keys per donor. "Покраска металла" is intentionally
# excluded: nearly every door has a black frame ("Муар чёрный"), it says
# nothing about the visible color.
# Labirint: "Отделка снаружи" / "Внутренняя отделка"
# Bunker:   "Внешняя панель"  / "Внутренняя панель"
# Intecron: "Отделка снаружи" (interior finish lives in the product name)
_OUTSIDE_KEYS = ("Отделка снаружи", "Внешняя панель")
_INSIDE_KEYS = ("Внутренняя отделка", "Внутренняя панель")

_WHITE_MARKERS = ("бел", "white")
_BLACK_MARKERS = ("черн", "чёрн", "black")


def _text_blob(name: str, attributes: Dict[str, str]) -> str:
    parts = [name or ""]
    for k, v in (attributes or {}).items():
        parts.append(str(k))
        parts.append(str(v))
    return " ".join(parts).lower()


def _finish_value(attributes: Dict[str, str], keys) -> Optional[str]:
    for key in keys:
        val = (attributes or {}).get(key)
        if val:
            return str(val).lower()
    return None


def _has_marker(text: Optional[str], markers) -> bool:
    return bool(text) and any(m in text for m in markers)


def classify_by_rules(name: str, attributes: Dict[str, str]) -> List[str]:
    """Returns category slugs matched by explicit rules."""
    blob = _text_blob(name, attributes)
    name_l = (name or "").lower()
    outside = _finish_value(attributes, _OUTSIDE_KEYS)
    inside = _finish_value(attributes, _INSIDE_KEYS)
    slugs: List[str] = []

    # For the house: thermal break or street-use markers
    if "терморазрыв" in blob or "уличн" in blob or "морозостойк" in blob:
        slugs.append("dveri-dlya-doma")
    else:
        # Entry doors without a thermal break are apartment doors
        slugs.append("dveri-dlya-kvartiry")

    # Mirror: mentioned in the name or interior finish
    if "зеркал" in name_l or _has_marker(inside, ("зеркал",)):
        slugs.append("dveri-s-zerkalom")

    # White doors must be white on BOTH sides (Larisa, 2026-07-10).
    # The product name usually describes the interior panel, so an unknown
    # side falls back to the name.
    out_white = _has_marker(outside, _WHITE_MARKERS) if outside else _has_marker(name_l, _WHITE_MARKERS)
    in_white = _has_marker(inside, _WHITE_MARKERS) if inside else _has_marker(name_l, _WHITE_MARKERS)
    if out_white and in_white:
        slugs.append("belye-dveri")

    # Black doors: judged by the street-facing side (or the name as fallback)
    out_black = _has_marker(outside, _BLACK_MARKERS) if outside else _has_marker(name_l, _BLACK_MARKERS)
    if out_black:
        slugs.append("chernye-dveri")

    # Wenge: panel color, name or either finish
    if "венге" in name_l or _has_marker(outside, ("венге",)) or _has_marker(inside, ("венге",)):
        slugs.append("dveri-venge")

    # Loft style: concrete/loft/graphite finishes
    finish_blob = " ".join(filter(None, (outside, inside)))
    if any(w in name_l or w in finish_blob for w in ("лофт", "бетон", "графит")):
        slugs.append("dveri-loft")

    return slugs
