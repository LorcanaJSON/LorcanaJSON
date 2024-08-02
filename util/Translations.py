from util import Language

TRANSLATIONS = {
	# An English translation doesn't make much sense, but it saves a lot of "if language == ENGLISH or translation == ..." checks
	# It also works as a good template when adding languages
	Language.ENGLISH: {
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
		"SUPER": "Super Rare",
		"LEGENDARY": "Legendary",
		"ENCHANTED": "Enchanted",
		"SPECIAL": "Special",
		# Types
		"Action": "Action",
		"Character": "Character",
		"Item": "Item",
		"Location": "Location"
	},
	Language.FRENCH: {
		# Colors (Always fully capitalized in the data file)
		"AMBER": "Ambre",
		"AMETHYST": "Améthyste",
		"EMERALD": "Émeraude",
		"RUBY": "Rubis",
		"SAPPHIRE": "Saphir",
		"STEEL": "Acier",
		# Rarities (Always fully capitalized in the data file)
		"COMMON": "Commune",
		"UNCOMMON": "Inhabituelle",
		"RARE": "Rare",
		"SUPER": "Très Rare",
		"LEGENDARY": "Légendaire",
		"ENCHANTED": "Enchantée",
		"SPECIAL": "Spécial",
		# Types
		"Action": "Action",
		"Character": "Personnage",
		"Item": "Objet",
		"Location": "Lieu"
	},
	Language.GERMAN: {
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
	Language.ITALIAN: {
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
