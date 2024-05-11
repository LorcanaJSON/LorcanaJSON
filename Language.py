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


TRANSLATIONS = {
	# An English translation doesn't make much sense, but it saves a lot of "if language == ENGLISH or translation == ..." checks
	# It also works as a good template when adding languages
	ENGLISH: {
		# Colors (Always fully capitalized in the data file)
		"AMBER": "Amber",
		"AMETHYST": "Amethyst",
		"EMERALD": "Emerald",
		"RUBY": "Ruby",
		"SAPPHIRE": "Sapphire",
		"STEEL": "Steel",
		# Rarities (Always fully capitalized in the data file)
		"COMMON": "Common",
		"UNCOMMON": "Uncommon",
		"RARE": "Rare",
		"SUPER": "Super",
		"LEGENDARY": "Legendary",
		"ENCHANTED": "Enchanted",
		"SPECIAL": "Special",
		# Types
		"Action": "Action",
		"Character": "Character",
		"Item": "Item",
		"Location": "Location"
	},
	FRENCH: {
		# Colors (Always fully capitalized in the data file)
		"AMBER": "Ambre",
		"AMETHYST": "Améthyste",
		"EMERALD": "Émeraude",
		"RUBY": "Rubis",
		"SAPPHIRE": "Saphir",
		"STEEL": "Acier",
		# Rarities (Always fully capitalized in the data file)
		"COMMON": "Commune",
		"UNCOMMON": "Peu commune",
		"RARE": "Rare",
		"SUPER": "Super Rare",
		"LEGENDARY": "Légendaire",
		"ENCHANTED": "Enchantée",
		"SPECIAL": "Spécial",
		# Types
		"Action": "Action",
		"Character": "Personnage",
		"Item": "Objet",
		"Location": "Lieu"
	},
	GERMAN: {
		# Colors (Always fully capitalized in the data file)
		"AMBER": "Bernstein",
		"AMETHYST": "Amethyst",
		"EMERALD": "Smaragd",
		"RUBY": "Rubin",
		"SAPPHIRE": "Saphir",
		"STEEL": "Stahl",
		# Rarities (Always fully capitalized in the data file)
		"COMMON": "Gewöhnlich",
		"UNCOMMON": "Ungewöhnlich",
		"RARE": "Selten",
		"SUPER": "Episch",
		"LEGENDARY": "Legendär",
		"ENCHANTED": "Verzaubert",
		"SPECIAL": " Speziell",
		# Types
		"Action": "Aktion",
		"Character": "Charakter",
		"Item": "Gegenstand",
		"Location": "Ort"
	},
	ITALIAN: {
		# Colors (Always fully capitalized in the data file)
		"AMBER": "Ambra",
		"AMETHYST": "Ametista",
		"EMERALD": "Smeraldo",
		"RUBY": "Rubino",
		"SAPPHIRE": "Zaffiro",
		"STEEL": "Acciaio",
		# Rarities (Always fully capitalized in the data file)
		"COMMON": "Comune",
		"UNCOMMON": "Non comune",
		"RARE": "Rara",
		"SUPER": "Super Rara",
		"LEGENDARY": "Leggendaria",
		"ENCHANTED": "Incantata",
		"SPECIAL": "Speciale",
		# Types
		"Action": "Azione",
		"Character": "Personaggio",
		"Item": "Oggetto",
		"Location": "Luogo"
	}
}
