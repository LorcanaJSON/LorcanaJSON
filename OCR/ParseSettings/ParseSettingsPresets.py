import dataclasses
from typing import Dict

from OCR import CardLayout, ImageArea
from OCR.ParseSettings import ParseSettingConstants
from OCR.ParseSettings.LabelParsingMethods import LABEL_PARSING_METHODS
from OCR.ParseSettings.ParseSettings import ParseSettings

DEFAULT_PARSE_SETTINGS = ParseSettings()
DEFAULT_ENCHANTED_PARSE_SETTINGS = ParseSettings(CardLayout.ENCHANTED, CardLayout.ENCHANTED_CHARACTER, CardLayout.ENCHANTED_LOCATION)
DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS = ParseSettings(CardLayout.NEW_ENCHANTED, CardLayout.NEW_ENCHANTED_CHARACTER, CardLayout.NEW_ENCHANTED_LOCATION,
											labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND)
DEFAULT_EPIC_PARSE_SETTINGS = dataclasses.replace(DEFAULT_ENCHANTED_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.DEFAULT, textboxLeftOffset=ParseSettingConstants.OPTIONAL_TEXTBOX_OFFSET,
												  labelStartThreshold=175, labelEndThreshold=185, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND)
PARSE_SETTINGS_FOR_EPIC_BY_SET: Dict[str, ParseSettings] = {
	"13": dataclasses.replace(DEFAULT_EPIC_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_BY_LINES),
}
PARSE_SETTINGS_FOR_ENCHANTED_BY_SET: Dict[str, ParseSettings] = {
	"6": dataclasses.replace(DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_BY_LINES, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, thresholdTextColor=ImageArea.TEXT_COLOUR_BLACK),
	"13": dataclasses.replace(DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS, typeImageTextColorOverride=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, typeImageRightOffset=60),
}
PARSE_SETTINGS_BY_SET: Dict[str, ParseSettings] = {
	"Q1": ParseSettings(labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE, labelMaskColor=ParseSettingConstants.BLACK),
	"Q2": ParseSettings(labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE, labelMaskColor=ParseSettingConstants.BLACK, textboxLeftOffset=26, textboxRightOffset=24)
}
PARSE_SETTINGS_BY_GROUPING: Dict[str, ParseSettings] = {
	"C1": ParseSettings(textboxLeftOffset=ParseSettingConstants.OPTIONAL_TEXTBOX_OFFSET),
	"D23": ParseSettings(getIdentifierFromCard=True, textboxLeftOffset=ParseSettingConstants.OPTIONAL_TEXTBOX_OFFSET, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_BY_LINES),
	"DIS": dataclasses.replace(DEFAULT_PARSE_SETTINGS, labelStartThreshold=100, labelEndThreshold=170, labelTextColor=ImageArea.TEXT_COLOUR_MIDDLE, textboxLeftOffset=10),
	"P1": ParseSettings(getIdentifierFromCard=True),
	"P3": dataclasses.replace(DEFAULT_PARSE_SETTINGS, labelStartThreshold=175, labelEndThreshold=180, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND),
	"PD1": dataclasses.replace(DEFAULT_PARSE_SETTINGS, labelIsDarkerThanBackground=False, thresholdTextColor=ImageArea.TEXT_COLOUR_WHITE, labelMaskColor=ParseSettingConstants.BLACK),
	"CC1": dataclasses.replace(DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS, labelParsingMethod=LABEL_PARSING_METHODS.FALLBACK_BY_LINES, labelTextColor=ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND, thresholdTextColor=ImageArea.TEXT_COLOUR_BLACK),
}
