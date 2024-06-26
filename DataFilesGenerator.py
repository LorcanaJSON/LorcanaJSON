import datetime, hashlib, json, logging, multiprocessing.pool, os, re, threading, time, zipfile
from typing import Dict, List, Union

import GlobalConfig, Language
from OCR import ImageParser
from output.StoryParser import StoryParser


_logger = logging.getLogger("LorcanaJSON")
FORMAT_VERSION = "1.3.1"
_CARD_CODE_LOOKUP = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
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
		if len(cardLine) < 2:
			_logger.debug(f"Ignoring line {cardLine!r} during correction because it's too short")
			continue
		originalCardLine = cardLine
		## First simple typos ##
		# Simplify quote mark if it's used in a contraction
		cardLine = re.sub(r"(?<=\w)’(?=\w)", "'", cardLine)
		# There's usually an ink symbol between a number and a dash
		cardLine = re.sub(r"(^| )(\d) ?[0OQ©]?( ?[-—]|,)", fr"\1\2 {ImageParser.INK_UNICODE}\3", cardLine)
		# For some reason it keeps reading the Strength symbol as the Euro symbol
		cardLine = re.sub(r"€[^ .]?", ImageParser.STRENGTH_UNICODE, cardLine)
		# Normally a closing quote mark should be preceded by a period, except mid-sentence
		cardLine = re.sub(r"([^.,'!?’])”(?!,| \w)", "\\1.”", cardLine)
		# An opening bracket shouldn't have a space after it
		cardLine = cardLine.replace("( ", "(")
		if re.search(r"[”’)]\s.$", cardLine):
			# Sometimes an extra character gets added after the closing quote mark or bracket from an inksplotch, remove that
			cardLine = cardLine[:-2]
		# Make sure there's a period before a closing bracket
		cardLine = re.sub(r"([^.,'!?’])\)", r"\1.)", cardLine)
		# Numbers followed by a comma generally need an Ink symbol inbetween
		cardLine = re.sub(r"\b(\d) ,", fr"\1 {ImageParser.INK_UNICODE},", cardLine)
		# 'Illuminary' and 'Illumineer(s)' often gets read as starting with three l's, instead of an I and two l's
		cardLine = cardLine.replace("lllumin", "Illumin")
		# The 'exert' symbol often gets mistaken for a @ or G, correct that
		cardLine = re.sub(r"^[(@G©]{1,2}([ ,])", fr"{ImageParser.EXERT_UNICODE}\1", cardLine)
		if re.search(r" [‘;]$", cardLine):
			# Strip erroneously detected characters from the end
			cardLine = cardLine[:-2]
		# The Lore symbol often gets mistaken for a 4, correct hat
		cardLine = re.sub(r"(\d) 4", fr"\1 {ImageParser.LORE_UNICODE}", cardLine)
		if re.match(r"[-+»] \w{2,} \w+", cardLine):
			# Assume this is a list, replace the start with the official separator
			cardLine = ImageParser.SEPARATOR_UNICODE + cardLine[1:]
		# A 7 often gets mistaken for a /, correct that
		cardLine = cardLine.replace(" / ", " 7 ")
		cardLine = re.sub(f"{ImageParser.INK_UNICODE}([-—])", fr"{ImageParser.INK_UNICODE} \1", cardLine)
		# Negative numbers are always followed by a strength symbol, correct that
		cardLine = re.sub(fr"(?<= )(-\d) [^{ImageParser.STRENGTH_UNICODE}{ImageParser.LORE_UNICODE}a-z]", fr"\1 {ImageParser.STRENGTH_UNICODE}", cardLine)

		if GlobalConfig.language == Language.ENGLISH:
			if re.match("[‘`']Shift ", cardLine):
				_logger.info("Removing erroneous character at the start of " + cardLine)
				cardLine = cardLine[1:]
			elif cardLine.startswith("‘"):
				cardLine = "“" + cardLine[1:]
			cardLine = cardLine.replace("1lore", "1 lore")
			# Somehow it reads 'Bodyquard' with a 'q' instead of or in addition to a 'g' a lot...
			cardLine = re.sub("Bodyqg?uard", "Bodyguard", cardLine)
			cardLine = re.sub(r"\bIhe\b", "The", cardLine)
			cardLine = cardLine.replace("|", "I")
			cardLine = cardLine.replace("“l ", "“I ")
			if cardLine.endswith("of i"):
				# The 'Floodborn' inksplashes sometimes confuse the reader into imagining another 'i' at the end of some reminder text, remove that
				cardLine = cardLine.rstrip(" i")
			cardLine = cardLine.replace(" ‘em ", " 'em ")
			# Correct some fancy qoute marks at the end of some plural possessives. This is needed on a case-by-case basis, otherwise too much text is changed
			cardLine = re.sub(r"teammates’( |$)", r"teammates'\1", cardLine)
			cardLine = re.sub(r"players’( |$)", r"players'\1", cardLine)
			cardLine = re.sub(r"opponents’( |$)", r"opponents'\1", cardLine)
			## Correct common phrases with symbols ##
			# Lore payment discounts
			cardLine, changeCount = re.subn(rf"pay (\d) ?[^{ImageParser.INK_UNICODE}]{{1,2}}( |$)", f"pay \\1 {ImageParser.INK_UNICODE}\\2", cardLine)
			if changeCount > 0:
				_logger.info("Correcting lore payment text")
			# Fields with Errata corrections have 'ERRATA' in the text, possibly with a colon. Remove that
			cardLine = re.sub(" ?ERRATA:? ?", "", cardLine)
			## Correct reminder text ##
			# Challenger, second line
			cardLine, changeCount = re.subn(rf"gets \+(\d) [^{ImageParser.STRENGTH_UNICODE}]{{1,2}}?\.?\)", fr"gets +\1 {ImageParser.STRENGTH_UNICODE}.)", cardLine)
			if changeCount > 0:
				_logger.info("Correcting second line of Challenger reminder text")
			# Song
			cardLine, changeCount = re.subn(f"can [^{ImageParser.EXERT_UNICODE}]{{1,2}} to sing this", f"can {ImageParser.EXERT_UNICODE} to sing this", cardLine)
			if changeCount > 0:
				_logger.info("Correcting Song reminder text")
			# Support, full line (not sure why it sometimes doesn't get cut into two lines
			if re.match("add their .{1,2} to another chosen character['’]s .{1,2} this", cardLine):
				cardLine, changeCount = re.subn(f"their [^{ImageParser.STRENGTH_UNICODE}]{{1,2}} to", f"their {ImageParser.STRENGTH_UNICODE} to", cardLine)
				cardLine, changeCount2 = re.subn(f"character's [^{ImageParser.STRENGTH_UNICODE}]{{1,2}} this", f"character's {ImageParser.STRENGTH_UNICODE} this", cardLine)
				if changeCount > 0 or changeCount2 > 0:
					_logger.info("Correcting Support reminder text (both symobls on one line)")
			# Support, first line if split
			cardLine, changeCount = re.subn(f"^their [^{ImageParser.STRENGTH_UNICODE}]{{1,2}} to", f"their {ImageParser.STRENGTH_UNICODE} to", cardLine)
			if changeCount > 0:
				_logger.info("Correcting first line of Support reminder text")
			# Support, second line if split
			cardLine, changeCount = re.subn(rf"^[^{ImageParser.STRENGTH_UNICODE}]{{1,2}} this turn\.?\)?", f"{ImageParser.STRENGTH_UNICODE} this turn.)", cardLine)
			if changeCount > 0:
				_logger.info("Correcting second line of Support reminder text")
			cardLine = cardLine.replace("(Upponents", "(Opponents")
			cardLine = re.sub(r"reduced by [lI]\.", "reduced by 1.", cardLine)
		elif GlobalConfig.language == Language.FRENCH:
			# Correct payment text
			cardLine = re.sub(r"\bpayer (\d+) (?:\W|O|Ô|Q) pour\b", f"payer \\1 {ImageParser.INK_UNICODE} pour", cardLine)
			# Correct support reminder text
			cardLine = re.sub(r"(?<=ajouter sa )\W+(?= à celle)", ImageParser.STRENGTH_UNICODE, cardLine)
			# Cost discount text
			cardLine = re.sub(fr"(coûte(?:nt)? )(\d+) [^{ImageParser.INK_UNICODE} ou]+", fr"\1\2 {ImageParser.INK_UNICODE}", cardLine)
			# Song card reminder text
			cardLine = re.sub(fr"Vous pouvez [^ {ImageParser.EXERT_UNICODE}]+ un(e carte)? personnage coûtant", f"Vous pouvez {ImageParser.EXERT_UNICODE} un\\1 personnage coûtant", cardLine)
			# 'Sing Together' reminder text
			cardLine = re.sub(fr"\(Vous pouvez [^ {ImageParser.EXERT_UNICODE}]+ n'importe quel", f"(Vous pouvez {ImageParser.EXERT_UNICODE} n'importe quel", cardLine)
			# Fix punctuation by turning multiple periods into an ellipsis character, and correct ellipsis preceded or followed by periods
			cardLine = re.sub(r"…?\.{2,}…?", "…", cardLine)
			# Ellipsis get misread as periods often, try to correct that
			# Try to recognize it by the first letter afterwards not being capitalized
			cardLine = re.sub(r"\.+ ([a-z])", r"… \1", cardLine)
			cardLine = re.sub(r"^‘", "“", cardLine)
			# "Il" often gets misread as "I!"
			cardLine = re.sub("(?<![A-Z])[I|/]!", "Il", cardLine)
			# French always has a space before punctuation marks
			cardLine = re.sub(r"(\S)!", r"\1 !", cardLine)
			cardLine = re.sub(r"!(\w)", r"! \1", cardLine)
			cardLine = cardLine.replace("//", "Il")
			cardLine = re.sub(r"(?<=\(Lorsqu'il défie, ce personnage gagne )\+(\d) .\.", fr"+\1 {ImageParser.STRENGTH_UNICODE}.", cardLine)
			# Fix second line of 'Challenger'/'Offensif' reminder text
			cardLine = re.sub(r"^\+(\d) ?[^.]{0,2}\.\)$", fr"+\1 {ImageParser.STRENGTH_UNICODE}.)", cardLine)
			# Misc common mistakes
			cardLine = cardLine.replace("||", "Il")
			cardLine = cardLine.replace("Ily", "Il y")
			cardLine = re.sub(r"\bCa\b", "Ça", cardLine)
			cardLine = re.sub(r"\bca\b", "ça", cardLine)
			cardLine = cardLine.replace("personhage", "personnage")

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
		correctedText = re.sub(r"([\xa0 ]?\.[\xa0 ]?){3}", "..." if GlobalConfig.language == Language.ENGLISH else "…", correctedText)
	if ".…" in correctedText:
		correctedText = re.sub(r"\.+…", "…", correctedText)
	correctedText = correctedText.rstrip(" -_")
	correctedText = correctedText.replace("““", "“")
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
		if regexMatchString is not None:
			_logger.warning(f"Trying to correct field '{fieldName}' in card {_createCardIdentifier(card)} from '{regexMatchString}' to '{correction}' but the field does not exist. Set the match string to 'null' if you want to add a field")
		else:
			card[fieldName] = correction
	elif regexMatchString is None:
		if correction is None:
			_logger.info(f"Removing field '{fieldName}' (value {card[fieldName]!r}) from card {_createCardIdentifier(card)}")
			del card[fieldName]
		elif fieldName in card:
			_logger.warning(f"Trying to add field '{fieldName}' to card {_createCardIdentifier(card)}, but that field already exists (value '{card[fieldName]!r}")
	elif isinstance(card[fieldName], str):
		preCorrectedText = card[fieldName]
		card[fieldName] = re.sub(regexMatchString, correction, preCorrectedText, flags=re.DOTALL)
		if card[fieldName] == preCorrectedText:
			_logger.warning(f"Correcting field '{fieldName}' in card {_createCardIdentifier(card)} didn't change anything, value is still {preCorrectedText!r}")
		else:
			_logger.info(f"Corrected field '{fieldName}' from {preCorrectedText!r} to {card[fieldName]!r} for card {_createCardIdentifier(card)}")
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
							_logger.warning(f"Correcting index {fieldIndex} of field '{fieldName}' in card {_createCardIdentifier(card)} didn't change anything, value is still '{preCorrectedText!r}'")
						else:
							_logger.info(f"Corrected index {fieldIndex} of field '{fieldName}' from {preCorrectedText!r} to {fieldEntry[fieldKey]!r} for card {_createCardIdentifier(card)}")
		elif isinstance(card[fieldName][0], str):
			for fieldIndex, fieldValue in enumerate(card[fieldName]):
				match = re.search(regexMatchString, fieldValue, flags=re.DOTALL)
				if match:
					matchFound = True
					preCorrectedText = fieldValue
					card[fieldName][fieldIndex] = re.sub(regexMatchString, correction, fieldValue, flags=re.DOTALL)
					if card[fieldName][fieldIndex] == preCorrectedText:
						_logger.warning(f"Correcting index {fieldIndex} of field '{fieldName}' in card {_createCardIdentifier(card)} didn't change anything")
					else:
						_logger.info(f"Corrected index {fieldIndex} of field '{fieldName}' from {preCorrectedText!r} to {card[fieldName][fieldIndex]!r} for card {_createCardIdentifier(card)}")
		else:
			_logger.error(f"Unhandled type of list entries ({type(card[fieldName][0])}) in card {_createCardIdentifier(card)}")
		if not matchFound:
			_logger.warning(f"Correction regex '{regexMatchString}' for field '{fieldName}' in card {_createCardIdentifier(card)} didn't match any of the entries in that field")
	elif isinstance(card[fieldName], int):
		if card[fieldName] != regexMatchString:
			_logger.warning(f"Expected value of field '{fieldName}' in card {_createCardIdentifier(card)} is {regexMatchString}, but actual value is {card[fieldName]}, skipping correction")
		else:
			_logger.info(f"Corrected numerical value of field '{fieldName}' in card {_createCardIdentifier(card)} from {card[fieldName]} to {correction}")
			card[fieldName] = correction
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

	with open(os.path.join("output", "outputDataCorrections.json"), "r", encoding="utf-8") as correctionsFile:
		cardDataCorrections: Dict[int, Dict[str, List[str, str]]] = {int(k, 10): v for k, v in json.load(correctionsFile).items()}
	correctionsFilePath = os.path.join("output", f"outputDataCorrections_{GlobalConfig.language.code}.json")
	if os.path.isfile(correctionsFilePath):
		with open(correctionsFilePath, "r", encoding="utf-8") as correctionsFile:
			# Convert all the ID keys to numbers as we load
			for cardId, corrections in json.load(correctionsFile).items():
				cardId = int(cardId, 10)
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
							if card["id"] in enchantedNonEnchantedIds and "nonEnchantedId" not in card and "enchantedId" not in card:
								card["nonEnchantedId" if card["rarity"] == Language.TRANSLATIONS[GlobalConfig.language]["ENCHANTED"] else "enchantedId"] = enchantedNonEnchantedIds[card["id"]]
							if card["id"] in promoNonPromoIds and "promoIds" not in card and "nonPromoId" not in card:
								promoResult = promoNonPromoIds[card["id"]]
								# For non-promo cards it stores a list of promo IDs, for promo cards it stores a single non-promo ID
								card["promoIds" if isinstance(promoResult, list) else "nonPromoId"] = promoResult
				del previousCardData
		else:
			_logger.warning("ID list provided but previously generated file doesn't exist. Generating all card data")

	def initThread():
		_threadingLocalStorage.imageParser = ImageParser.ImageParser()

	threadCount = GlobalConfig.threadCount
	if not threadCount:
		# Only use half the available cores for threads, because we're also IO- and GIL-bound, so more threads would just slow things down
		threadCount = max(1, os.cpu_count() // 2)
	_logger.debug(f"Using {threadCount:,} threads for parsing the cards")

	# Parse the cards we need to parse
	languageCodeToCheck = GlobalConfig.language.code.upper()
	cardToStoryParser = StoryParser()
	with multiprocessing.pool.ThreadPool(threadCount, initializer=initThread) as pool:
		results = []
		for cardType, inputCardlist in inputData["cards"].items():
			cardTypeText = cardType[:-1].title()  # 'cardType' is plural ('characters', 'items', etc), make it singular
			cardTypeText = Language.TRANSLATIONS[GlobalConfig.language][cardTypeText]
			for inputCardIndex in range(len(inputCardlist)):
				inputCard = inputCardlist.pop()
				cardId = inputCard["culture_invariant_id"]
				if cardId in cardIdsStored:
					_logger.debug(f"Skipping parsing card with ID {inputCard['culture_invariant_id']} since it's already in the card list")
					continue
				elif languageCodeToCheck not in inputCard["card_identifier"]:
					_logger.debug(f"Skipping card with ID {inputCard['culture_invariant_id']} because it's not in the requested language")
					continue
				elif onlyParseIds and cardId not in onlyParseIds:
					_logger.error(f"Card ID {cardId} is not in the ID parse list, but it's also not in the previous dataset. Skipping parsing for now, but this results in incomplete datafiles, so it's strongly recommended to rerun with this card ID included")
					continue
				try:
					results.append(pool.apply_async(_parseSingleCard, (inputCard, cardTypeText, imageFolder, enchantedNonEnchantedIds.get(cardId, None), promoNonPromoIds.get(cardId, None), variantsDeckBuildingIds.get(inputCard["deck_building_id"]),
												  cardDataCorrections.pop(cardId, None), cardToStoryParser, False, shouldShowImages)))
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
															   cardDataCorrections.pop(cardId, None), cardToStoryParser, True, shouldShowImages)))
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
	metaDataDict = {"formatVersion": FORMAT_VERSION, "generatedOn": datetime.datetime.utcnow().isoformat(), "language": GlobalConfig.language.code}
	outputDict = {"metadata": metaDataDict}

	# Add set data
	with open(os.path.join("output", f"baseSetData.json"), "r", encoding="utf-8") as baseSetDataFile:
		setsData = json.load(baseSetDataFile)
		for setCode in setsData:
			# Get just the current language's set names
			setsData[setCode]["name"] = setsData[setCode].pop("names")[GlobalConfig.language.code]
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
	for setCode, setdata in setsData.items():
		# Add setcode to the set file, so it's easier to find. 'allCards' doesn't need it, since it's already the dictionary key there
		setdata["code"] = setCode
		setdata["metadata"] = metaDataDict
		setdata["cards"] = []
	for card in outputDict["cards"]:
		# Remove the setNumber, if any, and the setCode, since those are clear from the setfile the card is in
		card.pop("setNumber", None)
		setId = card.pop("setCode")
		setsData[setId]["cards"].append(card)
	for setId, setData in setsData.items():
		if len(setData["cards"]) == 0:
			_logger.warning(f"No cards found for set '{setId}', not creating data file for it")
			continue
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
					 cardDataCorrections: Dict, storyParser: StoryParser, isExternalReveal: bool, shouldShowImage: bool = False) -> Dict:
	# Store some default values
	outputCard: Dict[str, Union[str, int, List, Dict]] = {
		"color": Language.TRANSLATIONS[GlobalConfig.language][inputCard["magic_ink_colors"][0]] if inputCard["magic_ink_colors"] else "",
		"id": inputCard["culture_invariant_id"],
		"inkwell": inputCard["ink_convertible"],
		"rarity": Language.TRANSLATIONS[GlobalConfig.language][inputCard["rarity"]],
		"type": cardType
	}
	if isExternalReveal:
		outputCard["isExternalReveal"] = True

	# When building a deck in the official app, it gets saves as a string. This string starts with a '2', and then each card gets a two-character code based on the card's ID
	# This card code is the card ID in base 62, using 0-9, a-z, and then A-Z for individual digits
	cardCodeDigits = divmod(outputCard["id"], 62)
	outputCard["code"] = _CARD_CODE_LOOKUP[cardCodeDigits[0]] + _CARD_CODE_LOOKUP[cardCodeDigits[1]]

	# Get required data by parsing the card image
	imagePath = os.path.join(imageFolder, f"{outputCard['id']}.jpg")
	if not os.path.isfile(imagePath):
		imagePath = os.path.join(imageFolder, f"{outputCard['id']}.png")
	if not os.path.isfile(imagePath):
		raise ValueError(f"Unable to find image for card ID {outputCard['id']}")
	isPromoCard: Union[None, bool] = None
	if "card_identifier" in inputCard:
		isPromoCard = re.match(r"^\d+/P\d", inputCard["card_identifier"]) is not None
	parsedImageAndTextData = _threadingLocalStorage.imageParser.getImageAndTextDataFromImage(imagePath,
																	  parseFully=isExternalReveal,
																	  includeIdentifier=True if isPromoCard is None else isPromoCard,
																	  isLocation=cardType == Language.TRANSLATIONS[GlobalConfig.language]["Location"],
																	  hasCardText=inputCard["rules_text"] != "" if "rules_text" in inputCard else None,
																	  hasFlavorText=inputCard["flavor_text"] != "" if "flavor_text" in inputCard else None,
																	  isEnchanted=outputCard["rarity"] == Language.TRANSLATIONS[GlobalConfig.language]["ENCHANTED"] or inputCard.get("foil_type", None) == "Satin",  # Disney100 cards need Enchanted parsing, foil_type seems best way to determine Disney100
																	  isQuest="Q" in inputCard["card_identifier"] if "card_identifier" in inputCard else None,
																	  showImage=shouldShowImage)

	# The card identifier in non-promo cards is mostly correct in the input card,
	# For promo cards, get the text from the image, since it can differ quite a bit
	if "card_identifier" in inputCard and isPromoCard is not True:
		outputCard["fullIdentifier"] = inputCard["card_identifier"].replace(" ", f" {ImageParser.SEPARATOR_UNICODE} ")
	else:
		outputCard["fullIdentifier"] = re.sub(fr" ?\W (?!$)", f" {ImageParser.SEPARATOR_UNICODE} ", parsedImageAndTextData["identifier"].text)
		outputCard["fullIdentifier"] = outputCard["fullIdentifier"].replace("I", "/").replace("1P ", "/P ")
		outputCard["fullIdentifier"] = re.sub(fr" ?[-+] ?", f" {ImageParser.SEPARATOR_UNICODE} ", outputCard["fullIdentifier"])

	# Get the set and card numbers from the identifier
	# Use the input card's identifier instead of the output card's, because the former's layout is consistent, while the latter's isn't (mainly in Set 1 promos)
	cardIdentifierMatch = re.match(r"^(\d+)([a-z])?/P?[0-9]+ .+ (Q?\d+)$", inputCard["card_identifier"])
	if not cardIdentifierMatch:
		raise ValueError(f"Unable to parse card and set numbers from card identifier '{outputCard['fullIdentifier']}' in card ID {outputCard['id']}")
	outputCard["number"] = int(cardIdentifierMatch.group(1), 10)
	if cardIdentifierMatch.group(2):
		outputCard["variant"] = cardIdentifierMatch.group(2)
		if variantIds:
			outputCard["variantIds"] = [variantId for variantId in variantIds if variantId != outputCard["id"]]
	outputCard["setCode"] = cardIdentifierMatch.group(3)
	if "Q" not in outputCard["setCode"]:
		# Quests don't have a set number, just a set code
		outputCard["setNumber"] = int(outputCard["setCode"], 10)

	# Always get the artist from the parsed data, since in the input data it often only lists the first artist when there's multiple, so it's not reliable
	outputCard["artist"] = parsedImageAndTextData["artist"].text.replace(" I ", " / ")
	if outputCard["artist"].startswith("Illus. ") or outputCard["artist"].startswith(". "):
		outputCard["artist"] = outputCard["artist"].split(" ", 1)[1]
	if outputCard["artist"].startswith("l") or outputCard["artist"].startswith("["):
		outputCard["artist"] = "I" + outputCard["artist"][1:]
	if re.search(" [a-z]$", outputCard["artist"]):
		outputCard["artist"] = outputCard["artist"].rsplit(" ", 1)[0]
	if outputCard["artist"].startswith("lan "):
		outputCard["artist"] = re.sub("^lan ", "Ian ", outputCard["artist"])
	if "Hadijie" in outputCard["artist"]:
		outputCard["artist"] = outputCard["artist"].replace("Hadijie", "Hadjie")
	elif "Higgman-Sund" in outputCard["artist"]:
		outputCard["artist"] = outputCard["artist"].replace("Higgman-Sund", "Häggman-Sund")
	elif re.match("noc[^4]urne", outputCard["artist"]):
		outputCard["artist"] = "noc4urne"
	elif "Nquyen" in outputCard["artist"]:
		outputCard["artist"] = outputCard["artist"].replace("Nquyen", "Nguyen")
	elif "Toziim" in outputCard["artist"] or "Tôzüm" in outputCard["artist"]:
		outputCard["artist"] = re.sub(r"\bT\w+z\w+m\b", "Tözüm", outputCard["artist"])
	if "“" in outputCard["artist"]:
		# Simplify quotemarks
		outputCard["artist"] = outputCard["artist"].replace("“", "\"").replace("”", "\"")

	outputCard["baseName"] = correctPunctuation(inputCard["name"].strip() if "name" in inputCard else parsedImageAndTextData["baseName"].text).replace("’", "'").replace("''", "'")
	if outputCard["baseName"] == "Balais Magiques":
		# This name is inconsistent, sometimes it has a capital 'M', sometimes a lowercase 'm'
		# Comparing with capitalization of other cards, this should be a lowercase 'm'
		outputCard["baseName"] = outputCard["baseName"].replace("M", "m")
	elif outputCard["baseName"].isupper():
		# Some names have capitals in the middle, correct those
		if cardType == Language.TRANSLATIONS[GlobalConfig.language]["Character"]:
			if outputCard["baseName"] == "HEIHEI" and GlobalConfig.language == Language.ENGLISH:
				outputCard["baseName"] = "HeiHei"
			elif outputCard["baseName"] == "LEFOU":
				outputCard["baseName"] = "LeFou"
			else:
				outputCard["baseName"] = _toTitleCase(outputCard["baseName"])
		elif GlobalConfig.language == Language.FRENCH:
			# French titlecase rules are complicated, just capitalize the first letter for now
			outputCard["baseName"] = outputCard["baseName"][0] + outputCard["baseName"][1:].lower()
		else:
			outputCard["baseName"] = _toTitleCase(outputCard["baseName"])
	outputCard["fullName"] = outputCard["baseName"]
	outputCard["simpleName"] = outputCard["fullName"]
	if "subtitle" in inputCard or parsedImageAndTextData.get("subtitle", None) is not None:
		outputCard["subtitle"] = (inputCard["subtitle"].strip() if "subtitle" in inputCard else parsedImageAndTextData["subtitle"].text).replace("’", "'")
		outputCard["fullName"] += " - " + outputCard["subtitle"]
		outputCard["simpleName"] += " " + outputCard["subtitle"]
	# simpleName is the full name with special characters and the base-subtitle dash removed, for easier lookup. So remove the special characters
	outputCard["simpleName"] = (re.sub(r"[!.,…?“”\"]", "", outputCard["simpleName"].lower()).rstrip()
								.replace("ā", "a")
								.replace("é", "e"))
	if GlobalConfig.language == Language.FRENCH:
		for charToReplace, replaceWithChar in {"à": "a", "â": "a", "ç": "c", "è": "e", "ê": "e", "í": "i", "î": "i", "ï": "i", "ô": "o", "û": "u", "œ": "oe"}.items():
			outputCard["simpleName"] = outputCard["simpleName"].replace(charToReplace, replaceWithChar)
	_logger.debug(f"Current card name is '{outputCard['fullName']}', ID {outputCard['id']}")

	try:
		outputCard["cost"] = inputCard["ink_cost"] if "ink_cost" in inputCard else int(parsedImageAndTextData["cost"].text)
	except Exception as e:
		_logger.error(f"Unable to parse {parsedImageAndTextData['cost'].text!r} as card cost in card ID {outputCard['id']}; Exception {type(e).__name__}: {e}")
		outputCard["cost"] = -1
	if "quest_value" in inputCard:
		outputCard["lore"] = inputCard["quest_value"]
	for inputFieldName, outputFieldName in (("move_cost", "moveCost"), ("strength", "strength"), ("willpower", "willpower")):
		if inputFieldName in inputCard:
			outputCard[outputFieldName] = inputCard[inputFieldName]
		elif parsedImageAndTextData.get(outputFieldName, None) is not None:
			try:
				outputCard[outputFieldName] = int(parsedImageAndTextData[outputFieldName].text, 10)
			except ValueError:
				_logger.error(f"Unable to parse {parsedImageAndTextData[outputFieldName].text!r} as {outputFieldName} in card ID {outputCard['id']}")
				outputCard[outputFieldName] = -1
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
		outputCard["nonEnchantedId" if outputCard["rarity"] == Language.TRANSLATIONS[GlobalConfig.language]["ENCHANTED"] else "enchantedId"] = enchantedNonEnchantedId
	# If the card is a promo card, store the non-promo ID
	# If the card has promo version, store the promo IDs
	if promoNonPromoId:
		outputCard["nonPromoId" if isPromoCard else "promoIds"] = promoNonPromoId
	# Store the different parts of the card text, correcting some values if needed
	if parsedImageAndTextData["flavorText"] is not None:
		flavorText = correctText(parsedImageAndTextData["flavorText"].text)
		flavorText = correctPunctuation(flavorText)
		# Tesseract often sees the italic 'T' as an 'I', especially at the start of a word. Fix that
		if GlobalConfig.language == Language.ENGLISH and "I" in flavorText:
			flavorText = re.sub(r"(^|\W)I(?=[ehiow]\w)", r"\1T", flavorText)
		elif GlobalConfig.language == Language.FRENCH and "-" in flavorText:
			# French cards use '–' (en dash, \u2013) a lot, for quote attribution and the like, which gets read as '-' (a normal dash) often. Correct that
			flavorText = flavorText.replace("\n-", "\n–").replace("” -", "” –")
		outputCard["flavorText"] = flavorText
	if parsedImageAndTextData["remainingText"] is not None:
		abilityText = parsedImageAndTextData["remainingText"].text.lstrip("“‘")
		# TODO FIXME Song reminder text is at the top of a Song card, should probably not be listed in the 'abilities' list
		abilityLines = re.sub(r"(\.\)\n)", r"\1\n", abilityText).split("\n\n")
		for abilityLineIndex in range(len(abilityLines) - 1, 0, -1):
			# Sometimes lines get split up into separate abilities when they shouldn't be,
			# for instance in choice lists, or just accidentally. Fix that
			if abilityLines[abilityLineIndex].startswith("-") or re.match(r"[a-z(]", abilityLines[abilityLineIndex]):
				abilityLines[abilityLineIndex - 1] += "\n" + abilityLines.pop(abilityLineIndex)
		for abilityLineIndex in range(len(abilityLines)):
			abilityLines[abilityLineIndex] = correctText(abilityLines[abilityLineIndex])
		outputCard["abilities"] = abilityLines
	if parsedImageAndTextData["effectLabels"]:
		outputCard["effects"]: List[Dict[str, str]] = []
		for effectIndex in range(len(parsedImageAndTextData["effectLabels"])):
			effectName = correctPunctuation(parsedImageAndTextData["effectLabels"][effectIndex].text.replace("’", "'").replace("''", "'")).rstrip(":")
			if GlobalConfig.language == Language.FRENCH:
				effectName = re.sub("A ?!(?=.{3,})", "AI", effectName)
				if "!" in effectName or "?" in effectName:
					# French puts a space before an exclamation or question mark, add that in
					effectName, replacementCount = re.subn(r"(\S)([!?])", r"\1 \2", effectName)
					if replacementCount > 0:
						_logger.debug(f"Added a space before the exclamation or question mark in effect '{effectName}'")
				effectName, replacementCount = re.subn(r"\bCA\b", "ÇA", effectName)
				if replacementCount > 0:
					_logger.debug(f"Corrected 'CA' to 'ÇA' in effect '{effectName}'")
			outputCard["effects"].append({
				"name": effectName,
				"text": correctText(parsedImageAndTextData["effectTexts"][effectIndex].text)
			})
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
			infoText = infoText.format(E=ImageParser.EXERT_UNICODE, I=ImageParser.INK_UNICODE, L=ImageParser.LORE_UNICODE, S=ImageParser.STRENGTH_UNICODE, W=ImageParser.WILLPOWER_UNICODE)
			if infoEntry["title"].startswith("Errata"):
				if " - " in infoEntry["title"]:
					# There's a suffix explaining what field the errata is about, prepend it to the text
					infoText = infoEntry["title"].split(" - ")[1] + "\n" + infoText
				errata.append(infoText)
			elif infoEntry["title"].startswith("FAQ") or infoEntry["title"].startswith("Keyword") or infoEntry["title"] == "Good to know":
				# Sometimes they cram multiple questions and answers into one entry, split those up into separate clarifications
				infoEntryClarifications = re.split("\\s*\n+(?=Q:)", infoText)
				clarifications.extend(infoEntryClarifications)
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
		translation = Language.TRANSLATIONS[GlobalConfig.language]
		if subtypes[0] == translation["Action"] or subtypes[0] == translation["Item"] or subtypes[0] == translation["Location"]:
			subtypes.pop(0)
		# 'Seven Dwarves' is a subtype, but it might get split up into two types. Turn it back into one subtype
		sevenDwarvesCheckTypes = None
		if GlobalConfig.language == Language.ENGLISH:
			sevenDwarvesCheckTypes = ("Seven", "Dwarfs")
		elif GlobalConfig.language == Language.FRENCH:
			sevenDwarvesCheckTypes = ("Sept", "Nains")
		elif GlobalConfig.language == Language.GERMAN:
			sevenDwarvesCheckTypes = ("Sieben", "Zwerge")
		if sevenDwarvesCheckTypes and sevenDwarvesCheckTypes[0] in subtypes and sevenDwarvesCheckTypes[1] in subtypes:
			subtypes.remove(sevenDwarvesCheckTypes[1])
			subtypes[subtypes.index(sevenDwarvesCheckTypes[0])] = " ".join(sevenDwarvesCheckTypes)
		for subtypeIndex in range(len(subtypes) - 1, -1, -1):
			subtype = subtypes[subtypeIndex]
			# Correct 'Floodborn'
			if subtype != "Floodborn" and re.match(r"^Flood[^b]?b?[^b]?orn$", subtype):
				_logger.debug(f"Correcting '{subtype}' to 'Floodborn'")
				subtypes[subtypeIndex] = "Floodborn"
			# Remove short subtypes, probably erroneous
			elif len(subtype) < 3:
				_logger.debug(f"Removing subtype '{subtype}', too short")
				subtypes.pop(subtypeIndex)
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
	if "abilities" in outputCard and (outputCard["type"] == Language.TRANSLATIONS[GlobalConfig.language]["Character"] or outputCard["type"] == Language.TRANSLATIONS[GlobalConfig.language]["Action"]):
		keywordAbilities = []
		# Find the ability name at the start of a sentence, optionally followed by a number, and then followed by the opening bracket of the reminder text
		for abilityLine in outputCard["abilities"]:
			# To prevent accidental matches, check if it's actually a keyword ability, and not just the last word(s) of a sentence. Check by assuming keyword abilities never end in a period
			abilityMatch = re.search(r"(?:^|\n)([A-ZÀ][^.]+)(?= \()", abilityLine)
			if abilityMatch:
				keywordAbilities.append(abilityMatch.group(1))
			# Some cards list keyword abilities without reminder text, sometimes multiple separated by commas
			elif ", " in abilityLine and not abilityLine.endswith("."):
				abilityLineParts = abilityLine.split(", ")
				for abilityLinePart in abilityLineParts:
					if " " in abilityLinePart and abilityLinePart != "Hors d'atteinte" and not re.match(r"Sing Together \d+", abilityLinePart):
						break
				else:
					# Sentence is single-word comma-separated parts, assume it's a list of keyword abilities
					keywordAbilities.extend(abilityLineParts)
		if keywordAbilities:
			outputCard["keywordAbilities"] = keywordAbilities
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
	else:
		storyName = storyParser.getStoryNameForCard(outputCard, outputCard["id"])
		outputCard["story"] = storyName if storyName else "[[unknown]]"
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
