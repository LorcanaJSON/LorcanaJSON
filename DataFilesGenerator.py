import datetime, hashlib, json, logging, os, re, time, zipfile
from typing import Dict, List, Union

import Language
from OCR import ImageParser

_logger = logging.getLogger("LorcanaJSON")
FORMAT_VERSION = "1.0.2"

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
			# For some reason it keeps reading the Strenght symbol as the Euro symbol
			cardLine = re.sub(r"€[^ ]?", ImageParser.STRENGTH_UNICODE, cardLine)
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
		# Correct common phrases with symbols
		if re.search(rf"pay \d ?[^{ImageParser.INK_UNICODE}]{{1,2}} less", cardLine):
			# Lore payment discounts
			cardLine = re.sub(rf"pay (\d) ?[^{ImageParser.INK_UNICODE}]{{1,2}} ?less", f"pay \\1 {ImageParser.INK_UNICODE} less", cardLine)
		# Fields with Errata corrections have 'ERRATA' in the text, possibly with a colon. Remove that
		if "ERRATA" in cardLine:
			cardLine = re.sub(" ?ERRATA:? ?", "", cardLine)
		# Correct reminder text
		if cardLine.startswith("Shift "):
			# Shift
			_logger.info("Correcting Shift reminder text")
			cardLine = re.sub(f" [^{ImageParser.INK_UNICODE}]{{1,2}} to play this on top", f" {ImageParser.INK_UNICODE} to play this on top", cardLine)
		elif re.match(r"^gets \+\d .{1,2}?\.?\)?$", cardLine):
			# Challenger, second line
			_logger.info("Correcting second line of Challenger reminder text")
			cardLine = re.sub(rf"gets \+(\d) [^{ImageParser.STRENGTH_UNICODE}]{{1,2}}?\.?\)", fr"gets +\1 {ImageParser.STRENGTH_UNICODE}.)", cardLine)
		elif re.match(r"\(A character with cost \d or more can .{1,2} to sing this( song for free)?", cardLine):
			# Song
			_logger.info("Correcting Song reminder text")
			cardLine = re.sub(f"can [^{ImageParser.EXERT_UNICODE}]{{1,2}} to sing this", f"can {ImageParser.EXERT_UNICODE} to sing this", cardLine)
		elif re.match("add their .{1,2} to another chosen character['’]s .{1,2} this", cardLine):
			# Support, full line (not sure why it sometimes doesn't get cut into two lines
			_logger.info("Correcting Support reminder text (both symobls on one line)")
			cardLine = re.sub(f"their [^{ImageParser.STRENGTH_UNICODE}]{{1,2}} to", f"their {ImageParser.STRENGTH_UNICODE} to", cardLine)
			cardLine = re.sub(f"character's [^{ImageParser.STRENGTH_UNICODE}]{{1,2}} this", f"character's {ImageParser.STRENGTH_UNICODE} this", cardLine)
		elif re.match("may add their .{1,2} to another chosen character[’']s", cardLine):
			# Support, first line if split
			_logger.info("Correcting first line of Support reminder text")
			cardLine = re.sub(f"their {ImageParser.STRENGTH_UNICODE}{{1,2}} to", f"their {ImageParser.STRENGTH_UNICODE} to", cardLine)
		elif re.match(rf"[^{ImageParser.STRENGTH_UNICODE}]{{1,2}} this turn\.?\)?", cardLine):
			# Support, second line if split
			_logger.info("Correcting second line of Support reminder text")
			cardLine = f"{ImageParser.STRENGTH_UNICODE} this turn.)"
		elif cardLine.startswith("Ward (Upponents "):
			_logger.info("Correcting 'Upponents' to 'Opponents'")
			cardLine = cardLine.replace("(Upponents", "(Opponents")
		if cardLine:
			correctedCardLines.append(cardLine)
		if originalCardLine != cardLine:
			_logger.info(f"Corrected card line from '{originalCardLine}' to '{cardLine}'")
	return "\n".join(correctedCardLines)

