"""Canonical 118-element table.

Atomic weights are the CIAAW strings transcribed from
https://www.ciaaw.org/atomic-weights.htm (Standard Atomic Weights 2024,
including the 2024 revisions of Gd, Lu, and Zr). An em dash in that table
is stored as kind "none". No mass number is substituted.

Period, group, and block are the IUPAC 18-group layout. Lanthanoids
(Z 57–71) and actinoids (Z 89–103) are series in periods 6 and 7 and have
no group number here, which is the footnote-row presentation. Helium is
group 18 and s-block. Category is a conventional class; it is null for Po,
At, and Z >= 104, where this dataset does not assert one.
"""

from __future__ import annotations

import json
from pathlib import Path

SOURCE = {
    "atomic_weights": (
        "CIAAW Standard Atomic Weights 2024 table, "
        "https://www.ciaaw.org/atomic-weights.htm, "
        "incorporating IUPAC Pure Appl. Chem. 2022 atomic weights "
        "and the 2024 revisions of gadolinium, lutetium, and zirconium"
    ),
    "layout": (
        "IUPAC 18-group periodic table. Lanthanoids Z=57-71 and "
        "actinoids Z=89-103 are series with group null. "
        "Helium is group 18 and block s."
    ),
    "categories": (
        "Conventional class for elements with an established class. "
        "Null where this dataset does not assign one (Po, At, Z>=104)."
    ),
}

# Published CIAAW text, atomic-number order. Spaces are the table's digit groups.
_WEIGHTS = (
    "[1.007 84, 1.008 11]",
    "4.002 602(2)",
    "[6.938, 6.997]",
    "9.012 1831(5)",
    "[10.806, 10.821]",
    "[12.0096, 12.0116]",
    "[14.006 43, 14.007 28]",
    "[15.999 03, 15.999 77]",
    "18.998 403 162(5)",
    "20.1797(6)",
    "22.989 769 28(2)",
    "[24.304, 24.307]",
    "26.981 5384(3)",
    "[28.084, 28.086]",
    "30.973 761 998(5)",
    "[32.059, 32.076]",
    "[35.446, 35.457]",
    "[39.792, 39.963]",
    "39.0983(1)",
    "40.078(4)",
    "44.955 907(4)",
    "47.867(1)",
    "50.9415(1)",
    "51.9961(6)",
    "54.938 043(2)",
    "55.845(2)",
    "58.933 194(3)",
    "58.6934(4)",
    "63.546(3)",
    "65.38(2)",
    "69.723(1)",
    "72.630(8)",
    "74.921 595(6)",
    "78.971(8)",
    "[79.901, 79.907]",
    "83.798(2)",
    "85.4678(3)",
    "87.62(1)",
    "88.905 838(2)",
    "91.222(3)",
    "92.906 37(1)",
    "95.95(1)",
    "—",
    "101.07(2)",
    "102.905 49(2)",
    "106.42(1)",
    "107.8682(2)",
    "112.414(4)",
    "114.818(1)",
    "118.710(7)",
    "121.760(1)",
    "127.60(3)",
    "126.904 47(3)",
    "131.293(6)",
    "132.905 451 96(6)",
    "137.327(7)",
    "138.905 47(7)",
    "140.116(1)",
    "140.907 66(1)",
    "144.242(3)",
    "—",
    "150.36(2)",
    "151.964(1)",
    "157.249(2)",
    "158.925 354(7)",
    "162.500(1)",
    "164.930 329(5)",
    "167.259(3)",
    "168.934 219(5)",
    "173.045(10)",
    "174.966 69(5)",
    "178.486(6)",
    "180.947 88(2)",
    "183.84(1)",
    "186.207(1)",
    "190.23(3)",
    "192.217(2)",
    "195.084(9)",
    "196.966 570(4)",
    "200.592(3)",
    "[204.382, 204.385]",
    "[206.14, 207.94]",
    "208.980 40(1)",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "232.0377(4)",
    "231.035 88(1)",
    "238.028 91(3)",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
    "—",
)

_NAMES = (
    "hydrogen", "helium", "lithium", "beryllium", "boron", "carbon", "nitrogen",
    "oxygen", "fluorine", "neon", "sodium", "magnesium", "aluminium", "silicon",
    "phosphorus", "sulfur", "chlorine", "argon", "potassium", "calcium",
    "scandium", "titanium", "vanadium", "chromium", "manganese", "iron", "cobalt",
    "nickel", "copper", "zinc", "gallium", "germanium", "arsenic", "selenium",
    "bromine", "krypton", "rubidium", "strontium", "yttrium", "zirconium",
    "niobium", "molybdenum", "technetium", "ruthenium", "rhodium", "palladium",
    "silver", "cadmium", "indium", "tin", "antimony", "tellurium", "iodine",
    "xenon", "caesium", "barium", "lanthanum", "cerium", "praseodymium",
    "neodymium", "promethium", "samarium", "europium", "gadolinium", "terbium",
    "dysprosium", "holmium", "erbium", "thulium", "ytterbium", "lutetium",
    "hafnium", "tantalum", "tungsten", "rhenium", "osmium", "iridium", "platinum",
    "gold", "mercury", "thallium", "lead", "bismuth", "polonium", "astatine",
    "radon", "francium", "radium", "actinium", "thorium", "protactinium",
    "uranium", "neptunium", "plutonium", "americium", "curium", "berkelium",
    "californium", "einsteinium", "fermium", "mendelevium", "nobelium",
    "lawrencium", "rutherfordium", "dubnium", "seaborgium", "bohrium", "hassium",
    "meitnerium", "darmstadtium", "roentgenium", "copernicium", "nihonium",
    "flerovium", "moscovium", "livermorium", "tennessine", "oganesson",
)

