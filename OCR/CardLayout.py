import dataclasses
from typing import Union

from OCR.ImageArea import *


@dataclasses.dataclass
class CardLayout:
	"""
	Defines which Image Areas to use for various card parts
	"""
	name: ImageArea
	types: ImageArea
	textbox: ImageArea
	# Character only
	version: Union[ImageArea, None] = None  # The subtitle of a card, only used for Characters and Locations
	strength: Union[ImageArea, None] = None
	willpower: Union[ImageArea, None] = None
	# Location only
	moveCost: Union[ImageArea, None] = None
	# At the bottom so we can set a default, since it's the same for almost every card
	# Actually set this in __post_innit__ instead of just setting it here because dataclass field defaults can't be mutable
	ink: ImageArea = None
	artist: ImageArea = None
	identifier: ImageArea = None

	def __post_init__(self):
		if self.ink is None:
			self.ink = INK_COST
		if self.artist is None:
			self.artist = ARTIST
		if self.identifier is None:
			self.identifier = CARD_IDENTIFIER


DEFAULT = CardLayout(CARD_NAME, TYPE, FULL_WIDTH_TEXT_BOX)
DEFAULT_CHARACTER = CardLayout(CHARACTER_NAME, TYPE, CHARACTER_TEXT_BOX, CARD_IDENTIFIER, CHARACTER_VERSION, STRENGTH, WILLPOWER)
DEFAULT_LOCATION = CardLayout(LOCATION_NAME, LOCATION_TYPE, LOCATION_TEXTBOX, LOCATION_VERSION, willpower=LOCATION_WILLPOWER, moveCost=LOCATION_MOVE_COST, artist=LOCATION_ARTIST, identifier=LOCATION_IDENTIFIER)

ENCHANTED = dataclasses.replace(DEFAULT, textbox=ENCHANTED_FULL_WIDTH_TEXT_BOX)
ENCHANTED_CHARACTER = dataclasses.replace(DEFAULT_CHARACTER, textbox=ENCHANTED_CHARACTER_TEXT_BOX)
ENCHANTED_LOCATION = dataclasses.replace(DEFAULT_LOCATION, textbox=ENCHANTED_LOCATION_TEXT_BOX)

QUEST = dataclasses.replace(DEFAULT, textbox=QUEST_FULL_WIDTH_TEXT_BOX)
QUEST_CHARACTER = dataclasses.replace(DEFAULT, textbox=QUEST_TEXTBOX)

NEW_ENCHANTED = CardLayout(NEW_ENCHANTED_CARD_NAME, NEW_ENCHANTED_TYPE, NEW_ENCHANTED_FULL_WIDTH_TEXT_BOX)
NEW_ENCHANTED_CHARACTER = CardLayout(NEW_ENCHANTED_CHARACTER_NAME, NEW_ENCHANTED_TYPE, NEW_ENCHANTED_CHARACTER_TEXT_BOX, NEW_ENCHANTED_VERSION, STRENGTH, WILLPOWER)
NEW_ENCHANTED_LOCATION = dataclasses.replace(ENCHANTED_LOCATION, types=NEW_ENCHANTED_LOCATION_TYPE, textbox=NEW_ENCHANTED_LOCATION_TEXT_BOX)
