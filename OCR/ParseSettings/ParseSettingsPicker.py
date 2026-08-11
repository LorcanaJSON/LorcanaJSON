from typing import Dict

from OCR.ParseSettings import ParseSettingsCardIdOverrides, ParseSettingsPresets
from OCR.ParseSettings.ParseSettings import ParseSettings
from util.IdentifierParser import Identifier


def getParseSettings(cardId: int, identifier: Identifier, isEpic: bool, isEnchanted: bool) -> ParseSettings:
	if cardId in ParseSettingsCardIdOverrides.PARSE_SETTINGS_BY_ID:
		return ParseSettingsCardIdOverrides.PARSE_SETTINGS_BY_ID[cardId]
	elif identifier.grouping in ParseSettingsPresets.PARSE_SETTINGS_BY_GROUPING:
		return ParseSettingsPresets.PARSE_SETTINGS_BY_GROUPING[identifier.grouping]
	elif identifier.setCode in ParseSettingsPresets.PARSE_SETTINGS_BY_SET:
		return ParseSettingsPresets.PARSE_SETTINGS_BY_SET[identifier.setCode]
	elif isEpic:
		if identifier.setCode in ParseSettingsPresets.PARSE_SETTINGS_FOR_EPIC_BY_SET:
			return ParseSettingsPresets.PARSE_SETTINGS_FOR_EPIC_BY_SET[identifier.setCode]
		else:
			return ParseSettingsPresets.DEFAULT_EPIC_PARSE_SETTINGS
	elif isEnchanted:
		if identifier.setCode in ParseSettingsPresets.PARSE_SETTINGS_FOR_ENCHANTED_BY_SET:
			return ParseSettingsPresets.PARSE_SETTINGS_FOR_ENCHANTED_BY_SET[identifier.setCode]
		elif identifier.setCode in ("1", "2", "3", "4"):
			return ParseSettingsPresets.DEFAULT_ENCHANTED_PARSE_SETTINGS
		else:
			return ParseSettingsPresets.DEFAULT_NEW_ENCHANTED_PARSE_SETTINGS
	return ParseSettingsPresets.DEFAULT_PARSE_SETTINGS

def getParseSettingsForCard(card: Dict, identifier: Identifier) -> ParseSettings:
	return getParseSettings(card["culture_invariant_id"], identifier, card["rarity"] == "EPIC", card["rarity"] == "ENCHANTED")
