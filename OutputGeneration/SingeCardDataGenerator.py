import logging, re
from typing import Dict, List, Optional, Union

import GlobalConfig
from OCR import OcrCacheHandler
from OCR.OcrResult import OcrResult
from OutputGeneration import TextCorrection
from OutputGeneration.AllowedInFormatsHandler import AllowedInFormats, AllowedInFormatsHandler
from OutputGeneration.RelatedCardsCollator import RelatedCards
from OutputGeneration.StoryParser import StoryParser
from util import CardUtil, IdentifierParser, Language, LorcanaSymbols

_logger = logging.getLogger("LorcanaJSON")
_CARD_CODE_LOOKUP = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_KEYWORD_REGEX = re.compile(r"(?:^|\n)([A-ZÀ][^.]+)(?=\s\([A-Z])")
_KEYWORD_REGEX_WITHOUT_REMINDER = re.compile(r"^([A-ZÀ][^ ]{2,}|À)( ([dl]['’])?[A-Zu][^ ]{2,})?( \d)?( .)?$")
_ABILITY_TYPE_CORRECTION_FIELD_TO_ABILITY_TYPE: Dict[str, str] = {"_forceAbilityIndexToActivated": "activated", "_forceAbilityIndexToKeyword": "keyword", "_forceAbilityIndexToStatic": "static", "_forceAbilityIndexToTriggered": "triggered"}


