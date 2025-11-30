import json, logging, os
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

import GlobalConfig
from util import Language

_logger = logging.getLogger("LorcanaJSON")

_REPLACEMENT_NAMES: Dict[str, Union[str, Dict[Language.Language, str]]] = {
	"CHALLENGE": "Challenge",
	"PARKS": "Disney Parks & Stores",
	# The official app data calls 'CHALLENGE' "Play", but it muddles DLC reward cards with local hobby store Organized Play, so add a field for the latter
	"PLAY": {
		Language.ENGLISH: "Organized Play",
		Language.FRENCH: "Jeu Organisé",
		Language.GERMAN: "Organized Play",
		Language.ITALIAN: "Gioco Organizzato"
	}
}


@dataclass
class PromoSource:
	sourceCategory: Optional[str]  # A general source category ("Challenge", "Event")
	source: Optional[str]  # A specific source for this card ("GenCon 2023", "Movie Release Moana 2")


class PromoSourceHandler:
	def __init__(self, inputData: Dict):
		self._sourceIdToCategory: Dict[str, Union[str, None]] = {entry["id"]: entry["name"] for entry in inputData["special_rarities"]}
		for sourceId, sourceData in _REPLACEMENT_NAMES.items():
			if isinstance(sourceData, str):
				self._sourceIdToCategory[sourceId] = sourceData
			elif GlobalConfig.language in _REPLACEMENT_NAMES[sourceId]:
				self._sourceIdToCategory[sourceId] = _REPLACEMENT_NAMES[sourceId][GlobalConfig.language]
		with open(os.path.join("OutputGeneration", "data", "promoSourceOverrides.json"), "r") as overridesFile:
			overrides = json.load(overridesFile)
		self._sourceCategoryOverrides: Dict[int, str] = {}
		for sourceCategoryName, cardIdList in overrides["sourceCategoryOverrides"].items():
			for cardId in cardIdList:
				self._sourceCategoryOverrides[cardId] = sourceCategoryName
		self._sourceOverrides: Dict[int, str] = {}
		for sourceIdentifier, sourceData in overrides["sources"].items():
			sourceName = sourceIdentifier
			cardIds = sourceData
			if isinstance(sourceData, dict):
				# Different names for different languages, get the correct one
				if GlobalConfig.language.code not in sourceData:
					continue
				sourceName = sourceData[GlobalConfig.language.code]
				cardIds = sourceData["ids"]
			for cardId in cardIds:
				self._sourceOverrides[cardId] = sourceName

	def getSpecialSourceForCard(self, inputCard: Dict) -> Union[None, PromoSource]:
		cardId = inputCard["culture_invariant_id"]

		sourceCategory: Optional[str] = None
		if "special_rarity_id" in inputCard:
			specialRarityId = inputCard["special_rarity_id"]
			if specialRarityId == "CHALLENGE" and "/P" in inputCard["card_identifier"]:
				# The P2 promo cards you can get for participating in LGS Organized Play are labelled as 'CHALLENGE'
				# This kind of makes sense since that's displayed as the vague 'Play' in the official app, but we want to separate cards won at Challenges from ones won at local Organized Play
				specialRarityId = "PLAY"
			sourceCategory = self._sourceIdToCategory[specialRarityId]
		if cardId in self._sourceCategoryOverrides:
			originalSourceCategory = sourceCategory
			sourceGroupId = self._sourceCategoryOverrides.pop(cardId)
			if sourceGroupId in self._sourceIdToCategory:
				sourceCategory = self._sourceIdToCategory[sourceGroupId]
			else:
				# It's either None, or a one-time override, use as-is
				sourceCategory = sourceGroupId
			if originalSourceCategory == sourceCategory:
				_logger.warning(f"Card ID {cardId} ({inputCard['card_identifier']}) has an overwritten Special Source Category, but it is the same as in the input file, namely {sourceCategory!r}")

		source: Optional[str] = self._sourceOverrides.pop(cardId, None)

		if not sourceCategory and not source:
			return None
		return PromoSource(sourceCategory, source)
