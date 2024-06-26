import json, os, re
from typing import Dict, List, Union

import GlobalConfig, Language
from OCR import ImageParser


_subtypeSeparatorString = f" {ImageParser.SEPARATOR_UNICODE} "

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

	idToInputCard = {}
	for cardtype, cardlist in inputCardStore["cards"].items():
		for inputCard in cardlist:
			idToInputCard[inputCard["culture_invariant_id"]] = inputCard

	cardDifferencesCount = 0
	for outputCard in outputCardStore["cards"]:
		if cardIdsToVerify and outputCard["id"] not in cardIdsToVerify:
			continue
		if outputCard.get("isExternalReval", False):
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
				if GlobalConfig.language == Language.ENGLISH:
					inputRulesText = inputRulesText.replace("Shift D", "Shift: D").replace("teammates’ ", "teammates' ").replace("players’ ", "players' ")
				elif GlobalConfig.language == Language.FRENCH:
					# Exclamation marks etc. should be preceded by a space
					inputRulesText = re.sub(r"(?<=\w)([?!:])", r" \1", inputRulesText)
					inputRulesText = re.sub("\\.{2,}", "…", inputRulesText)
			else:
				inputRulesText = ""

			if outputCard["fullText"]:
				outputRulesText = outputCard["fullText"].replace(" -\n", " - ").replace("-\n", "-").replace("\n", " ")
				# Remove all the Lorcana symbols:
				outputRulesText = re.sub(fr" ?[{ImageParser.EXERT_UNICODE}{ImageParser.INK_UNICODE}{ImageParser.LORE_UNICODE}{ImageParser.STRENGTH_UNICODE}{ImageParser.WILLPOWER_UNICODE}{ImageParser.INKWELL_UNICODE}] ?", " ", outputRulesText).lstrip()
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
		if outputCard["rarity"] == Language.TRANSLATIONS[GlobalConfig.language]["ENCHANTED"] and "nonEnchantedId" not in outputCard:
			print(f"{outputCard['fullName']} (ID {outputCard['id']} should have a non-enchanted ID field, but it doesn't")
		elif "Q" not in outputCard["setCode"] and outputCard["rarity"] == Language.TRANSLATIONS[GlobalConfig.language]["SPECIAL"] and "nonPromoId" not in outputCard:
			print(f"{outputCard['fullName']} (ID {outputCard['id']} should have a non-promo ID field, but it doesn't")

	print(f"Found {cardDifferencesCount:,} difference{'' if cardDifferencesCount == 1 else 's'} between input and output")

def _printDifferencesDescription(outputCard: Dict, fieldName: str, inputString: str, outputString: str):
	maxCharIndex = max(len(inputString), len(outputString))
	fieldDifferencesPointers = [" " for _ in range(maxCharIndex)]
	fieldDifferencesCount = 0
	for charIndex in range(maxCharIndex):
		if len(inputString) <= charIndex or len(outputString) <= charIndex or inputString[charIndex] != outputString[charIndex]:
			fieldDifferencesPointers[charIndex] = "^"
			fieldDifferencesCount += 1
	print(f"{outputCard['fullName']} (ID {outputCard['id']}, {outputCard['number']} of set {outputCard['setCode']}), {fieldName}, {fieldDifferencesCount:,} difference{'' if fieldDifferencesCount == 1 else 's'}:\n"
		  f"  IN:  {inputString!r}\n"
		  f"  OUT: {outputString!r}\n"
		  f"        {''.join(fieldDifferencesPointers).rstrip()}")
