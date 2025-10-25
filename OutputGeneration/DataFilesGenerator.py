import copy, datetime, hashlib, json, logging, multiprocessing.pool, os, re, threading, time, zipfile
import xml.etree.ElementTree as xmlElementTree
from typing import Dict, List, Optional, Union

import GlobalConfig
from APIScraping.ExternalLinksHandler import ExternalLinksHandler
from OCR import ImageParser
from OutputGeneration import SingeCardDataGenerator
from OutputGeneration.AllowedInFormatsHandler import AllowedInFormatsHandler
from OutputGeneration.RelatedCardsCollator import RelatedCardCollator
from OutputGeneration.StoryParser import StoryParser
from util import CardUtil, JsonUtil

_logger = logging.getLogger("LorcanaJSON")
FORMAT_VERSION = "2.3.0"
# The card parser is run in threads, and each thread needs to initialize its own ImageParser (otherwise weird errors happen in Tesseract)
# Store each initialized ImageParser in its own thread storage
_threadingLocalStorage = threading.local()
_threadingLocalStorage.imageParser: ImageParser.ImageParser = None
_threadingLocalStorage.externalIdsHandler: ExternalLinksHandler = None


def createOutputFiles(onlyParseIds: Optional[List[int]] = None, shouldShowImages: bool = False) -> None:
	startTime = time.perf_counter()
	imageFolder = os.path.join("downloads", "images", GlobalConfig.language.code)
	if not os.path.isdir(imageFolder):
		raise FileNotFoundError(f"Images folder for language '{GlobalConfig.language.code}' doesn't exist. Run the data downloader first")
	cardCatalogPath = os.path.join("downloads", "json", f"carddata.{GlobalConfig.language.code}.json")
	if not os.path.isfile(cardCatalogPath):
		raise FileNotFoundError(f"Card catalog for language '{GlobalConfig.language.code}' doesn't exist. Run the data downloader first")
	with open(cardCatalogPath, "r", encoding="utf-8") as inputFile:
		inputData = json.load(inputFile)

	cardDataCorrections: Dict[int, Dict[str, List[str, str]]] = JsonUtil.loadJsonWithNumberKeys(os.path.join("OutputGeneration", "data", "outputDataCorrections", "outputDataCorrections.json"))
	correctionsFilePath = os.path.join("OutputGeneration", "data", "outputDataCorrections", f"outputDataCorrections_{GlobalConfig.language.code}.json")
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

	historicDataFilePath = os.path.join("OutputGeneration", "data", "historicData", f"historicData_{GlobalConfig.language.code}.json")
	if os.path.isfile(historicDataFilePath):
		historicData = JsonUtil.loadJsonWithNumberKeys(historicDataFilePath)
	else:
		historicData = {}

	# Get the cards we don't have to parse (if any) from the previous generated file
	fullCardList: List[Dict] = []
	cardIdsStored: List[int] = []
	outputFolder = os.path.join("output", GlobalConfig.language.code)
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
	relatedCardCollator = RelatedCardCollator(inputData)
	allowedCardsHandler = AllowedInFormatsHandler()
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
					results.append(pool.apply_async(SingeCardDataGenerator.parseSingleCard, (inputCard, cardTypeText, imageFolder, _threadingLocalStorage, relatedCardCollator.getRelatedCards(inputCard),
												  cardDataCorrections.pop(cardId, None), cardToStoryParser, False, historicData.get(cardId, None), allowedCardsHandler, shouldShowImages)))
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
			results.append(pool.apply_async(SingeCardDataGenerator.parseSingleCard, (externalCard, externalCard["type"], imageFolder, _threadingLocalStorage, relatedCardCollator.getRelatedCards(externalCard),
															   cardDataCorrections.pop(cardId, None), cardToStoryParser, True, historicData.get(cardId, None), allowedCardsHandler, shouldShowImages)))
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
	with open(os.path.join("OutputGeneration", "data", "baseSetData.json"), "r", encoding="utf-8") as baseSetDataFile:
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
		with open(os.path.join("output", "parsedCards.json"), "w", encoding="utf-8") as parsedCardsFile:
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
	with open(os.path.join("OutputGeneration", "data", "baseDeckData.json"), "r", encoding="utf-8") as deckFile:
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
				_createMd5ForFile(simpleDeckFilePath)
				fullDeckFilePath = os.path.join(decksOutputFolder, f"{deckCode}.full.json")
				fullDeckFilePaths.append(fullDeckFilePath)
				with open(fullDeckFilePath, "w", encoding="utf-8") as fullDeckFile:
					json.dump(fullDeckData, fullDeckFile, indent=2)
				_createMd5ForFile(fullDeckFilePath)
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

def _saveFile(outputFilePath: str, dictToSave: Dict, createZip: bool = True):
	with open(outputFilePath, "w", encoding="utf-8") as outputFile:
		json.dump(dictToSave, outputFile, indent=2)
	_createMd5ForFile(outputFilePath)
	# Create a zipped version of the same file
	if createZip:
		_zipFile(outputFilePath)

def _zipFile(outputFilePath: str):
	outputZipFilePath = outputFilePath + ".zip"
	with zipfile.ZipFile(outputZipFilePath, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, strict_timestamps=False) as outputZipfile:
		outputZipfile.write(outputFilePath, os.path.basename(outputFilePath))
	_createMd5ForFile(outputZipFilePath)

def _createMd5ForFile(filePath: str):
	with open(filePath, "rb") as fileToHash, open(filePath + ".md5", "w", encoding="utf-8") as md5File:
		fileHash = hashlib.md5(fileToHash.read()).hexdigest()
		md5File.write(fileHash)

def _saveZippedFile(outputZipfilePath: str, filePathsToZip: List[str]):
	with zipfile.ZipFile(outputZipfilePath, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, strict_timestamps=False) as outputZipfile:
		for filePathToZip in filePathsToZip:
			outputZipfile.write(filePathToZip, os.path.basename(filePathToZip))
	_createMd5ForFile(outputZipfilePath)
