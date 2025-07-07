import copy, datetime, hashlib, json, logging, multiprocessing.pool, os, re, threading, time, zipfile
import xml.etree.ElementTree as xmlElementTree
from typing import Dict, List, Optional, Union

import GlobalConfig
from APIScraping.ExternalLinksHandler import ExternalLinksHandler
from OCR import ImageParser, OcrCacheHandler
from OCR.OcrResult import OcrResult
from OutputGeneration import TextCorrection
from output.StoryParser import StoryParser
from util import CardUtil, IdentifierParser, JsonUtil, Language, LorcanaSymbols


_logger = logging.getLogger("LorcanaJSON")
FORMAT_VERSION = "2.1.5"
_CARD_CODE_LOOKUP = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_KEYWORD_REGEX = re.compile(r"(?:^|\n)([A-ZÀ][^.]+)(?=\s\([A-Z])")
_KEYWORD_REGEX_WITHOUT_REMINDER = re.compile(r"^[A-Z][a-z]{2,}( \d)?$")
_ABILITY_TYPE_CORRECTION_FIELD_TO_ABILITY_TYPE: Dict[str, str] = {"_forceAbilityIndexToActivated": "activated", "_forceAbilityIndexToKeyword": "keyword", "_forceAbilityIndexToStatic": "static", "_forceAbilityIndexToTriggered": "triggered"}
# The card parser is run in threads, and each thread needs to initialize its own ImageParser (otherwise weird errors happen in Tesseract)
# Store each initialized ImageParser in its own thread storage
_threadingLocalStorage = threading.local()
_threadingLocalStorage.imageParser: ImageParser.ImageParser = None
_threadingLocalStorage.externalIdsHandler: ExternalLinksHandler = None

def _cleanUrl(url: str) -> str:
	"""
	Clean up the provided URL. This removes the 'checksum' URL parameter, since it's not needed
	:param url: The URL to clean up
	:return: The cleaned-up URL
	"""
	return url.split('?', 1)[0]

