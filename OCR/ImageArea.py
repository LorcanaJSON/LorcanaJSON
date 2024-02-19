from collections import namedtuple

import cv2


TextColour = namedtuple("TextColour", ("name", "thresholdValue", "thresholdType"))
TEXT_COLOUR_WHITE = TextColour("white", 150, cv2.THRESH_BINARY_INV)
TEXT_COLOUR_BLACK = TextColour("black", 50, cv2.THRESH_BINARY)
TEXT_COLOUR_MIDDLE = TextColour("middle", 127, cv2.THRESH_BINARY)

_Coords = namedtuple("Coords", ("left", "top", "right", "bottom"))

class ImageArea:
	def __init__(self, keyName: str, description: str, coords: _Coords, textColour: TextColour, isNumeric: bool = False, shouldShowImage: bool = False):
		self.keyName = keyName
		self.description = description
		self.coords = coords
		self.textColour = textColour
		self.isNumeric = isNumeric
		self.shouldShowImage = shouldShowImage


# Coordinates are left, top, right, bottom. Based on image size of 1468 x 2048
TYPE = ImageArea("type", "Card Type", _Coords(168, 1300, 1298, 1360), TEXT_COLOUR_WHITE)
INK_COST = ImageArea("inkCost", "Ink Cost", _Coords(101, 116, 191, 197), TEXT_COLOUR_WHITE, True)
CHARACTER_NAME = ImageArea("characterName", "Character Name", _Coords(60, 1111, 1026, 1213), TEXT_COLOUR_WHITE)
CARD_NAME = ImageArea("cardName", "Card Name", _Coords(88, 1124, 1393, 1245), TEXT_COLOUR_WHITE)
CHARACTER_SUBTITLE = ImageArea("characterSubtitle", "Character Subtitle", _Coords(60, 1213, 1026, 1287), TEXT_COLOUR_WHITE)
STRENGTH = ImageArea("strength", "Strength", _Coords(1099, 1146, 1188, 1244), TEXT_COLOUR_BLACK, True)
WILLPOWER = ImageArea("willpower", "Willpower", _Coords(1273, 1146, 1362, 1244), TEXT_COLOUR_WHITE, True)
CHARACTER_TEXT_BOX = ImageArea("textbox", "Character Text Box", _Coords(66,1378,  1311,1901), TEXT_COLOUR_MIDDLE)
ENCHANTED_CHARACTER_TEXT_BOX = ImageArea("textbox", "Enchanted Character Text Box", _Coords(36,1395,  1309,1901), TEXT_COLOUR_MIDDLE)
FULL_WIDTH_TEXT_BOX = ImageArea("textbox", "Full Width Text Box", _Coords(66,1378,  1400,1901), TEXT_COLOUR_MIDDLE)
ARTIST = ImageArea("artist", "Artist", _Coords(109, 1925, 666, 1969), TEXT_COLOUR_WHITE)
CARD_IDENTIFIER = ImageArea("card_identifier", "Card Identifier", _Coords(54,1969, 359,2017), TEXT_COLOUR_WHITE)

IS_INKABLE_CHECK = ImageArea("isInkable", "Is Inkable", _Coords(69,142, 70,143), TEXT_COLOUR_MIDDLE)
IS_BORDERLESS_CHECK = ImageArea("isBorderless", "Is Borderless", _Coords(8,260, 48,1290), TEXT_COLOUR_MIDDLE)
