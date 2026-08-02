import logging, json, os, re
from typing import Dict, List, Optional

import GlobalConfig
from OCR.ImageParser import ImageParser
from OCR.OcrResult import OcrResult
from OutputGeneration import TextCorrection
from OutputGeneration.ArtistsHandler import ArtistsHandler
from util import Language
from util.FormatCoconutCard import FormatCoconutCard

_LOGGER = logging.getLogger("LorcanaJSON")

def generateFormatCoconutCardData(inputCardData: Dict, outputCardList: List[Dict]) -> Optional[List[Dict]]:
	# For now only English has Coconut cards
	if GlobalConfig.language != Language.ENGLISH:
		_LOGGER.warning(f"Format Coconut cards only exist in English for now, not parsing for {GlobalConfig.language.englishName}")
		return None
	if "coconut_cards" not in inputCardData:
		_LOGGER.warning("No Format Coconut data found, not generating the data for it")
		return None

	# To match Coconut cards to their referred main cards, we need to create a name list
	cardNameToCard: Dict[str, Dict] = {}
	for outputCard in outputCardList:
		# Skip fancy-art and promo cards
		if "baseId" not in outputCard:
			cardNameToCard[outputCard["fullName"]] = outputCard

	cardCorrectionsPath = os.path.join("OutputGeneration", "data", "outputDataCorrections", f"formatCoconutCorrections_{GlobalConfig.language.code}.json")
	cardCorrections: Dict = {}
	if os.path.isfile(cardCorrectionsPath):
		with open(cardCorrectionsPath, "r") as cardCorrectionsFile:
			cardCorrections = json.load(cardCorrectionsFile)

	outputCoconutCards: List[Dict] = []
	imageParser: ImageParser = ImageParser()
	baseImagePath: str = os.path.join("downloads", "images", GlobalConfig.language.code, "coconut")
	for coconutCardData in inputCardData["coconut_cards"]:
		coconutCard = FormatCoconutCard(coconutCardData)
		if coconutCard.cleanFullName not in cardNameToCard:
			raise KeyError(f"Unable to match Format Coconut card {coconutCard} to any main card")
		outputCoconutCards.append(_generateDataForSingleFormatCoconutCard(coconutCard, cardNameToCard[coconutCard.cleanFullName], imageParser, baseImagePath, cardCorrections.pop(coconutCard.numberString, None)))
	outputCoconutCards.sort(key=lambda c: c["number"])
	return outputCoconutCards

def _generateDataForSingleFormatCoconutCard(coconutCard: FormatCoconutCard, associatedCard: Dict, imageParser: ImageParser, baseImagePath: str, cardCorrections: Optional[Dict]) -> Dict:
	ocrResult: OcrResult = imageParser.getOcrResultForCoconutCard(coconutCard, baseImagePath)
	fullText = ocrResult.remainingText
	# The Ink symbol could cause the OCR reader to read a double newline where it should be a single newline, fix that
	fullText = re.sub(r"(?<=[a-z])\n\n(?=\d)", "\n", fullText)
	reminderTextMatch = re.match(r"^\([^)]+\)", fullText)
	if not reminderTextMatch:
		raise ValueError(f"Unable to find reminder text in {fullText!r} of {coconutCard}")
	reminderText = reminderTextMatch.group(0)
	abilities: List[Dict] = [
		{
			"fullText": reminderText,
			"type": "static"
		}
	]
	abilitiesText = fullText[len(reminderText):].lstrip()
	for abilityText in abilitiesText.split("\n\n"):
		abilityText = TextCorrection.correctText(abilityText)
		abilityType = "static"
		if abilityText.startswith("Whenever"):
			abilityType = "triggered"
		elif re.match(r"Once(\sper\sgame)?\sduring\syour\sturn,\syou\smay", abilityText):
			abilityType = "activated"
		abilities.append({
			"fullText": abilityText,
			"type": abilityType
		})
	outputData = {
		"abilities": abilities,
		"artistsText": ArtistsHandler.correctArtistName(ocrResult.artistsText),
		"associatedCardId": associatedCard["id"],
		"associatedCardName": associatedCard["fullName"],
		"color": associatedCard["color"],
		"fullName": coconutCard.fullName,
		"images": {
			"closeup": coconutCard.coconutData["settings_thumbnail_url"],
			"full": coconutCard.coconutData["card_detail_url"],
			"thumbnail": coconutCard.coconutData["card_thumbnail_url"]
		},
		"name": coconutCard.coconutData["name"],
		"number": coconutCard.number,
		"subtitle": coconutCard.coconutData["subtitle"],
	}
	if cardCorrections:
		for fieldName, correctionList in cardCorrections.items():
			TextCorrection.correctCardFieldFromList(outputData, fieldName, correctionList)
	# After corrections are done, fill in fields based on other fields, to prevent needing double corrections
	outputData["fullTextSections"] = [a["fullText"] for a in abilities]
	outputData["fullText"] = "\n".join(outputData["fullTextSections"])
	outputData["artists"] = outputData["artistsText"].split(" / ")
	for abilityIndex in range(len(abilities)):
		ability = abilities[abilityIndex]
		ability["effect"] = ability["fullText"].strip("()").replace("\n", " ")
		abilities[abilityIndex] = {k: ability[k] for k in sorted(ability)}
	if abilities[0]["effect"] != f"You can have up to 4 copies of {associatedCard['fullName']} in your deck.":
		_LOGGER.warning(f"Reminder text for Format Coconut card {coconutCard} is incorrect")
	return {k: outputData[k] for k in sorted(outputData)}
