from collections import namedtuple
from typing import Tuple


Language = namedtuple("Language", ("code", "threeLetterCode", "englishName", "nativeName", "fromSet", "hasLorcanaTesseractModel"))

ENGLISH = Language("en", "eng", "English", "English", 1, True)
FRENCH = Language("fr", "fra", "French", "Français", 1, False)
GERMAN = Language("de", "deu", "German", "Deutsch", 1, False)
ITALIAN = Language("it", "ita", "Italian", "Italiano", 3, False)

ALL: Tuple[Language, ...] = (ENGLISH, FRENCH, GERMAN, ITALIAN)

def getLanguageByCode(languageCode: str) -> Language:
	languageCode = languageCode.lower()
	for language in ALL:
		if language.code == languageCode or language.threeLetterCode == languageCode:
			return language
	raise ValueError(f"Invalid language code '{languageCode}'")
