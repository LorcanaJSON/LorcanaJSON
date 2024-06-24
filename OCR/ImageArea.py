from collections import namedtuple

import cv2


# The image areas defined below are based on images of a set size, since that's the size they are in the official app
IMAGE_WIDTH = 1468
IMAGE_HEIGHT = 2048

TextColour = namedtuple("TextColour", ("name", "thresholdValue", "thresholdType"))
TEXT_COLOUR_WHITE = TextColour("white", 150, cv2.THRESH_BINARY_INV)
TEXT_COLOUR_WHITE_LIGHT_BACKGROUND = TextColour("whiteOnLight", 200, cv2.THRESH_BINARY_INV)
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
CHARACTER_NAME = ImageArea("characterName", "Character Name", _Coords(60, 1111, 1026, 1213), TEXT_COLOUR_WHITE_LIGHT_BACKGROUND)
CARD_NAME = ImageArea("cardName", "Card Name", _Coords(88, 1124, 1393, 1245), TEXT_COLOUR_WHITE_LIGHT_BACKGROUND)
CHARACTER_SUBTITLE = ImageArea("characterSubtitle", "Character Subtitle", _Coords(60, 1213, 1026, 1287), TEXT_COLOUR_WHITE_LIGHT_BACKGROUND)
STRENGTH = ImageArea("strength", "Strength", _Coords(1099, 1146, 1188, 1244), TEXT_COLOUR_BLACK, True)
WILLPOWER = ImageArea("willpower", "Willpower", _Coords(1273, 1146, 1362, 1244), TEXT_COLOUR_WHITE, True)
CHARACTER_TEXT_BOX = ImageArea("textbox", "Character Text Box", _Coords(66,1378,  1311,1901), TEXT_COLOUR_MIDDLE)
ENCHANTED_CHARACTER_TEXT_BOX = ImageArea("textbox", "Enchanted Character Text Box", _Coords(36,1395,  1309,1901), TEXT_COLOUR_MIDDLE)
FULL_WIDTH_TEXT_BOX = ImageArea("textbox", "Full Width Text Box", _Coords(66,1378,  1400,1901), TEXT_COLOUR_MIDDLE)
ENCHANTED_FULL_WIDTH_TEXT_BOX = ImageArea("textbox", "Enchanted Full Width Text Box", _Coords(35,1378,  1435,1901), TEXT_COLOUR_MIDDLE)
ARTIST = ImageArea("artist", "Artist", _Coords(109, 1925, 666, 1969), TEXT_COLOUR_WHITE)
CARD_IDENTIFIER = ImageArea("card_identifier", "Card Identifier", _Coords(54,1969, 359,2020), TEXT_COLOUR_WHITE)

LOCATION_NAME = ImageArea("cardName", "Location Name", _Coords(424,740, 1700,849), TEXT_COLOUR_WHITE_LIGHT_BACKGROUND)
LOCATION_SUBTITLE = ImageArea("subtitle", "Location Subtitle", _Coords(424,846, 1700,918), TEXT_COLOUR_WHITE_LIGHT_BACKGROUND)
LOCATION_TYPE = ImageArea("type", "Location Type", _Coords(210,934, 1855,998), TEXT_COLOUR_WHITE)
LOCATION_TEXTBOX = ImageArea("textbox", "Location Text Box", _Coords(65,1017, 1818,1317), TEXT_COLOUR_MIDDLE)
ENCHANTED_LOCATION_TEXT_BOX = ImageArea("textbox", "Enchanted Location Text Box", _Coords(20,1017, 1818,1317), TEXT_COLOUR_MIDDLE)
LOCATION_MOVE_COST = ImageArea("moveCost", "Location Move Cost", _Coords(152,767, 227,860), TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, isNumeric=True)
LOCATION_WILLPOWER = ImageArea("willpower", "Location Willpower", _Coords(1827, 767, 1919, 873), TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, isNumeric=True)
LOCATION_ARTIST = ImageArea("artist", "Location Artist", _Coords(112,1331, 948,1381), TEXT_COLOUR_WHITE)
LOCATION_IDENTIFIER = ImageArea("identifier", "Location Identifier", _Coords(54,1381, 365,1431), TEXT_COLOUR_WHITE)

QUEST_TEXTBOX = ImageArea("textbox", "Quest Text Box", _Coords(78,1378,  1311,1882), TEXT_COLOUR_WHITE)
QUEST_FULL_WIDTH_TEXT_BOX = ImageArea("textbox", "Full Width Quest Text Box", _Coords(78,1378,  1400,1861), TEXT_COLOUR_WHITE)

IS_INKABLE_CHECK = ImageArea("isInkable", "Is Inkable", _Coords(69,142, 70,143), TEXT_COLOUR_MIDDLE)
IS_BORDERLESS_CHECK = ImageArea("isBorderless", "Is Borderless", _Coords(5,260, 40,1290), TEXT_COLOUR_MIDDLE)
IS_LOCATION_CHECK = ImageArea("isLocation", "Is Location", _Coords(1330,414, 1392,848), TEXT_COLOUR_MIDDLE)
