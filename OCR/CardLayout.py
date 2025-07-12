import dataclasses
from typing import Optional

from OCR import ImageArea as IA


@dataclasses.dataclass
class CardLayout:
	"""
	Defines which Image Areas to use for various card parts
	"""
	name: IA.ImageArea
	types: IA.ImageArea
	textbox: IA.ImageArea
	# Character only
	version: Optional[IA.ImageArea] = None  # The subtitle of a card, only used for Characters and Locations
	strength: Optional[IA.ImageArea] = None
	willpower: Optional[IA.ImageArea] = None
	# Location only
	moveCost: Optional[IA.ImageArea] = None
	# At the bottom so we can set a default, since it's the same for almost every card
	# Actually set this in __post_innit__ instead of just setting it here because dataclass field defaults can't be mutable
	ink: IA.ImageArea = None
	artist: IA.ImageArea = None
	identifier: IA.ImageArea = None

	def __post_init__(self):
		if self.ink is None:
			self.ink = IA.INK_COST
		if self.artist is None:
			self.artist = IA.ARTIST
		if self.identifier is None:
			self.identifier = IA.CARD_IDENTIFIER


DEFAULT = CardLayout(IA.CARD_NAME, IA.TYPE, IA.FULL_WIDTH_TEXT_BOX)
DEFAULT_CHARACTER = CardLayout(IA.CHARACTER_NAME, IA.TYPE, IA.CHARACTER_TEXT_BOX, IA.CARD_IDENTIFIER, IA.CHARACTER_VERSION, IA.STRENGTH, IA.WILLPOWER)
DEFAULT_LOCATION = CardLayout(IA.LOCATION_NAME, IA.LOCATION_TYPE, IA.LOCATION_TEXTBOX, IA.LOCATION_VERSION, willpower=IA.LOCATION_WILLPOWER, moveCost=IA.LOCATION_MOVE_COST, artist=IA.LOCATION_ARTIST, identifier=IA.LOCATION_IDENTIFIER)

ENCHANTED = dataclasses.replace(DEFAULT, textbox=IA.ENCHANTED_FULL_WIDTH_TEXT_BOX)
ENCHANTED_CHARACTER = dataclasses.replace(DEFAULT_CHARACTER, textbox=IA.ENCHANTED_CHARACTER_TEXT_BOX)
ENCHANTED_LOCATION = dataclasses.replace(DEFAULT_LOCATION, textbox=IA.ENCHANTED_LOCATION_TEXT_BOX)

QUEST = dataclasses.replace(DEFAULT, textbox=IA.QUEST_FULL_WIDTH_TEXT_BOX)
QUEST_CHARACTER = dataclasses.replace(DEFAULT, textbox=IA.QUEST_TEXTBOX)

NEW_ENCHANTED = CardLayout(IA.NEW_ENCHANTED_CARD_NAME, IA.NEW_ENCHANTED_TYPE, IA.NEW_ENCHANTED_FULL_WIDTH_TEXT_BOX)
NEW_ENCHANTED_CHARACTER = CardLayout(IA.NEW_ENCHANTED_CHARACTER_NAME, IA.NEW_ENCHANTED_TYPE, IA.NEW_ENCHANTED_CHARACTER_TEXT_BOX, IA.NEW_ENCHANTED_VERSION, IA.STRENGTH, IA.WILLPOWER)
NEW_ENCHANTED_LOCATION = dataclasses.replace(ENCHANTED_LOCATION, types=IA.NEW_ENCHANTED_LOCATION_TYPE, textbox=IA.NEW_ENCHANTED_LOCATION_TEXT_BOX)