_SYMBOLS = (
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si",
    "P", "S", "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni",
    "Cu", "Zn", "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr", "Nb",
    "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te", "I", "Xe",
    "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho",
    "Er", "Tm", "Yb", "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
    "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th", "Pa", "U", "Np",
    "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm", "Md", "No", "Lr", "Rf", "Db", "Sg",
    "Bh", "Hs", "Mt", "Ds", "Rg", "Cn", "Nh", "Fl", "Mc", "Lv", "Ts", "Og",
)

_ALKALI = {"Li", "Na", "K", "Rb", "Cs", "Fr"}
_ALKALINE = {"Be", "Mg", "Ca", "Sr", "Ba", "Ra"}
_TRANSITION = {
    "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
    "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd",
    "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
}
_POST = {"Al", "Ga", "In", "Sn", "Tl", "Pb", "Bi"}
_METALLOID = {"B", "Si", "Ge", "As", "Sb", "Te"}
_NONMETAL = {"H", "C", "N", "O", "F", "P", "S", "Cl", "Se", "Br", "I"}
_NOBLE = {"He", "Ne", "Ar", "Kr", "Xe", "Rn"}

DATASET_PATH = Path(__file__).with_name("periodic_table.json")


def parse_weight(published: str) -> dict:
    """Parse one CIAAW cell. Does not invent a value for an em dash or an interval."""
    text = published.strip()
    if text in {"—", "-", "–"}:
        return {"kind": "none", "published": published}
    compact = text.replace(" ", "")
    if compact.startswith("[") and compact.endswith("]"):
        low_s, high_s = compact[1:-1].split(",")
        return {
            "kind": "interval",
            "published": published,
            "low": float(low_s),
            "high": float(high_s),
        }
    number, _, unc = compact.partition("(")
    if not _ or not unc.endswith(")"):
        raise ValueError(f"unrecognized atomic weight: {published!r}")
    digits = unc[:-1]
    if not digits.isdigit() or not number:
        raise ValueError(f"unrecognized atomic weight: {published!r}")
    decimals = len(number.split(".")[1]) if "." in number else 0
    return {
        "kind": "value",
        "published": published,
        "value": float(number),
        "uncertainty": int(digits) * (10 ** (-decimals)),
    }


def period_of(z: int) -> int:
    if z <= 2:
        return 1
    if z <= 10:
        return 2
    if z <= 18:
        return 3
    if z <= 36:
        return 4
    if z <= 54:
        return 5
    if z <= 86:
        return 6
    return 7


def series_of(z: int) -> str | None:
    if 57 <= z <= 71:
        return "lanthanide"
    if 89 <= z <= 103:
        return "actinide"
    return None


def group_of(z: int) -> int | None:
    """IUPAC group, or None for the lanthanoid and actinoid footnote rows.

    Periods 6 and 7 leave group 3 empty in the main row. Hf and Rf are
    group 4. The series themselves are not given a group number.
    """
    if series_of(z):
        return None
    if z <= 2:
        return 1 if z == 1 else 18
    if 3 <= z <= 4:
        return z - 2
    if 5 <= z <= 10:
        return z + 8
    if 11 <= z <= 12:
        return z - 10
    if 13 <= z <= 18:
        return z
    if 19 <= z <= 36:
        return z - 18
    if 37 <= z <= 54:
        return z - 36
    if z in (55, 56):
        return z - 54
    if 72 <= z <= 86:
        return z - 68
    if z in (87, 88):
        return z - 86
    if 104 <= z <= 118:
        return z - 100
    raise ValueError(f"no group rule for Z={z}")


def block_of(z: int) -> str:
    if series_of(z):
        return "f"
    group = group_of(z)
    if z in (1, 2) or group in (1, 2):
        return "s"
    if group is not None and 13 <= group <= 18:
        return "p"
    return "d"


def category_of(z: int, symbol: str) -> tuple[str | None, str]:
    series = series_of(z)
    if series == "lanthanide":
        return "lanthanide", "conventional"
    if series == "actinide":
        return "actinide", "conventional"
    if z >= 104 or symbol in {"Po", "At"}:
        return None, "not_assigned"
    if symbol in _ALKALI:
        return "alkali metal", "conventional"
    if symbol in _ALKALINE:
        return "alkaline earth metal", "conventional"
    if symbol in _TRANSITION:
        return "transition metal", "conventional"
    if symbol in _POST:
        return "post-transition metal", "conventional"
    if symbol in _METALLOID:
        return "metalloid", "conventional"
    if symbol in _NONMETAL:
        return "reactive nonmetal", "conventional"
    if symbol in _NOBLE:
        return "noble gas", "conventional"
    return None, "not_assigned"


def build_table() -> list[dict]:
    if not (len(_WEIGHTS) == len(_NAMES) == len(_SYMBOLS) == 118):
        raise RuntimeError("element transcription is not 118 long")
    rows = []
    for i, (symbol, name, published) in enumerate(zip(_SYMBOLS, _NAMES, _WEIGHTS), start=1):
        weight = parse_weight(published)
        category, status = category_of(i, symbol)
        rows.append(
            {
                "atomic_number": i,
                "symbol": symbol,
                "name": name,
                "atomic_weight": weight,
                "period": period_of(i),
                "group": group_of(i),
                "block": block_of(i),
                "category": category,
                "category_status": status,
                "series": series_of(i),
            }
        )
    return rows


def dataset_document() -> dict:
    return {"source": SOURCE, "elements": build_table()}


def write_dataset(path: Path = DATASET_PATH) -> None:
    path.write_text(json.dumps(dataset_document(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_dataset(path: Path = DATASET_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
