from collections import namedtuple
from typing import Tuple


Language = namedtuple("Language", ("code", "threeLetterCode", "englishName", "nativeName"))

ENGLISH = Language("en", "eng", "English", "English")
FRENCH = Language("fr", "fra", "French", "Français")
GERMAN = Language("de", "deu", "German", "Deutsch")

ALL: Tuple[Language, ...] = (ENGLISH, FRENCH, GERMAN)

def getLanguageByCode(languageCode: str) -> Language:
	languageCode = languageCode.lower()
	for language in ALL:
		if language.code == languageCode or language.threeLetterCode == languageCode:
			return language
	raise ValueError(f"Invalid language code '{languageCode}'")