def createOutputFiles(onlyParseIds: Union[None, List[int]] = None, shouldShowImages: bool = False) -> None:
	startTime = time.perf_counter()
	imageFolder = os.path.join("downloads", "images", GlobalConfig.language.code)
	if not os.path.isdir(imageFolder):
		raise FileNotFoundError(f"Images folder for language '{GlobalConfig.language.code}' doesn't exist. Run the data downloader first")
	cardCatalogPath = os.path.join("downloads", "json", f"carddata.{GlobalConfig.language.code}.json")
	if not os.path.isfile(cardCatalogPath):
		raise FileNotFoundError(f"Card catalog for language '{GlobalConfig.language.code}' doesn't exist. Run the data downloader first")
	with open(cardCatalogPath, "r", encoding="utf-8") as inputFile:
		inputData = json.load(inputFile)

	cardDataCorrections: Dict[int, Dict[str, List[str, str]]] = JsonUtil.loadJsonWithNumberKeys(os.path.join("output", "outputDataCorrections.json"))
	correctionsFilePath = os.path.join("output", f"outputDataCorrections_{GlobalConfig.language.code}.json")
	if os.path.isfile(correctionsFilePath):
		for cardId, corrections in JsonUtil.loadJsonWithNumberKeys(correctionsFilePath).items():
			if cardId in cardDataCorrections:
				# Merge the language-specific corrections with the global corrections
				for fieldCorrectionName, fieldCorrection in corrections.items():
					if fieldCorrectionName in cardDataCorrections[cardId]:
						cardDataCorrections[cardId][fieldCorrectionName].extend(fieldCorrection)
					else:
						cardDataCorrections[cardId][fieldCorrectionName] = fieldCorrection
			else:
				cardDataCorrections[cardId] = corrections
	else:
		_logger.warning(f"No corrections file exists for language '{GlobalConfig.language.code}', so no language-specific corrections will be done. This doesn't break anything, but results might not be perfect")

	# Enchanted-rarity and promo cards are special versions of existing cards. Store their shared ID so we can add a linking field to both versions
	# We do this before parse-id-checks and other parsing, so we can add these IDs to cards that have variant versions, even if they're not being parsed
	# Also, some cards have identical-rarity variants ("Dalmation Puppy', ID 436-440), store those so each can reference the others
	enchantedDeckbuildingIds = {}
	promoDeckBuildingIds = {}
	variantsDeckBuildingIds = {}
	for cardtype, cardlist in inputData["cards"].items():
		for card in cardlist:
			parsedIdentifier: IdentifierParser.Identifier = IdentifierParser.parseIdentifier(card["card_identifier"])
			if parsedIdentifier.isPromo():
				if card["deck_building_id"] not in promoDeckBuildingIds:
					promoDeckBuildingIds[card["deck_building_id"]] = []
				promoDeckBuildingIds[card["deck_building_id"]].append(card["culture_invariant_id"])
			# Some promo cards are listed as Enchanted-rarity, so don't store those promo cards as Enchanted too
			elif card["rarity"] == "ENCHANTED":
				if card["deck_building_id"] in enchantedDeckbuildingIds:
					_logger.info(f"Card {CardUtil.createCardIdentifier(card)} is Enchanted, but its deckbuilding ID already exists in the Enchanteds list, pointing to ID {enchantedDeckbuildingIds[card['deck_building_id']]}, not storing the ID")
				else:
					enchantedDeckbuildingIds[card["deck_building_id"]] = card["culture_invariant_id"]
			elif parsedIdentifier.number > 204:
				# A card numbered higher than the normal 204 that isn't an Enchanted is also most likely a promo card (F.i. the special Q1 cards like ID 1179
				if card["deck_building_id"] not in promoDeckBuildingIds:
					promoDeckBuildingIds[card["deck_building_id"]] = []
				promoDeckBuildingIds[card["deck_building_id"]].append(card["culture_invariant_id"])
			if parsedIdentifier.variant is not None:
				if card["deck_building_id"] not in variantsDeckBuildingIds:
					variantsDeckBuildingIds[card["deck_building_id"]] = []
				variantsDeckBuildingIds[card["deck_building_id"]].append(card["culture_invariant_id"])
	# Now find their matching 'normal' cards, and store IDs with links to each other
	# Enchanted to non-Enchanted is a one-on-one relation
	# One normal card can have multiple promos, so normal cards store a list of promo IDs, while promo IDs store just one normal ID
	enchantedNonEnchantedIds = {}
	promoNonPromoIds: Dict[int, Union[int, List[int]]] = {}
	for cardtype, cardlist in inputData["cards"].items():
		for card in cardlist:
			if card["deck_building_id"] in enchantedDeckbuildingIds and card["culture_invariant_id"] != enchantedDeckbuildingIds[card["deck_building_id"]]:
				nonEnchantedId = card["culture_invariant_id"]
				enchantedId = enchantedDeckbuildingIds[card["deck_building_id"]]
				if nonEnchantedId in enchantedNonEnchantedIds:
					_logger.info(f"Non-enchanted ID {nonEnchantedId} is already in the enchanted-nonenchanted list (stored pointing to {enchantedNonEnchantedIds[nonEnchantedId]}), skipping adding it again pointing to {enchantedId}")
				elif enchantedId in enchantedNonEnchantedIds:
					_logger.info(f"Enchanted ID {enchantedId} is already in the enchanted-nonenchanted list (stored pointing to {enchantedNonEnchantedIds[enchantedId]}), skipping adding it again pointing to {nonEnchantedId}")
				else:
					enchantedNonEnchantedIds[nonEnchantedId] = enchantedId
					enchantedNonEnchantedIds[enchantedId] = nonEnchantedId
			if card["deck_building_id"] in promoDeckBuildingIds and card["culture_invariant_id"] not in promoDeckBuildingIds[card["deck_building_id"]]:
				nonPromoId = card["culture_invariant_id"]
				promoIds = promoDeckBuildingIds[card["deck_building_id"]]
				if nonPromoId in promoNonPromoIds:
					_logger.info(f"Non-promo ID {nonPromoId} is already in promo-nonPromo list (stored pointing to {promoNonPromoIds[nonPromoId]}), skipping adding it again pointing to {promoIds}")
				else:
					promoNonPromoIds[nonPromoId] = promoIds
				for promoId in promoIds:
					if promoId in promoNonPromoIds:
						_logger.info(f"Promo ID {promoId} is already in promo-nonPromo list (stored pointing to {promoNonPromoIds[promoId]}), skipping adding it again pointing to {nonPromoId}")
					else:
						promoNonPromoIds[promoId] = nonPromoId
	del enchantedDeckbuildingIds
	del promoDeckBuildingIds

	historicDataFilePath = os.path.join("output", f"historicData_{GlobalConfig.language.code}.json")
	if os.path.isfile(historicDataFilePath):
		historicData = JsonUtil.loadJsonWithNumberKeys(historicDataFilePath)
	else:
		historicData = {}

	cardBans = JsonUtil.loadJsonWithNumberKeys(os.path.join("output", "CardBans.json"))

	# Get the cards we don't have to parse (if any) from the previous generated file
	fullCardList: List[Dict] = []
	cardIdsStored: List[int] = []
	outputFolder = os.path.join("output", "generated", GlobalConfig.language.code)
	if onlyParseIds:
		# Load the previous generated file to get the card data for cards that didn't change, instead of generating all cards
		outputFilePath = os.path.join(outputFolder, "allCards.json")
		if os.path.isfile(outputFilePath):
			with open(outputFilePath, "r", encoding="utf-8") as previousOutputFile:
				previousCardData = json.load(previousOutputFile)
				if previousCardData["metadata"]["formatVersion"] != FORMAT_VERSION:
					raise ValueError(f"Previous card data has a different format version ({previousCardData['metadata']['formatVersion']}, current one is {FORMAT_VERSION}), please run a full parse")
				else:
					for cardIndex in range(len(previousCardData["cards"])):
						card = previousCardData["cards"].pop()
						if card["id"] not in onlyParseIds:
							fullCardList.append(card)
							cardIdsStored.append(card["id"])
							# Remove the card from the corrections list, so we can still check if the corrections got applied properly
							cardDataCorrections.pop(card["id"], None)
							historicData.pop(card["id"], None)
				del previousCardData
		else:
			_logger.warning("ID list provided but previously generated file doesn't exist. Generating all card data")

	def initThread():
		_threadingLocalStorage.imageParser = ImageParser.ImageParser()
		_threadingLocalStorage.externalIdsHandler = ExternalLinksHandler()

	# Parse the cards we need to parse
	cardToStoryParser = StoryParser(onlyParseIds)
	with multiprocessing.pool.ThreadPool(GlobalConfig.threadCount, initializer=initThread) as pool:
		results = []
		for cardType, inputCardlist in inputData["cards"].items():
			cardTypeText = cardType[:-1].title()  # 'cardType' is plural ('characters', 'items', etc), make it singular
			cardTypeText = GlobalConfig.translation[cardTypeText]
			for inputCardIndex in range(len(inputCardlist)):
				inputCard = inputCardlist.pop()
				cardId = inputCard["culture_invariant_id"]
				if cardId in cardIdsStored:
					continue
				elif GlobalConfig.language.uppercaseCode not in inputCard["card_identifier"]:
					_logger.debug(f"Skipping card with ID {inputCard['culture_invariant_id']} because it's not in the requested language")
					continue
				elif onlyParseIds and cardId not in onlyParseIds:
					_logger.error(f"Card ID {cardId} is not in the ID parse list, but it's also not in the previous dataset. Skipping parsing for now, but this results in incomplete datafiles, so it's strongly recommended to rerun with this card ID included")
					continue
				try:
					results.append(pool.apply_async(_parseSingleCard, (inputCard, cardTypeText, imageFolder, enchantedNonEnchantedIds.get(cardId, None), promoNonPromoIds.get(cardId, None), variantsDeckBuildingIds.get(inputCard["deck_building_id"]),
												  cardDataCorrections.pop(cardId, None), cardToStoryParser, False, historicData.get(cardId, None), cardBans.pop(cardId, None), shouldShowImages)))
					cardIdsStored.append(cardId)
				except Exception as e:
					_logger.error(f"Exception {type(e)} occured while parsing card ID {inputCard['culture_invariant_id']}")
					raise e
		# Load in the external card reveals, which are cards revealed elsewhere but which aren't added to the official app yet
		externalCardReveals = []
		externalCardRevealsFilePath = os.path.join("output", f"externalCardReveals.{GlobalConfig.language.code}.json")
		if os.path.isfile(externalCardRevealsFilePath):
			with open(externalCardRevealsFilePath, "r", encoding="utf-8") as externalCardRevealsFile:
				externalCardReveals = json.load(externalCardRevealsFile)
		imageFolder = os.path.join(imageFolder, "external")
		for externalCard in externalCardReveals:
			cardId = externalCard["culture_invariant_id"]
			if cardId in cardIdsStored:
				_logger.debug(f"Card ID {cardId} is defined in the official file and in the external file, skipping the external data")
				continue
			results.append(pool.apply_async(_parseSingleCard, (externalCard, externalCard["type"], imageFolder, enchantedNonEnchantedIds.get(cardId, None), promoNonPromoIds.get(cardId, None), variantsDeckBuildingIds,
															   cardDataCorrections.pop(cardId, None), cardToStoryParser, True, historicData.get(cardId, None), cardBans.pop(cardId, None), shouldShowImages)))
		pool.close()
		pool.join()
	for result in results:
		outputCard = result.get()
		if outputCard:
			fullCardList.append(outputCard)
	_logger.info(f"Created card list in {time.perf_counter() - startTime} seconds")

	if cardDataCorrections:
		# Some card corrections are left, which shouldn't happen
		_logger.warning(f"{len(cardDataCorrections):,} card corrections left, which shouldn't happen: {cardDataCorrections}")
	# Sort the cards by set and card number
	fullCardList.sort(key=lambda c: c["id"])
	os.makedirs(outputFolder, exist_ok=True)
	# Add metadata
	metaDataDict = {"formatVersion": FORMAT_VERSION, "generatedOn": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S"), "language": GlobalConfig.language.code}
	outputDict: Dict[str, Union[Dict, List]] = {"metadata": metaDataDict}

	# Add set data
	with open(os.path.join("output", f"baseSetData.json"), "r", encoding="utf-8") as baseSetDataFile:
		setsData = json.load(baseSetDataFile)
		for setCode in list(setsData.keys()):
			if setsData[setCode]["names"].get(GlobalConfig.language.code, None):
				setsData[setCode]["name"] = setsData[setCode].pop("names")[GlobalConfig.language.code]
			else:
				_logger.info(f"Name for set {setCode} is empty or doesn't exist for language code '{GlobalConfig.language.code}', not adding the set to the output files")
				del setsData[setCode]
	outputDict["sets"] = setsData

	# Create the output files
	_saveFile(os.path.join(outputFolder, "metadata.json"), metaDataDict, False)
	outputDict["cards"] = fullCardList
	_saveFile(os.path.join(outputFolder, "allCards.json"), outputDict)
	_logger.info(f"Created main card file in {time.perf_counter() - startTime} seconds")
	# If we only parsed some specific cards, make a separate file with those, so checking them is a lot easier
	if onlyParseIds:
		parsedCards = {"metadata": metaDataDict, "cards": []}
		for card in outputDict["cards"]:
			if card["id"] in onlyParseIds:
				parsedCards["cards"].append(card)
		with open("parsedCards.json", "w", encoding="utf-8") as parsedCardsFile:
			json.dump(parsedCards, parsedCardsFile, indent=2)
	if GlobalConfig.limitedBuild:
		_logger.info("Limited build, not creating extra files")
		return

	# Build deck data
	decksOutputFolder = os.path.join(outputFolder, "decks")
	os.makedirs(decksOutputFolder, exist_ok=True)
	# To make lookups easier, we need an id-to-card dict
	idToCard = {}
	for card in fullCardList:
		idToCard[card["id"]] = card
	# Get the deck data
	with open(os.path.join("output", "baseDeckData.json"), "r", encoding="utf-8") as deckFile:
		decksData = json.load(deckFile)
	simpleDeckFilePaths = []
	fullDeckFilePaths = []
	for deckType, deckTypeData in decksData.items():
		deckTypeName = GlobalConfig.translation[deckType]
		for deckGroup, deckGroupData in deckTypeData.items():
			for deckIndex, deckData in enumerate(deckGroupData["decks"]):
				if GlobalConfig.language.code not in deckData["names"]:
					_logger.info(f"Skipping deck index {deckIndex} of deck group {deckGroup}, no name entry for current language")
					continue
				deckData["metadata"] = metaDataDict
				deckData["type"] = deckTypeName
				deckName = deckData.pop("names")[GlobalConfig.language.code]
				if deckName:
					deckData["name"] = deckName
				deckData["colors"] = sorted([GlobalConfig.translation[color] for color in deckData["colors"]])
				deckData["deckGroup"] = deckGroup
				deckData = {key: deckData[key] for key in sorted(deckData)}
				deckData["cards"] = []
				# Copy the deck data for the simple list so when we add full card data to the full list, they don't get added to the simple list
				simpleDeckData = copy.deepcopy(deckData)
				del simpleDeckData["cardsAndAmounts"]
				fullDeckData = deckData
				for cardId, cardAmount in deckData.pop("cardsAndAmounts").items():
					# JSON doesn't allow numbers as keys, convert it
					cardId = int(cardId, 10)
					if cardId not in idToCard:
						_logger.error(f"Deck index {deckIndex} of {deckGroup} contains card ID {cardId} but that ID doesn't exist in the full card list")
						continue
					simpleDeckData["cards"].append({"amount": cardAmount, "id": cardId, "isFoil": cardId in deckData["foilIds"]})
					# Copy the card data because we're adding fields
					cardInDeckData = copy.deepcopy(idToCard[cardId])
					cardInDeckData.update(simpleDeckData["cards"][-1])
					cardInDeckData = {key: cardInDeckData[key] for key in sorted(cardInDeckData)}
					fullDeckData["cards"].append(cardInDeckData)
				deckCode = f"deckdata.{deckGroup}-{deckIndex + 1}"
				simpleDeckFilePath = os.path.join(decksOutputFolder, f"{deckCode}.json")
				simpleDeckFilePaths.append(simpleDeckFilePath)
				with open(simpleDeckFilePath, "w", encoding="utf-8") as simpleDeckFile:
					json.dump(simpleDeckData, simpleDeckFile, indent=2)
				fullDeckFilePath = os.path.join(decksOutputFolder, f"{deckCode}.full.json")
				fullDeckFilePaths.append(fullDeckFilePath)
				with open(fullDeckFilePath, "w", encoding="utf-8") as fullDeckFile:
					json.dump(fullDeckData, fullDeckFile, indent=2)
	# Create a zipfile with all the decks
	_saveZippedFile(os.path.join(decksOutputFolder, "allDecks.zip"), simpleDeckFilePaths)
	_saveZippedFile(os.path.join(decksOutputFolder, "allDecks.full.zip"), fullDeckFilePaths)
	_logger.info(f"Created deck files in {time.perf_counter() - startTime} seconds")

	# Create an XML file that Cockatrice can load
	rootElement = xmlElementTree.Element("cockatrice_carddatabase", {"version": "4"})
	setsElement = xmlElementTree.SubElement(rootElement, "sets")
	for setId, setData in setsData.items():
		setElement = xmlElementTree.SubElement(setsElement, "set")
		xmlElementTree.SubElement(setElement, "settype").text = "Disney Lorcana TCG"
		xmlElementTree.SubElement(setElement, "name").text = setId
		xmlElementTree.SubElement(setElement, "longname").text = setData["name"]
		xmlElementTree.SubElement(setElement, "releasedate").text = setData["releaseDate"]
	cardsElement = xmlElementTree.SubElement(rootElement, "cards")
	for card in outputDict["cards"]:
		if "images" not in card or "full" not in card["images"]:
			_logger.error(f"Card {CardUtil.createCardIdentifier(card)} does not have an image stored, not adding it to the Cockatrice XML")
			continue
		cardElement = xmlElementTree.SubElement(cardsElement, "card")
		xmlElementTree.SubElement(cardElement, "name").text = card["fullName"]
		xmlElementTree.SubElement(cardElement, "text").text = card["fullText"]
		if card["type"] == GlobalConfig.translation.Location:
			# Location files should be shown in landscape
			xmlElementTree.SubElement(cardElement, "cipt").text = "1"
		tableRowNumber = "2"
		if card["type"] == GlobalConfig.translation.Action:
			tableRowNumber = "3"
		elif card["type"] != GlobalConfig.translation.Character:
			tableRowNumber = "1"
		xmlElementTree.SubElement(cardElement, "tablerow").text = tableRowNumber
		xmlElementTree.SubElement(cardElement, "set", attrib={"rarity": card["rarity"], "uuid": str(card["id"]), "num": str(card["number"]), "picurl": card["images"]["full"]}).text = card["setCode"]
		cardPropertyElement = xmlElementTree.SubElement(cardElement, "prop")
		xmlElementTree.SubElement(cardPropertyElement, "layout").text = "normal"
		xmlElementTree.SubElement(cardPropertyElement, "maintype").text = card["type"]
		fullType = card["type"]
		if "subtypesText" in card:
			fullType += " | " + card["subtypesText"]
		xmlElementTree.SubElement(cardPropertyElement, "type").text = fullType
		xmlElementTree.SubElement(cardPropertyElement, "cmc").text = str(card["cost"])
		if card.get("color", None):
			xmlElementTree.SubElement(cardPropertyElement, "colors").text = card["color"]
			xmlElementTree.SubElement(cardPropertyElement, "coloridentity").text = card["color"]
		if "willpower" in card:
			xmlElementTree.SubElement(cardPropertyElement, "pt").text = f"{card.get('strength', '-')}/{card['willpower']}"
		if "lore" in card:
			xmlElementTree.SubElement(cardPropertyElement, "loyalty").text = str(card["lore"])
	xmlElementTree.indent(rootElement)
	cockatriceXmlFilePath = os.path.join(outputFolder, "lorcana.cockatrice.xml")
	xmlElementTree.ElementTree(rootElement).write(cockatriceXmlFilePath, encoding="utf-8", xml_declaration=True)
	_createMd5ForFile(cockatriceXmlFilePath)
	_zipFile(cockatriceXmlFilePath)
	_logger.info(f"Created Cockatrice XML file in {time.perf_counter() - startTime:.4f} seconds")

	# Create separate set files
	setOutputFolder = os.path.join(outputFolder, "sets")
	os.makedirs(setOutputFolder, exist_ok=True)
	setFilePaths = []
	for setCode, setdata in setsData.items():
		# Add setcode to the set file, so it's easier to find. 'allCards' doesn't need it, since it's already the dictionary key there
		setdata["code"] = setCode
		setdata["metadata"] = metaDataDict
		setdata["cards"] = []
	for card in outputDict["cards"]:
		# Remove the setCode, since it's clear from the setfile the card is in
		setId = card.pop("setCode")
		setsData[setId]["cards"].append(card)
	for setId, setData in setsData.items():
		if len(setData["cards"]) == 0:
			_logger.info(f"No cards found for set '{setId}', not creating data file for it")
			continue
		setFilePath = os.path.join(setOutputFolder, f"setdata.{setId}.json")
		setFilePaths.append(setFilePath)
		_saveFile(setFilePath, setData)
	# Create a zipfile containing all the setfiles
	_saveZippedFile(os.path.join(setOutputFolder, "allSets.zip"), setFilePaths)
	_logger.info(f"Created the set files in {time.perf_counter() - startTime:.4f} seconds")

def _parseSingleCard(inputCard: Dict, cardType: str, imageFolder: str, enchantedNonEnchantedId: Union[int, None], promoNonPromoId: Union[int, List[int], None], variantIds: Union[List[int], None],
					 cardDataCorrections: Dict, storyParser: StoryParser, isExternalReveal: bool, historicData: Union[None, List[Dict]], bannedSince: Union[None, str] = None, shouldShowImage: bool = False) -> Union[Dict, None]:
	# Store some default values
	outputCard: Dict[str, Union[str, int, List, Dict]] = {
		"id": inputCard["culture_invariant_id"],
		"inkwell": inputCard["ink_convertible"],
		"rarity": GlobalConfig.translation[inputCard["rarity"]],
		"type": cardType
	}
	if isExternalReveal:
		outputCard["isExternalReveal"] = True
	if not inputCard["magic_ink_colors"]:
		outputCard["color"] = ""
	elif len(inputCard["magic_ink_colors"]) == 1:
		outputCard["color"] = GlobalConfig.translation[inputCard["magic_ink_colors"][0]]
	else:
		# Multi-colored card
		outputCard["colors"] = [GlobalConfig.translation[color] for color in inputCard["magic_ink_colors"]]
		outputCard["color"] = "-".join(outputCard["colors"])

	if "deck_building_limit" in inputCard:
		outputCard["maxCopiesInDeck"] = inputCard["deck_building_limit"]

	# When building a deck in the official app, it gets saves as a string. This string starts with a '2', and then each card gets a two-character code based on the card's ID
	# This card code is the card ID in base 62, using 0-9, a-z, and then A-Z for individual digits
	cardCodeDigits = divmod(outputCard["id"], 62)
	outputCard["code"] = _CARD_CODE_LOOKUP[cardCodeDigits[0]] + _CARD_CODE_LOOKUP[cardCodeDigits[1]]

	# Get required data by parsing the card image
	parsedIdentifier: Union[None, IdentifierParser.Identifier] = None
	if "card_identifier" in inputCard:
		parsedIdentifier = IdentifierParser.parseIdentifier(inputCard["card_identifier"])

	ocrResult: OcrResult = None
	if GlobalConfig.useCachedOcr and not GlobalConfig.skipOcrCache:
		ocrResult = OcrCacheHandler.getCachedOcrResult(outputCard["id"])

	if ocrResult is None:
		ocrResult = _threadingLocalStorage.imageParser.getImageAndTextDataFromImage(
			outputCard["id"],
			imageFolder,
			parseFully=isExternalReveal,
			parsedIdentifier=parsedIdentifier,
			cardType=cardType,
			hasCardText=inputCard["rules_text"] != "" if "rules_text" in inputCard else None,
			hasFlavorText=inputCard["flavor_text"] != "" if "flavor_text" in inputCard else None,
			isEnchanted=outputCard["rarity"] == GlobalConfig.translation.ENCHANTED or inputCard.get("foil_type", None) == "Satin",  # Disney100 cards need Enchanted parsing, foil_type seems best way to determine Disney100
			showImage=shouldShowImage
		)
		if not GlobalConfig.skipOcrCache:
			OcrCacheHandler.storeOcrResult(outputCard["id"], ocrResult)

	if ocrResult.identifier and (ocrResult.identifier.startswith("0") or "TFC" in ocrResult.identifier or GlobalConfig.language.uppercaseCode not in ocrResult.identifier):
		outputCard["fullIdentifier"] = re.sub(fr" ?\W (?!$)", LorcanaSymbols.SEPARATOR_STRING, ocrResult.identifier)
		outputCard["fullIdentifier"] = outputCard["fullIdentifier"].replace("I", "/").replace("1P ", "/P ").replace("//", "/").replace(".", "").replace("1TFC", "1 TFC").rstrip(" —")
		outputCard["fullIdentifier"] = re.sub(fr" ?[-+] ?", LorcanaSymbols.SEPARATOR_STRING, outputCard["fullIdentifier"])
		if parsedIdentifier is None:
			parsedIdentifier = IdentifierParser.parseIdentifier(outputCard["fullIdentifier"])
	else:
		outputCard["fullIdentifier"] = str(parsedIdentifier)
	if GlobalConfig.language.uppercaseCode not in outputCard["fullIdentifier"]:
		_logger.info(f"Card ID {outputCard['id']} ({outputCard['fullIdentifier']}) is not in current language '{GlobalConfig.language.englishName}', skipping")
		return None
	# Set the grouping ('P1', 'D23', etc) for promo cards
	if parsedIdentifier and parsedIdentifier.isPromo():
		outputCard["promoGrouping"] = parsedIdentifier.grouping

	# Get the set and card numbers from the identifier
	outputCard["number"] = parsedIdentifier.number
	if parsedIdentifier.variant:
		outputCard["variant"] = parsedIdentifier.variant
		if variantIds:
			outputCard["variantIds"] = [variantId for variantId in variantIds if variantId != outputCard["id"]]
	outputCard["setCode"] = parsedIdentifier.setCode

	# Always get the artist from the parsed data, since in the input data it often only lists the first artist when there's multiple, so it's not reliable
	outputCard["artistsText"] = ocrResult.artistsText.lstrip(". ").replace("’", "'").replace("|", "l").replace("NM", "M")
	oldArtistsText = outputCard["artistsText"]
	outputCard["artistsText"] = re.sub(r"^[l[]", "I", outputCard["artistsText"])
	while re.search(r" [a-zA0-9ÿI|(\\/_+.,;'”#—-]{1,2}$", outputCard["artistsText"]):
		outputCard["artistsText"] = outputCard["artistsText"].rsplit(" ", 1)[0]
	outputCard["artistsText"] = outputCard["artistsText"].rstrip(".")
	if "ggman-Sund" in outputCard["artistsText"]:
		outputCard["artistsText"] = re.sub("H[^ä]ggman-Sund", "Häggman-Sund", outputCard["artistsText"])
	# elif "Toziim" in outputCard["artistsText"] or "Tôzüm" in outputCard["artistsText"] or "Toztim" in outputCard["artistsText"] or "Tézim" in outputCard["artistsText"]:
	elif re.search(r"T[eéoô]z[iüt]{1,2}m\b", outputCard["artistsText"]):
		outputCard["artistsText"] = re.sub(r"\bT\w+z\w+m\b", "Tözüm", outputCard["artistsText"])
	elif re.match(r"Jo[^ã]o\b", outputCard["artistsText"]):
		outputCard["artistsText"] = re.sub("Jo[^ã]o", "João", outputCard["artistsText"])
	elif re.search(r"Krysi.{1,2}ski", outputCard["artistsText"]):
		outputCard["artistsText"] = re.sub(r"Krysi.{1,2}ski", "Krysiński", outputCard["artistsText"])
	elif "Cesar Vergara" in outputCard["artistsText"]:
		outputCard["artistsText"] = outputCard["artistsText"].replace("Cesar Vergara", "César Vergara")
	elif "Roger Perez" in outputCard["artistsText"]:
		outputCard["artistsText"] = re.sub(r"\bPerez\b", "Pérez", outputCard["artistsText"])
	elif outputCard["artistsText"].startswith("Niss ") or outputCard["artistsText"].startswith("Nilica "):
		outputCard["artistsText"] = "M" + outputCard["artistsText"][1:]
	elif GlobalConfig.language == Language.GERMAN:
		# For some bizarre reason, the German parser reads some artist names as something completely different
		if re.match(r"^ICHLER[GS]I?EN$", outputCard["artistsText"]):
			outputCard["artistsText"] = "Jenna Gray"
		elif outputCard["artistsText"] == "ES" or outputCard["artistsText"] == "ET":
			outputCard["artistsText"] = "Lauren Levering"
		outputCard["artistsText"] = outputCard["artistsText"].replace("Dösiree", "Désirée")
		outputCard["artistsText"] = re.sub(r"Man[6e]+\b", "Mané", outputCard["artistsText"])
	outputCard["artistsText"] = re.sub(r"\bAime\b", "Aimé", outputCard["artistsText"])
	outputCard["artistsText"] = re.sub(r"\bPe[^ñ]+a\b", "Peña", outputCard["artistsText"])
	if "“" in outputCard["artistsText"]:
		# Simplify quotemarks
		outputCard["artistsText"] = outputCard["artistsText"].replace("“", "\"").replace("”", "\"")
	if oldArtistsText != outputCard["artistsText"]:
		_logger.info(f"Corrected artist name from '{oldArtistsText}' to '{outputCard['artistsText']}' in card {CardUtil.createCardIdentifier(inputCard)}")

	outputCard["name"] = TextCorrection.correctPunctuation(inputCard["name"].strip() if "name" in inputCard else ocrResult.name).replace("’", "'").replace("‘", "'").replace("''", "'")
	if outputCard["name"] == "Balais Magiques":
		# This name is inconsistent, sometimes it has a capital 'M', sometimes a lowercase 'm'
		# Comparing with capitalization of other cards, this should be a lowercase 'm'
		outputCard["name"] = outputCard["name"].replace("M", "m")
	elif GlobalConfig.language == Language.ENGLISH and outputCard["name"] == "Heihei":
		# They're inconsistent about the spelling of 'HeiHei': Up to Set 6 they wrote it 'HeiHei' with the second 'H' capitalized,
		# but starting from Set 7, they started writing it 'Heihei', with the second 'h' lowercase
		# Searching around on non-Lorcana sources, the spelling isn't too consistent either, with sometimes 'Heihei' and sometimes 'Hei Hei'
		outputCard["name"] = "HeiHei"
	elif outputCard["name"].isupper() and outputCard["name"] != "B.E.N.":
		# Some names have capitals in the middle, correct those
		if cardType == GlobalConfig.translation.Character:
			if outputCard["name"] == "HEIHEI" and GlobalConfig.language == Language.ENGLISH:
				outputCard["name"] = "HeiHei"
			elif outputCard["name"] == "LEFOU":
				outputCard["name"] = "LeFou"
			else:
				outputCard["name"] = _toTitleCase(outputCard["name"])
		elif GlobalConfig.language == Language.FRENCH:
			# French titlecase rules are complicated, just capitalize the first letter for now
			outputCard["name"] = outputCard["name"][0] + outputCard["name"][1:].lower()
		else:
			outputCard["name"] = _toTitleCase(outputCard["name"])
	outputCard["fullName"] = outputCard["name"]
	outputCard["simpleName"] = outputCard["fullName"]
	if "subtitle" in inputCard or ocrResult.version:
		outputCard["version"] = (inputCard["subtitle"].strip() if "subtitle" in inputCard else ocrResult.version).replace("’", "'")
		outputCard["fullName"] += " - " + outputCard["version"]
		outputCard["simpleName"] += " " + outputCard["version"]
	# simpleName is the full name with special characters and the base-subtitle dash removed, for easier lookup. So remove the special characters
	outputCard["simpleName"] = re.sub(r"[!.,…?“”\"]", "", outputCard["simpleName"].lower()).rstrip()
	for replacementChar, charsToReplace in {"a": "[àâäā]", "c": "ç", "e": "[èêé]", "i": "[îïí]", "o": "[ôö]", "u": "[ùûü]", "oe": "œ", "ss": "ß"}.items():
		outputCard["simpleName"] = re.sub(charsToReplace, replacementChar, outputCard["simpleName"])
	_logger.debug(f"Current card name is '{outputCard['fullName']}', ID {outputCard['id']}")

	try:
		outputCard["cost"] = inputCard["ink_cost"] if "ink_cost" in inputCard else int(ocrResult.cost)
	except Exception as e:
		_logger.error(f"Unable to parse {ocrResult.cost!r} as card cost in card ID {outputCard['id']}; Exception {type(e).__name__}: {e}")
		outputCard["cost"] = -1
	if "quest_value" in inputCard:
		outputCard["lore"] = inputCard["quest_value"]
	for inputFieldName, outputFieldName in (("move_cost", "moveCost"), ("strength", "strength"), ("willpower", "willpower")):
		if inputFieldName in inputCard:
			outputCard[outputFieldName] = inputCard[inputFieldName]
		elif ocrResult[outputFieldName]:
			try:
				outputCard[outputFieldName] = int(ocrResult[outputFieldName], 10)
			except ValueError:
				_logger.error(f"Unable to parse {ocrResult[outputFieldName]!r} as {outputFieldName} in card ID {outputCard['id']}")
				outputCard[outputFieldName] = -1
	# Image URLs end with a checksum parameter, we don't need that
	if "image_urls" in inputCard:
		outputCard["images"] = {
			"full": _cleanUrl(inputCard["image_urls"][0]["url"]),
			"thumbnail": _cleanUrl(inputCard["image_urls"][1]["url"]),
		}
		if "foil_detail_url" in inputCard:
			outputCard["images"]["fullFoil"] = _cleanUrl(inputCard["foil_detail_url"])
		if "foil_mask_url" in inputCard:
			outputCard["images"]["foilMask"] = _cleanUrl(inputCard["foil_mask_url"])
		if "varnish_mask_url" in inputCard:
			outputCard["images"]["varnishMask"] = _cleanUrl(inputCard["varnish_mask_url"])
	elif "imageUrl" in inputCard:
		outputCard["images"] = {"full": inputCard["imageUrl"]}
	else:
		_logger.error(f"Card {CardUtil.createCardIdentifier(outputCard)} does not contain any image URLs")
	# If the card is Enchanted or has an Enchanted equivalent, store that
	if enchantedNonEnchantedId:
		outputCard["nonEnchantedId" if outputCard["rarity"] == GlobalConfig.translation.ENCHANTED else "enchantedId"] = enchantedNonEnchantedId
	# If the card is a promo card, store the non-promo ID
	# If the card has promo version, store the promo IDs
	if promoNonPromoId:
		outputCard["promoIds" if isinstance(promoNonPromoId, list) else "nonPromoId"] = promoNonPromoId
	# Store the different parts of the card text, correcting some values if needed
	if ocrResult.flavorText:
		flavorText = TextCorrection.correctText(ocrResult.flavorText)
		flavorText = TextCorrection.correctPunctuation(flavorText)
		# Tesseract often sees the italic 'T' as an 'I', especially at the start of a word. Fix that
		if GlobalConfig.language == Language.ENGLISH and "I" in flavorText:
			flavorText = re.sub(r"(^|\W)I(?=[ehiow]\w)", r"\1T", flavorText)
		elif GlobalConfig.language == Language.FRENCH and "-" in flavorText:
			# French cards use '–' (en dash, \u2013) a lot, for quote attribution and the like, which gets read as '-' (a normal dash) often. Correct that
			flavorText = flavorText.replace("\n-", "\n–").replace("” -", "” –")
		elif GlobalConfig.language == Language.GERMAN:
			if flavorText.endswith(" |"):
				flavorText = flavorText[:-2]
			flavorText = flavorText.replace("\nInschrift", "\n—Inschrift")
		outputCard["flavorText"] = flavorText
	abilities: List[Dict[str, str]] = []
	effects: List[str] = []
	if ocrResult.remainingText:
		remainingText = ocrResult.remainingText.lstrip("“‘").rstrip(" \n|")
		# No effect ends with a colon, it's probably the start of a choice list. Make sure it doesn't get split up
		remainingText = remainingText.replace(":\n\n", ":\n")
		# A closing bracket indicates the end of a section, make sure it gets read as such by making sure there's two newlines
		remainingTextLines = re.sub(r"(\.\)\n)", r"\1\n", remainingText).split("\n\n")
		for remainingTextLineIndex in range(len(remainingTextLines) - 1, 0, -1):
			remainingTextLine = remainingTextLines[remainingTextLineIndex]
			# Sometimes lines get split up into separate list entries when they shouldn't be,
			# for instance in choice lists, or just accidentally. Fix that. But if the previous line ended with a closing bracket and this with an opening one, don't join them
			if remainingTextLine.startswith("-") or (re.match(r"[a-z(]", remainingTextLine) and not remainingTextLines[remainingTextLineIndex-1].endswith(")")) or remainingTextLine.count(")") > remainingTextLine.count("("):
				_logger.info(f"Merging accidentally-split line {remainingTextLine!r} with previous line {remainingTextLines[remainingTextLineIndex - 1]!r}")
				remainingTextLines[remainingTextLineIndex - 1] += "\n" + remainingTextLines.pop(remainingTextLineIndex)

		for remainingTextLine in remainingTextLines:
			remainingTextLine = TextCorrection.correctText(TextCorrection.correctPunctuation(remainingTextLine))
			if len(remainingTextLine) < 4:
				_logger.info(f"Remaining text for card {CardUtil.createCardIdentifier(outputCard)} {remainingTextLine!r} is too short, discarding")
				continue
			# Check if this is a keyword ability
			if outputCard["type"] == GlobalConfig.translation.Character or outputCard["type"] == GlobalConfig.translation.Action or (parsedIdentifier.setCode == "Q2" and outputCard["type"] == GlobalConfig.translation.Location):
				if remainingTextLine.startswith("(") and ")" in remainingText:
					# Song cards have reminder text of how Songs work, and for instance 'Flotsam & Jetsam - Entangling Eels' (ID 735) has a bracketed phrase at the bottom
					# Treat those as static abilities
					abilities.append({"effect": remainingTextLine})
					continue
				keywordLines: List[str] = []
				keywordMatch = _KEYWORD_REGEX.search(remainingTextLine)
				if keywordMatch:
					keywordLines.append(remainingTextLine)
				# Some cards list keyword abilities without reminder text, sometimes multiple separated by commas
				elif ", " in remainingTextLine and not remainingTextLine.endswith("."):
					remainingTextLineParts = remainingTextLine.split(", ")
					for remainingTextLinePart in remainingTextLineParts:
						if " " in remainingTextLinePart and remainingTextLinePart != "Hors d'atteinte":
							break
					else:
						# Sentence is single-word comma-separated parts, assume it's a list of keyword abilities
						keywordLines.extend(remainingTextLineParts)
				elif _KEYWORD_REGEX_WITHOUT_REMINDER.match(remainingTextLine):
					# Single words, possibly followed by a number, but not followed by a period, are assumed to be keywords
					keywordLines.append(remainingTextLine)
				if keywordLines:
					for keywordLine in keywordLines:
						abilities.append({"type": "keyword", "fullText": keywordLine})
						# These entries will get more fleshed out after the corrections (if any) are applied, to prevent having to correct multiple fields
				elif len(remainingTextLine) > 10:
					# Since this isn't a named or keyword ability, assume it's a one-off effect
					effects.append(remainingTextLine)
				else:
					_logger.debug(f"Remaining textline is {remainingTextLine!r}, too short to parse, discarding")
			elif outputCard["type"] == GlobalConfig.translation.Item:
				# Some items ("Peter Pan's Dagger", ID 351; "Sword in the Stone", ID 352) have an ability without an ability name label. Store these as abilities too
				abilities.append({"effect": remainingTextLine})

	if ocrResult.abilityLabels:
		for abilityIndex in range(len(ocrResult.abilityLabels)):
			abilityName = TextCorrection.correctPunctuation(ocrResult.abilityLabels[abilityIndex].replace("''", "'")).rstrip(":")
			originalAbilityName = abilityName
			abilityName = re.sub(r"(?<=\w) ?[.7|»”©(\"]$", "", abilityName)
			if GlobalConfig.language == Language.ENGLISH:
				abilityName = abilityName.replace("|", "I")
				abilityName = re.sub("^l", "I", abilityName)
				# Use simple quotemark for plural possesive
				abilityName = re.sub(r"(?<=[A-Z]S)’(?=\s)", "'", abilityName)
			elif GlobalConfig.language == Language.FRENCH:
				abilityName = re.sub("A ?!(?=.{3,})", "AI", abilityName)
				if "!" in abilityName or "?" in abilityName:
					# French puts a space before an exclamation or question mark, add that in
					abilityName = re.sub(r"(?<![?! ])([!?])", r" \1", abilityName)
				abilityName = re.sub(r"\bCA\b", "ÇA", abilityName)
				abilityName = re.sub(r"\bTRES\b", "TRÈS", abilityName)
			elif GlobalConfig.language == Language.GERMAN:
				# It seems to misread a lot of ability names as ending with a period, correct that (unless it's ellipsis)
				if abilityName.endswith(".") and not abilityName.endswith("..."):
					abilityName = abilityName.rstrip(".")
				# German doesn't use fancy single-quotes in ability names, so replace all of the with simple ones
				abilityName = abilityName.replace("’", "'")
			elif GlobalConfig.language == Language.ITALIAN:
				abilityName = abilityName.replace("|", "I")
				# It keeps reading 'IO' wrong
				abilityName = re.sub("[1I]0", "IO", abilityName)
				# Italian doesn't use fancy single-quotes in ability names, so replace all of the with simple ones
				abilityName = abilityName.replace("’", "'")
			if abilityName != originalAbilityName:
				_logger.info(f"Corrected ability name from {originalAbilityName!r} to {abilityName!r}")
			abilityEffect = TextCorrection.correctText(TextCorrection.correctPunctuation(ocrResult.abilityTexts[abilityIndex]))
			abilities.append({
				"name": abilityName,
				"effect": abilityEffect
			})
	if abilities:
		outputCard["abilities"] = abilities
	if effects:
		outputCard["effects"] = effects
	# Some cards have errata or clarifications, both in the 'additional_info' fields. Split those up
	if inputCard.get("additional_info", None):
		errata = []
		clarifications = []
		for infoEntry in inputCard["additional_info"]:
			# The text has multiple \r\n's as newlines, reduce that to just a single \n
			infoText: str = infoEntry["body"].rstrip().replace("\r", "").replace("\n\n", "\n").replace("\t", " ")
			# The text uses unicode characters in some places, replace those with their simple equivalents
			infoText = infoText.replace("’", "'").replace("–", "-").replace("“", "\"").replace("”", "\"")
			# Sometimes they write cardnames as "basename- subtitle", add the space before the dash back in
			infoText = re.sub(r"(\w)- ", r"\1 - ", infoText)
			# The text uses {I} for ink and {S} for strength, replace those with our symbols
			infoText = infoText.format(E=LorcanaSymbols.EXERT, I=LorcanaSymbols.INK, L=LorcanaSymbols.LORE, S=LorcanaSymbols.STRENGTH, W=LorcanaSymbols.WILLPOWER)
			if infoEntry["title"].startswith("Errata") or infoEntry["title"].startswith("Ergänzung"):
				if " - " in infoEntry["title"]:
					# There's a suffix explaining what field the errata is about, prepend it to the text
					infoText = infoEntry["title"].split(" - ")[1] + "\n" + infoText
				errata.append(infoText)
			elif infoEntry["title"].startswith("FAQ") or infoEntry["title"].startswith("Keyword") or infoEntry["title"] == "Good to know":
				# Sometimes they cram multiple questions and answers into one entry, split those up into separate clarifications
				infoEntryClarifications = re.split("\\s*\n+(?=[FQ]:)", infoText)
				clarifications.extend(infoEntryClarifications)
			# Some German cards have an artist correction in their 'additional_info', but that's already correct in the data, so ignore that
			# Bans are listed as additional info, but we handle that separately, so ignore those
			# For other additional_info types, print an error, since that should be handled
			elif infoEntry["title"] != "Illustratorin" and infoEntry["title"] != "Ban":
				_logger.warning(f"Unknown 'additional_info' type '{infoEntry['title']}' in card {CardUtil.createCardIdentifier(outputCard)}")
		if errata:
			outputCard["errata"] = errata
		if clarifications:
			outputCard["clarifications"] = clarifications
	# Determine subtypes and their order. Items and Actions have an empty subtypes list, ignore those
	if ocrResult.subtypesText:
		subtypes: List[str] = re.sub(fr"[^A-Za-zàäèéöü{LorcanaSymbols.SEPARATOR} ]", "", ocrResult.subtypesText).split(LorcanaSymbols.SEPARATOR_STRING)
		if "ltem" in subtypes:
			subtypes[subtypes.index("ltem")] = "Item"
		# 'Seven Dwarves' is a subtype, but it might get split up into two types. Turn it back into one subtype
		sevenDwarvesCheckTypes = None
		if GlobalConfig.language == Language.ENGLISH:
			sevenDwarvesCheckTypes = ("Seven", "Dwarfs")
		elif GlobalConfig.language == Language.FRENCH:
			sevenDwarvesCheckTypes = ("Sept", "Nains")
		elif GlobalConfig.language == Language.GERMAN:
			sevenDwarvesCheckTypes = ("Sieben", "Zwerge")
		elif GlobalConfig.language == Language.ITALIAN:
			sevenDwarvesCheckTypes = ("Sette", "Nani")
		if sevenDwarvesCheckTypes and sevenDwarvesCheckTypes[0] in subtypes and sevenDwarvesCheckTypes[1] in subtypes:
			subtypes.remove(sevenDwarvesCheckTypes[1])
			subtypes[subtypes.index(sevenDwarvesCheckTypes[0])] = " ".join(sevenDwarvesCheckTypes)
		for subtypeIndex in range(len(subtypes) - 1, -1, -1):
			subtype = subtypes[subtypeIndex]
			if GlobalConfig.language in (Language.ENGLISH, Language.FRENCH) and subtype != "Floodborn" and re.match(r"^[EF][il][ao][aeo]d[^b]?b?[^b]?[aeo]r[an][es+-]?$", subtype):
				_logger.debug(f"Correcting '{subtype}' to 'Floodborn'")
				subtypes[subtypeIndex] = "Floodborn"
			elif GlobalConfig.language == Language.ENGLISH and subtype != "Hero" and re.match(r"e?H[eo]r[aeos]", subtype):
				subtypes[subtypeIndex] = "Hero"
			elif re.match("I?Hl?usion", subtype):
				subtypes[subtypeIndex] = "Illusion"
			elif GlobalConfig.language == Language.ITALIAN and subtype == "lena":
				subtypes[subtypeIndex] = "Iena"
			# Remove short subtypes, probably erroneous
			elif len(subtype) < (4 if GlobalConfig.language == Language.ENGLISH else 3) and subtype != "Re":  # 'Re' is Italian for 'King', so it's a valid subtype
				_logger.debug(f"Removing subtype '{subtype}', too short")
				subtypes.pop(subtypeIndex)
			elif not re.search("[aeiouAEIOU]", subtype):
				_logger.debug(f"Removing subtype '{subtype}', no vowels so it's probably invalid")
				subtypes.pop(subtypeIndex)
		# Non-character cards have their main type as their (first) subtype, remove those
		if subtypes and (subtypes[0] == GlobalConfig.translation.Action or subtypes[0] == GlobalConfig.translation.Item or subtypes[0] == GlobalConfig.translation.Location):
			subtypes.pop(0)
		if subtypes:
			outputCard["subtypes"] = subtypes
	# Card-specific corrections
	externalLinksCorrection: Union[None, List[str]] = None  # externalLinks depends on correct fullIdentifier, which may have a correction, but it also might need a correction itself. So store it for now, and correct it later
	fullTextCorrection: Union[None, List[str]] = None  # Since the fullText gets created as the last step, if there is a correction for it, save it for later
	forceAbilityTypeAtIndex: Dict[int, str] = {}  # index to ability type
	newlineAfterLabelIndex: int = -1
	mergeEffectIndexWithPrevious: int = -1
	moveAbilityAtIndexToIndex: Union[List[int, int], None] = None
	if cardDataCorrections:
		if cardDataCorrections.pop("_moveKeywordsLast", False):
			if "abilities" not in outputCard or "effect" not in outputCard["abilities"][-1]:
				raise KeyError(f"Correction to move keywords last is set for card {CardUtil.createCardIdentifier(outputCard)}, but no 'abilities' field exists or the last ability doesn't have an 'effect'")
			# Normally keyword abilities come before named abilities, except on some cards (e.g. 'Madam Mim - Fox' (ID 262))
			# Correct that by removing the keyword ability text from the last named ability text, and adding it as an ability
			lastAbility: Dict[str, str] = outputCard["abilities"][-1]
			lastAbilityText = lastAbility["effect"]
			keywordMatch = re.search(r"\n([A-ZÀ][^.]+)(?= \()", lastAbilityText)
			if keywordMatch:
				_logger.debug(f"'keywordsLast' is set, splitting last ability at index {keywordMatch.start()}")
				keywordText = lastAbilityText[keywordMatch.start() + 1:]  # +1 to skip the \n at the start of the match
				lastAbility["effect"] = lastAbilityText[:keywordMatch.start()]
				outputCard["abilities"].append({"type": "keyword", "fullText": keywordText})
			else:
				_logger.error(f"'keywordsLast' set but keyword couldn't be found for card {outputCard['id']}")
		for correctionAbilityField, abilityTypeCorrection in _ABILITY_TYPE_CORRECTION_FIELD_TO_ABILITY_TYPE.items():
			if correctionAbilityField in cardDataCorrections:
				abilityIndexToCorrect = cardDataCorrections.pop(correctionAbilityField)
				if abilityIndexToCorrect in forceAbilityTypeAtIndex:
					_logger.error(f"Ability at index {abilityIndexToCorrect} in card {CardUtil.createCardIdentifier(outputCard)} is being corrected to two types: '{forceAbilityTypeAtIndex[abilityIndexToCorrect]}' and '{abilityTypeCorrection}'")
				forceAbilityTypeAtIndex[abilityIndexToCorrect] = abilityTypeCorrection
		newlineAfterLabelIndex = cardDataCorrections.pop("_newlineAfterLabelIndex", -1)
		mergeEffectIndexWithPrevious = cardDataCorrections.pop("_mergeEffectIndexWithPrevious", -1)
		effectAtIndexIsAbility: Union[int, List[int, str]] = cardDataCorrections.pop("_effectAtIndexIsAbility", -1)
		effectAtIndexIsFlavorText: int = cardDataCorrections.pop("_effectAtIndexIsFlavorText", -1)
		externalLinksCorrection = cardDataCorrections.pop("externalLinks", None)
		fullTextCorrection = cardDataCorrections.pop("fullText", None)
		addNameToAbilityAtIndex: Union[None, List[int, str]] = cardDataCorrections.pop("_addNameToAbilityAtIndex", None)
		moveAbilityAtIndexToIndex = cardDataCorrections.pop("_moveAbilityAtIndexToIndex", None)
		splitAbilityNameAtIndex = cardDataCorrections.pop("_splitAbilityNameAtIndex", None)
		for fieldName, correction in cardDataCorrections.items():
			if len(correction) > 2:
				for correctionIndex in range(0, len(correction), 2):
					TextCorrection.correctCardField(outputCard, fieldName, correction[correctionIndex], correction[correctionIndex+1])
			else:
				TextCorrection.correctCardField(outputCard, fieldName, correction[0], correction[1])
		# If newlines got added through a correction, we may need to split the ability or effect in two
		if "abilities" in cardDataCorrections and "abilities" in outputCard:
			for abilityIndex in range(len(outputCard["abilities"]) - 1, -1, -1):
				ability = outputCard["abilities"][abilityIndex]
				abilityTextFieldName = "fullText" if "fullText" in ability else "effect"
				while "\n\n" in ability[abilityTextFieldName]:
					# We need to split this ability in two
					_logger.info(f"Splitting ability at index {abilityIndex} in two because it has a double newline, in card {CardUtil.createCardIdentifier(outputCard)}")
					firstAbilityTextPart, secondAbilityTextPart = ability[abilityTextFieldName].rsplit("\n\n", 1)
					ability[abilityTextFieldName] = firstAbilityTextPart
					outputCard["abilities"].insert(abilityIndex + 1, {"effect": secondAbilityTextPart})
		if "effects" in cardDataCorrections and "effects" in outputCard:
			for effectIndex in range(len(outputCard["effects"]) - 1, -1, -1):
				while "\n\n" in outputCard["effects"][effectIndex]:
					_logger.info(f"Splitting effect at index {effectIndex} in two because it has a double newline, in card {CardUtil.createCardIdentifier(outputCard)}")
					firstEffect, secondEffect = outputCard["effects"][effectIndex].rsplit("\n\n", 1)
					outputCard["effects"][effectIndex] = firstEffect
					outputCard["effects"].insert(effectIndex + 1, secondEffect)
		# Sometimes the ability name doesn't get recognised properly during fallback parsing, so there's a manual correction for it
		if splitAbilityNameAtIndex:
			ability = outputCard["abilities"][splitAbilityNameAtIndex[0]]
			ability["name"], ability["effect"] = re.split(splitAbilityNameAtIndex[1], ability["effect"], maxsplit=1)
			_logger.info(f"Split ability name and effect at index {splitAbilityNameAtIndex[0]} into name {ability['name']!r} and effect {ability['effect']!r}")
		# Sometimes ability names get missed, apply the correction to fix this
		if addNameToAbilityAtIndex:
			if addNameToAbilityAtIndex[0] >= len(outputCard["abilities"]):
				_logger.error(f"Supplied name '{addNameToAbilityAtIndex[1]}' to add to ability at index {addNameToAbilityAtIndex[0]} of card {CardUtil.createCardIdentifier(outputCard)}, but maximum ability index is {len(outputCard['abilities'])}")
			elif outputCard["abilities"][addNameToAbilityAtIndex[0]].get("name", None):
				_logger.error(f"Supplied name '{addNameToAbilityAtIndex[1]}' to add to ability at index {addNameToAbilityAtIndex[0]} of card {CardUtil.createCardIdentifier(outputCard)}, but ability already has name '{outputCard['abilities'][addNameToAbilityAtIndex[0]]['name']}'")
			else:
				_logger.info(f"Adding ability name '{addNameToAbilityAtIndex[1]}' to ability index {addNameToAbilityAtIndex[0]} for card {CardUtil.createCardIdentifier(outputCard)}")
				outputCard["abilities"][addNameToAbilityAtIndex[0]]["name"] = addNameToAbilityAtIndex[1]

		# Do this after the general corrections since one of those might add or split an effect
		if effectAtIndexIsAbility != -1:
			if "effects" not in outputCard:
				_logger.error(f"Correction to move effect index {effectAtIndexIsAbility} to abilities, but card {CardUtil.createCardIdentifier(outputCard)} doesn't have an 'effects' field")
			else:
				if "abilities" not in outputCard:
					outputCard["abilities"] = []
				abilityNameForEffectIsAbility = ""
				if isinstance(effectAtIndexIsAbility, list):
					effectAtIndexIsAbility, abilityNameForEffectIsAbility = effectAtIndexIsAbility
				_logger.info(f"Moving effect index {effectAtIndexIsAbility} to abilities")
				outputCard["abilities"].append({"name": abilityNameForEffectIsAbility, "effect": outputCard["effects"].pop(effectAtIndexIsAbility)})
				if len(outputCard["effects"]) == 0:
					del outputCard["effects"]
		if effectAtIndexIsFlavorText != -1:
			if "effects" not in outputCard:
				_logger.error(f"Correction to move effect index {effectAtIndexIsAbility} to flavor text, but card {CardUtil.createCardIdentifier(outputCard)} doesn't have an 'effects' field")
			elif "flavorText" in outputCard:
				_logger.error(f"Correction to move effect index {effectAtIndexIsAbility} to flavor text, but card {CardUtil.createCardIdentifier(outputCard)} already has a 'flavorText' field")
			else:
				_logger.info(f"Moving effect index {effectAtIndexIsFlavorText} to flavor text")
				outputCard["flavorText"] = TextCorrection.correctPunctuation(outputCard["effects"].pop(effectAtIndexIsFlavorText))
				if len(outputCard["effects"]) == 0:
					del outputCard["effects"]

	# An effect should never start with a separator; if it does, join it with the previous effect since it should be part of its option list
	if "effects" in outputCard:
		for effectIndex in range(len(outputCard["effects"]) - 1, 0, -1):
			if outputCard["effects"][effectIndex].startswith(LorcanaSymbols.SEPARATOR):
				outputCard["effects"][effectIndex - 1] += "\n" + outputCard["effects"].pop(effectIndex)
	# Now we can expand the ability fields with extra info, since it's all been corrected
	keywordAbilities: List[str] = []
	if "abilities" in outputCard:
		for abilityIndex in range(len(outputCard["abilities"])):
			ability: Dict = outputCard["abilities"][abilityIndex]
			if ability.get("type", None) == "keyword" or ("type" not in ability and not ability.get("name", None) and (_KEYWORD_REGEX.match(ability.get("fullText", ability["effect"])) or  _KEYWORD_REGEX_WITHOUT_REMINDER.match(ability.get("fullText", ability["effect"])))):
				# Clean up some mistakes from if an effect got corrected into a keyword ability
				if "fullText" not in ability:
					ability["fullText"] = ability["effect"]
				if "name" in ability:
					del ability["name"]
				if "effect" in ability:
					del ability["effect"]

				ability["type"] = "keyword"
				keyword = ability["fullText"]
				reminderText = None
				if "(" in keyword:
					# This includes reminder text, extract that
					keyword, reminderText = re.split(r"\s\(", keyword.rstrip(")"), 1)
					reminderText = reminderText.replace("\n", " ")
				keywordValue: Optional[str] = None
				if keyword[-1].isnumeric():
					keyword, keywordValue = keyword.rsplit(" ", 1)
				elif ":" in keyword:
					keyword, keywordValue = re.split(" ?: ?", keyword)
				ability["keyword"] = keyword
				if keywordValue is not None:
					ability["keywordValue"] = keywordValue
					if keywordValue[-1].isnumeric():
						ability["keywordValueNumber"] = int(keywordValue.lstrip("+"), 10)
				if reminderText is not None:
					ability["reminderText"] = reminderText
				keywordAbilities.append(keyword)
				if newlineAfterLabelIndex == abilityIndex:
					_logger.error(f"Ability at index {newlineAfterLabelIndex} is set to get a newline after its ability name, but it is a keyword ability and doesn't have a name")
			else:
				# Non-keyword ability, determine which type it is
				ability["type"] = "static"
				activatedAbilityMatch = re.search(r"(\s)([-–—])(\s)", ability["effect"])

				# Activated abilities require a cost, a dash, and then an effect
				# Some static abilities give characters such an activated ability, don't trigger on that
				# Some cards contain their own name (e.g. 'Dalmatian Puppy - Tail Wagger', ID 436), don't trigger on that dash either
				if (activatedAbilityMatch and
						("“" not in ability["effect"] or ability["effect"].index("“") > activatedAbilityMatch.start()) and
					  	("„" not in ability["effect"] or ability["effect"].index("„") > activatedAbilityMatch.start()) and
						(outputCard["name"] not in ability["effect"] or ability["effect"].index(outputCard["name"]) > activatedAbilityMatch.start())):
					# Assume there's a payment text in there
					ability["type"] = "activated"
					ability["costsText"] = ability["effect"][:activatedAbilityMatch.start()]
					ability["effect"] = ability["effect"][activatedAbilityMatch.end():]
				elif GlobalConfig.language == Language.ENGLISH:
					if ability["effect"].startswith("Once per turn, you may"):
						ability["type"] = "activated"
					elif (ability["effect"].startswith("At the start of") or ability["effect"].startswith("At the end of") or re.search(r"(^W|,[ \n]w)hen(ever)?[ \n]", ability["effect"])
							or re.search("when (he|she|it|they) enters play", ability["effect"])):
						ability["type"] = "triggered"
				elif GlobalConfig.language == Language.FRENCH:
					if ability["effect"].startswith("Une fois par tour, vous pouvez"):
						ability["type"] = "activated"
					elif (ability["effect"].startswith("Au début de chacun") or re.match(r"Au\sdébut\sd[eu](\svotre)?\stour\b", ability["effect"]) or ability["effect"].startswith("À la fin d") or
						re.search(r"(^L|\bl)orsqu(e|'une?|'il)\b", ability["effect"]) or re.search(r"(^À c|^C|,\sc)haque\sfois", ability["effect"]) or
						re.match("Si (?!vous avez|un personnage)", ability["effect"]) or re.search("gagnez .+ pour chaque", ability["effect"]) or
						re.search(r"une carte est\splacée", ability["effect"])):
						ability["type"] = "triggered"
				elif GlobalConfig.language == Language.GERMAN:
					if ability["effect"].startswith("Einmal pro Zug, darfst du"):
						ability["type"] = "activated"
					elif (re.match(r"Wenn(\sdu)?\sdiese", ability["effect"]) or re.match(r"Wenn\seiner\sdeiner\sCharaktere", ability["effect"]) or re.search(r"(^J|\bj)edes\sMal\b", ability["effect"]) or
						  re.match(r"Einmal\swährend\sdeines\sZuges\b", ability["effect"]) or ability["effect"].startswith("Einmal pro Zug, wenn") or
						  re.search(r"(^Z|\bz)u\sBeginn\s(deines|von\s\w+)\sZug", ability["effect"]) or re.match(r"Am\sEnde\s(deines|des)\sZuges", ability["effect"]) or
						  re.match(r"Falls\sdu\sGestaltwandel\sbenutzt\shas",ability["effect"]) or "wenn du eine Karte ziehst" in ability["effect"] or
						  re.search(r"\bwährend\ser\seinen?(\s|\w)+herausfordert\b", ability["effect"]) or re.search(r"wenn\sdieser\sCharakter\szu\seinem\sOrt\sbewegt", ability["effect"]) or
						  re.match(r"Wenn\s\w+\sdiese[nrs]\s\w+\sausspielt", ability["effect"]) or re.match(r"Wenn\sdu\seine.+ausspielst", ability["effect"], flags=re.DOTALL)):
						ability["type"] = "triggered"
				elif GlobalConfig.language == Language.ITALIAN:
					if re.match(r"Una\svolta\sper\sturno,\spuoi", ability["effect"]):
						ability["type"] = "activated"
					elif (re.match(r"Quando\sgiochi", ability["effect"]) or re.search(r"(^Q|\sq)uando\s(questo|sposti)", ability["effect"]) or re.search(r"(^O|\so)gni\svolta\sche", ability["effect"]) or
						  re.match(r"All'inizio\sdel\stuo\sturno", ability["effect"]) or re.match(r"Alla\sfine\sdel(\stuo)?\sturno", ability["effect"]) or
						  re.search(r"quando\saggiungi\suna\scarta\sal\stuo\scalamaio", ability["effect"]) or re.match(r"Quando\sun\savversario", ability["effect"])):
						ability["type"] = "triggered"

				if abilityIndex in forceAbilityTypeAtIndex:
					if forceAbilityTypeAtIndex[abilityIndex] == ability["type"]:
						_logger.error(f"Ability at index {abilityIndex} of {CardUtil.createCardIdentifier(outputCard)} should be corrected to '{forceAbilityTypeAtIndex[abilityIndex]}' but it is already that type")
					else:
						ability["type"] = forceAbilityTypeAtIndex[abilityIndex]
						_logger.info(f"Forcing ability type at index {abilityIndex} of card ID {outputCard['id']} to '{ability['type']}'")

				# All parts determined, now reconstruct the full ability text
				if "name" in ability and not ability["name"]:
					# Abilities added through corrections may have an empty name, remove that
					ability.pop("name")
				if "name" in ability:
					ability["fullText"] = ability["name"]
					if newlineAfterLabelIndex == abilityIndex:
						_logger.info(f"Adding newline after ability label index {abilityIndex}")
						ability["fullText"] += "\n"
					else:
						ability["fullText"] += " "
				else:
					ability["fullText"] = ""
					if newlineAfterLabelIndex == abilityIndex:
						_logger.error(f"Ability at index {newlineAfterLabelIndex} is set to get a newline after its ability name, but it doesn't have a name")
				if "costsText" in ability:
					# Usually we want to get the specific type of cost separator dash from the input data, but sometimes that's wrong
					costSeparatorDash = None
					if GlobalConfig.language == Language.GERMAN:
						if parsedIdentifier.setCode == "1":
							costSeparatorDash = "–"  # en-dash, \u2013
						elif parsedIdentifier.setCode == "5":
							costSeparatorDash = "—"  # em-dash, \u2014
					if not costSeparatorDash:
						if "rules_text" in inputCard:
							costSeparatorDash = re.search(r"\s([-–—])\s", inputCard["rules_text"]).group(1)
						else:
							costSeparatorDash = activatedAbilityMatch.group(2)
					ability["fullText"] += ability["costsText"] + activatedAbilityMatch.group(1) + costSeparatorDash + activatedAbilityMatch.group(3)
					ability["costsText"] = ability["costsText"].replace("\n", " ")
					ability["costs"] = ability["costsText"].split(", ")
				ability["fullText"] += ability["effect"]
				ability["effect"] = ability["effect"].replace("\n", " ")
				if ability["effect"].startswith("("):
					# Song reminder text has brackets around it. Keep it in the 'fullText', but remove it from the 'effect'
					ability["effect"] = ability["effect"].strip("()")
				# If the first line of the fullText is too long, the ability label is probably the full width of the card, so we need to add a newline after it (But not for Locations, those have longer lines)
				if outputCard["type"] != GlobalConfig.translation.Location and "name" in ability and (ability["fullText"].index("\n") if "\n" in ability["fullText"] else len(ability["fullText"])) >= 70:
					_logger.info(f"Adding newline after ability label index {abilityIndex}")
					ability["fullText"] = ability["fullText"][:len(ability["name"])] + "\n" + ability["fullText"][len(ability["name"]) + 1:]
			outputCard["abilities"][abilityIndex] = {abilityKey: ability[abilityKey] for abilityKey in sorted(ability)}
	if keywordAbilities:
		outputCard["keywordAbilities"] = keywordAbilities
	outputCard["artists"] = outputCard["artistsText"].split(" / ")
	if "subtypes" in outputCard:
		outputCard["subtypesText"] = LorcanaSymbols.SEPARATOR_STRING.join(outputCard["subtypes"])
	# Add external links (Do this after corrections so we can use a corrected 'fullIdentifier')
	outputCard["externalLinks"] = _threadingLocalStorage.externalIdsHandler.getExternalLinksForCard(parsedIdentifier, "enchantedId" in outputCard)
	if externalLinksCorrection:
		TextCorrection.correctCardField(outputCard, "externalLinks", externalLinksCorrection[0], externalLinksCorrection[1])
	if moveAbilityAtIndexToIndex:
		_logger.info(f"Moving ability at index {moveAbilityAtIndexToIndex[0]} to index {moveAbilityAtIndexToIndex[1]}")
		outputCard["abilities"].insert(moveAbilityAtIndexToIndex[1], outputCard["abilities"].pop(moveAbilityAtIndexToIndex[0]))
	# Reconstruct the full card text. Do that after storing and correcting fields, so any corrections will be taken into account
	# Remove the newlines in the fields we use while we're at it, because we only needed those to reconstruct the fullText
	fullTextSections = []
	if "abilities" in outputCard:
		previousAbilityWasKeywordWithoutReminder: bool = False
		for ability in outputCard["abilities"]:  # type: Dict[str, str]
			# Some cards have multiple keyword abilities on one line without reminder text. They'll be stored as separate abilities, but they should be in one section
			if ability["type"] == "keyword" and ability["keyword"] == ability["fullText"]:
				if previousAbilityWasKeywordWithoutReminder:
					# Add this keyword to the previous section, since that's how it's on the card
					fullTextSections[-1] += ", " + ability["fullText"]
				else:
					previousAbilityWasKeywordWithoutReminder = True
					fullTextSections.append(ability["fullText"])
			else:
				fullTextSections.append(ability["fullText"])
	if "effects" in outputCard:
		if mergeEffectIndexWithPrevious > -1:
			_logger.info(f"Merging effect index {mergeEffectIndexWithPrevious} with previous index for card {CardUtil.createCardIdentifier(outputCard)}")
			outputCard["effects"][mergeEffectIndexWithPrevious - 1] += "\n" + outputCard["effects"].pop(mergeEffectIndexWithPrevious)
		fullTextSections.extend(outputCard["effects"])
	outputCard["fullText"] = "\n".join(fullTextSections)
	outputCard["fullTextSections"] = fullTextSections
	if fullTextCorrection:
		TextCorrection.correctCardField(outputCard, "fullText", fullTextCorrection[0], fullTextCorrection[1])
	if "story" in inputCard:
		outputCard["story"] = inputCard["story"]
	else:
		outputCard["story"] = storyParser.getStoryNameForCard(outputCard, outputCard["id"], inputCard.get("searchable_keywords", None))
	if "foil_type" in inputCard:
		outputCard["foilTypes"] = ["None"] if inputCard["foil_type"] is None else [inputCard["foil_type"]]
	elif not isExternalReveal:
		# We can't know the foil type(s) of externally revealed cards, so not having the data at all is better than adding possibly wrong data
		# 'Normal' (so non-promo non-Enchanted) cards exist in unfoiled and cold-foiled types, so just default to that if no explicit foil type is provided
		outputCard["foilTypes"] = ["None", "Cold"]
	if "varnish_type" in inputCard:
		outputCard["varnishType"] = inputCard["varnish_type"]
	if historicData:
		outputCard["historicData"] = historicData
	if bannedSince:
		outputCard["bannedSince"] = bannedSince
	# Sort the dictionary by key
	outputCard = {key: outputCard[key] for key in sorted(outputCard)}
	return outputCard

def _saveFile(outputFilePath: str, dictToSave: Dict, createZip: bool = True):
	with open(outputFilePath, "w", encoding="utf-8") as outputFile:
		json.dump(dictToSave, outputFile, indent=2)
	_createMd5ForFile(outputFilePath)
	# Create a zipped version of the same file
	if createZip:
		_zipFile(outputFilePath)

def _zipFile(outputFilePath: str):
	outputZipFilePath = outputFilePath + ".zip"
	with zipfile.ZipFile(outputZipFilePath, "w", compression=zipfile.ZIP_LZMA, strict_timestamps=False) as outputZipfile:
		outputZipfile.write(outputFilePath, os.path.basename(outputFilePath))
	_createMd5ForFile(outputZipFilePath)

def _createMd5ForFile(filePath: str):
	with open(filePath, "rb") as fileToHash, open(filePath + ".md5", "w", encoding="utf-8") as md5File:
		fileHash = hashlib.md5(fileToHash.read()).hexdigest()
		md5File.write(fileHash)

def _saveZippedFile(outputZipfilePath: str, filePathsToZip: List[str]):
	with zipfile.ZipFile(outputZipfilePath, "w", compression=zipfile.ZIP_LZMA, strict_timestamps=False) as outputZipfile:
		for filePathToZip in filePathsToZip:
			outputZipfile.write(filePathToZip, os.path.basename(filePathToZip))
	_createMd5ForFile(outputZipfilePath)

def _toTitleCase(s: str) -> str:
	s = re.sub(r"(?:^| |\n|\(|-| '| d')([a-z])(?!')", lambda m: m.group(0).upper(), s.lower())
	toLowerCaseWords = None
	if GlobalConfig.language == Language.ENGLISH:
		toLowerCaseWords = (" A ", " At ", " In ", " Into ", " Of ", " The ", " To ")
	elif GlobalConfig.language == Language.FRENCH:
		toLowerCaseWords = (" D'", " De ", " Des ", " Du ")
	if toLowerCaseWords:
		for toLowerCaseWord in toLowerCaseWords:
			if toLowerCaseWord in s:
				s = s.replace(toLowerCaseWord, toLowerCaseWord.lower())
	return s
