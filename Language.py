from collections import namedtuple
from typing import Tuple


Language = namedtuple("Language", ("code", "threeLetterCode", "englishName", "nativeName"))

ENGLISH = Language("en", "eng", "English", "English")
FRENCH = Language("fr", "fra", "French", "Français")
GERMAN = Language("de", "deu", "German", "Deutsch")

ALL: Tuple[Language, ...] = (ENGLISH, FRENCH, GERMAN)
