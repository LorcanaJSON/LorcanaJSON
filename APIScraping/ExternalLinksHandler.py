import json, logging, os, re, string
from typing import Dict, List, Tuple, Union

import requests

import GlobalConfig
from util import Language
from util.IdentifierParser import Identifier


_LOGGER = logging.getLogger("LorcanaJSON")
_EXTERNAL_LINKS_FILE_PATH = os.path.join("output", "generated", "externalLinks.json")
_CARD_TRADER_LORCANA_ID = 18
_CARD_TRADER_SINGLES_CATEGORY_ID = 214  # CardTrader also sells inserts, puzzle cards, etc; This is the ID of actual cards, skip anything else
_CARD_MARKET_LANGUAGE_TO_CODE = {
	Language.ENGLISH: 1,
	Language.FRENCH: 2,
	Language.GERMAN: 3,
	Language.ITALIAN: 5
}
_CARD_MARKET_CARD_GROUP_TO_NAME = {
	"C1": "Disney-Lorcana-Challenge-Promos",
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
		},
		"5": {
			"Mickey Mouse - Brave Little Tailor": ("Promos", "5/C1")
		},
		"6": {
			"Invited to the Ball": ("Promos", "6/C1")
		},
		"7": {
			"Elsa's Ice Palace - Place of Solitude": ("Promos", "7/C1")
		},
		"8": {
			"Kuzco - Temperamental Emperor": ("Promos", "8/C1")
		},
		"9": {
			"Baymax - Armored Companion": ("Promos", "9/C1")
		},
		"10": {
			"A Whole New World": ("Promos", "10/C1")
		},
		"24/P2": {
			"Hiro Hamada - Armor Designer": ("Promos", "24A/P2")
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
	},
	"Q2": {
		"223": {
			"Bolt - Superdog": ("7", "223/204"),
			"Goofy - Groundbreaking Chef": ("8", "223/204")
		},
		"224": {
			"Elsa - Ice Maker": ("7", "224/204"),
			"Pinocchio - Strings Attached": ("8", "224/204")
		}
	},
	"8": {
		"154": {
			"Olaf - Recapping the Story": ("8", "156/204")
		}
	}
}


