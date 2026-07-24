import json, logging, os, re, string
from typing import Dict, List, Optional, Union

import natsort, requests

import GlobalConfig
from APIScraping import ExternalLinksDataAdditions
from util import Language
from util.IdentifierParser import Identifier


_LOGGER = logging.getLogger("LorcanaJSON")
_EXTERNAL_LINKS_FILE_PATH = os.path.join("output", "externalLinks.json")
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
	"C2": "Lorcana-Challenge-Promos-Year-3",
	"CC1": "Curators-Collection-Heroines-Edition",
	"D23": "D23-Expo-2024-Collectors-Set",
	"DIS": "Discover-Promo",
	"P1": "Promos",
	"PD1": "Promos-Year-4",
}
# This regex gets the card number and the 'group' from the full identifier. Use a regex instead of splitting to handle the earlier cards with different formatting
_IDENTIFIER_REGEX = re.compile(r"\b(?P<identifier>(?P<number>\d+[a-z]?)/(?P<cardGroup>[A-Z0-9]+))\b")


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
		with open(os.path.join("OutputGeneration", "data", "baseSetData.json"), "r", encoding="utf-8") as setDataFile:
			setsData = json.load(setDataFile)
		setNameToCode = {}
		setCodeToName = {}
		for setCode, setData in setsData.items():
			setName = setData["names"]["en"]
			setNameToCode[setName] = setCode
			# CardTrader doesn't always keep the 'The' at the start, so store the name without that too
			if setName.startswith("The "):
				setName = setName.split(" ", 1)[1]
				setNameToCode[setName] = setCode
			# Do this after 'The ' correction since we need the setname without it
			setCodeToName[setCode] = setName

		# Get data from CardTrader, it includes Cardmarket and TCGplayer card IDs
		headers = {"Authorization": "Bearer " + cardTraderToken}
		expansionsRequest = requests.get("https://api.cardtrader.com/api/v2/expansions", headers=headers, timeout=10)
		cardsBySet: Dict[str, Dict[str, Dict[str, Union[int, str]]]] = {"Promos": {}}  # Top level is the set code, it contains for each card number (as string, because it can have f.i. 'P1') in that set a dictionary with the card IDs and URLs for various stores
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
			cardNumberSuffix: Optional[str] = None
			if expansionName in setNameToCode:
				setCodeToUse = setNameToCode[expansionName]
			elif expansionName in ("Lorcana Challenge Promos", "Promos") or expansionName.startswith("Promos Year "):
				setCodeToUse = "Promos"
			elif expansionName.endswith("Promo") or expansionName.endswith("Promos"):
				_LOGGER.info(f"Falling back to 'Promos' setcode for expansion name '{expansionName}'")
				setCodeToUse = "Promos"
			elif expansionName == "Curator’s Collection: Heroines Edition":
				setCodeToUse = "Promos"
				cardNumberSuffix = "/CC1"
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
				if not cardNumber:
					# 'Bruno Madrigal - Undetected Uncle' (ID 1936) is card 0/204 of Set 9, handle that
					cardNumber = "0"
				# Some Enchanted cards are listed with an 'a' at the end for some reason. Remove that, being careful not to remove it from cards that do need it (Like 'Dalmatian Puppy - Tail Wagger' ID 436)
				if len(cardNumber) == 4 and cardNumber.endswith("a"):
					cardNumber = cardNumber[:-1]
				if cardNumberSuffix:
					cardNumber += cardNumberSuffix
				cardSetCodeToUse = setCodeToUse
				if card.get("version", None) and "/" in card["version"] and "/" not in cardNumber:
					# Some promo cards have the full card number in the version, as "[promo source] | [number]/[promo group]" (f.e. "Pre-Release Promo | 28/P3")
					# If the card number doesn't include that promo group yet, add it
					promoGroupingMatch = _IDENTIFIER_REGEX.search(card["version"])
					if promoGroupingMatch:
						cardNumber = promoGroupingMatch.group("identifier").lstrip("0")
					else:
						_LOGGER.error(f"Unable to find promo group in version '{card['version']}'")
				if setCodeToUse in ExternalLinksDataAdditions.CORRECTIONS and cardNumber in ExternalLinksDataAdditions.CORRECTIONS[setCodeToUse] and card["name"] in ExternalLinksDataAdditions.CORRECTIONS[setCodeToUse][cardNumber]:
					_LOGGER.info(f"Correcting card '{card['name']}', changing setcode '{setCodeToUse}' and cardnumber '{cardNumber}' to {ExternalLinksDataAdditions.CORRECTIONS[setCodeToUse][cardNumber][card['name']]}")
					cardSetCodeToUse, cardNumber = ExternalLinksDataAdditions.CORRECTIONS[setCodeToUse][cardNumber][card["name"]]
				# Label cards from the first promo series as such, to make constructing URLs easier
				if cardSetCodeToUse == "Promos" and "/" not in cardNumber:
					cardNumber += "/P1"
				if cardNumber in cardsBySet[cardSetCodeToUse]:
					# Card with this number already exists
					_LOGGER.error(f"While adding card '{card['name']}' (Version '{card.get('version', 'unknown')}') from set '{expansionName}', already found card with number {cardNumber} in setcode {cardSetCodeToUse}")
					continue
				# Card Trader IDs always exist
				cardExternalLinks = {"cardTraderId": card["id"], "cardTraderUrl": f"https://www.cardtrader.com/cards/{card['id']}"}

				ExternalLinksHandler._addStoreId(card["card_market_ids"][0] if card["card_market_ids"] else None, ExternalLinksDataAdditions.CARDMARKET_ID_ADDITIONS.get(cardNumber, None), cardExternalLinks, "cardmarketId", cardNumber)
				cardmarketCategoryName: str = ""
				if cardSetCodeToUse == "Promos" and "/P2" in card["fixed_properties"]["collector_number"]:
					cardmarketCategoryName = "Promos-Year-2"
				elif cardSetCodeToUse == "Q1":
					cardmarketCategoryName = "Ursulas-Deck"
				elif cardSetCodeToUse != setCodeToUse:
					cardmarketCategoryName = _convertStringToUrlValue(setCodeToName[cardSetCodeToUse])
				elif re.search("/[A-Z]", cardNumber):
					cardCategory = cardNumber.split("/", 1)[1].strip()
					if cardCategory in _CARD_MARKET_CARD_GROUP_TO_NAME:
						cardmarketCategoryName = _CARD_MARKET_CARD_GROUP_TO_NAME[cardCategory]
					elif cardCategory[0] == "P" and cardCategory[1].isnumeric():
						cardmarketCategoryName = f"Promos-Year-{cardCategory[1]}"
					else:
						_LOGGER.error(f"Unknown CardMarket Group {cardCategory!r} for card {cardNumber} {card['name']!r}")
				elif expansionName == "Promos Year 1":
					cardmarketCategoryName = "Promos"
				else:
					cardmarketCategoryName = _convertStringToUrlValue(expansionName)
				if cardmarketCategoryName:
					cardmarketCardName = _convertStringToUrlValue(card["name"], cardSetCodeToUse in ("5", "7"))  # For some reason, they remove mid-word dashes (like in 'mid-word') only in cardnames from some sets, correct for that
					cardExternalLinks["cardmarketUrl"] = f"https://www.cardmarket.com/{{languageCode}}/Lorcana/Products/Singles/{cardmarketCategoryName}/{cardmarketCardName}[[versionSuffix]]?language={{cardmarketLanguageCode}}"

				ExternalLinksHandler._addStoreId(card.get("tcg_player_id", None), ExternalLinksDataAdditions.TCGPLAYER_ID_ADDITIONS.get(cardNumber, None), cardExternalLinks, "tcgPlayerId", cardNumber)
				if "tcgPlayerId" in cardExternalLinks:
					cardExternalLinks["tcgPlayerUrl"] = f"https://www.tcgplayer.com/product/{cardExternalLinks['tcgPlayerId']}"

				# Sort the entries
				cardExternalLinks = {key: cardExternalLinks[key] for key in sorted(cardExternalLinks)}
				# and store 'em
				cardsBySet[cardSetCodeToUse][cardNumber] = cardExternalLinks

		# Find cards with the same cardmarket URL, so we can fill in the version suffix
		for setcode in cardsBySet:
			# Sort cards by number so we know which one needs the '-V1' suffix and which the '-V2'
			cardsBySet[setcode] = {cardnumber: cardsBySet[setcode][cardnumber] for cardnumber in natsort.natsorted(cardsBySet[setcode])}
			cardmarketUrlToCardNumbers: Dict[str, List[str]] = {}
			# First build a list of all the card numbers that have the same cardmarket url, so we know which suffix they need
			for cardnumber, carddata in cardsBySet[setcode].items():
				cardmarketUrl: Optional[str] = carddata.get("cardmarketUrl", None)
				if cardmarketUrl:
					cardmarketUrl = cardmarketUrl.lower()  # Prevent case differences in names from causing problems ("Look at this Family" versus "Look at This Family")
					if cardmarketUrl not in cardmarketUrlToCardNumbers:
						cardmarketUrlToCardNumbers[cardmarketUrl] = []
					cardmarketUrlToCardNumbers[cardmarketUrl].append(cardnumber)
			# Now set the suffixes
			for cardmarketUrl, cardNumbers in cardmarketUrlToCardNumbers.items():
				if len(cardNumbers) == 1:
					# No duplicate URLs, so this card is unique and doesn't need a suffix
					carddata = cardsBySet[setcode][cardNumbers[0]]
					carddata["cardmarketUrl"] = carddata["cardmarketUrl"].replace("[[versionSuffix]]", "")
				else:
					# Multiple cards with the same URL, fill in each suffix
					for index, cardNumber in enumerate(cardNumbers):
						carddata = cardsBySet[setcode][cardNumber]
						carddata["cardmarketUrl"] = carddata["cardmarketUrl"].replace("[[versionSuffix]]", f"-V{index+1}")

		# Downloading and parsing data is done, list differences with the previous file (if it exists)
		wasChangeFound = False
		newCardCount = 0
		if os.path.isfile(_EXTERNAL_LINKS_FILE_PATH):
			with open(_EXTERNAL_LINKS_FILE_PATH, "r", encoding="utf-8") as oldExternalLinksFile:
				oldCardsBySet = json.load(oldExternalLinksFile)
			for setCode, newSetData in cardsBySet.items():
				if setCode not in oldCardsBySet:
					wasChangeFound = True
					_LOGGER.info(f"Setcode {setCode} exists in the new external-links data but not in the old")
				else:
					oldSetData = oldCardsBySet[setCode]
					for cardId, newCardData in newSetData.items():
						if cardId not in oldSetData:
							wasChangeFound = True
							newCardCount += 1
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
			wasChangeFound = True
			_LOGGER.info("No externalLinks file existed yet, so no list of changes can be made")

		# Done, save the new data, overwriting the old, if needed
		if wasChangeFound:
			if newCardCount:
				_LOGGER.info(f"Found new data for {newCardCount:,} cards")
			with open(_EXTERNAL_LINKS_FILE_PATH, "w", encoding="utf-8") as externalLinksFile:
				json.dump(cardsBySet, externalLinksFile, indent=2)
			#TODO Check here if all cards have externalLinks and warn about cards that don't

	@staticmethod
	def _addStoreId(storeIdFromInput: Optional[int], storeIdFromAdditions: Optional[int], outputData: Dict, outputKey: str, cardNumber: str):
		outputId: Optional[int] = storeIdFromInput
		if storeIdFromAdditions:
			if storeIdFromInput:
				if storeIdFromInput == storeIdFromAdditions:
					_LOGGER.warning(f"'{outputKey}' for card {cardNumber} is already the same as the override, namely {storeIdFromInput}")
				else:
					_LOGGER.warning(f"'{outputKey}'  for card {cardNumber} exists in input data, however it is {outputId} there but {storeIdFromAdditions} in the override data, using the override value")
					outputId = storeIdFromAdditions
			else:
				_LOGGER.debug(f"Setting '{outputKey}' from override for card {cardNumber}")
				outputId = storeIdFromAdditions
		if outputId:
			outputData[outputKey] = outputId

	def getExternalLinksForCard(self, parsedIdentifier: Identifier) -> Optional[Dict[str, str]]:
		if parsedIdentifier.setCode not in self._externalLinks:
			_LOGGER.error(f"Setcode '{parsedIdentifier.setCode}' does not exist in the External IDs data")
		numberGroupingString = f"{parsedIdentifier.number}/{parsedIdentifier.grouping}"
		numberString = str(parsedIdentifier.number)
		if parsedIdentifier.variant:
			numberGroupingString = numberGroupingString.replace("/", parsedIdentifier.variant + "/")
			numberString += parsedIdentifier.variant
		cardExternalLinks: Optional[Dict] = None
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
		# In rare cases multiple cards have the same number grouping ("Moana/Viana - Adventurer on Land and Sea", ID 1433 & 1663); make a copy of the data so changes in one card's data don't affect the other
		cardExternalLinks = cardExternalLinks.copy()
		# Some parts need extra filling in
		# Cardmarket lists Enchanted cards with '-V2' at the end, and the non-Enchanted version with '-V1'. Promo versions are either '-V1' or '-V2'
		if "cardmarketUrl" in cardExternalLinks:
			cardExternalLinks["cardmarketUrl"] = cardExternalLinks["cardmarketUrl"].format(languageCode=GlobalConfig.language.code, cardmarketLanguageCode=self._cardmarketLanguageCode)
		return cardExternalLinks