def correctCardField(card: Dict, fieldName: str, regexMatchString: str, correction: str) -> None:
	"""
	Correct card-specific mistakes in the fieldName field of the provided card
	:param card: The output card as parsed so far
	:param fieldName: The fieldname to correct
	:param regexMatchString: A regex that matches the card's mistake, this text will get replaced with the 'correction' string
	:param correction: The correction for the mistake matched by 'regexMatchString'
	"""
	if fieldName not in card:
		card[fieldName] = correction
	elif isinstance(card[fieldName], str):
		preCorrectedText = card[fieldName]
		card[fieldName] = re.sub(regexMatchString, correction, preCorrectedText, flags=re.DOTALL)
		if card[fieldName] == preCorrectedText:
			_logger.warning(f"Correcting field '{fieldName}' in card {_createCardIdentifier(card)} didn't change anything, value is still '{repr(preCorrectedText)}'")
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
	Create an identifier string for a parsed card, consisting of the full name and the ID
	:param card: The card dictionary
	:return: A string with the full card name and the card ID
	"""
	return f"'{card['fullName']}' (ID {card['id']})"

def createOutputFiles(language: Language.Language, onlyParseIds: Union[None, List[int]] = None, shouldShowImages: bool = False) -> None:
	startTime = time.perf_counter()
	imageFolder = os.path.join("downloads", "images", language.code)
	if not os.path.isdir(imageFolder):
		raise FileNotFoundError(f"Images folder for language '{language.code}' doesn't exist. Run the data downloader first")
	cardCatalogPath = os.path.join("downloads", "json", f"carddata.{language.code}.json")
	if not os.path.isfile(cardCatalogPath):
		raise FileNotFoundError(f"Card catalog for language '{language.code}' doesn't exist. Run the data downloader first")
	with open(cardCatalogPath, "r", encoding="utf-8") as inputFile:
		inputData = json.load(inputFile)

	correctionsFilePath = os.path.join("output", f"outputDataCorrections_{language.code}.json")
	if os.path.isfile(correctionsFilePath):
		with open(correctionsFilePath, "r", encoding="utf-8") as correctionsFile:
			# Convert all the ID keys to numbers as we load
			cardDataCorrections: Dict[int, Dict[str, List[str, str]]] = {int(k, 10): v for k, v in json.load(correctionsFile).items()}
	else:
		_logger.warning(f"No corrections file found for language '{language.code}', assuming no corrections are necessary")
		cardDataCorrections = {}

	# Enchanted-rarity cards are special versions of existing cards. Store their shared ID so we can add a linking field to both versions
	# There are only Character Enchanted cards for now, so only check those
	# We do this before parse-id-checks and other parsing, so we can add these IDs to cards that have Enchanted versions, even if they're not being parsed
	enchantedDeckbuildingIds = {}
	for card in inputData["cards"]["characters"]:
		if card["rarity"] == "ENCHANTED":
			enchantedDeckbuildingIds[card["deck_building_id"]] = card["culture_invariant_id"]
	# Now find their matching non-Enchanted cards, and store both IDs with a link to each other
	enchantedNonEnchantedIds = {}
	for card in inputData["cards"]["characters"]:
		if card["rarity"] != "ENCHANTED" and card["deck_building_id"] in enchantedDeckbuildingIds:
			nonEnchantedId = card["culture_invariant_id"]
			enchantedId = enchantedDeckbuildingIds[card["deck_building_id"]]
			enchantedNonEnchantedIds[nonEnchantedId] = enchantedId
			enchantedNonEnchantedIds[enchantedId] = nonEnchantedId
	del enchantedDeckbuildingIds

	# Get the cards we don't have to parse (if any) from the previous generated file
	fullCardList = []
	cardIdsStored = []
	outputFolder = os.path.join("output", "generated", language.code)
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
				del previousCardData
		else:
			_logger.warning("ID list provided but previously generated file doesn't exist. Generating all card data")

	# Parse the cards we need to parse
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
			try:
				outputCard = _parseSingleCard(inputCard, cardTypeText, imageFolder, enchantedNonEnchantedIds, cardDataCorrections, shouldShowImage=shouldShowImages)
				fullCardList.append(outputCard)
			except Exception as e:
				_logger.error(f"Exception {type(e)} occured while parsing card ID {inputCard['culture_invariant_id']}")
				raise e
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
	with open(os.path.join("output", f"baseSetData.{language.code}.json"), "r", encoding="utf-8") as baseSetDataFile:
		setsData = json.load(baseSetDataFile)
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

def _parseSingleCard(inputCard: Dict, cardType: str, imageFolder: str, enchantedNonEnchantedIds: Dict, cardDataCorrections: Dict, shouldShowImage: bool = False) -> Dict:
	outputCard: Dict[str, Union[str, int, List, Dict]] = {
		"artist": inputCard["author"].strip(),
		"baseName": inputCard["name"].strip().replace("’", "'"),
		"color": inputCard["magic_ink_color"].title(),
		"cost": inputCard["ink_cost"],
		"id": inputCard["culture_invariant_id"],
		"inkwell": inputCard["ink_convertible"],
		"number": int(re.search(r"(\d+)/\d+", inputCard["card_identifier"]).group(1), 10),
		"rarity": inputCard["rarity"].title(),
		"setNumber": inputCard["expansion_number"],
		"type": cardType,
	}
	# Set 'fullName' separately so it uses the corrected baseName
	outputCard["fullName"] = outputCard["baseName"]
	outputCard["simpleName"] = outputCard["fullName"]
	if "subtitle" in inputCard:
		outputCard["subtitle"] = inputCard["subtitle"].strip().replace("’", "'")
		outputCard["fullName"] += " - " + outputCard["subtitle"]
		outputCard["simpleName"] += " " + outputCard["subtitle"]
	# simpleName is the full name with special characters and the base-subtitle dash removed, for easier lookup. So remove the special characters
	outputCard["simpleName"] = re.sub(r"[!.?]", "", outputCard["simpleName"].lower()).replace("ā", "a")
	_logger.debug(f"Current card name is '{outputCard['fullName']}, ID {outputCard['id']}")
	if "quest_value" in inputCard:
		outputCard["lore"] = inputCard["quest_value"]
	if "strength" in inputCard:
		outputCard["strength"] = inputCard["strength"]
	if "willpower" in inputCard:
		outputCard["willpower"] = inputCard["willpower"]
	# Image URLs end with a checksum parameter, we don't need that
	outputCard["images"] = {
		"full": _cleanUrl(inputCard["image_urls"][0]["url"]),
		"thumbnail": _cleanUrl(inputCard["image_urls"][1]["url"]),
		"foilMask": _cleanUrl(inputCard["foil_mask_url"])
	}
	# If the card is Enchanted or has an Enchanted equivalent, store that
	if outputCard["id"] in enchantedNonEnchantedIds:
		outputCard["nonEnchantedId" if outputCard["rarity"] == "Enchanted" else "enchantedId"] = enchantedNonEnchantedIds[outputCard["id"]]
	# Store the different parts of the card text, correcting some values if needed
	parsedImageAndTextData = ImageParser.getImageAndTextDataFromImage(os.path.join(imageFolder, f"{outputCard['id']}.jpg"),
																	  hasCardText=inputCard["rules_text"] != "",
																	  hasFlavorText=inputCard["flavor_text"] != "",
																	  isEnchanted=outputCard["rarity"] == "Enchanted",
																	  showImage=shouldShowImage)
	if parsedImageAndTextData["flavorText"] is not None:
		flavorText = correctText(parsedImageAndTextData["flavorText"].text)
		if flavorText.count(".") > 2:
			_logger.info(f"Correcting weird ellipsis in flavor text of '{outputCard['fullName']}'")
			# Flavor text with ellipses gets parsed weird, with spaces between periods where they don't belong. Fix that
			flavorText = re.sub(r" ?\. ?\. ?\. ?", "...", flavorText)
		outputCard["flavorText"] = flavorText
	if parsedImageAndTextData["remainingText"] is not None:
		abilityText = correctText(parsedImageAndTextData["remainingText"].text)
		# TODO FIXME Song reminder text is at the top of a Song card, should probably not be listed in the 'abilities' list
		outputCard["abilities"]: List[str] = re.sub(r"(\.\)?\n)", r"\1\n", abilityText).split("\n\n")
		# Sometimes reminder text gets split while it shouldn't, so count the opening and closing brackets to fix this
		for abilityLineIndex in range(len(outputCard["abilities"]) - 1, 0, -1):
			abilityLine = outputCard["abilities"][abilityLineIndex]
			_logger.debug(f"{abilityLineIndex=} {abilityLine=}")
			if abilityLine.count(")") > abilityLine.count("("):
				# Closing bracket got moved a line down, merge it with the previous line
				_logger.info(f"Merging accidentally-split ability line '{abilityLine}' with previous line '{outputCard['abilities'][abilityLineIndex - 1]}'")
				outputCard["abilities"][abilityLineIndex - 1] += " " + outputCard["abilities"].pop(abilityLineIndex)
	if parsedImageAndTextData["effectLabels"]:
		outputCard["effects"]: List[Dict[str, str]] = []
		for effectIndex in range(len(parsedImageAndTextData["effectLabels"])):
			effectLabel = parsedImageAndTextData["effectLabels"][effectIndex].text
			effectText = parsedImageAndTextData["effectTexts"][effectIndex].text
			outputCard["effects"].append({
				"name": effectLabel.replace("’", "'"),
				"text": correctText(effectText)
			})
	# Some cards have errata or clarifications, both in the 'additional_info' fields. Split those up
	if inputCard.get("additional_info", None):
		errata = []
		clarifications = []
		for infoEntry in inputCard["additional_info"]:
			# The text has \r\n as newlines, reduce that to just \n
			infoText: str = infoEntry["body"].replace("\r", "")
			# The text uses {I} for ink and {S} for strength, replace those with our symbols
			infoText = infoText.format(I=ImageParser.INK_UNICODE, S=ImageParser.STRENGTH_UNICODE, L=ImageParser.LORE_UNICODE)
			if infoEntry["title"].startswith("Errata"):
				if " - " in infoEntry["title"]:
					# There's a suffix explaining what field the errata is about, prepend it to the text
					infoText = infoEntry["title"].split(" - ")[1] + "\n" + infoText
				errata.append(infoText)
			elif infoEntry["title"].startswith("FAQ") or infoEntry["title"].startswith("Keyword"):
				clarifications.append(infoText)
			else:
				_logger.error(f"Unknown 'additional_info' type '{infoEntry['title']}' in card {_createCardIdentifier(outputCard)}")
		if errata:
			outputCard["errata"] = errata
		if clarifications:
			outputCard["clarifications"] = clarifications
	# Determine subtypes and their order. Items and Actions have an empty subtypes list, ignore those
	if inputCard.get("subtypes", None) and parsedImageAndTextData["subtypesText"]:
		_logger.debug(f"({_createCardIdentifier(outputCard)}) {inputCard['subtypes']=}, {parsedImageAndTextData['subtypesText'].text=}")
		subtypesText = parsedImageAndTextData["subtypesText"].text
		subtypeNameToIndex = {}
		for subtype in inputCard["subtypes"]:
			matchIndex = subtypesText.find(subtype)
			if matchIndex == -1:
				_logger.warning(f"Couldn't find subtype '{subtype}' in parsed subtype string '{subtypesText}'")
			else:
				subtypeNameToIndex[subtype] = matchIndex
		outputCard["subtypes"]: List[str] = inputCard["subtypes"]
		outputCard["subtypes"].sort(key=lambda subtypeKey: subtypeNameToIndex[subtypeKey])
	# Card-specific corrections
	#  Since the fullText gets created as the last step, if there is a correction for it, save it for later
	fullTextCorrection = None
	if outputCard["id"] in cardDataCorrections:
		for fieldName, correction in cardDataCorrections[outputCard["id"]].items():
			if fieldName == "fullText":
				fullTextCorrection = correction
			elif isinstance(correction[0], bool):
				if outputCard[fieldName] == correction[1]:
					_logger.warning(f"Corrected value for boolean field '{fieldName}' is the same as the existing value '{outputCard[fieldName]}' for card {_createCardIdentifier(outputCard)}")
				else:
					_logger.info(f"Corrected boolean field '{fieldName}' in card {_createCardIdentifier(outputCard)} from {outputCard[fieldName]} to {correction}")
					outputCard[fieldName] = correction
			else:
				correctCardField(outputCard, fieldName, correction[0], correction[1])
		# Remove the correction, so we can check at the end if we used all the corrections
		del cardDataCorrections[outputCard["id"]]
	# Store keyword abilities. Some abilities have a number after them (Like Shift 5), store those too
	# For now assume that only Characters can have abilities, since they started adding f.i.
	#  the 'Support' ability to actions that temporarily grant Support to another character,
	#  which breaks the regex, and doesn't make too much sense, since the action itself doesn't have Support
	if outputCard["type"] == "Character" and inputCard.get("abilities", None) and "abilities" in outputCard:
		outputCard["keywordAbilities"] = []
		_logger.debug(f"{inputCard['abilities']=}, {outputCard['abilities']=}")
		for ability in inputCard["abilities"]:
			# Find the ability name at the start of a sentence, optionally followed by a number, and then followed by the opening bracket of the reminder text
			for abilityLine in outputCard["abilities"]:
				abilityMatch = re.search(fr"(^|\n){ability}( \+?\d)?(?= \()", abilityLine)
				if abilityMatch:
					break
			else:
				abilityText = "\n".join(outputCard["abilities"])
				raise ValueError(f"Unable to match ability '{ability}' in ability text {abilityText!r} for card {_createCardIdentifier(outputCard)}")
			outputCard["keywordAbilities"].append(abilityMatch.group(0).lstrip())
		# Sort the abilities by card order
		outputCard["keywordAbilities"].sort(key=lambda ability: inputCard["rules_text"].index(ability))
	# Reconstruct the full card text. Do that after storing the parts, so any corrections will be taken into account
	# Remove the newlines in the fields we use while we're at it, because we only needed those to reconstruct the fullText
	# TODO Some cards (Madam Mim - Fox, ID 262) have the abilities after the effect, think of a more elegant solution than the current regex hack in the corrections file
	fullTextSections = []
	if "abilities" in outputCard:
		fullTextSections.append("\n".join(outputCard["abilities"]))
		for abilityIndex in range(len(outputCard["abilities"])):
			outputCard["abilities"][abilityIndex] = outputCard["abilities"][abilityIndex].replace("\n", " ")
	if "effects" in outputCard:
		for effect in outputCard["effects"]:
			fullTextSections.append(f"{effect['name']} {effect['text']}")
			effect["text"] = effect["text"].replace("\n", " ")
	outputCard["fullText"] = "\n".join(fullTextSections)
	if fullTextCorrection:
		correctCardField(outputCard, "fullText", fullTextCorrection[0], fullTextCorrection[1])
	return outputCard

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
