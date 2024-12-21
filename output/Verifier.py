import json, os, re
from typing import Dict, List, Union

import GlobalConfig
from util import Language, LorcanaSymbols, Translations


_subtypeSeparatorString = f" {LorcanaSymbols.SEPARATOR} "

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
		inputCard = idToInputCard[outputCard["id"]]

		# Compare rules text
		if inputCard.get("rules_text", None) or outputCard["fullText"]:
			if inputCard.get("rules_text", None):
				inputRulesText = inputCard["rules_text"].replace("–", "-").replace("\\", "")
				inputRulesText = re.sub(r"(?<=\w)’(?=\w)", "'", inputRulesText)
				inputRulesText = inputRulesText.replace("\u00a0", " " if GlobalConfig.language == Language.FRENCH else "").replace("  ", " ")
				# Sometimes there's no space between the previous ability text and the next label or ability, fix that
				inputRulesText = re.sub(r"([).])([A-Z])", r"\1 \2", inputRulesText)
				if GlobalConfig.language == Language.ENGLISH:
					inputRulesText = inputRulesText.replace("teammates’ ", "teammates' ").replace("players’ ", "players' ")
				elif GlobalConfig.language == Language.FRENCH:
					# Exclamation marks etc. should be preceded by a space
					inputRulesText = re.sub(r"(?<=\w)([?!:])", r" \1", inputRulesText)
					inputRulesText = re.sub("\\.{2,}", "…", inputRulesText)
			else:
				inputRulesText = ""

			if outputCard["fullText"]:
				outputRulesText = outputCard["fullText"].replace(" -\n", " - ").replace("-\n", "-").replace("\n", " ")
				# Remove all the Lorcana symbols:
				outputRulesText = outputRulesText.replace(f"{LorcanaSymbols.EXERT},", ",")
				outputRulesText = re.sub(fr" ?[{LorcanaSymbols.EXERT}{LorcanaSymbols.INK}{LorcanaSymbols.LORE}{LorcanaSymbols.STRENGTH}{LorcanaSymbols.WILLPOWER}{LorcanaSymbols.INKWELL}] ?", " ", outputRulesText).lstrip()
				outputRulesText = outputRulesText.replace("  ", " ").replace(" .", ".").replace("“", "\"").replace("”", "\"")
				if GlobalConfig.language == Language.FRENCH:
					# 'Alter' ('Shift') with special costs is followed by a colon, but that's missing from the input text, so remove it from the output too, otherwise comparison becomes impossible
					outputRulesText = outputRulesText.replace("Alter : ", "Alter ")
			else:
				outputRulesText = ""

			if inputRulesText != outputRulesText:
				cardDifferencesCount += 1
				_printDifferencesDescription(outputCard, "rules text", inputRulesText, outputRulesText)

		# Compare flavor text
		if inputCard.get("flavor_text", None) or "flavorText" in outputCard:
			if "flavor_text" in inputCard and inputCard["flavor_text"] != "ERRATA":
				inputFlavorText: str = inputCard["flavor_text"].replace("\u00a0", "").replace("‘", "'").replace("’", "'").replace("…", "...").replace(" ..", "..").replace(".. ", "..").replace("<", "").replace(">", "").replace("%", " ").rstrip()
				inputFlavorText = inputFlavorText.replace("  ", " ")
				# The quote attribution dash always has a space after it in the input text, but never on the actual card. Ignore that
				inputFlavorText = re.sub(" ([—-]) (?=[A-Z])", r" \1", inputFlavorText)
				if inputFlavorText.endswith(" ERRATA"):
					inputFlavorText = inputFlavorText.rsplit(" ", 1)[0]
				if GlobalConfig.language == Language.FRENCH:
					inputFlavorText = re.sub(r"(?<=\w)([?!:])", r" \1", inputFlavorText)
			else:
				inputFlavorText = ""

			if "flavorText" in outputCard:
				outputFlavorText = outputCard['flavorText']
				outputFlavorText = outputFlavorText.replace("“", "").replace("”", "").replace("‘", "'").replace("’", "'")
				outputFlavorText = outputFlavorText.replace("-\n", "-").replace("—\n", "—").replace("\n", " ")
				outputFlavorText = outputFlavorText.replace("…", "...").replace(" ..", "..").replace(".. ", "..")
			else:
				outputFlavorText = ""

			if outputFlavorText != inputFlavorText:
				cardDifferencesCount += 1
				_printDifferencesDescription(outputCard, "flavor text", inputFlavorText, outputFlavorText)

		# Compare subtypes
		if inputCard["subtypes"] or "subtypes" in outputCard:
			inputSubtypesText = _subtypeSeparatorString.join(inputCard["subtypes"])
			outputSubtypesText = _subtypeSeparatorString.join(outputCard.get("subtypes", []))
			if inputSubtypesText != outputSubtypesText:
				cardDifferencesCount += 1
				_printDifferencesDescription(outputCard, "subtypes", inputSubtypesText, outputSubtypesText)

		# Cards beyond the 'normal' numbering are either Enchanted or otherwise Special, check if that's stored properly
		if outputCard["rarity"] == GlobalConfig.translation.ENCHANTED and "nonEnchantedId" not in outputCard and "nonPromoId" not in outputCard:
			print(f"{outputCard['fullName']} (ID {outputCard['id']}) should have a non-enchanted ID or non-promo ID field, but it doesn't")
		elif "Q" not in outputCard["setCode"] and outputCard["rarity"] == GlobalConfig.translation.SPECIAL and "nonPromoId" not in outputCard:
			print(f"{outputCard['fullName']} (ID {outputCard['id']}) should have a non-promo ID field, but it doesn't")

		inputIdentifier = inputCard["card_identifier"].replace(" ", f" {LorcanaSymbols.SEPARATOR} ")
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

		# If this isn't English, compare with the English results
		# English is easier to manually verify, so this is done to prevent mistakes or oddities, like ability type mismatches between languages
		if idToEnglishOutputCard:
			englishCard = idToEnglishOutputCard[outputCard["id"]]
			cardId = outputCard["id"]
			for fieldname in ('abilities', 'artistsText', 'enchantedId', 'cost', 'effects', 'fullTextSections', 'historicData', 'inkwell', 'keywordAbilities',
							  'lore', 'moveCost', 'nonEnchantedId', 'nonPromoId', 'number', 'strength', 'subtypes', 'variant', 'variandIds', 'willPower'):
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
				for symbol in ("⟳", "⬡", "◊", "¤", "⛉", "◉", "•"):
					expectedCount = englishCard["fullText"].count(symbol)
					if GlobalConfig.language == Language.FRENCH and symbol == "¤" and "Soutien" in outputCard["fullText"]:
						# While most languages use two strength symbols in the Support reminder text, French uses just one. To prevent false positives and negatives, adjust our expectations
						expectedCount -= 1
					if outputCard["fullText"].count(symbol) != expectedCount:
						cardDifferencesCount += 1
						print(f"{cardId}: Symbol '{symbol}' occurs {outputCard['fullText'].count(symbol)} times in {GlobalConfig.language.englishName} fullText but {expectedCount} was expected based on English")
					# Check if the symbols have whitespace around them, since in previous verification steps we've ignored the symbols
					if re.search(f"[^ \n“]{symbol}", outputCard["fullText"]) or re.search(f"{symbol}[^ \n.,]", outputCard["fullText"]):
						cardDifferencesCount += 1
						print(f"{cardId}: Symbol '{symbol}' doesn't have whitespace around it")
			if "abilities" in outputCard and "abilities" in englishCard:
				for abilityIndex in range(min(len(outputCard["abilities"]), len(englishCard["abilities"]))):
					if outputCard["abilities"][abilityIndex]["type"] != englishCard["abilities"][abilityIndex]["type"]:
						cardDifferencesCount += 1
						print(f"{cardId}: Ability index {abilityIndex} type mismatch, {GlobalConfig.language.englishName} type is '{outputCard['abilities'][abilityIndex]['type']}', English type is '{englishCard['abilities'][abilityIndex]['type']}'")
			# Compare rarities
			if currentLanguageRarities.index(outputCard["rarity"]) != englishRarities.index(englishCard["rarity"]):
				cardDifferencesCount += 1
				print(f"{cardId}: {GlobalConfig.language.englishName} rarity is {englishRarities[currentLanguageRarities.index(outputCard['rarity'])]} ({outputCard['rarity']}) but English rarity is {englishCard['rarity']}")

	print(f"Found {cardDifferencesCount:,} difference{'' if cardDifferencesCount == 1 else 's'} between input and output")

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
