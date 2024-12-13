import dataclasses
from enum import auto, StrEnum
from typing import Dict, Tuple, Union

from OCR import CardLayout, ImageArea
from util.IdentifierParser import Identifier

_BLACK = (0, 0, 0)
_WHITE = (255, 255, 255)
_OPTIONAL_TEXTBOX_OFFSET: int = 41  # A standard textbox offset to use, since it's the same for a lot of cards that need it


class LABEL_PARSING_METHODS(StrEnum):
	DEFAULT = auto()
	FALLBACK_WHITE_ABILITY_TEXT = auto()
	FALLBACK_BY_LINES = auto()

@dataclasses.dataclass
class ParseSettings:
	# Layouts to use. Set these to None here and actually set them to the defaults in __post_init__ since you can't assign mutables at class-level in a dataclass
	cardLayout: CardLayout.CardLayout = None
	characterCardLayout: CardLayout.CardLayout = None
	locationCardLayout: CardLayout.CardLayout = None
	textboxOffset: int = 0
	labelParsingMethod: LABEL_PARSING_METHODS = LABEL_PARSING_METHODS.DEFAULT
	thresholdTextColor: ImageArea.TextColour = ImageArea.TEXT_COLOUR_BLACK
	labelTextColor: ImageArea.TextColour = ImageArea.TEXT_COLOUR_WHITE
	labelMaskColor: Tuple[int, int, int] = _WHITE
	parseIdentifier: bool = False
	getIdentifierFromCard: bool = False
	hasFlavorTextOverride: Union[None, bool] = None

	def __post_init__(self):
		# Set layouts to defaults here, because we can't set them on class-level since they can't be mutalbe
		if self.cardLayout is None:
			self.cardLayout = CardLayout.DEFAULT
		if self.characterCardLayout is None:
			self.characterCardLayout = CardLayout.DEFAULT_CHARACTER
		if self.locationCardLayout is None:
			self.locationCardLayout = CardLayout.DEFAULT_LOCATION


_DEFAULT_PARSE_SETTINGS = ParseSettings()
_DEFAULT_ENCHANTED_PARSE_SETTINGS = ParseSettings(CardLayout.ENCHANTED, CardLayout.ENCHANTED_CHARACTER, CardLayout.ENCHANTED_LOCATION)
_DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS = ParseSettings(CardLayout.NEW_ENCHANTED, CardLayout.NEW_ENCHANTED_CHARACTER, CardLayout.NEW_ENCHANTED_LOCATION)
_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET: Dict[str, ParseSettings] = {
	"5": dataclasses.replace(_DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	"6": dataclasses.replace(_DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_BY_LINES),
}
_PARSE_SETTINGS_BY_SET: Dict[str, ParseSettings] = {
	"Q1": ParseSettings(labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE, labelMaskColor=_BLACK),
}
_PARSE_SETTINGS_BY_GROUPING: Dict[str, ParseSettings] = {
	"C1": ParseSettings(textboxOffset=_OPTIONAL_TEXTBOX_OFFSET),
	"D23": ParseSettings(getIdentifierFromCard=True, textboxOffset=_OPTIONAL_TEXTBOX_OFFSET, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_BY_LINES),
	"P1": ParseSettings(getIdentifierFromCard=True)
}
_PARSE_SETTINGS_BY_ID: Dict[int, ParseSettings] = {
	677: _DEFAULT_ENCHANTED_PARSE_SETTINGS,
	678: _DEFAULT_ENCHANTED_PARSE_SETTINGS,
	679: _DEFAULT_ENCHANTED_PARSE_SETTINGS,
	680: _DEFAULT_ENCHANTED_PARSE_SETTINGS,
	681: _DEFAULT_ENCHANTED_PARSE_SETTINGS,
	954: _DEFAULT_ENCHANTED_PARSE_SETTINGS,
	1186: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["5"], hasFlavorTextOverride=False),
	1191: ParseSettings(labelParsingMethod=LABEL_PARSING_METHODS.DEFAULT, textboxOffset=_OPTIONAL_TEXTBOX_OFFSET, getIdentifierFromCard=True),
	1432: ParseSettings(textboxOffset=0, labelParsingMethod=LABEL_PARSING_METHODS.DEFAULT, getIdentifierFromCard=True),
	1429: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["5"], hasFlavorTextOverride=False),
}


def getParseSettings(cardId: int, identifier: Identifier, isEnchanted: bool) -> ParseSettings:
	if cardId in _PARSE_SETTINGS_BY_ID:
		return _PARSE_SETTINGS_BY_ID[cardId]
	elif identifier.grouping in _PARSE_SETTINGS_BY_GROUPING:
		return _PARSE_SETTINGS_BY_GROUPING[identifier.grouping]
	elif identifier.setCode in _PARSE_SETTINGS_BY_SET:
		return _PARSE_SETTINGS_BY_SET[identifier.setCode]
	elif isEnchanted:
		if identifier.setCode in _PARSE_SETTINGS_FOR_ENCHANTED_BY_SET:
			return _PARSE_SETTINGS_FOR_ENCHANTED_BY_SET[identifier.setCode]
		else:
			return _DEFAULT_ENCHANTED_PARSE_SETTINGS
	return _DEFAULT_PARSE_SETTINGS