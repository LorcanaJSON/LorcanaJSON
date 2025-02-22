from dataclasses import dataclass
from typing import Tuple

@dataclass(frozen=True)
class Language:
	code: str
	uppercaseCode: str
	threeLetterCode: str
	englishName: str
	nativeName: str


ENGLISH = Language("en", "EN", "eng", "English", "English")
FRENCH = Language("fr", "FR", "fra", "French", "Français")
GERMAN = Language("de", "DE", "deu", "German", "Deutsch")
ITALIAN = Language("it", "IT", "ita", "Italian", "Italiano")

ALL: Tuple[Language, ...] = (ENGLISH, FRENCH, GERMAN, ITALIAN)

def getLanguageByCode(languageCode: str) -> Language:
	languageCode = languageCode.lower()
	for language in ALL:
		if language.code == languageCode or language.threeLetterCode == languageCode:
			return language
	raise ValueError(f"Invalid language code '{languageCode}'")
