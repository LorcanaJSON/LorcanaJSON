from collections import namedtuple
from typing import Tuple


Language = namedtuple("Language", ("code", "threeLetterCode", "englishName", "nativeName", "hasLorcanaTesseractModel"))

ENGLISH = Language("en", "eng", "English", "English", True)
FRENCH = Language("fr", "fra", "French", "Français", False)
GERMAN = Language("de", "deu", "German", "Deutsch", False)
ITALIAN = Language("it", "ita", "Italian", "Italiano", False)

ALL: Tuple[Language, ...] = (ENGLISH, FRENCH, GERMAN, ITALIAN)

def getLanguageByCode(languageCode: str) -> Language:
	languageCode = languageCode.lower()
	for language in ALL:
		if language.code == languageCode or language.threeLetterCode == languageCode:
			return language
	raise ValueError(f"Invalid language code '{languageCode}'")
