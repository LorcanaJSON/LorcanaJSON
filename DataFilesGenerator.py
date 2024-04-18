import datetime, hashlib, json, logging, multiprocessing.pool, os, re, threading, time, zipfile
from typing import Dict, List, Union

import GlobalConfig, Language
from OCR import ImageParser

_logger = logging.getLogger("LorcanaJSON")
FORMAT_VERSION = "1.2.0"
# The card parser is run in threads, and each thread needs to initialize its own ImageParser (otherwise weird errors happen in Tesseract)
# Store each initialized ImageParser in its own thread storage
_threadingLocalStorage = threading.local()
_threadingLocalStorage.imageParser = None

def correctText(cardText: str) -> str:
	"""
	Fix some re-occuring mistakes and errors in the text of the cards
	:param cardText: The text to correct
	:return: The card text with common problems fixed
	"""
	correctedCardLines = []
	for cardLine in cardText.splitlines():
		originalCardLine = cardLine
		# First simple typos
		if re.match("[‘`']Shift ", cardLine):
			_logger.info("Removing erroneous character at the start of " + cardLine)
			cardLine = cardLine[1:]
		if "’" in cardLine:
			cardLine = re.sub(r"(?<=\w)’(?=\w)", "'", cardLine)
		if "1lore" in cardLine:
			cardLine = cardLine.replace("1lore", "1 lore")
		if " 1O " in cardLine:
			cardLine = cardLine.replace(" 1O ", f" 1 {ImageParser.INK_UNICODE} ")
		if "€" in cardLine:
			# For some reason it keeps reading the Strength symbol as the Euro symbol
			cardLine = re.sub(r"€[^ .]?", ImageParser.STRENGTH_UNICODE, cardLine)
		if "”" in cardLine:
			# Normally a closing quote mark should be preceded by a period
			cardLine = re.sub("([^.,'!?’])”", "\\1.”", cardLine)
		if "Bodyquard" in cardLine:
			# Somehow it reads 'Bodyquard' with a 'q' instead of a 'g' a lot...
			cardLine = cardLine.replace("Bodyquard", "Bodyguard")
		if "( " in cardLine:
			cardLine = cardLine.replace("( ", "(")
		if "lll" in cardLine:
			# 'Illuminary' and 'Illumineer(s)' often gets read as starting with three l's, instead of an I and two l's
			cardLine = cardLine.replace("lllumin", "Illumin")
		if "Ihe" in cardLine:
			cardLine = re.sub(r"\bIhe\b", "The", cardLine)
		if "|" in cardLine:
			cardLine = cardLine.replace("|", "I")
		if cardLine.endswith("of i"):
			# The 'Floodborn' inksplashes sometimes confuse the reader into imagining another 'i' at the end of some reminder text, remove that
			cardLine = cardLine.rstrip(" i")
		# Correct common phrases with symbols
		if re.search(rf"pay \d ?[^{ImageParser.INK_UNICODE}]{{1,2}}(?: |$)", cardLine):
			# Lore payment discounts
			cardLine, changeCount = re.subn(rf"pay (\d) ?[^{ImageParser.INK_UNICODE}]{{1,2}}( |$)", f"pay \\1 {ImageParser.INK_UNICODE}\\2", cardLine)
			if changeCount > 0:
				_logger.info("Correcting lore payment text")
		# Fields with Errata corrections have 'ERRATA' in the text, possibly with a colon. Remove that
		if "ERRATA" in cardLine:
			cardLine = re.sub(" ?ERRATA:? ?", "", cardLine)
		# Correct reminder text
		if re.match(r"^gets \+\d .{1,2}?\.?\)?$", cardLine):
			# Challenger, second line
			cardLine, changeCount = re.subn(rf"gets \+(\d) [^{ImageParser.STRENGTH_UNICODE}]{{1,2}}?\.?\)", fr"gets +\1 {ImageParser.STRENGTH_UNICODE}.)", cardLine)
			if changeCount > 0:
				_logger.info("Correcting second line of Challenger reminder text")
		elif re.match(r"\(A character with cost \d or more can .{1,2} to sing this( song for free)?", cardLine):
			# Song
			cardLine, changeCount = re.subn(f"can [^{ImageParser.EXERT_UNICODE}]{{1,2}} to sing this", f"can {ImageParser.EXERT_UNICODE} to sing this", cardLine)
			if changeCount > 0:
				_logger.info("Correcting Song reminder text")
		elif re.match("add their .{1,2} to another chosen character['’]s .{1,2} this", cardLine):
			# Support, full line (not sure why it sometimes doesn't get cut into two lines
			cardLine, changeCount = re.subn(f"their [^{ImageParser.STRENGTH_UNICODE}]{{1,2}} to", f"their {ImageParser.STRENGTH_UNICODE} to", cardLine)
			cardLine, changeCount2 = re.subn(f"character's [^{ImageParser.STRENGTH_UNICODE}]{{1,2}} this", f"character's {ImageParser.STRENGTH_UNICODE} this", cardLine)
			if changeCount > 0 or changeCount2 > 0:
				_logger.info("Correcting Support reminder text (both symobls on one line)")
		elif re.match("may add their .{1,2} to another chosen character[’']s", cardLine):
			# Support, first line if split
			cardLine, changeCount = re.subn(f"their {ImageParser.STRENGTH_UNICODE}{{1,2}} to", f"their {ImageParser.STRENGTH_UNICODE} to", cardLine)
			if changeCount > 0:
				_logger.info("Correcting first line of Support reminder text")
		elif re.match(rf"[^{ImageParser.STRENGTH_UNICODE}]{{1,2}} this turn\.?\)?", cardLine):
			# Support, second line if split
			_logger.info("Correcting second line of Support reminder text")
			cardLine = f"{ImageParser.STRENGTH_UNICODE} this turn.)"
		elif cardLine.startswith("Ward (Upponents "):
			_logger.info("Correcting 'Upponents' to 'Opponents'")
			cardLine = cardLine.replace("(Upponents", "(Opponents")
		elif re.search(r"reduced by [lI]\.", cardLine):
			cardLine = re.sub(r"reduced by [lI]\.", "reduced by 1.", cardLine)
		if cardLine:
			correctedCardLines.append(cardLine)
		if originalCardLine != cardLine:
			_logger.info(f"Corrected card line from '{originalCardLine}' to '{cardLine}'")
	return "\n".join(correctedCardLines)

