import json, os, re
from typing import Dict, List, Union

import GlobalConfig
from util import JsonUtil, Language, LorcanaSymbols, Translations


def compareInputToOutput(cardIdsToVerify: Union[List[int], None]):
	inputFilePath = os.path.join("downloads", "json", f"carddata.{GlobalConfig.language.code}.json")
	if not os.path.isfile(inputFilePath):
		print("Input file does not exist. Please run the 'download' action for the specified language first")
		return
	outputFilePath = os.path.join("output", "generated", GlobalConfig.language.code, "allCards.json")
	if not os.path.isfile(outputFilePath):
		print("Output file does not exist. Please run the 'parse' action for the specified language first")
		return

	with open(inputFilePath, "r", encoding="utf-8") as inputFile:
		inputCardStore = json.load(inputFile)
	with open(outputFilePath, "r", encoding="utf-8") as outputFile:
		outputCardStore = json.load(outputFile)
	idToEnglishOutputCard = {}
	englishRarities = ()
	currentLanguageRarities = ()
	if GlobalConfig.language != Language.ENGLISH:
		englishOutputFilePath = os.path.join("output", "generated", Language.ENGLISH.code, "allCards.json")
		if os.path.isfile(englishOutputFilePath):
			with open(englishOutputFilePath, "r", encoding="utf-8") as englishOutputFile:
				englishOutputCardStore = json.load(englishOutputFile)
				for englishCard in englishOutputCardStore["cards"]:
					idToEnglishOutputCard[englishCard["id"]] = englishCard
		else:
			print("WARNING: English output file doesn't exist, skipping comparison")
		englishRarities = (Translations.ENGLISH.COMMON, Translations.ENGLISH.UNCOMMON, Translations.ENGLISH.RARE, Translations.ENGLISH.SUPER, Translations.ENGLISH.LEGENDARY, Translations.ENGLISH.ENCHANTED, Translations.ENGLISH.SPECIAL)
		currentTranslation = Translations.getForLanguage(GlobalConfig.language)
		currentLanguageRarities = (currentTranslation.COMMON, currentTranslation.UNCOMMON, currentTranslation.RARE, currentTranslation.SUPER, currentTranslation.LEGENDARY, currentTranslation.ENCHANTED, currentTranslation.SPECIAL)

	idToInputCard = {}
	for cardtype, cardlist in inputCardStore["cards"].items():
		for inputCard in cardlist:
			idToInputCard[inputCard["culture_invariant_id"]] = inputCard

	# Some of the data in the input file is wrong, which leads to false positives. Get override values here, to prevent that
	# It's organised by language, then by card ID, then by inputCard field, where the value is a pair of strings (regex match and correction), or a new number if it's a numeric field
	overridesFilePath = os.path.join("output", f"verifierOverrides_{GlobalConfig.language.code}.json")
	if os.path.isfile(overridesFilePath):
		inputOverrides = JsonUtil.loadJsonWithNumberKeys(overridesFilePath)
		print(f"Overrides file found, loaded {len(inputOverrides):,} input overrides")
	else:
		print("No overrides file found")
		inputOverrides = {}

	openQuotemark = "„" if GlobalConfig.language == Language.GERMAN else "“"
	closeQuotemark = "“" if GlobalConfig.language == Language.GERMAN else "”"
	cardDifferencesCount = 0
	for outputCard in outputCardStore["cards"]:
		if cardIdsToVerify and outputCard["id"] not in cardIdsToVerify:
			continue
		if outputCard.get("isExternalReval", False):
			print(f"Skipping external reveal card '{outputCard['fullName']}' (ID {outputCard['id']})")
			continue
		if outputCard["id"] not in idToInputCard:
			print(f"WARNING: '{outputCard['fullName']}' (ID {outputCard['id']}) does not exist in the input file, skipping")
			continue
		cardId = outputCard["id"]
		inputCard = idToInputCard[cardId]

		# Implement overrides
		symbolCountChange = None
		if cardId in inputOverrides:
			symbolCountChange = inputOverrides[cardId].pop("_symbolCountChange", None)
			for fieldName, correctionsTuple in inputOverrides[cardId].items():
				for correctionIndex in range(0, len(correctionsTuple), 2):
					regexMatch = correctionsTuple[correctionIndex]
					correctionText = correctionsTuple[correctionIndex+1]
					if isinstance(regexMatch, int):
						if inputCard[fieldName] == regexMatch:
							inputCard[fieldName] = correctionText
						else:
							print(f"ERROR: Correction override number {regexMatch} does not match actual input card value {inputCard[fieldName]} for field '{fieldName}' in card {cardId}")
					else:
						inputCard[fieldName], correctionCount = re.subn(regexMatch, correctionText, inputCard[fieldName])
						if correctionCount == 0:
							print(f"ERROR: Invalid correction override {regexMatch!r} for field '{fieldName}' for card ID {cardId}")

		# Compare rules text
		if inputCard.get("rules_text", None) or outputCard["fullText"]:
			if inputCard.get("rules_text", None):
				inputRulesText = inputCard["rules_text"].replace("\\", "")
				inputRulesText = re.sub(r"(?<=\w)’(?=\w)", "'", inputRulesText)
				inputRulesText = inputRulesText.replace("\u00a0", " " if GlobalConfig.language == Language.FRENCH else "").replace("  ", " ")
				inputRulesText = inputRulesText.replace(" \"", " “")
				inputRulesText = re.sub("\"( |$)", "”\\1", inputRulesText)
				# Sometimes there's no space between the previous ability text and the next label or ability, fix that
				inputRulesText = re.sub(r"([).])([A-Z])", r"\1 \2", inputRulesText)
				# Some cards have an m-dash instead of normal 'minus' dash in front of numbers
				inputRulesText = re.sub(r"[–—](?=\d)", "-", inputRulesText)
				if GlobalConfig.language == Language.ENGLISH:
					inputRulesText = inputRulesText.replace("teammates’ ", "teammates' ").replace("players’ ", "players' ").replace("Illumineers’ ", "Illumineers' ")
				elif GlobalConfig.language == Language.FRENCH:
					# Exclamation marks etc. should be preceded by a space
					inputRulesText = re.sub(r"(?<=\w)([?!:])", r" \1", inputRulesText)
					inputRulesText = re.sub("\\.{2,}", "…", inputRulesText)
				elif GlobalConfig.language == Language.ITALIAN:
					inputRulesText = inputRulesText.replace("...", "…")
			else:
				inputRulesText = ""

			if outputCard["fullText"]:
				outputRulesText = outputCard["fullText"].replace(" -\n", " - ").replace("-\n", "-").replace("\n", " ")
				# Remove all the Lorcana symbols:
				outputRulesText = outputRulesText.replace(f"{LorcanaSymbols.EXERT},", ",")
				outputRulesText = re.sub(fr" ?[{LorcanaSymbols.EXERT}{LorcanaSymbols.INK}{LorcanaSymbols.LORE}{LorcanaSymbols.STRENGTH}{LorcanaSymbols.WILLPOWER}{LorcanaSymbols.INKWELL}] ?", " ", outputRulesText).lstrip()
				outputRulesText = re.sub(r"(?<=\d) \)", ")", outputRulesText)
				outputRulesText = outputRulesText.replace("  ", " ").replace(" .", ".")
			else:
				outputRulesText = ""

			if inputRulesText != outputRulesText:
				cardDifferencesCount += 1
				_printDifferencesDescription(outputCard, "rules text", inputRulesText, outputRulesText)

		# Compare flavor text
		if inputCard.get("flavor_text", None) or "flavorText" in outputCard:
			if "flavor_text" in inputCard and inputCard["flavor_text"] != "ERRATA":
				inputFlavorText: str = inputCard["flavor_text"].replace("\u00a0", "").replace("‘", "'").replace("’", "'").replace("<", "").replace(">", "").rstrip()
				# '%' seems to be a substitute for a newline character
				inputFlavorText = inputFlavorText.replace("—%", "—")
				inputFlavorText = re.sub("%— (?=[A-Z])", " —", inputFlavorText)
				inputFlavorText = re.sub(r"(?<!\d) ?% ?", " ", inputFlavorText)
				inputFlavorText = inputFlavorText.replace("  ", " ")
				if inputFlavorText.endswith(" ERRATA"):
					inputFlavorText = inputFlavorText.rsplit(" ", 1)[0]
				if GlobalConfig.language == Language.ENGLISH:
					# Input text always has a space after written-out ellipsis, while the card doesn't, remove it, unless it's just before a quote attribution dash
					inputFlavorText = re.sub(r"\.\.\. (?!—)", "...", inputFlavorText)
				else:
					# Use the ellipsis character instead of three separate periods
					inputFlavorText = inputFlavorText.replace("...", "…")
				if GlobalConfig.language == Language.FRENCH:
					inputFlavorText = re.sub(r"(?<=\w|’|')([?!:])", r" \1", inputFlavorText)
				elif GlobalConfig.language == Language.GERMAN:
					# Quote attribution uses the wrong dash and doesn't have a space in the input text, but it does on the card. Ignore the difference
					# The second set use a short n-dash instead of a long m-dash, correct for that
					inputFlavorText = re.sub(r"(?<=\s)[–—](?=[A-Z])", "–" if 204 < cardId <= 432 else "—", inputFlavorText)
					# Ellipsis are always preceded by a space
					inputFlavorText = re.sub(r"(?<=\w)…", " …", inputFlavorText)
			else:
				inputFlavorText = ""

			if "flavorText" in outputCard:
				outputFlavorText = outputCard['flavorText']
				if outputFlavorText.count(openQuotemark) != outputFlavorText.count(closeQuotemark):
					cardDifferencesCount += 1
					print(f"{outputCard['fullName']} (ID {cardId}, {outputCard['fullIdentifier']}): Mismatched count of open and close quotemarks in flavor text {outputFlavorText!r}")
				outputFlavorText = outputFlavorText.replace("“", "").replace("”", "").replace("„", "").replace("‘", "'").replace("’", "'")
				# Don't put a space between ellipses and the next word if there's a newline after the ellipsis...
				outputFlavorText = re.sub(r"(?<=\.\.\.)\n(?=\w)", "", outputFlavorText)
				# ... nor if the ellipsis are the first thing on a newline
				outputFlavorText = re.sub(r"(?<=\w)\n(?=\.\.\.)", "", outputFlavorText)
				# Newlines are spaces in the input text, except after connecting dashes just before a newline
				outputFlavorText = outputFlavorText.replace("-\n", "-").replace("—\n", "—").replace("\n", " ")
			else:
				outputFlavorText = ""

			if outputFlavorText != inputFlavorText:
				cardDifferencesCount += 1
				_printDifferencesDescription(outputCard, "flavor text", inputFlavorText, outputFlavorText)

		# Compare subtypes
		if inputCard["subtypes"] or "subtypes" in outputCard:
			inputSubtypesText = LorcanaSymbols.SEPARATOR_STRING.join(inputCard["subtypes"])
			outputSubtypesText = LorcanaSymbols.SEPARATOR_STRING.join(outputCard.get("subtypes", []))
			if inputSubtypesText != outputSubtypesText:
				cardDifferencesCount += 1
				_printDifferencesDescription(outputCard, "subtypes", inputSubtypesText, outputSubtypesText)

		# Cards beyond the 'normal' numbering are either Enchanted or otherwise Special, check if that's stored properly
		if outputCard["rarity"] == GlobalConfig.translation.ENCHANTED and "nonEnchantedId" not in outputCard and "nonPromoId" not in outputCard:
			cardDifferencesCount += 1
			print(f"{outputCard['fullName']} (ID {outputCard['id']}) should have a non-enchanted ID or non-promo ID field, but it doesn't")
		elif "Q" not in outputCard["setCode"] and outputCard["rarity"] == GlobalConfig.translation.SPECIAL and "nonPromoId" not in outputCard:
			cardDifferencesCount += 1
			print(f"{outputCard['fullName']} (ID {outputCard['id']}) should have a non-promo ID field, but it doesn't")

		inputIdentifier = inputCard["card_identifier"].replace(" ", LorcanaSymbols.SEPARATOR_STRING).replace("1TFC", "1 TFC")
		outputIdentifier = outputCard["fullIdentifier"].lstrip("0")  # The input identifiers don't have the leading zero, so strip it here too
		if inputIdentifier != outputIdentifier:
			cardDifferencesCount += 1
			_printDifferencesDescription(outputCard, "fullIdentifier", inputIdentifier, outputCard["fullIdentifier"])

		# Compare basic fields
		for inputField, outputField in (("author", "artistsText"), ("ink_cost", "cost"), ("move_cost", "moveCost"), ("quest_value", "lore"), ("strength", "strength"), ("willpower", "willpower")):
			inputValue = inputCard.get(inputField, None)
			outputValue = outputCard.get(outputField, None)
			if inputValue is None and outputValue is None:
				continue
			if inputValue != outputValue:
				cardDifferencesCount += 1
				_printDifferencesDescription(outputCard, outputField, str(inputValue), str(outputValue))

		# Check if the story is properly filled in
		# This isn't strictly speaking a verification since it doesn't compare with anything in the input file, but it is important to know about missing stories
		if not outputCard.get("story", None):
			cardDifferencesCount += 1
			print(f"WARNING: {outputCard['fullName']} (ID {outputCard['id']}) does not have a valid story set")

		# Check if the whitespace is correct
		for symbol in LorcanaSymbols.ALL_SYMBOLS:
			# Symbols should have whitespace around them
			if re.search(f"[^ \n“„+]{symbol}", outputCard["fullText"]) or re.search(fr"{symbol}[^ \n.,)—-]", outputCard["fullText"]):
				cardDifferencesCount += 1
				print(f"{cardId}: Symbol '{symbol}' doesn't have whitespace around it")
		if re.search(r"\s{2,}", outputCard["fullText"]):
			cardDifferencesCount += 1
			print(f"{cardId}: Fulltext has two or more whitespace characters in a row")

		# If this isn't English, compare with the English results
		# English is easier to manually verify, so this is done to prevent mistakes or oddities, like ability type mismatches between languages
		if idToEnglishOutputCard:
			englishCard = idToEnglishOutputCard[outputCard["id"]]
			cardId = outputCard["id"]
			for fieldname in ('abilities', 'artistsText', 'enchantedId', 'cost', 'effects', 'fullTextSections', 'inkwell', 'keywordAbilities', 'lore',
							  'maxCardsInDeck', 'moveCost', 'nonEnchantedId', 'nonPromoId', 'number', 'strength', 'subtypes', 'variant', 'variandIds', 'willPower'):
				if fieldname not in outputCard and fieldname not in englishCard:
					continue
				if fieldname in outputCard and fieldname not in englishCard:
					cardDifferencesCount += 1
					print(f"{cardId}: '{fieldname}' exists in {GlobalConfig.language.englishName} but not in English")
				elif fieldname not in outputCard and fieldname in englishCard:
					cardDifferencesCount += 1
					print(f"{cardId}: '{fieldname}' doesn't exist in {GlobalConfig.language.englishName} but does in English")
				elif isinstance(outputCard[fieldname], list):
					if len(outputCard[fieldname]) != len(englishCard[fieldname]):
						cardDifferencesCount += 1
						print(f"{cardId}: '{fieldname}' doesn't have same length in {GlobalConfig.language.englishName} and English: length is {len(outputCard[fieldname])} in {GlobalConfig.language.englishName} but {len(englishCard[fieldname])} in English")
				elif outputCard[fieldname] != englishCard[fieldname]:
					cardDifferencesCount += 1
					print(f"{cardId}: '{fieldname}' differs between {GlobalConfig.language.englishName} '{outputCard[fieldname]}' and English '{englishCard[fieldname]}'")
			if outputCard["fullText"] or englishCard["fullText"]:
				for symbol in LorcanaSymbols.ALL_SYMBOLS:
					expectedCount = englishCard["fullText"].count(symbol)
					if GlobalConfig.language == Language.FRENCH and symbol == "¤" and re.search(r"Soutien.+\(", outputCard["fullText"], flags=re.DOTALL):
						# While most languages use two strength symbols in the Support reminder text, French uses just one. To prevent false positives and negatives, adjust our expectations
						expectedCount -= 1
					if symbolCountChange and symbol in symbolCountChange:
						expectedCount += symbolCountChange[symbol]
					if outputCard["fullText"].count(symbol) != expectedCount:
						cardDifferencesCount += 1
						print(f"{cardId}: Symbol '{symbol}' occurs {outputCard['fullText'].count(symbol)} times in {GlobalConfig.language.englishName} fullText but {expectedCount} was expected based on English")
			if "abilities" in outputCard and "abilities" in englishCard:
				for abilityIndex in range(min(len(outputCard["abilities"]), len(englishCard["abilities"]))):
					if outputCard["abilities"][abilityIndex]["type"] != englishCard["abilities"][abilityIndex]["type"]:
						cardDifferencesCount += 1
						print(f"{cardId}: Ability index {abilityIndex} type mismatch, {GlobalConfig.language.englishName} type is '{outputCard['abilities'][abilityIndex]['type']}', English type is '{englishCard['abilities'][abilityIndex]['type']}'")
			# Compare rarities
			if currentLanguageRarities.index(outputCard["rarity"]) != englishRarities.index(englishCard["rarity"]):
				cardDifferencesCount += 1
				print(f"{cardId}: {GlobalConfig.language.englishName} rarity is {englishRarities[currentLanguageRarities.index(outputCard['rarity'])]} ({outputCard['rarity']}) but English rarity is {englishCard['rarity']}")
			# Compare Card Market URLs, except for the language code (Other external links are always the same, since they're based on IDs)
			if "cardmarketUrl" in outputCard["externalLinks"] and outputCard["externalLinks"]["cardmarketUrl"][:-1].replace(f"/{GlobalConfig.language.code}/", "/en/") != englishCard["externalLinks"]["cardmarketUrl"][:-1]:
				cardDifferencesCount += 1
				print(f"{cardId}: Cardmarket URL differs; {GlobalConfig.language.englishName} is {outputCard['externalLinks']['cardmarketUrl']}, English is {englishCard['externalLinks']['cardmarketUrl']}")

	print(f"----------\nFound {cardDifferencesCount:,} difference{'' if cardDifferencesCount == 1 else 's'} between input and output")

def _printDifferencesDescription(outputCard: Dict, fieldName: str, inputString: str, outputString: str):
	maxCharIndex = max(len(inputString), len(outputString))
	fieldDifferencesPointers = [" " for _ in range(maxCharIndex)]
	fieldDifferencesCount = 0
	for charIndex in range(maxCharIndex):
		if len(inputString) <= charIndex or len(outputString) <= charIndex or inputString[charIndex] != outputString[charIndex]:
			fieldDifferencesPointers[charIndex] = "^"
			fieldDifferencesCount += 1
	print(f"{outputCard['fullName']} (ID {outputCard['id']}, {outputCard['fullIdentifier']}), {fieldName}, {fieldDifferencesCount:,} difference{'' if fieldDifferencesCount == 1 else 's'}:\n"
		  f"  IN:  {inputString!r}\n"
		  f"  OUT: {outputString!r}\n"
		  f"        {''.join(fieldDifferencesPointers).rstrip()}")
