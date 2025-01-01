import copy
import datetime, hashlib, json, logging, multiprocessing.pool, os, re, threading, time, zipfile
from typing import Dict, List, Optional, Union

import GlobalConfig
from APIScraping.ExternalLinksHandler import ExternalLinksHandler
from OCR import ImageParser
from output.StoryParser import StoryParser
from util import IdentifierParser, Language, LorcanaSymbols


_logger = logging.getLogger("LorcanaJSON")
FORMAT_VERSION = "2.0.2"
_CARD_CODE_LOOKUP = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_KEYWORD_REGEX = re.compile(r"(?:^|\n)([A-ZÀ][^.]+)(?= \()")
# The card parser is run in threads, and each thread needs to initialize its own ImageParser (otherwise weird errors happen in Tesseract)
# Store each initialized ImageParser in its own thread storage
_threadingLocalStorage = threading.local()
_threadingLocalStorage.imageParser: ImageParser.ImageParser = None
_threadingLocalStorage.externalIdsHandler: ExternalLinksHandler = None

def correctText(cardText: str) -> str:
	"""
	Fix some re-occuring mistakes and errors in the text of the cards
	:param cardText: The text to correct
	:return: The card text with common problems fixed
	"""
	originalCardText = cardText
	cardText = re.sub("\n{2,}", "\n", cardText.strip())
	## First simple typos ##
	# Commas should always be followed by a space
	cardText = re.sub(",(?! |’|”|$)", ", ", cardText, flags=re.MULTILINE)
	# Simplify quote mark if it's used in a contraction
	cardText = re.sub(r"(?<=\w)[‘’](?=\w)", "'", cardText)
	# The 'Exert' symbol often gets read as a 6
	cardText = re.sub(r"^6 ?,", f"{LorcanaSymbols.EXERT},", cardText, flags=re.MULTILINE)
	# There's usually an ink symbol between a number and a dash
	cardText = re.sub(r"(^| )(\d) ?[0OQ©]{,2}( ?[-—]|,)", fr"\1\2 {LorcanaSymbols.INK}\3", cardText, re.MULTILINE)
	# Normally a closing quote mark should be preceded by a period, except mid-sentence
	cardText = re.sub(r"([^.,'!?’])”(?!,| \w)", "\\1.”", cardText)
	# An opening bracket shouldn't have a space after it
	cardText = cardText.replace("( ", "(")
	# Sometimes an extra character gets added after the closing quote mark or bracket from an inksplotch, remove that
	cardText = re.sub(r"(?<=[”’)])\s.$", "", cardText, re.MULTILINE)
	# Make sure there's a period before a closing bracket
	cardText = re.sub(r"([^.,'!?’])\)", r"\1.)", cardText)
	# The 'exert' symbol often gets mistaken for a @ or G, correct that
	cardText = re.sub(r"(?<![0-9s])(^|\"|“| )[(@G©€]{1,3}9?([ ,])", fr"\1{LorcanaSymbols.EXERT}\2", cardText, re.MULTILINE)
	# Other weird symbols are probably strength symbols
	cardText = re.sub(r"[&@©%$*<>{}€£¥Ÿ]{1,2}[0-9yF+*%]*", LorcanaSymbols.STRENGTH, cardText)
	cardText = re.sub(r"(?<=\d )[CÇD]\b", LorcanaSymbols.STRENGTH, cardText)
	# Strip erroneously detected characters from the end
	cardText = re.sub(r" [‘;]$", "", cardText, flags=re.MULTILINE)
	# The Lore symbol often gets mistaken for a 4, correct hat
	cardText = re.sub(r"(\d) ?4", fr"\1 {LorcanaSymbols.LORE}", cardText)
	cardText = re.sub(r"^[-+«»¢](?= \w{2,} \w+)", LorcanaSymbols.SEPARATOR, cardText, flags=re.MULTILINE)
	# It sometimes misses the strength symbol between a number and the closing bracket
	cardText = re.sub(r"^\+(\d)(\.\)?)$", f"+\\1 {LorcanaSymbols.STRENGTH}\\2", cardText, flags=re.MULTILINE)
	cardText = re.sub(r"^([-+]\d)0(\.\)?)$", fr"\1 {LorcanaSymbols.STRENGTH}\2", cardText, flags=re.MULTILINE)
	# A 7 often gets mistaken for a /, correct that
	cardText = cardText.replace(" / ", " 7 ")
	cardText = re.sub(f"{LorcanaSymbols.INK}([-—])", fr"{LorcanaSymbols.INK} \1", cardText)
	# Negative numbers are always followed by a strength symbol, correct that
	cardText = re.sub(fr"(?<= )(-\d)( [^{LorcanaSymbols.STRENGTH}{LorcanaSymbols.LORE}a-z .]{{1,2}})?( \w|$)", fr"\1 {LorcanaSymbols.STRENGTH}\3", cardText, flags=re.MULTILINE)
	# Two numbers in a row never happens, or a digit followed by a loose capital lettter. The latter should probably be a Strength symbol
	cardText = re.sub(r"(\d) [0-9DGOQ]\b", f"\\1 {LorcanaSymbols.STRENGTH}", cardText)
	# Letters after a quotemark at the start of a line should be capitalized
	cardText = re.sub("^“[a-z]", lambda m: m.group(0).upper(), cardText, flags=re.MULTILINE)
	
	if GlobalConfig.language == Language.ENGLISH:
		cardText = re.sub("^‘", "“", cardText, flags=re.MULTILINE)
		cardText = re.sub(" [:i]$", "", cardText, flags=re.MULTILINE)
		# Somehow it reads 'Bodyquard' with a 'q' instead of or in addition to a 'g' a lot...
		cardText = re.sub("Bodyqg?uard", "Bodyguard", cardText)
		# Fix some common typos
		cardText = cardText.replace("-|", "-1").replace("|", "I")
		cardText = re.sub(r"“[LT\[]([ '])", r"“I\1", cardText)
		cardText = cardText.replace("—l", "—I")
		cardText = re.sub(r"(?<=\w)!(?=,? ?[a-z])", "l", cardText)  # Replace exclamation mark followed by a lowercase letter by an 'l'
		cardText = re.sub(r"^(“)?! ", r"\1I ", cardText)
		cardText = re.sub(r"(^| |\n|“)[lIL!]([dlmM]l?)\b", r"\1I'\2", cardText, flags=re.MULTILINE)
		cardText = re.sub(r" ‘em\b", " 'em", cardText)
		# Correct some fancy qoute marks at the end of some plural possessives. This is needed on a case-by-case basis, otherwise too much text is changed
		cardText = re.sub(r"\bteammates’( |$)", r"teammates'\1", cardText, flags=re.MULTILINE)
		cardText = re.sub(r"\bplayers’( |$)", r"players'\1", cardText, flags=re.MULTILINE)
		cardText = re.sub(r"\bopponents’( |$)", r"opponents'\1", cardText, flags=re.MULTILINE)
		## Correct common phrases with symbols ##
		# Ink payment discounts
		cardText = re.sub(r"\bpay (\d) .?to\b", f"pay \\1 {LorcanaSymbols.INK} to", cardText)
		cardText = re.sub(rf"pay(s?) ?(\d)\.? ?[^{LorcanaSymbols.INK}.]{{1,2}}( |\.|$)", f"pay\\1 \\2 {LorcanaSymbols.INK}\\3", cardText, flags=re.MULTILINE)
		cardText = re.sub(r"\bpay (\d) less\b", f"pay \\1 {LorcanaSymbols.INK} less", cardText)
		# It gets a bit confused about exert and payment, correct that
		cardText = re.sub(r"^\(20 ", f"{LorcanaSymbols.EXERT}, 2 {LorcanaSymbols.INK} ", cardText)
		# The Lore symbol after 'location's' often gets missed
		cardText = cardText.replace("location's .", f"location's {LorcanaSymbols.LORE}.")
		## Correct reminder text ##
		# Challenger
		cardText = re.sub(r"\(They get \+(\d)$", f"(They get +\\1 {LorcanaSymbols.STRENGTH}", cardText, flags=re.MULTILINE)
		# Shift
		cardText = re.sub(f"pay (\\d+) {LorcanaSymbols.INK} play this", f"pay \\1 {LorcanaSymbols.INK} to play this", cardText)
		# Song
		cardText = re.sub(f"(can|may)( [^{LorcanaSymbols.EXERT}]{{1,2}})? to sing this", f"\\1 {LorcanaSymbols.EXERT} to sing this", cardText)
		# Support, full line (not sure why it sometimes doesn't get cut into two lines
		if re.search(r"their \S{1,3}\sto another chosen character['’]s", cardText):
			cardText = re.sub(f"their [^{LorcanaSymbols.STRENGTH}]{{1,3}} to", f"their {LorcanaSymbols.STRENGTH} to", cardText)
		# Support, first line if split
		cardText = re.sub(fr"(^|\badd )their [^{LorcanaSymbols.STRENGTH}]{{1,2}} to", f"\\1their {LorcanaSymbols.STRENGTH} to", cardText, flags=re.MULTILINE)
		# Support, second line if split (prevent hit on 'of this turn.' or '+2 this turn', which is unrelated to what we're correcting)
		cardText = re.sub(rf"^([^{LorcanaSymbols.STRENGTH}of+]{{1,2}} )?this turn\.?\)$", f"{LorcanaSymbols.STRENGTH} this turn.)", cardText, flags=re.MULTILINE)
		cardText = re.sub(f"chosen character's( [^{LorcanaSymbols.LORE}{LorcanaSymbols.STRENGTH}])? this turn", f"chosen character's {LorcanaSymbols.STRENGTH} this turn", cardText)
		# Common typos
		cardText = re.sub(r"\bluminary\b", "Illuminary", cardText)
		cardText = re.sub(r"([Dd])rawa ?card", r"\1raw a card", cardText)
		cardText = re.sub(r"\bLt\b", "It", cardText)
		cardText = re.sub(r"\b([Hh])ed\b", r"\1e'd", cardText)
		# Somehow 'a's often miss the space after it
		cardText = re.sub(r"\bina\b", "in a", cardText)
		cardText = re.sub(r"\bacard\b", "a card", cardText)
		# Make sure dash in ability cost and in quote attribution is always long-dash
		cardText = re.sub(r"(?<!\w)[-—~]+(?=\D|$)", r"—", cardText, flags=re.MULTILINE)
	elif GlobalConfig.language == Language.FRENCH:
		# Correct payment text
		cardText = re.sub(fr"\bpa(yer|ie) (\d+) (?:\W|D|O|Ô|Q|{LorcanaSymbols.STRENGTH})", f"pa\\1 \\2 {LorcanaSymbols.INK}", cardText)
		cardText = re.sub(fr"^(\d) ?[{LorcanaSymbols.STRENGTH}O0](\s)(pour|de moins)\b", fr"\1 {LorcanaSymbols.INK}\2\3", cardText, flags=re.MULTILINE)
		# Correct support reminder text
		cardText = re.sub(r"(?<=ajouter sa )\W+(?= à celle)", LorcanaSymbols.STRENGTH, cardText)
		# Correct Challenger/Offensif reminder text
		cardText = re.sub(r"gagne \+(\d+) \.\)", fr"gagne +\1 {LorcanaSymbols.STRENGTH}.)", cardText)
		# Cost discount text
		cardText = re.sub(fr"(coûte(?:nt)? )(\d+) [^{LorcanaSymbols.INK} \nou]+", fr"\1\2 {LorcanaSymbols.INK}", cardText)
		# Fix punctuation by turning multiple periods into an ellipsis character, and correct ellipsis preceded or followed by periods
		cardText = re.sub(r"…?\.{2,}…?", "…", cardText)
		# Ellipsis get misread as periods often, try to recognize it by the first letter after a period not being capitalized
		cardText = re.sub(r"\.+ ([a-z])", r"… \1", cardText)
		cardText = re.sub(r"^‘", "“", cardText, flags=re.MULTILINE)
		# "Il" often gets misread as "I!" or "[|"
		cardText = re.sub(r"(?<![A-Z])[I|/[][!|]", "Il", cardText)
		# French always has a space before punctuation marks
		cardText = re.sub(r"(\S)!", r"\1 !", cardText)
		cardText = re.sub(r"!(\w)", r"! \1", cardText)
		cardText = cardText.replace("//", "Il")
		cardText = re.sub(fr"((?:\bce personnage|\bil) gagne )\+(\d) [^{LorcanaSymbols.LORE}{LorcanaSymbols.STRENGTH}{LorcanaSymbols.WILLPOWER}]?\.", fr"\1+\2 {LorcanaSymbols.STRENGTH}.", cardText)
		# Fix second line of 'Challenger'/'Offensif' reminder text
		cardText = re.sub(r"^\+(\d) ?[^.]{0,2}\.\)$", fr"+\1 {LorcanaSymbols.STRENGTH}.)", cardText, flags=re.MULTILINE)
		# Sometimes a number before 'dommage' gets read as something else, correct that
		cardText = re.sub(r"\b[l|] dommage", "1 dommage", cardText)
		# Misc common mistakes
		cardText = cardText.replace("Ily", "Il y")
		cardText = re.sub(r"\bCa\b", "Ça", cardText)
		cardText = cardText.replace("personhage", "personnage")

	if cardText != originalCardText:
		_logger.info(f"Corrected card text from {originalCardText!r} to {cardText!r}")
	return cardText

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
	if correctedText.endswith(","):
		correctedText = correctedText[:-1] + "."
	correctedText = correctedText.rstrip(" -_")
	correctedText = correctedText.replace("““", "“")
	if correctedText.startswith("\""):
		correctedText = "“" + correctedText[1:]
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
			_logger.warning(f"Trying to correct field '{fieldName}' in card {_createCardIdentifier(card)} from {regexMatchString!r} to {correction!r} but the field does not exist. Set the match string to 'null' if you want to add a field")
		elif correction is None:
			_logger.warning(f"Trying to remove field '{fieldName}' but it already doesn't exist in card {_createCardIdentifier(card)}")
		else:
			card[fieldName] = correction
	elif regexMatchString is None:
		if correction is None:
			_logger.info(f"Removing field '{fieldName}' (value {card[fieldName]!r}) from card {_createCardIdentifier(card)}")
			del card[fieldName]
		elif fieldName in card:
			if isinstance(card[fieldName], list):
				if isinstance(card[fieldName][0], type(correction)):
					_logger.info(f"Appending value {correction} to list field {fieldName} in card {_createCardIdentifier(card)}")
				else:
					_logger.warning(f"Trying to add value {correction!r} of type {type(correction)} to list of {type(card[fieldName][0])} types in card {_createCardIdentifier(card)}, skipping")
			else:
				_logger.warning(f"Trying to add field '{fieldName}' to card {_createCardIdentifier(card)}, but that field already exists (value {card[fieldName]!r})")
	elif isinstance(card[fieldName], str):
		preCorrectedText = card[fieldName]
		card[fieldName] = re.sub(regexMatchString, correction, preCorrectedText, flags=re.DOTALL)
		if card[fieldName] == preCorrectedText:
			_logger.warning(f"Correcting field '{fieldName}' in card {_createCardIdentifier(card)} with regex {regexMatchString!r} didn't change anything, value is still {preCorrectedText!r}")
		else:
			_logger.info(f"Corrected field '{fieldName}' from {preCorrectedText!r} to {card[fieldName]!r} for card {_createCardIdentifier(card)}")
	elif isinstance(card[fieldName], list):
		matchFound = False
		if isinstance(card[fieldName][0], dict):
			# The field is a list of dicts, apply the correction to each entry if applicable
			for fieldIndex, fieldEntry in enumerate(card[fieldName]):
				for fieldKey, fieldValue in fieldEntry.items():
					if not isinstance(fieldValue, str):
						continue
					match = re.search(regexMatchString, fieldValue, flags=re.DOTALL)
					if match:
						matchFound = True
						preCorrectedText = fieldValue
						fieldEntry[fieldKey] = re.sub(regexMatchString, correction, fieldValue, flags=re.DOTALL)
						if fieldEntry[fieldKey] == preCorrectedText:
							_logger.warning(f"Correcting index {fieldIndex} of field '{fieldName}' in card {_createCardIdentifier(card)} with regex {regexMatchString!r} didn't change anything, value is still {preCorrectedText!r}")
						else:
							_logger.info(f"Corrected index {fieldIndex} of field '{fieldName}' from {preCorrectedText!r} to {fieldEntry[fieldKey]!r} for card {_createCardIdentifier(card)}")
		elif isinstance(card[fieldName][0], str):
			for fieldIndex in range(len(card[fieldName]) - 1, -1, -1):
				fieldValue = card[fieldName][fieldIndex]
				match = re.search(regexMatchString, fieldValue, flags=re.DOTALL)
				if match:
					matchFound = True
					if correction is None:
						# Delete the value
						_logger.info(f"Removing index {fieldIndex} value {fieldValue!r} from field '{fieldName}' in card {_createCardIdentifier(card)}")
						card[fieldName].pop(fieldIndex)
					else:
						preCorrectedText = fieldValue
						card[fieldName][fieldIndex] = re.sub(regexMatchString, correction, fieldValue, flags=re.DOTALL)
						if card[fieldName][fieldIndex] == preCorrectedText:
							_logger.warning(f"Correcting index {fieldIndex} of field '{fieldName}' in card {_createCardIdentifier(card)} with regex {regexMatchString!r} didn't change anything")
						else:
							_logger.info(f"Corrected index {fieldIndex} of field '{fieldName}' from {preCorrectedText!r} to {card[fieldName][fieldIndex]!r} for card {_createCardIdentifier(card)}")
		else:
			_logger.error(f"Unhandled type of list entries ({type(card[fieldName][0])}) in card {_createCardIdentifier(card)}")
		if not matchFound:
			_logger.warning(f"Correction regex {regexMatchString!r} for field '{fieldName}' in card {_createCardIdentifier(card)} didn't match any of the entries in that field")
	elif isinstance(card[fieldName], int):
		if card[fieldName] != regexMatchString:
			_logger.warning(f"Expected value of field '{fieldName}' in card {_createCardIdentifier(card)} is {regexMatchString!r}, but actual value is {card[fieldName]!r}, skipping correction")
		else:
			_logger.info(f"Corrected numerical value of field '{fieldName}' in card {_createCardIdentifier(card)} from {card[fieldName]} to {correction}")
			card[fieldName] = correction
	elif isinstance(card[fieldName], bool):
		if card[fieldName] == correction:
			_logger.warning(f"Corrected value for boolean field '{fieldName}' is the same as the existing value '{card[fieldName]}' for card {_createCardIdentifier(card)}")
		else:
			_logger.info(f"Corrected boolean field '{fieldName}' in card {_createCardIdentifier(card)} from {card[fieldName]} to {correction}")
			card[fieldName] = correction
	elif isinstance(card[fieldName], dict):
		# Go through each key-value pair to try and find a matching entry
		isStringMatch = isinstance(regexMatchString, str)
		for key in card[fieldName]:
			value = card[fieldName][key]
			if isStringMatch and isinstance(value, str) and re.search(regexMatchString, value, flags=re.DOTALL):
				card[fieldName][key] = re.sub(regexMatchString, correction, value)
				if value == card[fieldName][key]:
					_logger.warning(f"Correcting value for key '{key}' in dictionary field '{fieldName}' of card {_createCardIdentifier(card)} with regex {regexMatchString!r} didn't change anything, value is still '{value}'")
				else:
					_logger.info(f"Corrected value '{value}' to '{card[fieldName][key]}' in key '{key}' of dictionary field '{fieldName}' in card {_createCardIdentifier(card)}")
				break
		else:
			_logger.warning(f"Correction {regexMatchString!r} for dictionary field '{fieldName}' in card {_createCardIdentifier(card)} didn't match any of the values")
	else:
		raise ValueError(f"Card correction {regexMatchString!r} for field '{fieldName}' in card {_createCardIdentifier(card)} is of unsupported type '{type(card[fieldName])}'")

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
			parsedIdentifier: IdentifierParser.Identifier = IdentifierParser.parseIdentifier(card["card_identifier"])
			if parsedIdentifier.isPromo():
				if card["deck_building_id"] not in promoDeckBuildingIds:
					promoDeckBuildingIds[card["deck_building_id"]] = []
				promoDeckBuildingIds[card["deck_building_id"]].append(card["culture_invariant_id"])
			# Some promo cards are listed as Enchanted-rarity, so don't store those promo cards as Enchanted too
			elif card["rarity"] == "ENCHANTED":
				if card["deck_building_id"] in enchantedDeckbuildingIds:
					_logger.info(f"Card {_createCardIdentifier(card)} is Enchanted, but its deckbuilding ID already exists in the Enchanteds list, pointing to ID {enchantedDeckbuildingIds[card['deck_building_id']]}, not storing the ID")
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
		with open(historicDataFilePath, "r", encoding="utf-8") as historicDataFile:
			historicData = {int(k, 10): v for k, v in json.load(historicDataFile).items()}
	else:
		historicData = {}

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
							historicData.pop(card["id"], None)
				del previousCardData
		else:
			_logger.warning("ID list provided but previously generated file doesn't exist. Generating all card data")

	def initThread():
		_threadingLocalStorage.imageParser = ImageParser.ImageParser()
		_threadingLocalStorage.externalIdsHandler = ExternalLinksHandler()

	# Parse the cards we need to parse
	languageCodeToCheck = GlobalConfig.language.code.upper()
	cardToStoryParser = StoryParser()
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
				elif languageCodeToCheck not in inputCard["card_identifier"]:
					_logger.debug(f"Skipping card with ID {inputCard['culture_invariant_id']} because it's not in the requested language")
					continue
				elif onlyParseIds and cardId not in onlyParseIds:
					_logger.error(f"Card ID {cardId} is not in the ID parse list, but it's also not in the previous dataset. Skipping parsing for now, but this results in incomplete datafiles, so it's strongly recommended to rerun with this card ID included")
					continue
				try:
					results.append(pool.apply_async(_parseSingleCard, (inputCard, cardTypeText, imageFolder, enchantedNonEnchantedIds.get(cardId, None), promoNonPromoIds.get(cardId, None), variantsDeckBuildingIds.get(inputCard["deck_building_id"]),
												  cardDataCorrections.pop(cardId, None), cardToStoryParser, False, historicData.get(cardId, None), shouldShowImages)))
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
															   cardDataCorrections.pop(cardId, None), cardToStoryParser, True, historicData.get(cardId, None), shouldShowImages)))
		pool.close()
		pool.join()
	for result in results:
		outputCard = result.get()
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
	outputDict = {"metadata": metaDataDict}

	# Add set data
	with open(os.path.join("output", f"baseSetData.json"), "r", encoding="utf-8") as baseSetDataFile:
		setsData = json.load(baseSetDataFile)
		for setCode in setsData:
			# Get just the current language's set names
			setsData[setCode]["name"] = setsData[setCode].pop("names")[GlobalConfig.language.code]
	outputDict["sets"] = setsData

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
		# Remove the setCode, since it's clear from the setfile the card is in
		setId = card.pop("setCode")
		setsData[setId]["cards"].append(card)
	for setId, setData in setsData.items():
		if len(setData["cards"]) == 0:
			_logger.warning(f"No cards found for set '{setId}', not creating data file for it")
			continue
		setFilePath = os.path.join(setOutputFolder, f"setdata.{setId}.json")
		setFilePaths.append(setFilePath)
		_saveFile(setFilePath, setData)
	# Create a zipfile containing all the setfiles
	_saveZippedFile(os.path.join(setOutputFolder, "allSets.zip"), setFilePaths)
	_logger.info(f"Created the set files in {time.perf_counter() - startTime:.4f} seconds")

