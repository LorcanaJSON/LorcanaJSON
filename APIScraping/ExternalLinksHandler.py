import json, logging, os, re
from typing import Dict, List, Tuple, Union

import requests

import GlobalConfig
from util import Language


_LOGGER = logging.getLogger("LorcanaJSON")
_EXTERNAL_LINKS_FILE_PATH = os.path.join("output", "generated", "externalLinks.json")
_CARD_TRADER_LORCANA_ID = 18
_CARD_MARKET_LANGUAGE_TO_CODE = {
	Language.ENGLISH: 1,
	Language.FRENCH: 2,
	Language.GERMAN: 3,
	Language.ITALIAN: 5
}
_CARD_MARKET_CARD_GROUP_TO_NAME = {
	"C1": "D23-Expo-2024-Collectors-Set",
	"D23": "D23-Expo-2024-Collectors-Set",
	"P1": "Promos",
	"P2": "Promos-Year-2"
}
# This regex gets the card number and the 'group' from the full identifier. Use a regex instead of splitting to handle the earlier cards with different formatting
_IDENTIFIER_REGEX = re.compile(r"\b(?P<identifier>(?P<number>\d+[a-z]?)/(?P<cardGroup>[A-Z0-9]+))\b")

_CORRECTIONS = {
	"Promos": {
		"1": {
			"Dragon Fire": ("Promos", "1/C1")
		},
		"2": {
			"Let It Go": ("Promos", "2/C1")
		},
		"3": {
			"Cinderella - Stouthearted": ("Promos", "3/C1")
		},
		"4": {
			"Rapunzel - Gifted with Healing": ("Promos", "4/C1")
		}
	},
	"Q1": {
		"11": {
			"The Hexwell Crown": ("Q1", "29")
		},
		"223": {
			"Piglet - Pooh Pirate Captain": ("3", "223/204"),
			"Yen Sid - Powerful Sorcerer": ("4", "223/204")
		},
		"224": {
			"Mulan - Elite Archer": ("4", "224/204")
		},
		"225": {
			"Mickey Mouse - Playful Sorcerer": ("4", "225/204")
		}
	}
}


def _convertStringToUrlValue(inputString: str, shouldRemoveMidwordDashes: bool = False) -> str:
	outputString = inputString
	if shouldRemoveMidwordDashes:
		outputString = re.sub(r"(?<=\S)-(?=\S)", "", outputString)
	outputString = re.sub(" - ?", "-", outputString)
	outputString = outputString.replace("é", "e")
	outputString = re.sub("[:!.,'ā]+", "", outputString)
	outputString = outputString.replace(" & ", " ").replace("\"", " ")
	outputString = re.sub(" {2,}", " ", outputString.rstrip())
	outputString = outputString.replace(" ", "-")
	return outputString


