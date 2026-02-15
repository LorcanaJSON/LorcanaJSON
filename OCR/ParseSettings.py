import dataclasses
from enum import auto, StrEnum
from typing import Dict, Optional, Tuple

from OCR import CardLayout, ImageArea
from util.IdentifierParser import Identifier

_BLACK = (0, 0, 0)
_WHITE = (255, 255, 255)
_OPTIONAL_TEXTBOX_OFFSET: int = 41  # A standard textbox offset to use, since it's the same for a lot of cards that need it


class LABEL_PARSING_METHODS(StrEnum):
	DEFAULT = auto()
	FALLBACK_WHITE_ABILITY_TEXT = auto()
	FALLBACK_BY_LINES = auto()
	NONE = auto()

@dataclasses.dataclass
class ParseSettings:
	# Layouts to use. Set these to None here and actually set them to the defaults in __post_init__ since you can't assign mutables at class-level in a dataclass
	cardLayout: CardLayout.CardLayout = None
	characterCardLayout: CardLayout.CardLayout = None
	locationCardLayout: CardLayout.CardLayout = None
	textboxOffset: int = 0  # Shrinks the textbox from the left by this many pixels
	textboxRightOffset: int = 0  # Shrinks the textbox from the right by this many pixels
	labelParsingMethod: LABEL_PARSING_METHODS = LABEL_PARSING_METHODS.DEFAULT
	thresholdTextColor: ImageArea.TextColour = ImageArea.TEXT_COLOUR_BLACK
	labelIsDarkerThanBackground: bool = True  # For most cards, the label is darker than the background, which is used when finding labels. Set this to 'False' if the label is lighter than the background
	labelTextColor: ImageArea.TextColour = ImageArea.TEXT_COLOUR_WHITE
	labelStartThreshold: int = 105  # Pixel values lower than this (if 'labelIsDarkerThanBackground', otherwise higher) indicate a label started
	labelEndThreshold: int = 110  # Pixel values higher than this (if 'labelIsDarkerThanBackground', otherwise lower) indicate a label ended
	labelMaskColor: Tuple[int, int, int] = _WHITE
	cardTextHasOutline: bool = False  # Iconic cards don't just have one card text color, but they have dark text with a white outline, which confuses parsing. Set this to True for those cards to floodfill and fix that problem
	typeImageTextColorOverride: Optional[ImageArea.TextColour] = None  # If a different type image text color should be used than default for the card layout, set it here
	parseIdentifier: bool = False
	getIdentifierFromCard: bool = False
	forceArtistTextColor: Optional[ImageArea.TextColour] = None
	# Force some checks that could fail or be wrong on some cards. 'None' means they're not overridden, setting them to 'True' or 'False' uses those values instead of whatever is normally determined
	hasCardTextOverride: Optional[bool] = None
	hasFlavorTextOverride: Optional[bool] = None
	isLocationOverride: Optional[bool] = None
	isItemOverride: Optional[bool] = None

	def __post_init__(self):
		# Set layouts to defaults here, because we can't set them on class-level since they can't be mutable
		if self.cardLayout is None:
			self.cardLayout = CardLayout.DEFAULT
		if self.characterCardLayout is None:
			self.characterCardLayout = CardLayout.DEFAULT_CHARACTER
		if self.locationCardLayout is None:
			self.locationCardLayout = CardLayout.DEFAULT_LOCATION