def _parseSingleCard(inputCard: Dict, cardType: str, imageFolder: str, enchantedNonEnchantedId: Union[int, None], promoNonPromoId: Union[int, List[int], None], variantIds: Union[List[int], None],
					 cardDataCorrections: Dict, storyParser: StoryParser, isExternalReveal: bool, historicData: List[Dict], shouldShowImage: bool = False) -> Dict:
	# Store some default values
	outputCard: Dict[str, Union[str, int, List, Dict]] = {
		"color": GlobalConfig.translation[inputCard["magic_ink_colors"][0]] if inputCard["magic_ink_colors"] else "",
		"id": inputCard["culture_invariant_id"],
		"inkwell": inputCard["ink_convertible"],
		"rarity": GlobalConfig.translation[inputCard["rarity"]],
		"type": cardType
	}
	if isExternalReveal:
		outputCard["isExternalReveal"] = True

	# When building a deck in the official app, it gets saves as a string. This string starts with a '2', and then each card gets a two-character code based on the card's ID
	# This card code is the card ID in base 62, using 0-9, a-z, and then A-Z for individual digits
	cardCodeDigits = divmod(outputCard["id"], 62)
	outputCard["code"] = _CARD_CODE_LOOKUP[cardCodeDigits[0]] + _CARD_CODE_LOOKUP[cardCodeDigits[1]]

	# Get required data by parsing the card image
	parsedIdentifier: Union[None, IdentifierParser.Identifier] = None
	if "card_identifier" in inputCard:
		parsedIdentifier = IdentifierParser.parseIdentifier(inputCard["card_identifier"])
	parsedImageAndTextData = _threadingLocalStorage.imageParser.getImageAndTextDataFromImage(
		outputCard["id"],
		imageFolder,
		parseFully=isExternalReveal,
		parsedIdentifier=parsedIdentifier,
		isLocation=cardType == GlobalConfig.translation.Location,
		hasCardText=inputCard["rules_text"] != "" if "rules_text" in inputCard else None,
		hasFlavorText=inputCard["flavor_text"] != "" if "flavor_text" in inputCard else None,
		isEnchanted=outputCard["rarity"] == GlobalConfig.translation.ENCHANTED or inputCard.get("foil_type", None) == "Satin",  # Disney100 cards need Enchanted parsing, foil_type seems best way to determine Disney100
 		showImage=shouldShowImage
	)

	if parsedImageAndTextData.get("identifier", None) is not None:
		outputCard["fullIdentifier"] = re.sub(fr" ?\W (?!$)", f" {LorcanaSymbols.SEPARATOR} ", parsedImageAndTextData["identifier"].text)
		outputCard["fullIdentifier"] = outputCard["fullIdentifier"].replace("I", "/").replace("1P ", "/P ").replace("//", "/").replace(".", "").replace("1TFC", "1 TFC")
		outputCard["fullIdentifier"] = re.sub(fr" ?[-+] ?", f" {LorcanaSymbols.SEPARATOR} ", outputCard["fullIdentifier"])
		if parsedIdentifier is None:
			parsedIdentifier = IdentifierParser.parseIdentifier(outputCard["fullIdentifier"])
	else:
		outputCard["fullIdentifier"] = str(parsedIdentifier)
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
	outputCard["artistsText"] = parsedImageAndTextData["artist"].text.lstrip(". ").replace("’", "'").replace("|", "l")
	oldArtistsText = outputCard["artistsText"]
	outputCard["artistsText"] = re.sub(r"^[l[]", "I", outputCard["artistsText"])
	while re.search(r" [a-z0-9ÿI|(\\_+.”—-]{1,2}$", outputCard["artistsText"]):
		outputCard["artistsText"] = outputCard["artistsText"].rsplit(" ", 1)[0]
	outputCard["artistsText"] = outputCard["artistsText"].rstrip(".")
	if "Haggman-Sund" in outputCard["artistsText"]:
		outputCard["artistsText"] = outputCard["artistsText"].replace("Haggman-Sund", "Häggman-Sund")
	elif "Toziim" in outputCard["artistsText"] or "Tôzüm" in outputCard["artistsText"] or "Toztim" in outputCard["artistsText"]:
		outputCard["artistsText"] = re.sub(r"\bT\w+z\w+m\b", "Tözüm", outputCard["artistsText"])
	elif re.match(r"Jo[^ã]o\b", outputCard["artistsText"]):
		outputCard["artistsText"] = re.sub("Jo[^ã]o", "João", outputCard["artistsText"])
	elif re.search(r"Krysi.{1,2}ski", outputCard["artistsText"]):
		outputCard["artistsText"] = re.sub(r"Krysi.{1,2}ski", "Krysiński", outputCard["artistsText"])
	if "“" in outputCard["artistsText"]:
		# Simplify quotemarks
		outputCard["artistsText"] = outputCard["artistsText"].replace("“", "\"").replace("”", "\"")
	if oldArtistsText != outputCard["artistsText"]:
		_logger.info(f"Corrected artist name from '{oldArtistsText}' to '{outputCard['artistsText']}' in card {_createCardIdentifier(inputCard)}")

	outputCard["name"] = correctPunctuation(inputCard["name"].strip() if "name" in inputCard else parsedImageAndTextData["name"].text).replace("’", "'").replace("‘", "'").replace("''", "'")
	if outputCard["name"] == "Balais Magiques":
		# This name is inconsistent, sometimes it has a capital 'M', sometimes a lowercase 'm'
		# Comparing with capitalization of other cards, this should be a lowercase 'm'
		outputCard["name"] = outputCard["name"].replace("M", "m")
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
	if "subtitle" in inputCard or parsedImageAndTextData.get("version", None) is not None:
		outputCard["version"] = (inputCard["subtitle"].strip() if "subtitle" in inputCard else parsedImageAndTextData["version"].text).replace("’", "'")
		outputCard["fullName"] += " - " + outputCard["version"]
		outputCard["simpleName"] += " " + outputCard["version"]
	# simpleName is the full name with special characters and the base-subtitle dash removed, for easier lookup. So remove the special characters
	outputCard["simpleName"] = re.sub(r"[!.,…?“”\"]", "", outputCard["simpleName"].lower()).rstrip()
	for replacementChar, charsToReplace in {"a": "[àâäā]", "c": "ç", "e": "[èêé]", "i": "[îïí]", "o": "[ôö]", "u": "[ùûü]", "oe": "œ", "ss": "ß"}.items():
		outputCard["simpleName"] = re.sub(charsToReplace, replacementChar, outputCard["simpleName"])
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
	elif "imageUrl" in inputCard:
		outputCard["images"] = {"full": inputCard["imageUrl"]}
	else:
		_logger.error(f"Card {_createCardIdentifier(outputCard)} does not contain any image URLs")
	# If the card is Enchanted or has an Enchanted equivalent, store that
	if enchantedNonEnchantedId:
		outputCard["nonEnchantedId" if outputCard["rarity"] == GlobalConfig.translation.ENCHANTED else "enchantedId"] = enchantedNonEnchantedId
	# If the card is a promo card, store the non-promo ID
	# If the card has promo version, store the promo IDs
	if promoNonPromoId:
		outputCard["promoIds" if isinstance(promoNonPromoId, list) else "nonPromoId"] = promoNonPromoId
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
	abilities: List[Dict[str, str]] = []
	effects: List[str] = []
	if parsedImageAndTextData["remainingText"] is not None:
		remainingText = parsedImageAndTextData["remainingText"].text.lstrip("“‘").rstrip(" \n|")
		# No effect ends with a colon, it's probably the start of a choice list. Make sure it doesn't get split up
		remainingText = remainingText.replace(":\n\n", ":\n")
		# A closing bracket indicates the end of a section, make sure it gets read as such by making sure there's two newlines
		remainingTextLines = re.sub(r"(\.\)\n)", r"\1\n", remainingText).split("\n\n")
		for remainingTextLineIndex in range(len(remainingTextLines) - 1, 0, -1):
			remainingTextLine = remainingTextLines[remainingTextLineIndex]
			# Sometimes lines get split up into separate list entries when they shouldn't be,
			# for instance in choice lists, or just accidentally. Fix that. But if the previous line ended with a closing bracket and this with an opening one, don't join them
			if remainingTextLine.startswith("-") or (re.match(r"[a-z(]", remainingTextLine) and not remainingTextLines[remainingTextLineIndex-1].endswith(")")) or remainingTextLine.count(")") > remainingTextLine.count("("):
				_logger.info(f"Merging accidentally-split line '{remainingTextLine}' with previous line '{remainingTextLines[remainingTextLineIndex - 1]}'")
				remainingTextLines[remainingTextLineIndex - 1] += "\n" + remainingTextLines.pop(remainingTextLineIndex)

		for remainingTextLine in remainingTextLines:
			remainingTextLine = correctText(remainingTextLine)
			# Check if this is a keyword ability
			if outputCard["type"] == GlobalConfig.translation.Character or outputCard["type"] == GlobalConfig.translation.Action:
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
				if keywordLines:
					for keywordLine in keywordLines:
						abilities.append({"type": "keyword", "fullText": keywordLine})
						# These entries will get more fleshed out after the corrections (if any) are applied, to prevent having to correct multiple fields
				else:
					# Since this isn't a named or keyword ability, assume it's a one-off effect
					effects.append(remainingTextLine)
			elif outputCard["type"] == GlobalConfig.translation.Item:
				# Some items ("Peter Pan's Dagger", ID 351; "Sword in the Stone", ID 352) have an ability without an ability name label. Store these as abilities too
				abilities.append({"effect": remainingTextLine})

	if parsedImageAndTextData["abilityLabels"]:
		for abilityIndex in range(len(parsedImageAndTextData["abilityLabels"])):
			abilityName = correctPunctuation(parsedImageAndTextData["abilityLabels"][abilityIndex].text.replace("‘", "'").replace("’", "'").replace("''", "'")).rstrip(":")
			abilityName = re.sub(r"(?<=\w) ?[.7|»”©\"]$", "", abilityName)
			if GlobalConfig.language == Language.ENGLISH:
				abilityName = abilityName.replace("|", "I")
			elif GlobalConfig.language == Language.FRENCH:
				abilityName = re.sub("A ?!(?=.{3,})", "AI", abilityName)
				if "!" in abilityName or "?" in abilityName:
					# French puts a space before an exclamation or question mark, add that in
					abilityName, replacementCount = re.subn(r"(\S)([!?])", r"\1 \2", abilityName)
					if replacementCount > 0:
						_logger.debug(f"Added a space before the exclamation or question mark in ability name '{abilityName}'")
				abilityName, replacementCount = re.subn(r"\bCA\b", "ÇA", abilityName)
				if replacementCount > 0:
					_logger.debug(f"Corrected 'CA' to 'ÇA' in abilty name '{abilityName}'")
			abilityEffect = correctText(parsedImageAndTextData["abilityTexts"][abilityIndex].text)
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
				_logger.warning(f"Unknown 'additional_info' type '{infoEntry['title']}' in card {_createCardIdentifier(outputCard)}")
		if errata:
			outputCard["errata"] = errata
		if clarifications:
			outputCard["clarifications"] = clarifications
	# Determine subtypes and their order. Items and Actions have an empty subtypes list, ignore those
	if parsedImageAndTextData["subtypesText"] and parsedImageAndTextData["subtypesText"].text:
		subtypes: List[str] = parsedImageAndTextData["subtypesText"].text.split(f" {LorcanaSymbols.SEPARATOR} ")
		if "ltem" in subtypes:
			subtypes[subtypes.index("ltem")] = "Item"
		# Non-character cards have their main type as their (first) subtype, remove those
		if subtypes[0] == GlobalConfig.translation.Action or subtypes[0] == GlobalConfig.translation.Item or subtypes[0] == GlobalConfig.translation.Location:
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
			if GlobalConfig.language in (Language.ENGLISH, Language.FRENCH) and subtype != "Floodborn" and re.match(r"^F[il]o[ao]d[^b]?b?[^b]?[aeo]r[an][e-]?$", subtype):
				_logger.debug(f"Correcting '{subtype}' to 'Floodborn'")
				subtypes[subtypeIndex] = "Floodborn"
			elif GlobalConfig.language == Language.ENGLISH and subtype != "Hero" and re.match(r"e?Her[aeos]", subtype):
				subtypes[subtypeIndex] = "Hero"
			# Remove short subtypes, probably erroneous
			elif len(subtype) < 3:
				_logger.debug(f"Removing subtype '{subtype}', too short")
				subtypes.pop(subtypeIndex)
		if subtypes:
			outputCard["subtypes"] = subtypes
	# Card-specific corrections
	externalLinksCorrection: Union[None, List[str]] = None  # externalLinks depends on correct fullIdentifier, which may have a correction, but it also might need a correction itself. So store it for now, and correct it later
	fullTextCorrection: Union[None, List[str]] = None  # Since the fullText gets created as the last step, if there is a correction for it, save it for later
	forceAbilityTypeIndexToActivated: int = -1
	forceAbilityTypeIndexToTriggered: int = -1
	forceAbilityTypeIndexToStatic: int = -1
	newlineAfterLabelIndex: int = -1
	mergeEffectIndexWithPrevious: int = -1
	if cardDataCorrections:
		if cardDataCorrections.pop("_moveKeywordsLast", False):
			if "abilities" not in outputCard or "effect" not in outputCard["abilities"][-1]:
				raise KeyError(f"Correction to move keywords last is set for card {_createCardIdentifier(outputCard)}, but no 'abilities' field exists or the last ability doesn't have an 'effect'")
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
		forceAbilityTypeIndexToActivated = cardDataCorrections.pop("_forceAbilityIndexToActivated", -1)
		forceAbilityTypeIndexToTriggered = cardDataCorrections.pop("_forceAbilityIndexToTriggered", -1)
		forceAbilityTypeIndexToStatic = cardDataCorrections.pop("_forceAbilityIndexToStatic", -1)
		newlineAfterLabelIndex = cardDataCorrections.pop("_newlineAfterLabelIndex", -1)
		mergeEffectIndexWithPrevious = cardDataCorrections.pop("_mergeEffectIndexWithPrevious", -1)
		effectAtIndexIsAbility: Union[int, List[int, str]] = cardDataCorrections.pop("_effectAtIndexIsAbility", -1)
		externalLinksCorrection = cardDataCorrections.pop("externalLinks", None)
		fullTextCorrection = cardDataCorrections.pop("fullText", None)
		for fieldName, correction in cardDataCorrections.items():
			if len(correction) > 2:
				for correctionIndex in range(0, len(correction), 2):
					correctCardField(outputCard, fieldName, correction[correctionIndex], correction[correctionIndex+1])
			else:
				correctCardField(outputCard, fieldName, correction[0], correction[1])
		# If newlines got added through a correction, we may need to split the effect in two
		if "effects" in cardDataCorrections and "effects" in outputCard:
			for effectIndex in range(len(outputCard["effects"]) - 1, -1, -1):
				while "\n\n" in outputCard["effects"][effectIndex]:
					_logger.info(f"Splitting effect at index {effectIndex} in two because it has a double newline, in card {_createCardIdentifier(outputCard)}")
					firstEffect, secondEffect = outputCard["effects"][effectIndex].rsplit("\n\n", 1)
					outputCard["effects"][effectIndex] = firstEffect
					outputCard["effects"].insert(effectIndex + 1, secondEffect)
		# Do this after the general corrections since one of those might add or split an effect
		if effectAtIndexIsAbility != -1:
			if "effects" not in outputCard:
				_logger.error(f"Correction to move effect index {effectAtIndexIsAbility} to abilities, but card {_createCardIdentifier(outputCard)} doesn't have an 'effects' field")
			if "abilities" not in outputCard:
				outputCard["abilities"] = []
			abilityNameForEffectIsAbility = ""
			if isinstance(effectAtIndexIsAbility, list):
				effectAtIndexIsAbility, abilityNameForEffectIsAbility = effectAtIndexIsAbility
			_logger.info(f"Moving effect index {effectAtIndexIsAbility} to abilities")
			outputCard["abilities"].append({"name": abilityNameForEffectIsAbility, "effect": outputCard["effects"].pop(effectAtIndexIsAbility)})
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
			if ability.get("type", None) == "keyword":
				keyword = ability["fullText"]
				reminderText = None
				if "(" in keyword:
					# This includes reminder text, extract that
					keyword, reminderText = keyword.rstrip(")").split(" (", 1)
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
			else:
				# Non-keyword ability, determine which type it is
				ability["type"] = "static"
				activatedAbilityMatch = re.search("[ \n][-–—][ \n]", ability["effect"])
				if forceAbilityTypeIndexToActivated == abilityIndex:
					_logger.info(f"Forcing ability type at index {abilityIndex} of card ID {outputCard['id']} to 'activated'")
					ability["type"] = "activated"
				elif forceAbilityTypeIndexToTriggered == abilityIndex:
					_logger.info(f"Forcing ability type at index {abilityIndex} of card ID {outputCard['id']} to 'triggered'")
					ability["type"] = "triggered"
				elif forceAbilityTypeIndexToStatic == abilityIndex:
					_logger.info(f"Forcing ability type at index {abilityIndex} of card ID {outputCard['id']} to 'static'")
				# Activated abilities require a cost, a dash, and then an effect
				# Some static abilities give characters such an activated ability, don't trigger on that
				# Some cards contain their own name (e.g. 'Dalmatian Puppy - Tail Wagger', ID 436), don't trigger on that dash either
				elif (activatedAbilityMatch and
						("“" not in ability["effect"] or ability["effect"].index("“") > activatedAbilityMatch.start()) and
						(outputCard["name"] not in ability["effect"] or ability["effect"].index(outputCard["name"]) > activatedAbilityMatch.start())):
					# Assume there's a payment text in there
					ability["type"] = "activated"
					ability["costsText"] = ability["effect"][:activatedAbilityMatch.start()]
					ability["effect"] = ability["effect"][activatedAbilityMatch.end():]
				elif GlobalConfig.language == Language.ENGLISH:
					if ability["effect"].startswith("Once per turn, you may"):
						ability["type"] = "activated"
					elif (ability["effect"].startswith("At the start of") or ability["effect"].startswith("At the end of") or	re.search(r"(^W|,[ \n]w)hen(ever)?[ \n]", ability["effect"])
							or re.search("when (he|she|it|they) enters play", ability["effect"])):
						ability["type"] = "triggered"
				elif GlobalConfig.language == Language.FRENCH:
					if ability["effect"].startswith("Une fois par tour, vous pouvez"):
						ability["type"] = "activated"
					elif (ability["effect"].startswith("Au début de chacun") or re.match(r"Au début\sde votre tour", ability["effect"]) or ability["effect"].startswith("À la fin d") or
						re.search(r"(^L|\bl)orsqu(e|'un|'il)\b", ability["effect"]) or re.search(r"(^À c|^C|,\sc)haque\sfois", ability["effect"]) or
						re.match("Si (?!vous avez|un personnage)", ability["effect"]) or re.search("gagnez .+ pour chaque", ability["effect"]) or
						re.search(r"une carte est\splacée", ability["effect"])):
						ability["type"] = "triggered"
				# All parts determined, now reconstruct the full ability text
				if "name" in ability and not ability["name"]:
					# Abilities added through corrections may have an empty name, remove that
					ability.pop("name")
				if "name" in ability:
					ability["fullText"] = ability["name"]
					if newlineAfterLabelIndex == abilityIndex:
						_logger.info(f"Adding newline after abilty label index {abilityIndex}")
						ability["fullText"] += "\n"
					else:
						ability["fullText"] += " "
				else:
					ability["fullText"] = ""
				if "costsText" in ability:
					ability["fullText"] += ability["costsText"] + activatedAbilityMatch.group(0)  # Since we don't know the exact type of separating dash, get it from the regex
					ability["costsText"] = ability["costsText"].replace("\n", " ")
					ability["costs"] = ability["costsText"].split(", ")
				ability["fullText"] += ability["effect"]
				ability["effect"] = ability["effect"].replace("\n", " ")
				if ability["effect"].startswith("("):
					# Song reminder text has brackets around it. Keep it in the 'fullText', but remove it from the 'effect'
					ability["effect"] = ability["effect"].strip("()")
			outputCard["abilities"][abilityIndex] = {abilityKey: ability[abilityKey] for abilityKey in sorted(ability)}
	if keywordAbilities:
		outputCard["keywordAbilities"] = keywordAbilities
	outputCard["artists"] = outputCard["artistsText"].split(" / ")
	# Add external links (Do this after corrections so we can use a corrected 'fullIdentifier')
	outputCard["externalLinks"] = _threadingLocalStorage.externalIdsHandler.getExternalLinksForCard(parsedIdentifier, "enchantedId" in outputCard)
	if externalLinksCorrection:
		correctCardField(outputCard, "externalLinks", externalLinksCorrection[0], externalLinksCorrection[1])
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
			_logger.info(f"Merging effect index {mergeEffectIndexWithPrevious} with previous index for card {_createCardIdentifier(outputCard)}")
			outputCard["effects"][mergeEffectIndexWithPrevious - 1] += "\n" + outputCard["effects"].pop(mergeEffectIndexWithPrevious)
		fullTextSections.extend(outputCard["effects"])
	outputCard["fullText"] = "\n".join(fullTextSections)
	outputCard["fullTextSections"] = fullTextSections
	if fullTextCorrection:
		correctCardField(outputCard, "fullText", fullTextCorrection[0], fullTextCorrection[1])
	if "story" in inputCard:
		outputCard["story"] = inputCard["story"]
	else:
		outputCard["story"] = storyParser.getStoryNameForCard(outputCard, outputCard["id"])
	if "foil_type" in inputCard:
		outputCard["foilTypes"] = ["None"] if inputCard["foil_type"] is None else [inputCard["foil_type"]]
	elif not isExternalReveal:
		# We can't know the foil type(s) of externally revealed cards, so not having the data at all is better than adding possibly wrong data
		# 'Normal' (so non-promo non-Enchanted) cards exist in unfoiled and cold-foiled types, so just default to that if no explicit foil type is provided
		outputCard["foilTypes"] = ["None", "Cold"]
	if historicData:
		outputCard["historicData"] = historicData
	# Sort the dictionary by key
	outputCard = {key: outputCard[key] for key in sorted(outputCard)}
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
