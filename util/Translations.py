from dataclasses import dataclass

from util import Language

@dataclass(eq=False, frozen=True, kw_only=True, repr=False)
class Translation:
	language: Language.Language
	# Colors (Always fully capitalized in the data file)
	AMBER: str
	AMETHYST: str
	EMERALD: str
	RUBY: str
	SAPPHIRE: str
	STEEL: str
	# Rarities (Always fully capitalized in the data file)
	COMMON: str
	UNCOMMON: str
	RARE: str
	SUPER: str
	LEGENDARY: str
	ENCHANTED: str
	SPECIAL: str
	# Types
	Action: str
	Character: str
	Item: str
	Location: str
	# Product names
	gateway: str
	quest: str
	starter: str

	def __getitem__(self, item) -> str:
		# This allows the use of item subscription (myTranslation['AMBER'] or myTranslation[card[color]])
		return self.__getattribute__(item)


# An English translation doesn't make much sense, but it saves a lot of if language == ENGLISH or translation == ..." checks
# It also works as a good template when adding languages
ENGLISH = Translation(
	language=Language.ENGLISH,
	# Colors (Always fully capitalized in the data file)
	AMBER="Amber",
	AMETHYST="Amethyst",
	EMERALD="Emerald",
	RUBY="Ruby",
	SAPPHIRE="Sapphire",
	STEEL="Steel",
	# Rarities (Always fully capitalized in the data file)
	COMMON="Common",
	UNCOMMON="Uncommon",
	RARE="Rare",
	SUPER="Super Rare",
	LEGENDARY="Legendary",
	ENCHANTED="Enchanted",
	SPECIAL="Special",
	# Types
	Action="Action",
	Character="Character",
	Item="Item",
	Location="Location",
	# Product names
	gateway="Gateway",
	quest="Quest",
	starter="Starter Deck"
)

FRENCH = Translation(
	language=Language.FRENCH,
	# Colors (Always fully capitalized in the data file)
	AMBER="Ambre",
	AMETHYST="Améthyste",
	EMERALD="Émeraude",
	RUBY="Rubis",
	SAPPHIRE="Saphir",
	STEEL="Acier",
	# Rarities (Always fully capitalized in the data file)
	COMMON="Commune",
	UNCOMMON="Inhabituelle",
	RARE="Rare",
	SUPER="Très Rare",
	LEGENDARY="Légendaire",
	ENCHANTED="Enchantée",
	SPECIAL="Spécial",
	# Types
	Action="Action",
	Character="Personnage",
	Item="Objet",
	Location="Lieu",
	# Product names
	gateway="Prélude",
	quest="Quête",
	starter="Deck de Démarrage"
)

GERMAN = Translation(
	language=Language.GERMAN,
	# Colors (Always fully capitalized in the data file)
	AMBER="Bernstein",
	AMETHYST="Amethyst",
	EMERALD="Smaragd",
	RUBY="Rubin",
	SAPPHIRE="Saphir",
	STEEL="Stahl",
	# Rarities (Always fully capitalized in the data file)
	COMMON="Gewöhnlich",
	UNCOMMON="Ungewöhnlich",
	RARE="Selten",
	SUPER="Episch",
	LEGENDARY="Legendär",
	ENCHANTED="Verzaubert",
	SPECIAL="Speziell",
	# Types
	Action="Aktion",
	Character="Charakter",
	Item="Gegenstand",
	Location="Ort",
	# Product names
	gateway="Der Einstieg",
	quest="Chroniken",
	starter="Deck für 1 Person"
)

ITALIAN = Translation(
	language=Language.ITALIAN,
	# Colors (Always fully capitalized in the data file)
	AMBER="Ambra",
	AMETHYST="Ametista",
	EMERALD="Smeraldo",
	RUBY="Rubino",
	SAPPHIRE="Zaffiro",
	STEEL="Acciaio",
	# Rarities (Always fully capitalized in the data file)
	COMMON="Comune",
	UNCOMMON="Non comune",
	RARE="Rara",
	SUPER="Super Rara",
	LEGENDARY="Leggendaria",
	ENCHANTED="Incantata",
	SPECIAL="Speciale",
	# Types
	Action="Azione",
	Character="Personaggio",
	Item="Oggetto",
	Location="Luogo",
	# Product names
	gateway="Preludio",
	quest="Avventura",
	starter="Mazzi per giocatore singolo"
)

def getForLanguage(language: Language.Language):
	for translation in (ENGLISH, FRENCH, GERMAN, ITALIAN):
		if translation.language == language:
			return translation
	raise ValueError(f"No translation found for language {language}")