_DEFAULT_PARSE_SETTINGS = ParseSettings()
_DEFAULT_ENCHANTED_PARSE_SETTINGS = ParseSettings(CardLayout.ENCHANTED, CardLayout.ENCHANTED_CHARACTER, CardLayout.ENCHANTED_LOCATION)
_DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS = ParseSettings(CardLayout.NEW_ENCHANTED, CardLayout.NEW_ENCHANTED_CHARACTER, CardLayout.NEW_ENCHANTED_LOCATION)
_DEFAULT_EPIC_PARSE_SETTINGS = dataclasses.replace(_DEFAULT_ENCHANTED_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.DEFAULT, textboxOffset=_OPTIONAL_TEXTBOX_OFFSET, labelStartThreshold=175, labelEndThreshold=185, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND)
_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET: Dict[str, ParseSettings] = {
	"5": dataclasses.replace(_DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	"6": dataclasses.replace(_DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_BY_LINES, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	"7": dataclasses.replace(_DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	"8": dataclasses.replace(_DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	"9": dataclasses.replace(_DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	"10": dataclasses.replace(_DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	"11": dataclasses.replace(_DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
}
_PARSE_SETTINGS_BY_SET: Dict[str, ParseSettings] = {
	"Q1": ParseSettings(labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE, labelMaskColor=_BLACK),
	"Q2": ParseSettings(labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE, labelMaskColor=_BLACK, textboxOffset=26, textboxRightOffset=24)
}
_PARSE_SETTINGS_BY_GROUPING: Dict[str, ParseSettings] = {
	"C1": ParseSettings(textboxOffset=_OPTIONAL_TEXTBOX_OFFSET),
	"D23": ParseSettings(getIdentifierFromCard=True, textboxOffset=_OPTIONAL_TEXTBOX_OFFSET, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_BY_LINES),
	"P1": ParseSettings(getIdentifierFromCard=True),
	"P3": dataclasses.replace(_DEFAULT_PARSE_SETTINGS, labelStartThreshold=175, labelEndThreshold=180, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
}
_PARSE_SETTINGS_BY_ID: Dict[int, ParseSettings] = {
	676: _DEFAULT_ENCHANTED_PARSE_SETTINGS,
	677: _DEFAULT_ENCHANTED_PARSE_SETTINGS,
	678: _DEFAULT_ENCHANTED_PARSE_SETTINGS,
	679: _DEFAULT_ENCHANTED_PARSE_SETTINGS,
	680: _DEFAULT_ENCHANTED_PARSE_SETTINGS,
	681: _DEFAULT_ENCHANTED_PARSE_SETTINGS,
	954: _DEFAULT_ENCHANTED_PARSE_SETTINGS,
	1161: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["5"], typeImageTextColorOverride=ImageArea.TEXT_COLOUR_WHITE),
	1172: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["5"], isLocationOverride=True),
	1178: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["5"], isLocationOverride=True),
	1186: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["5"], hasFlavorTextOverride=False, typeImageTextColorOverride=ImageArea.TEXT_COLOUR_WHITE),
	1187: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["C1"], labelParsingMethod=LABEL_PARSING_METHODS.NONE),
	1191: ParseSettings(labelParsingMethod=LABEL_PARSING_METHODS.DEFAULT, textboxOffset=_OPTIONAL_TEXTBOX_OFFSET, getIdentifierFromCard=True),
	1199: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["C1"], textboxOffset=_OPTIONAL_TEXTBOX_OFFSET-5),
	1197: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["C1"], textboxOffset=39),
	1405: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["6"], typeImageTextColorOverride=ImageArea.TEXT_COLOUR_WHITE),
	1406: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["6"], isLocationOverride=True),
	1407: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["6"], typeImageTextColorOverride=ImageArea.TEXT_COLOUR_WHITE),
	1412: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["6"], labelParsingMethod=LABEL_PARSING_METHODS.NONE),
	1415: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["6"], labelParsingMethod=LABEL_PARSING_METHODS.NONE),
	1418: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["6"], labelParsingMethod=LABEL_PARSING_METHODS.NONE),
	1421: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["6"], isLocationOverride=True),
	1430: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, textboxOffset=24),
	1431: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, textboxOffset=24),
	1432: ParseSettings(textboxOffset=0, labelParsingMethod=LABEL_PARSING_METHODS.DEFAULT, getIdentifierFromCard=True),
	1429: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["5"], hasFlavorTextOverride=False),
	1638: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["7"], typeImageTextColorOverride=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	1641: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["7"], isItemOverride=True),
	1662: _PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["7"],
	1664: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["C1"], labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_BY_LINES),
	1869: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["8"], typeImageTextColorOverride=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	1871: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["8"], typeImageTextColorOverride=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	1872: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["8"], typeImageTextColorOverride=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	1893: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["8"], typeImageTextColorOverride=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	1895: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["D23"], textboxOffset=15),
	1931: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_BY_LINES),
	1932: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_BY_LINES),
	1933: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_BY_LINES, hasFlavorTextOverride=True),
	1934: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_BY_LINES),
	1935: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_BY_LINES),
	1938: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, hasCardTextOverride=True),
	2084: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, hasCardTextOverride=True),
	2141: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["9"], typeImageTextColorOverride=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, hasCardTextOverride=True),
	2142: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["9"], cardLayout=CardLayout.NEW_ENCHANTED_SMALL_TEXTBOX, characterCardLayout=CardLayout.NEW_ENCHANTED_CHARACTER_SMALL_TEXTBOX),
	2143: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["9"], cardLayout=CardLayout.NEW_ENCHANTED_SMALL_TEXTBOX),
	2145: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["9"], cardLayout=CardLayout.NEW_ENCHANTED_SMALL_TEXTBOX, characterCardLayout=CardLayout.NEW_ENCHANTED_CHARACTER_SMALL_TEXTBOX),
	2149: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["9"], cardLayout=CardLayout.NEW_ENCHANTED_SMALL_TEXTBOX, characterCardLayout=CardLayout.NEW_ENCHANTED_CHARACTER_SMALL_TEXTBOX),
	2160: dataclasses.replace(_DEFAULT_EPIC_PARSE_SETTINGS, labelStartThreshold=180),
	2177: dataclasses.replace(_DEFAULT_ENCHANTED_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	2178: dataclasses.replace(_DEFAULT_ENCHANTED_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	2183: _PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["8"],
	2184: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, textboxOffset=18),
	2188: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, textboxOffset=24),
	2413: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["10"], typeImageTextColorOverride=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	2417: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["10"], cardLayout=CardLayout.NEW_ENCHANTED_SMALL_TEXTBOX),
	2420: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["10"], cardLayout=CardLayout.NEW_ENCHANTED_SMALL_TEXTBOX),
	2426: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["10"], cardLayout=CardLayout.NEW_ENCHANTED_SMALL_TEXTBOX),
	2430: dataclasses.replace(_DEFAULT_ENCHANTED_PARSE_SETTINGS, cardTextHasOutline=True, labelIsDarkerThanBackground=False, labelMaskColor=_BLACK, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND,
							  thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, forceArtistTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	2431: dataclasses.replace(_DEFAULT_ENCHANTED_PARSE_SETTINGS, cardTextHasOutline=True, labelIsDarkerThanBackground=False, labelMaskColor=_BLACK, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	2432: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["P3"], forceArtistTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	2433: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, textboxOffset=15),
	2435: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["P3"], forceArtistTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	2436: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["P3"], forceArtistTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	2437: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["P3"], forceArtistTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	2439: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["P3"], labelIsDarkerThanBackground=False, labelTextColor=ImageArea.TEXT_COLOUR_BLACK, labelMaskColor=_BLACK, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE),
	2440: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["P3"], labelIsDarkerThanBackground=False, labelTextColor=ImageArea.TEXT_COLOUR_BLACK, labelMaskColor=_BLACK, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE),
	2441: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["P3"], labelIsDarkerThanBackground=False, labelTextColor=ImageArea.TEXT_COLOUR_BLACK, labelMaskColor=_BLACK, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE),
	2442: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["P3"], labelIsDarkerThanBackground=False, labelTextColor=ImageArea.TEXT_COLOUR_BLACK, labelMaskColor=_BLACK, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE),
	2443: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["P3"], labelIsDarkerThanBackground=False, labelTextColor=ImageArea.TEXT_COLOUR_BLACK, labelMaskColor=_BLACK, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE),
	2444: _PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["10"],
	2445: _PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["10"],
	2450: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["P3"], labelStartThreshold=100, labelEndThreshold=170, labelTextColor=ImageArea.TEXT_COLOUR_MIDDLE, textboxOffset=10, hasCardTextOverride=True),
	2461: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["P3"], labelStartThreshold=100, labelEndThreshold=170, labelTextColor=ImageArea.TEXT_COLOUR_MIDDLE, textboxOffset=10),
	2462: dataclasses.replace(_PARSE_SETTINGS_BY_GROUPING["P3"], labelStartThreshold=100, labelEndThreshold=170, labelTextColor=ImageArea.TEXT_COLOUR_MIDDLE, textboxOffset=10),
	2669: dataclasses.replace(_DEFAULT_EPIC_PARSE_SETTINGS, labelStartThreshold=180, labelEndThreshold=185),
	2687: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["11"], cardLayout=CardLayout.NEW_ENCHANTED_SMALL_TEXTBOX),
	2688: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["11"], cardLayout=CardLayout.NEW_ENCHANTED_SMALL_TEXTBOX),
	2691: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["11"], cardLayout=CardLayout.NEW_ENCHANTED_SMALL_TEXTBOX),
	2692: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["11"], characterCardLayout=CardLayout.NEW_ENCHANTED_CHARACTER_SMALL_TEXTBOX),
	2694: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["11"], cardLayout=CardLayout.NEW_ENCHANTED_SMALL_TEXTBOX),
	2702: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["11"], typeImageTextColorOverride=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	2704: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["11"], labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, textboxOffset=-80, thresholdTextColor=ImageArea.TEXT_COLOUR_MIDDLE),
	2705: dataclasses.replace(_PARSE_SETTINGS_FOR_ENCHANTED_BY_SET["11"], cardLayout=CardLayout.NEW_ENCHANTED_CHARACTER_SMALL_TEXTBOX, characterCardLayout=CardLayout.NEW_ENCHANTED_CHARACTER_SMALL_TEXTBOX,
							  labelIsDarkerThanBackground=False, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_BY_LINES, textboxOffset=-75),
	2706: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, labelIsDarkerThanBackground=False, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE),
	2707: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, labelIsDarkerThanBackground=False, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE),
	2708: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, labelIsDarkerThanBackground=False, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE),
	2710: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, labelIsDarkerThanBackground=False, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE),
	2714: dataclasses.replace(_DEFAULT_PARSE_SETTINGS, textboxOffset=15, forceArtistTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	2715: _DEFAULT_PARSE_SETTINGS
}

def getParseSetingsById(cardId: int) -> Optional[ParseSettings]:
	return _PARSE_SETTINGS_BY_ID.get(cardId, None)

def getParseSettings(cardId: int, identifier: Identifier, isEpic: bool, isEnchanted: bool) -> ParseSettings:
	if cardId in _PARSE_SETTINGS_BY_ID:
		return _PARSE_SETTINGS_BY_ID[cardId]
	elif identifier.grouping in _PARSE_SETTINGS_BY_GROUPING:
		return _PARSE_SETTINGS_BY_GROUPING[identifier.grouping]
	elif identifier.setCode in _PARSE_SETTINGS_BY_SET:
		return _PARSE_SETTINGS_BY_SET[identifier.setCode]
	elif isEpic:
		return _DEFAULT_EPIC_PARSE_SETTINGS
	elif isEnchanted:
		if identifier.setCode in _PARSE_SETTINGS_FOR_ENCHANTED_BY_SET:
			return _PARSE_SETTINGS_FOR_ENCHANTED_BY_SET[identifier.setCode]
		else:
			return _DEFAULT_ENCHANTED_PARSE_SETTINGS
	return _DEFAULT_PARSE_SETTINGS
