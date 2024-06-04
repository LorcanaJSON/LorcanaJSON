import json, os, re
from typing import Dict, List, Union

import GlobalConfig, Language
from OCR import ImageParser


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
			else:
				inputRulesText = ""

			if outputCard["fullText"]:
				outputRulesText = outputCard["fullText"].replace("\n", " ")
				# Remove all the Lorcana symbols:
				outputRulesText = re.sub(fr" ?[{ImageParser.EXERT_UNICODE}{ImageParser.INK_UNICODE}{ImageParser.LORE_UNICODE}{ImageParser.STRENGTH_UNICODE}{ImageParser.WILLPOWER_UNICODE}{ImageParser.INKWELL_UNICODE}] ?", " ", outputRulesText)
				outputRulesText = outputRulesText.replace("  ", " ").replace(" .", ".")
			else:
				outputRulesText = ""

			if inputRulesText != outputRulesText:
				cardDifferencesCount += 1
				_printDifferencesDescription(outputCard, "rules text", inputRulesText, outputRulesText)

		# Compare flavor text
		if inputCard.get("flavor_text", None) or "flavorText" in outputCard:
			if "flavor_text" in inputCard and inputCard["flavor_text"] != "ERRATA":
				inputFlavorText: str = inputCard["flavor_text"].replace("\u00a0", "").replace("‘", "'").replace("’", "'").replace("…", "...").replace(" ..", "..").replace(".. ", "..").replace("<", "").replace(">", "").replace("%", " ").rstrip()
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
	print(f"Found {cardDifferencesCount:,} difference{'' if cardDifferencesCount == 1 else 's'} between input and output")

def _printDifferencesDescription(outputCard: Dict, fieldName: str, inputString: str, outputString: str):
	maxCharIndex = max(len(inputString), len(outputString))
	fieldDifferencesPointers = [" " for _ in range(maxCharIndex)]
	fieldDifferencesCount = 0
	for charIndex in range(maxCharIndex):
		if len(inputString) <= charIndex or len(outputString) <= charIndex or inputString[charIndex] != outputString[charIndex]:
			fieldDifferencesPointers[charIndex] = "^"
			fieldDifferencesCount += 1
	print(f"{outputCard['fullName']} (ID {outputCard['id']}), {fieldName}, {fieldDifferencesCount:,} difference{'' if fieldDifferencesCount == 1 else 's'}:\n"
		  f"  IN:  {inputString!r}\n"
		  f"  OUT: {outputString!r}\n"
		  f"        {''.join(fieldDifferencesPointers)}")
