import json, logging, os, re, time
from typing import Dict, Optional

import GlobalConfig


_logger = logging.getLogger("LorcanaJSON")

def _createCardIdentifier(card, cardId):
	name = card.get("name", card.get("baseName", "[[unknown]]"))
	return f"'{name}' (ID {cardId})"

class StoryParser:
	def __init__(self):
		startTime = time.perf_counter()
		with open(os.path.join("output", "fromStories.json"), "r", encoding="utf-8") as fromStoriesFile:
			fromStories = json.load(fromStoriesFile)
		# The fromStories file is organised by story to make it easy to write and maintain
		# Reformat it so matching individual cards to a story is easier
		self._cardIdToStoryName: Dict[int, str] = {}
		self._cardNameToStoryName: Dict[str, str] = {}
		self._subtypeToStoryName: Dict[str, str] = {}
		self._fieldMatchers: Dict[str, Dict[str, str]] = {}  # A dictionary with for each fieldname a dict of matchers and their matching story name
		for storyId, storyData in fromStories.items():
			storyName = storyData["displayNames"][GlobalConfig.language.code]
			if "matchingIds" in storyData:
				for cardId in storyData["matchingIds"]:
					self._cardIdToStoryName[cardId] = storyName
			if "matchingNames" in storyData:
				for name in storyData["matchingNames"]:
					self._cardNameToStoryName[name] = storyName
			if "matchingFields" in storyData:
				for fieldName, fieldMatch in storyData["matchingFields"].items():
					if fieldName == "subtypes":
						self._subtypeToStoryName[fieldMatch] = storyName
					else:
						if fieldName not in self._fieldMatchers:
							self._fieldMatchers[fieldName] = {}
						elif fieldMatch in self._fieldMatchers[fieldName]:
							raise ValueError(f"Duplicate field matcher '{fieldMatch}' in '{self._fieldMatchers[fieldName][fieldMatch]}' and '{storyName}'")
						self._fieldMatchers[fieldName][fieldMatch] = storyName
		# Now we can go through every card and try to match each to a story
		# Use the English cardstore regardless of the set language, since that's what the stories file is based on
		cardStorePath = os.path.join("downloads", "json", "carddata.en.json")
		if not os.path.isfile(cardStorePath):
			raise FileNotFoundError("The English carddata file does not exist, please run the 'download' action for English first")
		with open(cardStorePath, "r", encoding="utf-8") as cardstoreFile:
			cardstore = json.load(cardstoreFile)
		for cardtype, cardlist in cardstore["cards"].items():
			for card in cardlist:
				cardId = card["culture_invariant_id"]
				if cardId not in self._cardIdToStoryName:
					storyName = self.getStoryNameForCard(card, cardId)
					if storyName:
						self._cardIdToStoryName[cardId] = storyName
		_logger.debug(f"Reorganized story data after {time.perf_counter() - startTime:.4f} seconds")

	def getStoryNameForCard(self, card, cardId: int) -> Optional[str]:
		if cardId in self._cardIdToStoryName:
			# Card is already stored, by directly referencing its ID in the 'fromStories' file, so we don't need to do anything anymore
			return self._cardIdToStoryName[cardId]
		# Check the subtypes list first, those are unique enough that they can often take precedence over names (f.i. Musketeer)
		if "subtypes" in card:
			for subtype in card["subtypes"]:
				if subtype in self._subtypeToStoryName:
					return self._subtypeToStoryName[subtype]
		for fieldName in ("name", "baseName", "subtitle", "fullName"):
			if fieldName in card and card[fieldName] in self._cardNameToStoryName:
				return self._cardNameToStoryName[card[fieldName]]
		# Go through each field matcher to see if it matches anything
		for fieldName, fieldData in self._fieldMatchers.items():
			if fieldName not in card:
				continue
			for fieldMatch, storyName in fieldData.items():
				if isinstance(card[fieldName], list):
					if fieldMatch in card[fieldName]:
						return storyName
				elif fieldMatch in card[fieldName] or re.search(fieldMatch, card[fieldName]):
					return storyName
		# No match, try to see if any of the names occurs in some of the card's fields
		for name, storyName in self._cardNameToStoryName.items():
			nameRegex = re.compile(rf"\b{name}\b")
			for fieldName in ("flavor_text", "flavorText", "rules_text", "fullText", "name", "baseName", "subtitle"):
				if fieldName in card and nameRegex.search(card[fieldName]):
					_logger.debug(f"Assuming {_createCardIdentifier(card, cardId)} is in story '{storyName}' based on '{name}' in the field '{fieldName}': {card[fieldName]!r}")
					return storyName
		# As a last resort, check if one of the subtypes is listed somewhere in the card
		for subtype, storyName in self._subtypeToStoryName.items():
			subtypeRegex = re.compile(rf"\b{subtype}\b")
			for fieldName in ("flavor_text", "flavorText", "rules_text", "fullText", "name", "baseName", "subtitle"):
				if fieldName in card and subtypeRegex.search(card[fieldName]):
					_logger.debug(f"Assuming {_createCardIdentifier(card, cardId)} is in story '{storyName}' based on subtype '{subtype}' in the field '{fieldName}': {card[fieldName]!r}")
					return storyName
		_logger.error(f"Unable to determine story ID of card {_createCardIdentifier(card, cardId)}")
		return None