def correctPunctuation(textToCorrect: str) -> str:
	"""
	Corrects some punctuation, like fixing weirdly spaced ellipses, or quote marks
	Mainly useful to correct flavor text
	:param textToCorrect: The text to correct. Can be multiline
	:return: The fixed text, or the original text if there was nothing to fix
	"""
	correctedText = textToCorrect
	# Ellipses get parsed weird, with spaces between periods where they don't belong. Fix that
	if correctedText.count(".") > 2:
		correctedText = re.sub(r"([\xa0 ]?\.[\xa0 ]?){3}", "...", correctedText)
	if correctedText != textToCorrect:
		_logger.info(f"Corrected punctuation from {textToCorrect!r} to {correctedText!r}")
	return correctedText

def correctCardField(card: Dict, fieldName: str, regexMatchString: str, correction: str) -> None:
	"""
	Correct card-specific mistakes in the fieldName field of the provided card
	:param card: The output card as parsed so far
	:param fieldName: The fieldname to correct
	:param regexMatchString: A regex that matches the card's mistake, this text will get replaced with the 'correction' string. Can be None if the field doesn't exist yet. To remove a field, set this and 'correction' to None
	:param correction: The correction for the mistake matched by 'regexMatchString', or the value to set if the field doesn't exist. To remove a field, set this and 'regexMatchString' to None
	"""
	if fieldName not in card:
		card[fieldName] = correction
	elif regexMatchString is None and correction is None:
		_logger.info(f"Removing field '{fieldName}' from card {_createCardIdentifier(card)}")
		del card[fieldName]
	elif isinstance(card[fieldName], str):
		preCorrectedText = card[fieldName]
		card[fieldName] = re.sub(regexMatchString, correction, preCorrectedText, flags=re.DOTALL)
		if card[fieldName] == preCorrectedText:
			_logger.warning(f"Correcting field '{fieldName}' in card {_createCardIdentifier(card)} didn't change anything, value is still {preCorrectedText!r}")
		else:
			_logger.info(f"Corrected field '{fieldName}' from {repr(preCorrectedText)} to {repr(card[fieldName])} for card {_createCardIdentifier(card)}")
	elif isinstance(card[fieldName], list):
		matchFound = False
		if isinstance(card[fieldName][0], dict):
			# The field is a list of dicts, apply the correction to each entry if applicable
			for fieldIndex, fieldEntry in enumerate(card[fieldName]):
				for fieldKey, fieldValue in fieldEntry.items():
					match = re.search(regexMatchString, fieldValue, flags=re.DOTALL)
					if match:
						matchFound = True
						preCorrectedText = fieldValue
						fieldEntry[fieldKey] = re.sub(regexMatchString, correction, fieldValue, flags=re.DOTALL)
						if fieldEntry[fieldKey] == preCorrectedText:
							_logger.warning(f"Correcting index {fieldIndex} of field '{fieldName}' in card {_createCardIdentifier(card)} didn't change anything, value is still '{preCorrectedText}'")
						else:
							_logger.info(f"Corrected index {fieldIndex} of field '{fieldName}' from {repr(preCorrectedText)} to {repr(fieldEntry[fieldKey])} for card {_createCardIdentifier(card)}")
		elif isinstance(card[fieldName][0], str):
			for fieldIndex, fieldValue in enumerate(card[fieldName]):
				match = re.search(regexMatchString, fieldValue, flags=re.DOTALL)
				if match:
					matchFound = True
					preCorrectedText = fieldValue
					card[fieldName][fieldIndex] = re.sub(regexMatchString, correction, fieldValue)
					if card[fieldName][fieldIndex] == preCorrectedText:
						_logger.warning(f"Correcting index {fieldIndex} of field '{fieldName}' in card {_createCardIdentifier(card)} didn't change anything")
					else:
						_logger.info(f"Corrected index {fieldIndex} of field '{fieldName}' from {repr(preCorrectedText)} to {repr(card[fieldName][fieldIndex])} for card {_createCardIdentifier(card)}")
		else:
			_logger.error(f"Unhandled type of list entries ({type(card[fieldName][0])}) in card {_createCardIdentifier(card)}")
		if not matchFound:
			_logger.warning(f"Correction regex '{regexMatchString}' for field '{fieldName}' in card {_createCardIdentifier(card)} didn't match any of the entries in that field")
	else:
		raise ValueError(f"Card correction for field '{fieldName}' in card {_createCardIdentifier(card)} is of unsupported type '{type(card[fieldName])}'")