def _convertStringToUrlValue(inputString: str, shouldRemoveMidwordDashes: bool = False) -> str:
	outputString = inputString
	if shouldRemoveMidwordDashes:
		outputString = re.sub(r"(?<=\S)-(?=\S)", "", outputString)
	outputString = re.sub(" [-–] ?", "-", outputString)
	outputString = outputString.replace("é", "e")
	outputString = re.sub("[:!.,'’ā]+", "", outputString)
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
			setName = setData["names"]["en"]
			setNameToCode[setName] = setCode
			setCodeToName[setCode] = setName
			# CardTrader doesn't always keep the 'The' at the start, so store the name without that too
			if setName.startswith("The "):
				setNameToCode[setName.split(" ", 1)[1]] = setCode

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
				if (not card["fixed_properties"] or not card["fixed_properties"]["collector_number"] or card["version"] in ("Cinese Exclusive", "Chinese Exclusive", "Oversized",) or
						card["fixed_properties"].get("lorcana_rarity", None) == "Oversized" or card["category_id"] != _CARD_TRADER_SINGLES_CATEGORY_ID):
					continue
				cardNumber: str = card["fixed_properties"]["collector_number"].lstrip("0")
				# Some Enchanted cards are listed with an 'a' at the end for some reason. Remove that, being careful not to remove it from cards that do need it (Like 'Dalmatian Puppy - Tail Wagger' ID 436)
				if len(cardNumber) == 4 and cardNumber.endswith("a"):
					cardNumber = cardNumber[:-1]
				cardSetCodeToUse = setCodeToUse
				if setCodeToUse in _CORRECTIONS and cardNumber in _CORRECTIONS[setCodeToUse] and card["name"] in _CORRECTIONS[setCodeToUse][cardNumber]:
					_LOGGER.info(f"Correcting card '{card['name']}', changing setcode '{setCodeToUse}' and cardnumber '{cardNumber}' to {_CORRECTIONS[setCodeToUse][cardNumber][card['name']]}")
					cardSetCodeToUse, cardNumber = _CORRECTIONS[setCodeToUse][cardNumber][card["name"]]
				# Label cards from the first promo series as such, to make constructing URLs easier
				if cardSetCodeToUse == "Promos" and "/" not in cardNumber:
					cardNumber += "/P1"
				if cardNumber in cardsBySet[cardSetCodeToUse]:
					# Card with this number already exists
					_LOGGER.error(f"While adding card '{card['name']}' from set '{expansionName}', already found card with number {cardNumber} in setcode {cardSetCodeToUse}")
					continue
				# Card Trader IDs always exist
				cardExternalLinks = {"cardTraderId": card["id"], "cardTraderUrl": f"https://www.cardtrader.com/cards/{card['id']}"}

				if card["card_market_ids"]:
					if len(card["card_market_ids"]) > 1:
						_LOGGER.warning(f"Found {len(card['card_market_ids']):,} Cardmarket IDs for card '{card['name']}' (CardTrader ID {card['id']}) in expansion {expansionName} (ID {expansion['id']}), using first one")
					cardExternalLinks["cardmarketId"] = card["card_market_ids"][0]
				cardmarketCategoryName: str = ""
				if cardSetCodeToUse == "Promos" and "/P2" in card["fixed_properties"]["collector_number"]:
					cardmarketCategoryName = "Promos-Year-2"
				elif cardSetCodeToUse == "Q1":
					cardmarketCategoryName = "Ursulas-Deck"
				elif expansionName == "Lorcana Challenge Promos":
					cardmarketCategoryName = "Disney-Lorcana-Challenge-Promos"
				elif cardSetCodeToUse != setCodeToUse:
					cardmarketCategoryName = _convertStringToUrlValue(setCodeToName[cardSetCodeToUse])
				elif re.search("/[A-Z]", card["fixed_properties"]["collector_number"]):
					cardCategory = card["fixed_properties"]["collector_number"].split("/", 1)[1].strip()
					if cardCategory in _CARD_MARKET_CARD_GROUP_TO_NAME:
						cardmarketCategoryName = _CARD_MARKET_CARD_GROUP_TO_NAME[cardCategory]
					else:
						_LOGGER.error(f"Unknown CardMarket Group {cardCategory!r} for card {cardNumber} {card['name']!r}")
				else:
					cardmarketCategoryName = _convertStringToUrlValue(expansionName)
				if cardmarketCategoryName:
					cardmarketCardName = _convertStringToUrlValue(card["name"], cardSetCodeToUse in ("5", "7"))  # For some reason, they remove mid-word dashes (like in 'mid-word') only in cardnames from some sets, correct for that
					cardExternalLinks["cardmarketUrl"] = f"https://www.cardmarket.com/{{languageCode}}/Lorcana/Products/Singles/{cardmarketCategoryName}/{cardmarketCardName}{{cardmarketVersionSuffix}}?language={{cardmarketLanguageCode}}"

				if card["tcg_player_id"]:
					cardExternalLinks["tcgPlayerId"] = card["tcg_player_id"]
					cardExternalLinks["tcgPlayerUrl"] = f"https://www.tcgplayer.com/product/{cardExternalLinks['tcgPlayerId']}"

				# Sort the entries
				cardExternalLinks = {key: cardExternalLinks[key] for key in sorted(cardExternalLinks)}
				# and store 'em
				cardsBySet[cardSetCodeToUse][cardNumber] = cardExternalLinks

		# Downloading and parsing data is done, list differences with the previous file (if it exists)
		if os.path.isfile(_EXTERNAL_LINKS_FILE_PATH):
			with open(_EXTERNAL_LINKS_FILE_PATH, "r", encoding="utf-8") as oldExternalLinksFile:
				oldCardsBySet = json.load(oldExternalLinksFile)
			wasChangeFound = False
			for setCode, newSetData in cardsBySet.items():
				if setCode not in oldCardsBySet:
					wasChangeFound = True
					_LOGGER.info(f"Setcode {setCode} exists in the new external-links data but not in the old")
				else:
					oldSetData = oldCardsBySet[setCode]
					for cardId, newCardData in newSetData.items():
						if cardId not in oldSetData:
							wasChangeFound = True
							_LOGGER.info(f"Card {cardId} of set {setCode} exists in the new external-links data but not in the old")
						else:
							oldCardData = oldSetData[cardId]
							for externalLinkKey, externalLinkValue in newCardData.items():
								if externalLinkKey not in oldCardData:
									wasChangeFound = True
									_LOGGER.info(f"Key {externalLinkKey} of card {cardId} in set {setCode} exists in the new external-links data but not in the old")
								elif externalLinkValue != oldCardData[externalLinkKey]:
									wasChangeFound = True
									_LOGGER.info(f"Key {externalLinkKey} of card {cardId} in set {setCode} was {oldCardData[externalLinkKey]!r} in the old data but is {externalLinkValue!r} in the new data")
			if not wasChangeFound:
				_LOGGER.info("No changes found between old and new externalLinks data")
		else:
			_LOGGER.info("No externalLinks file existed yet, so no list of changes can be made")

		# Done, save the new data, overwriting the old
		with open(_EXTERNAL_LINKS_FILE_PATH, "w", encoding="utf-8") as externalLinksFile:
			json.dump(cardsBySet, externalLinksFile, indent=2)

	def getExternalLinksForCard(self, parsedIdentifier: Identifier, hasEnchanted: bool) -> Union[None, Dict[str, str]]:
		if parsedIdentifier.setCode not in self._externalLinks:
			_LOGGER.error(f"Setcode '{parsedIdentifier.setCode}' does not exist in the External IDs data")
		numberGroupingString = f"{parsedIdentifier.number}/{parsedIdentifier.grouping}"
		numberString = str(parsedIdentifier.number)
		if parsedIdentifier.variant:
			numberGroupingString = numberGroupingString.replace("/", parsedIdentifier.variant + "/")
			numberString += parsedIdentifier.variant
		cardExternalLinks = None
		if parsedIdentifier.isPromo():
			if numberGroupingString in self._externalLinks["Promos"]:
				cardExternalLinks = self._externalLinks["Promos"][numberGroupingString]
			elif numberString in self._externalLinks["Promos"]:
				cardExternalLinks = self._externalLinks["Promos"][numberString]
		else:
			if numberGroupingString in self._externalLinks[parsedIdentifier.setCode]:
				cardExternalLinks = self._externalLinks[parsedIdentifier.setCode][numberGroupingString]
			elif numberString in self._externalLinks[parsedIdentifier.setCode]:
				cardExternalLinks = self._externalLinks[parsedIdentifier.setCode][numberString]
		if not cardExternalLinks:
			_LOGGER.warning(f"Unable to find external ID entry for full identifier '{parsedIdentifier}'")
			return {}

		# Some parts need extra filling in
		# Cardmarket lists Enchanted cards with '-V2' at the end, and the non-Enchanted version with '-V1'. Promo versions are either '-V1' or '-V2'
		if "cardmarketUrl" in cardExternalLinks:
			cardmarketVersionSuffix = ""
			if hasEnchanted:
				cardmarketVersionSuffix = "-V1"
			elif parsedIdentifier.number > 204:
				cardmarketVersionSuffix = "-V2"
			elif parsedIdentifier.variant:
				variantVersion = string.ascii_lowercase.index(parsedIdentifier.variant.lower()) + 1
				cardmarketVersionSuffix = f"-V{variantVersion}"
			cardExternalLinks["cardmarketUrl"] = cardExternalLinks["cardmarketUrl"].format(languageCode=GlobalConfig.language.code, cardmarketLanguageCode=self._cardmarketLanguageCode, cardmarketVersionSuffix=cardmarketVersionSuffix)
		return cardExternalLinks
