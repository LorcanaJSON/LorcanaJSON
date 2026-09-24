import dataclasses
from typing import Optional, Tuple

from OCR import CardLayout, ImageArea
from OCR.ParseSettings.LabelParsingMethods import LABEL_PARSING_METHODS
from OCR.ParseSettings import ParseSettingConstants


@dataclasses.dataclass(frozen=True)
class ParseSettings:
	# Layouts to use. Set these to None here and actually set them to the defaults in __post_init__ since you can't assign mutables at class-level in a dataclass
	cardLayout: CardLayout.CardLayout = CardLayout.DEFAULT
	characterCardLayout: CardLayout.CardLayout = CardLayout.DEFAULT_CHARACTER
	locationCardLayout: CardLayout.CardLayout = CardLayout.DEFAULT_LOCATION
	textboxLeftOffset: int = 0  # Shrinks the textbox from the left by this many pixels
	textboxRightOffset: int = 0  # Shrinks the textbox from the right by this many pixels
	textboxTopOffset: int = 0  # A positive number here starts the textbox image further down; this value gets added to the y-value from the CardLayout
	textboxBottomOffset: int = 0  # A positive number here ends the textbox image further down; this value gets added the the y-value from the CardLayout
	labelParsingMethod: LABEL_PARSING_METHODS = LABEL_PARSING_METHODS.DEFAULT
	thresholdTextColor: ImageArea.TextColour = ImageArea.TEXT_COLOUR_BLACK
	labelIsDarkerThanBackground: bool = True  # For most cards, the label is darker than the background, which is used when finding labels. Set this to 'False' if the label is lighter than the background
	labelTextColor: ImageArea.TextColour = ImageArea.TEXT_COLOUR_WHITE
	labelStartThreshold: int = 105  # Pixel values lower than this (if 'labelIsDarkerThanBackground', otherwise higher) indicate a label started
	labelEndThreshold: int = 110  # Pixel values higher than this (if 'labelIsDarkerThanBackground', otherwise lower) indicate a label ended
	labelMaskColor: Tuple[int, int, int] = ParseSettingConstants.WHITE
	cardTextHasOutline: bool = False  # Iconic cards don't just have one card text color, but they have dark text with a white outline, which confuses parsing. Set this to True for those cards to floodfill and fix that problem
	typeImageTextColorOverride: Optional[ImageArea.TextColour] = None  # If a different type image text color should be used than default for the card layout, set it here
	typeImageLeftOffset: int = 0  # Positive values shrink the types subimage from the left, negative values make it wider on the left
	typeImageRightOffset: int = 0  # Positive values make the types subimage wider on the right, negative values shrink it on the right
	typeImageVerticalOffset: int = 0  # Positive values make the types subimage start further down, negative values make it start further up
	parseIdentifier: bool = False
	getIdentifierFromCard: bool = False
	forceArtistTextColor: Optional[ImageArea.TextColour] = None
	artistRightOffset: int = 0
	lineParsingMaxGap: int = 3  # The line parsing fallback method has a max distance between horizontally-adjacent lines to join them. This setting can override that limit
	# Line parsing color filter fallback needs a lower and and upper bound of colors to keep. For other parse settings, these values do nothing. NOTE: These are in BGR format
	colorFilterLowerBound: Optional[Tuple[int]] = None
	colorFilterUpperBound: Optional[Tuple[int]] = None
	# Force some checks that could fail or be wrong on some cards. 'None' means they're not overridden, setting them to 'True' or 'False' uses those values instead of whatever is normally determined
	hasCardTextOverride: Optional[bool] = None
	hasFlavorTextOverride: Optional[bool] = None
	isLocationOverride: Optional[bool] = None
	isItemOverride: Optional[bool] = None