def _cleanUrl(url: str) -> str:
	"""
	Clean up the provided URL. This removes the 'checksum' URL parameter, since it's not needed
	:param url: The URL to clean up
	:return: The cleaned-up URL
	"""
	return url.split('?', 1)[0]

def _createCardIdentifier(card: Dict) -> str:
	"""
	Create an identifier string for an input or output card, consisting of the full name and the ID
	:param card: The card dictionary
	:return: A string with the full card name and the card ID
	"""
	if "id" in card:
		# Output card
		return f"'{card['fullName']}' (ID {card['id']})"
	# Input card
	return f"'{card['name']} - {card.get('subtitle', None)}' (ID {card['culture_invariant_id']})"

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
	cardIdToStoryName = _determineCardIdToStoryName(onlyParseIds)

	correctionsFilePath = os.path.join("output", f"outputDataCorrections_{GlobalConfig.language.code}.json")
	if os.path.isfile(correctionsFilePath):
		with open(correctionsFilePath, "r", encoding="utf-8") as correctionsFile:
			# Convert all the ID keys to numbers as we load
			cardDataCorrections: Dict[int, Dict[str, List[str, str]]] = {int(k, 10): v for k, v in json.load(correctionsFile).items()}
	else:
		_logger.warning(f"No corrections file found for language '{GlobalConfig.language.code}', assuming no corrections are necessary")
		cardDataCorrections = {}

	# Enchanted-rarity and promo cards are special versions of existing cards. Store their shared ID so we can add a linking field to both versions
	# We do this before parse-id-checks and other parsing, so we can add these IDs to cards that have variant versions, even if they're not being parsed
	# Also, some cards have identical-rarity variants ("Dalmation Puppy', ID 436-440), store those so each can reference the others
	enchantedDeckbuildingIds = {}
	promoDeckBuildingIds = {}
	variantsDeckBuildingIds = {}
	for cardtype, cardlist in inputData["cards"].items():
		for card in cardlist:
			# Promo cards are number x of 'P1' instead of a number of cards
			if "/P" in card["card_identifier"]:
				if card["deck_building_id"] not in promoDeckBuildingIds:
					promoDeckBuildingIds[card["deck_building_id"]] = []
				promoDeckBuildingIds[card["deck_building_id"]].append(card["culture_invariant_id"])
			# Some promo cards are listed as Enchanted-rarity, so don't store those promo cards as Enchanted too
			elif card["rarity"] == "ENCHANTED":
				enchantedDeckbuildingIds[card["deck_building_id"]] = card["culture_invariant_id"]
			if re.match(r"^\d+[a-z]/", card["card_identifier"]):
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
			if card["rarity"] != "ENCHANTED" and card["deck_building_id"] in enchantedDeckbuildingIds:
				nonEnchantedId = card["culture_invariant_id"]
				enchantedId = enchantedDeckbuildingIds[card["deck_building_id"]]
				enchantedNonEnchantedIds[nonEnchantedId] = enchantedId
				enchantedNonEnchantedIds[enchantedId] = nonEnchantedId
			if "/P" not in card["card_identifier"] and card["deck_building_id"] in promoDeckBuildingIds:
				nonPromoId = card["culture_invariant_id"]
				promoIds = promoDeckBuildingIds[card["deck_building_id"]]
				promoNonPromoIds[nonPromoId] = promoIds
				for promoId in promoIds:
					promoNonPromoIds[promoId] = nonPromoId
	del enchantedDeckbuildingIds
	del promoDeckBuildingIds

	# Get the cards we don't have to parse (if any) from the previous generated file
	fullCardList = []
	cardIdsStored = []
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
							# If this card is an Enchanted card or has an Enchanted equivalent, add that field, so we don't need to fully parse the card
							if card["id"] in enchantedNonEnchantedIds:
								card["nonEnchantedId" if card["rarity"] == "Enchanted" else "enchantedId"] = enchantedNonEnchantedIds[card["id"]]
							if card["id"] in promoNonPromoIds and "promoIds" not in card and "nonPromoId" not in card:
								promoResult = promoNonPromoIds[card["id"]]
								# For non-promo cards it stores a list of promo IDs, for promo cards it stores a single non-promo ID
								card["promoIds" if isinstance(promoResult, list) else "nonPromoId"] = promoResult
				del previousCardData
		else:
			_logger.warning("ID list provided but previously generated file doesn't exist. Generating all card data")

	def initThread():
		_threadingLocalStorage.imageParser = ImageParser.ImageParser(True)

	# Parse the cards we need to parse
	threadCount = GlobalConfig.threadCount
	if not threadCount:
		# Only use half the available cores for threads, because we're also IO- and GIL-bound, so more threads would just slow things down
		threadCount = max(1, os.cpu_count() // 2)
	_logger.debug(f"Using {threadCount:,} threads for parsing the cards")
	with multiprocessing.pool.ThreadPool(threadCount, initializer=initThread) as pool:
		results = []
		for cardType, inputCardlist in inputData["cards"].items():
			cardTypeText = cardType[:-1].title()  # 'cardType' is plural ('characters', 'items', etc), make it singular
			for inputCardIndex in range(len(inputCardlist)):
				inputCard = inputCardlist.pop()
				cardId = inputCard["culture_invariant_id"]
				if cardId in cardIdsStored:
					_logger.debug(f"Skipping parsing card with ID {inputCard['culture_invariant_id']} since it's already in the card list")
					continue
				elif onlyParseIds and cardId not in onlyParseIds:
					_logger.error(f"Card ID {cardId} is not in the ID parse list, but it's also not in the previous dataset. Skipping parsing for now, but this results in incomplete datafiles, so it's strongly recommended to rerun with this card ID included")
					continue
				elif inputCard["expansion_number"] < GlobalConfig.language.fromSet:
					_logger.debug(f"Skipping card with ID {inputCard['culture_invariant_id']} because it's from set {inputCard['expansion_number']} and language {GlobalConfig.language.englishName} started from set {GlobalConfig.language.fromSet}")
					continue
				try:
					results.append(pool.apply_async(_parseSingleCard, (inputCard, cardTypeText, imageFolder, enchantedNonEnchantedIds.get(cardId, None), promoNonPromoIds.get(cardId, None), variantsDeckBuildingIds.get(inputCard["deck_building_id"]),
												  cardDataCorrections.pop(cardId, None), cardIdToStoryName.pop(cardId), False, shouldShowImages)))
					cardIdsStored.append(cardId)
				except Exception as e:
					_logger.error(f"Exception {type(e)} occured while parsing card ID {inputCard['culture_invariant_id']}")
					raise e
		# Load in the external card reveals, which are cards revealed elsewhere but which aren't added to the official app yet
		externalCardReveals = []
		externalCardRevealsFileName = f"externalCardReveals.{GlobalConfig.language.code}.json"
		if os.path.isfile(externalCardRevealsFileName):
			with open(externalCardRevealsFileName, "r", encoding="utf-8") as externalCardRevealsFile:
				externalCardReveals = json.load(externalCardRevealsFile)
		imageFolder = os.path.join(imageFolder, "external")
		for externalCard in externalCardReveals:
			cardId = externalCard["culture_invariant_id"]
			if cardId in cardIdsStored:
				_logger.debug(f"Card ID {cardId} is defined in the official file and in the external file, skipping the external data")
				continue
			results.append(pool.apply_async(_parseSingleCard, (externalCard, externalCard["type"], imageFolder, enchantedNonEnchantedIds.get(cardId, None), promoNonPromoIds.get(cardId, None), variantsDeckBuildingIds,
															   cardDataCorrections.pop(cardId, None), cardIdToStoryName.pop(cardId, None), True, shouldShowImages)))
		pool.close()
		pool.join()
	for result in results:
		outputCard = result.get()
		fullCardList.append(outputCard)

	if cardDataCorrections:
		# Some card corrections are left, which shouldn't happen
		_logger.warning(f"{len(cardDataCorrections):,} card corrections left, which shouldn't happen: {cardDataCorrections}")
	# Sort the cards by set and cardnumber
	fullCardList.sort(key=lambda card: card["id"])
	os.makedirs(outputFolder, exist_ok=True)
	# Add metadata
	metaDataDict = {"formatVersion": FORMAT_VERSION, "generatedOn": datetime.datetime.utcnow().isoformat()}
	outputDict = {"metadata": metaDataDict}

	# Add set data
	with open(os.path.join("output", f"baseSetData.json"), "r", encoding="utf-8") as baseSetDataFile:
		setsData = json.load(baseSetDataFile)
		for setNumber in setsData:
			# Get just the current language's set names
			setsData[setNumber]["name"] = setsData[setNumber].pop("names")[GlobalConfig.language.code]
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
	# Create separate set files
	setOutputFolder = os.path.join(outputFolder, "sets")
	os.makedirs(setOutputFolder, exist_ok=True)
	setFilePaths = []
	for setdata in setsData.values():
		setdata["cards"] = []
	for card in outputDict["cards"]:
		setId = str(card.pop("setNumber"))
		setsData[setId]["cards"].append(card)
	for setId, setData in setsData.items():
		if len(setData["cards"]) == 0:
			_logger.warning(f"No cards found for set '{setId}', not creating data file for it")
			continue
		setData["metadata"] = metaDataDict
		setFilePaths.append(os.path.join(setOutputFolder, f"setdata.{setId}.json"))
		_saveFile(setFilePaths[-1], setData)
	# Create a zipfile containing all the setfiles
	setsZipfilePath = os.path.join(setOutputFolder, "allSets.zip")
	with zipfile.ZipFile(setsZipfilePath, "w", compression=zipfile.ZIP_LZMA, strict_timestamps=False) as setsZipfile:
		for setFilePath in setFilePaths:
			setsZipfile.write(setFilePath, os.path.basename(setFilePath))
	_createMd5ForFile(setsZipfilePath)

	_logger.info(f"Creating the output files took {time.perf_counter() - startTime:.4f} seconds")

def _parseSingleCard(inputCard: Dict, cardType: str, imageFolder: str, enchantedNonEnchantedId: Union[int, None], promoNonPromoId: Union[int, List[int], None], variantIds: Union[List[int], None],
					 cardDataCorrections: Dict, storyName: str, isExternalReveal: bool, shouldShowImage: bool = False) -> Dict:
	# Store some default values
	outputCard: Dict[str, Union[str, int, List, Dict]] = {
		"color": inputCard["magic_ink_color"].title(),
		"id": inputCard["culture_invariant_id"],
		"inkwell": inputCard["ink_convertible"],
		"rarity": inputCard["rarity"].title(),
		"type": cardType
	}
	if isExternalReveal:
		outputCard["isExternalReveal"] = True

	# Get required data by parsing the card image
	imagePath = os.path.join(imageFolder, f"{outputCard['id']}.jpg")
	if not os.path.isfile(imagePath):
		imagePath = os.path.join(imageFolder, f"{outputCard['id']}.png")
	if not os.path.isfile(imagePath):
		raise ValueError(f"Unable to find image for card ID {outputCard['id']}")
	parsedImageAndTextData = _threadingLocalStorage.imageParser.getImageAndTextDataFromImage(imagePath,
																	  parseFully=isExternalReveal,
																	  includeIdentifier="/P" in inputCard.get("card_identifier", "/P"),
																	  isLocation=cardType == "Location",
																	  hasCardText=inputCard["rules_text"] != "" if "rules_text" in inputCard else None,
																	  hasFlavorText=inputCard["flavor_text"] != "" if "flavor_text" in inputCard else None,
																	  isEnchanted=outputCard["rarity"] == "Enchanted" or inputCard.get("foil_type", None) == "Satin",  # Disney100 cards need Enchanted parsing, foil_type seems best way to determine Disney100
																	  showImage=shouldShowImage)

	# The card identifier in non-promo cards is mostly correct in the input card,
	# For promo cards, get the text from the image, since it can differ quite a bit
	if "card_identifier" in inputCard and "/P" not in inputCard["card_identifier"]:
		outputCard["fullIdentifier"] = inputCard["card_identifier"].replace(" ", f" {ImageParser.SEPARATOR_UNICODE} ")
	else:
		outputCard["fullIdentifier"] = re.sub(fr" ?\W (?!$)", f" {ImageParser.SEPARATOR_UNICODE} ", parsedImageAndTextData["identifier"].text).replace("I", "/")
	if "number" in inputCard:
		outputCard["number"] = inputCard["number"]
	if "expansion_number" in inputCard:
		outputCard["setNumber"] = inputCard["expansion_number"]
	if "number" not in outputCard or "setNumber" not in outputCard:
		# Get the set and card numbers from the parsed identifier
		cardIdentifierMatch = re.match(r"^(\d+)([a-z])?/[0-9P]+ .+ (\d+)$", inputCard["card_identifier"] if "card_identifier" in inputCard else parsedImageAndTextData["identifier"].text)
		if not cardIdentifierMatch:
			raise ValueError(f"Unable to parse card and set numbers from card identifier '{parsedImageAndTextData['identifier'].text}")
		if "number" not in outputCard:
			outputCard["number"] = int(cardIdentifierMatch.group(1), 10)
		if cardIdentifierMatch.group(2):
			outputCard["variant"] = cardIdentifierMatch.group(2)
			if variantIds:
				outputCard["variantIds"] = [variantId for variantId in variantIds if variantId != outputCard["id"]]
		if "setNumber" not in outputCard:
			outputCard["setNumber"] = int(cardIdentifierMatch.group(3), 10)

	outputCard["artist"] = inputCard["author"].strip() if "author" in inputCard else parsedImageAndTextData["artist"].text
	if outputCard["artist"].startswith("Illus. "):
		outputCard["artist"] = outputCard["artist"].split(" ", 1)[1]
	outputCard["baseName"] = correctPunctuation(inputCard["name"].strip().replace("’", "'") if "name" in inputCard else parsedImageAndTextData["baseName"].text.title())
	outputCard["fullName"] = outputCard["baseName"]
	outputCard["simpleName"] = outputCard["fullName"]
	if "subtitle" in inputCard or parsedImageAndTextData.get("subtitle", None) is not None:
		outputCard["subtitle"] = inputCard["subtitle"].strip().replace("’", "'") if "subtitle" in inputCard else parsedImageAndTextData["subtitle"].text
		outputCard["fullName"] += " - " + outputCard["subtitle"]
		outputCard["simpleName"] += " " + outputCard["subtitle"]
	# simpleName is the full name with special characters and the base-subtitle dash removed, for easier lookup. So remove the special characters
	outputCard["simpleName"] = re.sub(r"[!.?]", "", outputCard["simpleName"].lower()).replace("ā", "a").rstrip()
	_logger.debug(f"Current card name is '{outputCard['fullName']}, ID {outputCard['id']}")

	outputCard["cost"] = inputCard["ink_cost"] if "ink_cost" in inputCard else int(parsedImageAndTextData["cost"].text, 10)
	if "quest_value" in inputCard:
		outputCard["lore"] = inputCard["quest_value"]
	for inputFieldName, outputFieldName in (("move_cost", "moveCost"), ("strength", "strength"), ("willpower", "willpower")):
		if inputFieldName in inputCard:
			outputCard[outputFieldName] = inputCard[inputFieldName]
		elif parsedImageAndTextData.get(outputFieldName, None) is not None:
			outputCard[outputFieldName] = int(parsedImageAndTextData[outputFieldName].text, 10)
	# Image URLs end with a checksum parameter, we don't need that
	if "image_urls" in inputCard:
		outputCard["images"] = {
			"full": _cleanUrl(inputCard["image_urls"][0]["url"]),
			"thumbnail": _cleanUrl(inputCard["image_urls"][1]["url"]),
		}
		if "foil_mask_url" in inputCard:
			outputCard["images"]["foilMask"] = _cleanUrl(inputCard["foil_mask_url"])
	else:
		outputCard["images"] = {"full": inputCard["imageUrl"]}
	# If the card is Enchanted or has an Enchanted equivalent, store that
	if enchantedNonEnchantedId:
		outputCard["nonEnchantedId" if outputCard["rarity"] == "Enchanted" else "enchantedId"] = enchantedNonEnchantedId
	# If the card is a promo card, store the non-promo ID
	# If the card has promo version, store the promo IDs
	if promoNonPromoId:
		outputCard["nonPromoId" if "/P" in inputCard["card_identifier"] else "promoIds"] = promoNonPromoId
	# Store the different parts of the card text, correcting some values if needed
	if parsedImageAndTextData["flavorText"] is not None:
		flavorText = correctText(parsedImageAndTextData["flavorText"].text)
		flavorText = correctPunctuation(flavorText)
		# Tesseract often sees the italic 'T' as an 'I', especially at the start of a word. Fix that
		if "I" in flavorText:
			flavorText = re.sub(r"(^|\W)I(?=[ehiow]\w)", r"\1T", flavorText)
		outputCard["flavorText"] = flavorText
	if parsedImageAndTextData["remainingText"] is not None:
		abilityText = correctText(parsedImageAndTextData["remainingText"].text)
		# TODO FIXME Song reminder text is at the top of a Song card, should probably not be listed in the 'abilities' list
		outputCard["abilities"]: List[str] = re.sub(r"(\.\)?\n)", r"\1\n", abilityText).split("\n\n")
	if parsedImageAndTextData["effectLabels"]:
		outputCard["effects"]: List[Dict[str, str]] = []
		for effectIndex in range(len(parsedImageAndTextData["effectLabels"])):
			outputCard["effects"].append({
				"name": parsedImageAndTextData["effectLabels"][effectIndex].text.replace("’", "'").replace("''", "'"),
				"text": correctText(parsedImageAndTextData["effectTexts"][effectIndex].text)
			})
	# Some cards have errata or clarifications, both in the 'additional_info' fields. Split those up
	if inputCard.get("additional_info", None):
		errata = []
		clarifications = []
		for infoEntry in inputCard["additional_info"]:
			# The text has multiple \r\n's as newlines, reduce that to just a single \n
			infoText: str = infoEntry["body"].rstrip().replace("\r", "").replace("\n\n", "\n")
			# The text uses unicode characters in some places, replace those with their simple equivalents
			infoText = infoText.replace("\u2019", "'").replace("\u2013", "-").replace("\u201c", "\"").replace("\u201d", "\"")
			# Sometimes they write cardnames as "basename- subtitle", add the space before the dash back in
			infoText = re.sub(r"(\w)- ", r"\1 - ", infoText)
			# The text uses {I} for ink and {S} for strength, replace those with our symbols
			infoText = infoText.format(I=ImageParser.INK_UNICODE, S=ImageParser.STRENGTH_UNICODE, L=ImageParser.LORE_UNICODE)
			if infoEntry["title"].startswith("Errata"):
				if " - " in infoEntry["title"]:
					# There's a suffix explaining what field the errata is about, prepend it to the text
					infoText = infoEntry["title"].split(" - ")[1] + "\n" + infoText
				errata.append(infoText)
			elif infoEntry["title"].startswith("FAQ") or infoEntry["title"].startswith("Keyword") or infoEntry["title"] == "Good to know":
				clarifications.append(infoText)
			else:
				_logger.error(f"Unknown 'additional_info' type '{infoEntry['title']}' in card {_createCardIdentifier(outputCard)}")
		if errata:
			outputCard["errata"] = errata
		if clarifications:
			outputCard["clarifications"] = clarifications
	# Determine subtypes and their order. Items and Actions have an empty subtypes list, ignore those
	if parsedImageAndTextData["subtypesText"] and parsedImageAndTextData["subtypesText"].text:
		subtypes: List[str] = parsedImageAndTextData["subtypesText"].text.split(f" {ImageParser.SEPARATOR_UNICODE} ")
		# Non-character cards have their main type as their (first) subtype, remove those
		if subtypes[0] == "Action" or subtypes[0] == "Item":
			subtypes.pop(0)
		# 'Seven Dwarves' is a subtype, but it might get split up into two types. Turn it back into one subtype
		if "Seven" in subtypes and "Dwarfs" in subtypes:
			subtypes.remove("Dwarfs")
			subtypes[subtypes.index("Seven")] = "Seven Dwarfs"
		if subtypes:
			outputCard["subtypes"] = subtypes
	# Card-specific corrections
	#  Since the fullText gets created as the last step, if there is a correction for it, save it for later
	fullTextCorrection = None
	if cardDataCorrections:
		for fieldName, correction in cardDataCorrections.items():
			if fieldName == "fullText":
				fullTextCorrection = correction
			elif isinstance(correction[0], bool):
				if outputCard[fieldName] == correction[1]:
					_logger.warning(f"Corrected value for boolean field '{fieldName}' is the same as the existing value '{outputCard[fieldName]}' for card {_createCardIdentifier(outputCard)}")
				else:
					_logger.info(f"Corrected boolean field '{fieldName}' in card {_createCardIdentifier(outputCard)} from {outputCard[fieldName]} to {correction}")
					outputCard[fieldName] = correction[1]
			elif len(correction) > 2:
				for correctionIndex in range(0, len(correction), 2):
					correctCardField(outputCard, fieldName, correction[correctionIndex], correction[correctionIndex+1])
			else:
				correctCardField(outputCard, fieldName, correction[0], correction[1])
	# Store keyword abilities. Some abilities have a number after them (Like Shift 5), store those too
	# For now assume that only Characters can have abilities, since they started adding f.i.
	#  the 'Support' ability to actions that temporarily grant Support to another character,
	#  which breaks the regex, and doesn't make too much sense, since the action itself doesn't have Support
	if outputCard["type"] == "Character" and "abilities" in outputCard:
		outputCard["keywordAbilities"] = []
		# Find the ability name at the start of a sentence, optionally followed by a number, and then followed by the opening bracket of the reminder text
		for abilityLine in outputCard["abilities"]:
			abilityMatch = re.search(fr"(^|\n)(\S+)( \+?\d)?(?= \()", abilityLine)
			if abilityMatch:
				outputCard["keywordAbilities"].append(abilityMatch.group(0).lstrip())
	# Reconstruct the full card text. Do that after storing the parts, so any corrections will be taken into account
	# Remove the newlines in the fields we use while we're at it, because we only needed those to reconstruct the fullText
	# TODO Some cards (Madam Mim - Fox, ID 262) have the abilities after the effect, think of a more elegant solution than the current regex hack in the corrections file
	fullTextSections = []
	if "abilities" in outputCard:
		fullTextSections.append("\n".join(outputCard["abilities"]))
		for abilityIndex in range(len(outputCard["abilities"])):
			outputCard["abilities"][abilityIndex] = outputCard["abilities"][abilityIndex].replace("\n", " ")
		# Sometimes reminder text gets split into multiple abilities while it shouldn't, so count the opening and closing brackets to fix this
		# Do this after building the fulltext, since we need the newlines for that
		for abilityLineIndex in range(len(outputCard["abilities"]) - 1, 0, -1):
			abilityLine = outputCard["abilities"][abilityLineIndex]
			_logger.debug(f"{abilityLineIndex=} {abilityLine=}")
			if abilityLine.count(")") > abilityLine.count("("):
				# Closing bracket got moved a line down, merge it with the previous line
				_logger.info(f"Merging accidentally-split ability line '{abilityLine}' with previous line '{outputCard['abilities'][abilityLineIndex - 1]}'")
				outputCard["abilities"][abilityLineIndex - 1] += " " + outputCard["abilities"].pop(abilityLineIndex)
	if "effects" in outputCard:
		for effect in outputCard["effects"]:
			fullTextSections.append(f"{effect['name']} {effect['text']}")
			effect["text"] = effect["text"].replace("\n", " ")
	outputCard["fullText"] = "\n".join(fullTextSections)
	if fullTextCorrection:
		correctCardField(outputCard, "fullText", fullTextCorrection[0], fullTextCorrection[1])
	if "story" in inputCard:
		outputCard["story"] = inputCard["story"]
	elif storyName:
		outputCard["story"] = storyName
	else:
		outputCard["story"] = "[unknown]"
	return outputCard

def _determineCardIdToStoryName(idsToParse: List[int] = None) -> Dict[int, str]:
	startTime = time.perf_counter()
	cardStorePath = os.path.join("downloads", "json", "carddata.en.json")
	if not os.path.isfile(cardStorePath):
		raise FileNotFoundError("The English carddata file does not exist, please run the 'download' action for English first")
	with open(cardStorePath, "r", encoding="utf-8") as cardstoreFile:
		cardstore = json.load(cardstoreFile)
	with open(os.path.join("output", "fromStories.json"), "r", encoding="utf-8") as fromStoriesFile:
		fromStories = json.load(fromStoriesFile)
	# The fromStories file is organised by story to make it easy to write and maintain
	# Reformat it so matching individual cards to a story is easier
	cardIdToStoryName: Dict[int, str] = {}
	cardNameToStoryName: Dict[str, str] = {}
	fieldMatchers: Dict[str, Dict[str, str]] = {}  # A dictionary with for each fieldname a dict of matchers and their matching story name
	for storyId, storyData in fromStories.items():
		storyName = storyData["displayNames"][GlobalConfig.language.code]
		if "matchingIds" in storyData:
			for cardId in storyData["matchingIds"]:
				cardIdToStoryName[cardId] = storyName
		if "matchingNames" in storyData:
			for name in storyData["matchingNames"]:
				cardNameToStoryName[name] = storyName
		if "matchingFields" in storyData:
			for fieldName, fieldMatch in storyData["matchingFields"].items():
				if fieldName not in fieldMatchers:
					fieldMatchers[fieldName] = {}
				elif fieldMatch in fieldMatchers[fieldName]:
					raise ValueError(f"Duplicate field matcher '{fieldMatch}' in '{fieldMatchers[fieldName][fieldMatch]}' and '{storyName}'")
				fieldMatchers[fieldName][fieldMatch] = storyName
	_logger.debug(f"Reorganized story data after {time.perf_counter() - startTime:.4f} seconds")
	# Now we can go through every card and try to match each to a story
	for cardtype, cardlist in cardstore["cards"].items():
		for card in cardlist:
			cardId = card["culture_invariant_id"]
			if idsToParse and cardId not in idsToParse:
				continue
			if cardId in cardIdToStoryName:
				# Card is already stored, by directly referencing its ID in the 'fromStories' file, so we don't need to do anything anymore
				continue
			if card["name"] in cardNameToStoryName:
				cardIdToStoryName[cardId] = cardNameToStoryName[card["name"]]
				continue
			# Go through each field matcher to see if it matches anything
			try:
				for fieldName, fieldData in fieldMatchers.items():
					if fieldName not in card:
						continue
					for fieldMatch, storyName in fieldData.items():
						if isinstance(card[fieldName], list):
							if fieldMatch in card[fieldName]:
								cardIdToStoryName[cardId] = storyName
								raise StopIteration()
						elif fieldMatch in card[fieldName] or re.search(fieldMatch, card[fieldName]):
							cardIdToStoryName[cardId] = storyName
							raise StopIteration()
			except StopIteration:
				pass
			else:
				try:
					# No match, try to see if any of the names occurs in some of the card's fields
					for name, storyName in cardNameToStoryName.items():
						nameRegex = re.compile(rf"(^|\W){name}(\W|$)")
						for fieldName in ("flavor_text", "rules_text", "name", "subtitle"):
							if fieldName in card and nameRegex.search(card[fieldName]):
								_logger.debug(f"Assuming {_createCardIdentifier(card)} is in story '{storyName}' based on '{name}' in the field '{fieldName}': {card[fieldName]!r}")
								cardIdToStoryName[cardId] = storyName
								raise StopIteration()
				except StopIteration:
					pass
				else:
					_logger.error(f"Unable to determine story ID of card {_createCardIdentifier(card)}")
					cardIdToStoryName[cardId] = "_unknown"
	_logger.debug(f"Finished determining cards' stories after {time.perf_counter() - startTime:.4f} seconds")
	return cardIdToStoryName

def _saveFile(outputFilePath: str, dictToSave: Dict, createZip: bool = True):
	with open(outputFilePath, "w", encoding="utf-8") as outputFile:
		json.dump(dictToSave, outputFile, indent=2)
	_createMd5ForFile(outputFilePath)
	# Create a zipped version of the same file
	if createZip:
		outputZipFilePath = outputFilePath + ".zip"
		with zipfile.ZipFile(outputZipFilePath, "w", compression=zipfile.ZIP_LZMA, strict_timestamps=False) as outputZipfile:
			outputZipfile.write(outputFilePath, os.path.basename(outputFilePath))
		_createMd5ForFile(outputZipFilePath)

def _createMd5ForFile(filePath: str):
	with open(filePath, "rb") as fileToHash, open(filePath + ".md5", "w", encoding="utf-8") as md5File:
		fileHash = hashlib.md5(fileToHash.read()).hexdigest()
		md5File.write(fileHash)