def parseSingleCard(inputCard: Dict, cardType: str, imageFolder: str, threadLocalStorage, relatedCards: RelatedCards, cardDataCorrections: Dict, storyParser: StoryParser, isExternalReveal: bool, historicData: Optional[List[Dict]],
					allowedCardsHandler: AllowedInFormatsHandler, shouldShowImage: bool = False) -> Optional[Dict]:
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
	parsedIdentifier: Optional[IdentifierParser.Identifier] = None
	if "card_identifier" in inputCard:
		parsedIdentifier = IdentifierParser.parseIdentifier(inputCard["card_identifier"])

	ocrResult: Optional[OcrResult] = None
	if GlobalConfig.useCachedOcr and not GlobalConfig.skipOcrCache:
		ocrResult = OcrCacheHandler.getCachedOcrResult(outputCard["id"])

	if ocrResult is None:
		ocrResult = threadLocalStorage.imageParser.getImageAndTextDataFromImage(
			outputCard["id"],
			imageFolder,
			parseFully=isExternalReveal,
			parsedIdentifier=parsedIdentifier,
			cardType=cardType,
			hasCardText=inputCard["rules_text"] != "" if "rules_text" in inputCard else None,
			hasFlavorText=inputCard["flavor_text"] != "" if "flavor_text" in inputCard else None,
			isEpic=outputCard["rarity"] == GlobalConfig.translation.EPIC,
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
	outputCard["setCode"] = parsedIdentifier.setCode

	# Always get the artist from the parsed data, since in the input data it often only lists the first artist when there's multiple, so it's not reliable
	outputCard["artistsText"] = ocrResult.artistsText.lstrip(". ").replace("’", "'").replace("|", "l").replace("NM", "M")
	oldArtistsText = outputCard["artistsText"]
	outputCard["artistsText"] = re.sub(r"^[l[]", "I", outputCard["artistsText"])
	while re.search(r" [a-zA0-9ÿI|(\\/_+.,;'”#=—-]{1,2}$", outputCard["artistsText"]):
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
	outputCard["artistsText"] = re.sub("Le[éô]n", "León", outputCard["artistsText"])
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
	elif outputCard["name"].isupper() and outputCard["name"] not in ("B.E.N.", "I2I"):
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
	if "variants" in inputCard:
		outputImageData: Dict[str, str] = {}
		normalImageUrl = None
		foilTypes: List[str] = []
		varnishType = None
		for inputImageVariantData in inputCard["variants"]:
			imageType = inputImageVariantData["variant_id"]
			if imageType == "Regular":
				# Normal version
				outputImageData["full"] = _cleanUrl(inputImageVariantData["detail_image_url"])
				normalImageUrl = inputImageVariantData["detail_image_url"]
				if "foil_mask_url" in inputImageVariantData:
					outputImageData["foilMask"] = inputImageVariantData["foil_mask_url"]
				if "foil_top_layer_mask_url" in inputImageVariantData:
					# Despite being called 'foil', this is the varnish mask; foil data is in a different ImageVariant dictionary
					outputImageData["varnishMask"] = _cleanUrl(inputImageVariantData["foil_top_layer_mask_url"])
				foilTypes.append(inputImageVariantData.get("foil_type", "None"))
				if "foil_top_layer" in inputImageVariantData:
					varnishType = inputImageVariantData["foil_top_layer"]
			elif imageType == "Foiled":
				# Foil version
				if "foilMask" in outputImageData:
					_logger.warning(f"'Foiled' image data of {CardUtil.createCardIdentifier(outputCard)} contains a foil mask, but it was already set")
				else:
					outputImageData["foilMask"] = inputImageVariantData["foil_mask_url"]
				if normalImageUrl and inputImageVariantData["detail_image_url"] != normalImageUrl:
					# Foil basic art differs from normal art (missing black edge, etc), store it
					outputImageData["fullFoil"] = _cleanUrl(inputImageVariantData["detail_image_url"])
				foilTypes.append(inputImageVariantData["foil_type"])
				if "foil_top_layer" in inputImageVariantData:
					if varnishType is None:
						varnishType = inputImageVariantData["foil_top_layer"]
					elif varnishType != inputImageVariantData["foil_top_layer"]:
						_logger.warning(f"Varnish type is both '{varnishType}' and '{inputImageVariantData['foil_top_layer']}' in card {CardUtil.createCardIdentifier(outputCard)}; Keeping '{varnishType}'")

		if foilTypes:
			outputCard["foilTypes"] = foilTypes
		elif not isExternalReveal:
			# We can't know the foil type(s) of externally revealed cards, so not having the data at all is better than adding possibly wrong data
			# 'Normal' (so non-promo non-Enchanted) cards exist in unfoiled and silver-foiled types, so just default to that if no explicit foil type is provided
			outputCard["foilTypes"] = ["None", "Silver"]
		if varnishType:
			outputCard["varnishType"] = varnishType
		if "thumbnail_url" in inputCard:
			outputImageData["thumbnail"] = _cleanUrl(inputCard["thumbnail_url"])
		else:
			_logger.warning(f"Missing thumbnail URL for {CardUtil.createCardIdentifier(outputCard)}")
		if outputImageData:
			outputImageData = {key: outputImageData[key] for key in sorted(outputImageData)}
			outputCard["images"] = outputImageData
		else:
			_logger.error(f"Unable to determine any images for {CardUtil.createCardIdentifier(outputCard)}")
	elif "imageUrl" in inputCard:
		outputCard["images"] = {"full": inputCard["imageUrl"]}
	else:
		_logger.error(f"Card {CardUtil.createCardIdentifier(outputCard)} does not contain any image URLs")

	# Store relations to other cards, like (non-)Enchanted and (non-)Promo cards
	otherRelatedCards = relatedCards.getOtherRelatedCards(outputCard["setCode"], outputCard["id"])
	if otherRelatedCards.epicId:
		outputCard["epicId"] = otherRelatedCards.epicId
	elif otherRelatedCards.nonEpicId:
		outputCard["baseId"] = otherRelatedCards.nonEpicId
	if otherRelatedCards.enchantedId:
		outputCard["enchantedId"] = otherRelatedCards.enchantedId
	elif otherRelatedCards.nonEnchantedId:
		outputCard["nonEnchantedId"] = otherRelatedCards.nonEnchantedId
		outputCard["baseId"] = otherRelatedCards.nonEnchantedId
	if otherRelatedCards.iconicId:
		outputCard["iconicId"] = otherRelatedCards.iconicId
	elif otherRelatedCards.nonIconicId:
		outputCard["baseId"] = otherRelatedCards.nonIconicId
	if otherRelatedCards.nonPromoId:
		outputCard["nonPromoId"] = otherRelatedCards.nonPromoId
		if "baseId" in outputCard:
			_logger.error(f"baseId is already set to {outputCard['baseId']} from a rarity, not setting it to non-promo ID {otherRelatedCards.nonPromoId} for card {CardUtil.createCardIdentifier(outputCard)}")
		outputCard["baseId"] = otherRelatedCards.nonPromoId
	elif otherRelatedCards.promoIds:
		outputCard["promoIds"] = otherRelatedCards.promoIds
	if otherRelatedCards.otherVariantIds:
		outputCard["variantIds"] = otherRelatedCards.otherVariantIds
		outputCard["variant"] = parsedIdentifier.variant
	if otherRelatedCards.reprintedAsIds:
		outputCard["reprintedAsIds"] = otherRelatedCards.reprintedAsIds
	elif otherRelatedCards.reprintOfId:
		outputCard["reprintOfId"] = otherRelatedCards.reprintOfId

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
				if _KEYWORD_REGEX.match(remainingTextLine):
					keywordLines.append(remainingTextLine)
				# Some cards list keyword abilities without reminder text, sometimes multiple separated by commas
				elif ", " in remainingTextLine and not remainingTextLine.endswith("."):
					remainingTextLineParts = remainingTextLine.split(", ")
					for remainingTextLinePart in remainingTextLineParts:
						if not _KEYWORD_REGEX_WITHOUT_REMINDER.match(remainingTextLinePart.rstrip()):
							break
					else:
						# Sentence is single-word comma-separated parts, assume it's a list of keyword abilities
						keywordLines.extend(remainingTextLineParts)
				elif _KEYWORD_REGEX_WITHOUT_REMINDER.match(remainingTextLine):
					# Single words, possibly followed by a number, but not followed by a period, are assumed to be keywords
					keywordLines.append(remainingTextLine)
				if keywordLines:
					for keywordLine in keywordLines:
						abilities.append({"type": "keyword", "fullText": keywordLine.rstrip()})
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
			abilityName = re.sub(r"(?<=\w) ?[.7|»”©(\"=~]$", "", abilityName)
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
			if GlobalConfig.language in (Language.ENGLISH, Language.FRENCH) and subtype != "Floodborn" and re.match(r"^[EF][il][ao][aeo]d[^b]?b?[^b]?[aeo](r[an][es+-]?|m)$", subtype):
				_logger.debug(f"Correcting '{subtype}' to 'Floodborn'")
				subtypes[subtypeIndex] = "Floodborn"
			elif GlobalConfig.language == Language.ENGLISH and subtype != "Hero" and re.match(r"e?H[eo]r[aeos]", subtype):
				subtypes[subtypeIndex] = "Hero"
			elif re.match("I?Hl?usion", subtype):
				subtypes[subtypeIndex] = "Illusion"
			elif GlobalConfig.language == Language.ITALIAN and subtype == "lena":
				subtypes[subtypeIndex] = "Iena"
			elif subtype == "Hros":
				subtypes[subtypeIndex] = "Héros"
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
	externalLinksCorrection: Optional[List[str]] = None  # externalLinks depends on correct fullIdentifier, which may have a correction, but it also might need a correction itself. So store it for now, and correct it later
	fullTextCorrection: Optional[List[str]] = None  # Since the fullText gets created as the last step, if there is a correction for it, save it for later
	forceAbilityTypeAtIndex: Dict[int, str] = {}  # index to ability type
	newlineAfterLabelIndex: int = -1
	mergeEffectIndexWithPrevious: int = -1
	moveAbilityAtIndexToIndex: Optional[List[int, int]] = None
	skipFullTextSectionMergeAtIndex: int = -1
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
		if "_insertAbilityAtIndex" in cardDataCorrections:
			if "abilities" not in outputCard:
				outputCard["abilities"]: List[Dict] = []
			insertAbilityData: List = cardDataCorrections.pop("_insertAbilityAtIndex")
			while insertAbilityData:
				insertAbilityIndex = insertAbilityData.pop(0)
				insertAbilityText = insertAbilityData.pop(0)
				outputCard["abilities"].insert(insertAbilityIndex, {"effect": insertAbilityText, "fullText": insertAbilityText})
				if insertAbilityData and isinstance(insertAbilityData[0], str):
					outputCard["abilities"][insertAbilityIndex]["name"] = insertAbilityData.pop(0)
		for correctionAbilityField, abilityTypeCorrection in _ABILITY_TYPE_CORRECTION_FIELD_TO_ABILITY_TYPE.items():
			if correctionAbilityField in cardDataCorrections:
				abilityIndexToCorrect = cardDataCorrections.pop(correctionAbilityField)
				if abilityIndexToCorrect in forceAbilityTypeAtIndex:
					_logger.error(f"Ability at index {abilityIndexToCorrect} in card {CardUtil.createCardIdentifier(outputCard)} is being corrected to two types: '{forceAbilityTypeAtIndex[abilityIndexToCorrect]}' and '{abilityTypeCorrection}'")
				forceAbilityTypeAtIndex[abilityIndexToCorrect] = abilityTypeCorrection
		newlineAfterLabelIndex: int = cardDataCorrections.pop("_newlineAfterLabelIndex", -1)
		mergeEffectIndexWithPrevious: int = cardDataCorrections.pop("_mergeEffectIndexWithPrevious", -1)
		effectAtIndexIsAbility: Union[int, List[int, str]] = cardDataCorrections.pop("_effectAtIndexIsAbility", -1)
		effectAtIndexIsFlavorText: int = cardDataCorrections.pop("_effectAtIndexIsFlavorText", -1)
		externalLinksCorrection: Optional[List[str]] = cardDataCorrections.pop("externalLinks", None)
		fullTextCorrection: Optional[List[str]] = cardDataCorrections.pop("fullText", None)
		addNameToAbilityAtIndex: Optional[List[Union[int, str]]] = cardDataCorrections.pop("_addNameToAbilityAtIndex", None)
		moveAbilityAtIndexToIndex: Optional[List[Union[int, int]]] = cardDataCorrections.pop("_moveAbilityAtIndexToIndex", None)
		splitAbilityNameAtIndex: Optional[List[Union[int, str]]] = cardDataCorrections.pop("_splitAbilityNameAtIndex", None)
		skipFullTextSectionMergeAtIndex: int = cardDataCorrections.pop("_skipFullTextSectionMergeAtIndex", -1)
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
			# Splitting effects may lead to one or more effects being a keyword ability instead, correct that
			for effectIndex in range(len(outputCard["effects"]) - 1, -1, -1):
				effectText = outputCard["effects"][effectIndex]
				if _KEYWORD_REGEX.match(effectText) or _KEYWORD_REGEX_WITHOUT_REMINDER.match(effectText):
					_logger.info(f"Effect at index {effectIndex} is a keyword ability, moving it to 'abilities', in card {CardUtil.createCardIdentifier(outputCard)}")
					outputCard["effects"].pop(effectIndex)
					if "abilities" not in outputCard:
						outputCard["abilities"] = []
					outputCard["abilities"].insert(0, {"effect": effectText, "fullText": effectText, "type": "keyword"})
			if len(outputCard["effects"]) == 0:
				del outputCard["effects"]
		# Sometimes the ability name doesn't get recognised properly during fallback parsing, so there's a manual correction for it
		if splitAbilityNameAtIndex:
			ability: Dict[str, str] = outputCard["abilities"][splitAbilityNameAtIndex[0]]
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
			if ability.get("type", None) == "keyword" or ("type" not in ability and not ability.get("name", None) and (_KEYWORD_REGEX.match(ability.get("fullText", ability["effect"])) or _KEYWORD_REGEX_WITHOUT_REMINDER.match(ability.get("fullText", ability["effect"])))):
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
					if " " in keyword:
						keyword, keywordValue = keyword.rsplit(" ", 1)
					else:
						# There should've been a space between the keyword and the numeric value, but something went wrong with parsing. Try to add it back in
						_logger.debug(f"No space found in keyword-keywordvalue pair {keyword!r}, splitting by regular expression")
						keywordNameValueMatch = re.match(r"(\w+)(\d+)", keyword)
						keyword = keywordNameValueMatch.group(1)
						keywordValue = keywordNameValueMatch.group(2)
				elif keyword[-3].isnumeric():
					# From set 9 on, Shift gets written as "Shift x {ink}", check for that too
					keyword, keywordValue, inkSymbol = keyword.rsplit(" ", 2)
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
				# Some static abilities give characters such an activated ability, don't trigger on that (by ignoring quotemarks before a dash)
				activatedAbilityMatch = re.search(r"^[^\"“„«]+(\s)([-–—])(\s)", ability["effect"])

				# Activated abilities require a cost, a dash, and then an effect
				# Some cards contain their own name (e.g. 'Dalmatian Puppy - Tail Wagger', ID 436), don't trigger on that dash either
				if activatedAbilityMatch and (outputCard["name"] not in ability["effect"] or ability["effect"].index(outputCard["name"]) > activatedAbilityMatch.start(1)):
					# Assume there's a payment text in there
					ability["type"] = "activated"
					ability["costsText"] = ability["effect"][:activatedAbilityMatch.start(1)]
					ability["effect"] = ability["effect"][activatedAbilityMatch.end(3):]
				elif GlobalConfig.language == Language.ENGLISH:
					if re.match("Once (during your|per) turn, you may", ability["effect"]):
						ability["type"] = "activated"
					elif (ability["effect"].startswith("At the start of") or ability["effect"].startswith("At the end of") or re.search(r"(^W|,[ \n]w)hen(ever)?[ \n]", ability["effect"])
							or re.search("when (he|she|it|they) enters play", ability["effect"])):
						ability["type"] = "triggered"
				elif GlobalConfig.language == Language.FRENCH:
					if re.match("Une fois (durant votre|par) tour, vous pouvez", ability["effect"]):
						ability["type"] = "activated"
					elif (ability["effect"].startswith("Au début de chacun") or re.match(r"Au\sdébut\sd[eu](\svotre)?\stour\b", ability["effect"]) or ability["effect"].startswith("À la fin d") or
						re.search(r"(^L|\bl)orsqu(e|'une?|'il)\b", ability["effect"]) or re.search(r"(^À c|^C|,\sc)haque\sfois", ability["effect"]) or
						re.match("Si (?!vous avez|un personnage)", ability["effect"]) or re.search("gagnez .+ pour chaque", ability["effect"]) or
						re.search(r"une carte est\splacée", ability["effect"])):
						ability["type"] = "triggered"
				elif GlobalConfig.language == Language.GERMAN:
					if re.match(r"Einmal (pro|während deines) Zug(es)?,? darfst\sdu", ability["effect"]):
						ability["type"] = "activated"
					elif (re.match(r"Wenn(\sdu)?\sdiese", ability["effect"]) or re.match(r"Wenn\seiner\sdeiner\sCharaktere", ability["effect"]) or re.search(r"(^J|\bj)edes\sMal\b", ability["effect"]) or
						  re.match(r"Einmal\swährend\sdeines\sZuges\b", ability["effect"]) or ability["effect"].startswith("Einmal pro Zug, wenn") or
						  re.search(r"(^Z|\bz)u\sBeginn\s(deines|von\s\w+)\sZug", ability["effect"]) or re.match(r"Am\sEnde\s(deines|des)\sZuges", ability["effect"]) or
						  re.match(r"Falls\sdu\sGestaltwandel\sbenutzt\shas", ability["effect"]) or "wenn du eine Karte ziehst" in ability["effect"] or
						  re.search(r"\bwährend\ser\seinen?(\s|\w)+herausfordert\b", ability["effect"]) or re.search(r"wenn\sdieser\sCharakter\szu\seinem\sOrt\sbewegt", ability["effect"]) or
						  re.match(r"Wenn\s\w+\sdiese[nrs]\s\w+\sausspielt", ability["effect"]) or re.match(r"Wenn\sdu\seine.+ausspielst", ability["effect"], flags=re.DOTALL)):
						ability["type"] = "triggered"
				elif GlobalConfig.language == Language.ITALIAN:
					if re.match(r"Una\svolta\s(durante\sil\stuo|per)\sturno,\spuoi\spagare", ability["effect"]):
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
						costSeparatorDash = None
						if "rules_text" in inputCard:
							costSeparatorDashMatch = re.search(r"\s([-–—])\s", inputCard["rules_text"])
							if costSeparatorDashMatch:
								costSeparatorDash = costSeparatorDashMatch.group(1)
							else:
								_logger.error(f"Unable to find cost separator dash match in '{inputCard['rules_text']}' in {CardUtil.createCardIdentifier(outputCard)}")
						if not costSeparatorDash:
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
	outputCard["externalLinks"] = threadLocalStorage.externalIdsHandler.getExternalLinksForCard(parsedIdentifier, "enchantedId" in outputCard)
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
		for abilityIndex, ability in enumerate(outputCard["abilities"]):  # type: Dict[str, str]
			# Some cards have multiple keyword abilities on one line without reminder text. They'll be stored as separate abilities, but they should be in one section
			if abilityIndex != skipFullTextSectionMergeAtIndex and ability["type"] == "keyword" and _KEYWORD_REGEX_WITHOUT_REMINDER.match(ability["fullText"]):
				if previousAbilityWasKeywordWithoutReminder:
					# Add this keyword to the previous section, since that's how it's on the card
					fullTextSections[-1] += ", " + ability["fullText"]
				else:
					previousAbilityWasKeywordWithoutReminder = True
					fullTextSections.append(ability["fullText"])
			else:
				if abilityIndex == skipFullTextSectionMergeAtIndex:
					_logger.debug(f"Skipping joining keyword ability at index {abilityIndex} with the previous line in card {CardUtil.createCardIdentifier(outputCard)}")
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
	if historicData:
		outputCard["historicData"] = historicData

	allowedInFormats: AllowedInFormats = allowedCardsHandler.getAllowedInFormatsForCard(outputCard["id"], relatedCards.printedInSets)
	outputCard["allowedInTournamentsFromDate"] = allowedInFormats.allowedInTournamentsFromDate
	outputCard["allowedInFormats"] = {}
	for formatName, allowedInFormat in (("Core", allowedInFormats.allowedInCore), ("Infinity", allowedInFormats.allowedInInfinity)):
		outputCard["allowedInFormats"][formatName]: Dict[str, Union[bool, str]] = {"allowed": allowedInFormat.allowed}
		if allowedInFormat.allowedUntil:
			outputCard["allowedInFormats"][formatName]["allowedUntilDate"] = allowedInFormat.allowedUntil
		if allowedInFormat.bannedSince:
			outputCard["allowedInFormats"][formatName]["bannedSinceDate"] = allowedInFormat.bannedSince

	# Sort the dictionary by key
	outputCard = {key: outputCard[key] for key in sorted(outputCard)}
	return outputCard

def _cleanUrl(url: str) -> str:
	"""
	Clean up the provided URL. This removes the 'checksum' URL parameter, since it's not needed
	:param url: The URL to clean up
	:return: The cleaned-up URL
	"""
	return url.split('?', 1)[0]

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