class ExternalLinksHandler:
	def __init__(self):
		if not os.path.isfile(_EXTERNAL_LINKS_FILE_PATH):
			raise FileNotFoundError("The External IDs file does not exist, please run the action to create that file first")
		with open(_EXTERNAL_LINKS_FILE_PATH, "r", encoding="utf-8") as externalLinksFile:
			self._externalLinks = json.load(externalLinksFile)
		self._cardmarketLanguageCode = _CARD_MARKET_LANGUAGE_TO_CODE[GlobalConfig.language]

	@staticmethod
	def updateCardshopData(cardTraderToken):
		# CardTrader data is split into the sets by name, so we need to map from English name to set code
		# For URL construction, we also need the reverse
		with open(os.path.join("output", "baseSetData.json"), "r", encoding="utf-8") as setDataFile:
			setsData = json.load(setDataFile)
		setNameToCode = {}
		setCodeToName = {}
		for setCode, setData in setsData.items():
			setNameToCode[setData["names"]["en"]] = setCode
			setCodeToName[setCode] = setData["names"]["en"]

		# Get data from CardTrader, it includes Cardmarket and TCGplayer card IDs
		headers = {"Authorization": "Bearer " + cardTraderToken}
		expansionsRequest = requests.get("https://api.cardtrader.com/api/v2/expansions", headers=headers, timeout=10)
		cardsBySet: Dict[str, Dict[str, Dict[str, int]]] = {"Promos": {}}  # Top level is the set code, it contains for each card number (as string, because it can have f.i. 'P1') in that set a dictionary with the card IDs for various stores
		for setName, setCode in setNameToCode.items():
			cardsBySet[setCode] = {}
		if expansionsRequest.status_code != 200:
			_LOGGER.error(f"Expansions retrieval request failed, status code {expansionsRequest.status_code}")
			return
		expansionsRequestJson = expansionsRequest.json()
		for expansion in expansionsRequestJson:
			if expansion["game_id"] != _CARD_TRADER_LORCANA_ID:
				continue
			expansionName = expansion["name"]
			if expansionName in setNameToCode:
				setCodeToUse = setNameToCode[expansionName]
			elif expansionName == "Promos" or expansionName == "Lorcana Challenge Promos":
				setCodeToUse = "Promos"
			elif expansionName == "Errata Cards":
				continue
			else:
				_LOGGER.error(f"Unknown expansion name '{expansionName}' while parsing card shop data")
				continue
			# Get the cards for this expansion
			expansionCardsRequest = requests.get("https://api.cardtrader.com/api/v2/blueprints/export", params={"expansion_id": expansion["id"]}, headers=headers, timeout=10)
			for card in expansionCardsRequest.json():
				# The data also includes boosters, pins, marketing cards, and other non-card items, skip those
				if not card["fixed_properties"] or not card["fixed_properties"]["collector_number"] or card["version"] == "Oversized" or card["fixed_properties"].get("lorcana_rarity", None) == "Oversized":
					continue
				cardNumber: str = card["fixed_properties"]["collector_number"].lstrip("0")
				# Some Enchanted cards are listed with an 'a' at the end for some reason. Remove that, being careful not to remove it from cards that do need it (Like 'Dalmatian Puppy - Tail Wagger' ID 436)
				if len(cardNumber) == 4 and cardNumber.endswith("a"):
					cardNumber = cardNumber[:-1]
				cardSetCodeToUse = setCodeToUse
				if setCodeToUse in _CORRECTIONS and cardNumber in _CORRECTIONS[setCodeToUse] and card["name"] in _CORRECTIONS[setCodeToUse][cardNumber]:
					_LOGGER.info(f"Correcting card '{card['name']}', changing setcode '{setCodeToUse}' and cardnumber '{cardNumber}' to {_CORRECTIONS[setCodeToUse][cardNumber][card['name']]}")
					cardSetCodeToUse, cardNumber = _CORRECTIONS[setCodeToUse][cardNumber][card["name"]]
				if cardNumber in cardsBySet[cardSetCodeToUse]:
					# Card with this number already exists
					otherCard = cardsBySet[cardSetCodeToUse][cardNumber]
					_LOGGER.error(f"While adding card '{card['name']}' from set '{expansionName}', already found card '{otherCard['name']}' with number {cardNumber} in setcode {cardSetCodeToUse} named '{otherCard['expansion']}'")
				# Label cards from the first promo series as such, to make constructing URLs easier
				if cardSetCodeToUse == "Promos" and "/" not in cardNumber:
					cardNumber += "/P1"
				# Only add ID fields if they exist
				cardExternalLinks = {}
				if card["card_market_ids"]:
					if len(card["card_market_ids"]) > 1:
						_LOGGER.warning(f"Found {len(card['card_market_ids']):,} Cardmarket IDs for card '{card['name']}' (CardTrader ID {card['id']}) in expansion {expansionName} (ID {expansion['id']}), using first one")
					cardExternalLinks["cardmarketId"] = card["card_market_ids"][0]
				if card["tcg_player_id"]:
					cardExternalLinks["tcgPlayerId"] = card["tcg_player_id"]
				# Only create an entry if we have IDs
				if cardExternalLinks:
					cardExternalLinks["cardTraderId"] = card["id"]
					# Create URLs
					cardExternalLinks["cardTraderUrl"] = f"https://www.cardtrader.com/cards/{cardExternalLinks['cardTraderId']}"

					cardmarketCategoryName: str = None
					if cardSetCodeToUse == "Promos" and "/P2" in card["fixed_properties"]["collector_number"]:
						cardmarketCategoryName = "Promos-Year-2"
					elif cardSetCodeToUse == "Q1":
						cardmarketCategoryName = "Ursulas-Deck"
					elif expansionName == "Lorcana Challenge Promos":
						cardmarketCategoryName = "Disney-Lorcana-Challenge-Promos"
					elif cardSetCodeToUse != setCodeToUse:
						cardmarketCategoryName = _convertStringToUrlValue(setCodeToName[cardSetCodeToUse])
					elif re.search("/[A-Z]", card["fixed_properties"]["collector_number"]):
						cardCategory = card["fixed_properties"]["collector_number"].split("/", 1)[1]
						cardmarketCategoryName = _CARD_MARKET_CARD_GROUP_TO_NAME[cardCategory]
					else:
						cardmarketCategoryName = _convertStringToUrlValue(expansionName)
					cardmarketCardName = _convertStringToUrlValue(card["name"], cardSetCodeToUse == "5")  # For some reason, they remove mid-word dashes (like in 'mid-word') only in cardnames from Set 5, correct for that
					cardExternalLinks["cardmarketUrl"] = f"https://www.cardmarket.com/{{languageCode}}/Lorcana/Products/Singles/{cardmarketCategoryName}/{cardmarketCardName}{{cardmarketVersionSuffix}}?language={{cardmarketLanguageCode}}"

					if cardExternalLinks.get("tcgPlayerId", None):
						cardExternalLinks["tcgPlayerUrl"] = f"https://www.tcgplayer.com/product/{cardExternalLinks['tcgPlayerId']}"

					# Sort the entries
					cardExternalLinks = {key: cardExternalLinks[key] for key in sorted(cardExternalLinks)}
					# and store 'em
					cardsBySet[cardSetCodeToUse][cardNumber] = cardExternalLinks
		with open(_EXTERNAL_LINKS_FILE_PATH, "w", encoding="utf-8") as externalLinksFile:
			json.dump(cardsBySet, externalLinksFile, indent=2)

	def getExternalLinksForCard(self, setCode: str, fullIdentifier: str, cardNumber: int, isPromo: bool, hasEnchanted: bool) -> Union[None, Dict[str, str]]:
		if setCode not in self._externalLinks:
			raise KeyError(f"Setcode '{setCode}' does not exist in the External IDs data")
		identifierMatch = _IDENTIFIER_REGEX.search(fullIdentifier)
		if not identifierMatch:
			_LOGGER.error(f"Unable to parse full identifier '{fullIdentifier}'")
			return None
		identifierNumberString = identifierMatch.group("identifier").lstrip("0")
		cardNumberString = identifierMatch.group("number")
		cardExternalLinks: Union[None, Dict[str, str]] = None
		if isPromo:
			if identifierNumberString in self._externalLinks["Promos"]:
				cardExternalLinks = self._externalLinks["Promos"][identifierNumberString]
			elif cardNumberString in self._externalLinks["Promos"]:
				cardExternalLinks = self._externalLinks["Promos"][cardNumberString]
		else:
			if identifierNumberString in self._externalLinks[setCode]:
				cardExternalLinks = self._externalLinks[setCode][identifierNumberString]
			elif cardNumberString in self._externalLinks[setCode]:
				cardExternalLinks = self._externalLinks[setCode][cardNumberString]
		if not cardExternalLinks:
			_LOGGER.error(f"Unable to find external ID entry for full identifier '{fullIdentifier}'")
			return {}

		# Some parts need extra filling in
		# Cardmarket lists Enchanted cards with '-V2' at the end, and the non-Enchanted version with '-V1'. Promo versions are either '-V1' or '-V2'
		cardmarketVersionSuffix = ""
		if hasEnchanted:
			cardmarketVersionSuffix = "-V1"
		elif cardNumber > 204:
			cardmarketVersionSuffix = "-V2"
		cardExternalLinks["cardmarketUrl"] = cardExternalLinks["cardmarketUrl"].format(languageCode=GlobalConfig.language.code, cardmarketLanguageCode=self._cardmarketLanguageCode, cardmarketVersionSuffix=cardmarketVersionSuffix)
		return cardExternalLinks
