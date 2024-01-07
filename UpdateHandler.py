import datetime, json, logging, os
from typing import Any, Dict, List, Tuple

import DataFilesGenerator
from APIScraping import RavensburgerApiHandler
from Language import Language


_logger = logging.getLogger("LorcanaJSON")

def checkForNewCardData(language: Language, newCardCatalog: Dict = None, fieldsToIgnore: List[str] = None, includeCardChanges: bool = True, ignoreOrderChanges: bool = True) -> Tuple[List, List]:
	# We need to find the old cards by ID, so set up a dict
	oldCards = {}
	pathToCardCatalog = os.path.join("downloads", "json", f"carddata.{language.code}.json")
	if os.path.isfile(pathToCardCatalog):
		with open(pathToCardCatalog, "r") as cardCatalogFile:
			oldCardCatalog = json.load(cardCatalogFile)
		for cardtype, cardlist in oldCardCatalog["cards"].items():
			for cardIndex in range(len(cardlist)):
				card = cardlist.pop()
				cardId = card["culture_invariant_id"]
				oldCards[cardId] = card
	else:
		_logger.info("No card catalog stored, so full update is needed")

	# Get the new card catalog, if needed
	if not newCardCatalog:
		newCardCatalog = RavensburgerApiHandler.retrieveCardCatalog(language)

	# Now go through all the new cards and see if the card exists in the old list, and if so, if the values are the same
	addedCards: List[Tuple[int, str]] = []  # A list of tuples, with the first tuple entry being the new card's ID and the second tuple entry the card's name
	cardChanges: List[Tuple[int, str, str, Any, Any]] = []  # A list of tuples, with each tuple consisting of the changed card's ID, its name, the name of the changed field, the old field value, and the new field value
	for cardType, cardList in newCardCatalog["cards"].items():
		for card in cardList:
			cardId = card["culture_invariant_id"]
			cardDescriptor = card["name"]
			if "subtitle" in card:
				cardDescriptor += " - " + card["subtitle"]
			if cardId not in oldCards:
				addedCards.append((cardId, cardDescriptor))
			elif includeCardChanges:
				oldCard = oldCards[cardId]
				for fieldName, fieldValue in card.items():
					if fieldsToIgnore and fieldName in fieldsToIgnore:
						continue
					if fieldName not in oldCard:
						cardChanges.append((cardId, cardDescriptor, fieldName, None, fieldValue))
					elif isinstance(fieldValue, list):
						if len(fieldValue) != len(oldCard[fieldName]):
							cardChanges.append((cardId, cardDescriptor, fieldName, oldCard[fieldName], fieldValue))
						else:
							for listValueIndex in range(len(fieldValue)):
								oldListEntry = oldCard[fieldName][listValueIndex]
								newListEntry = fieldValue[listValueIndex]
								if isinstance(newListEntry, str):
									if ignoreOrderChanges:
										if newListEntry not in oldCard[fieldName]:
											cardChanges.append((cardId, cardDescriptor, fieldName, None, newListEntry))
									elif newListEntry != oldListEntry:
										cardChanges.append((cardId, cardDescriptor, fieldName, oldListEntry, newListEntry))
								elif isinstance(newListEntry, dict):
									if len(oldListEntry) != len(newListEntry):
										cardChanges.append((cardId, cardDescriptor, fieldName, oldListEntry, newListEntry))
									else:
										for listEntryKey, listEntryValue in newListEntry.items():
											if listEntryKey not in oldListEntry:
												cardChanges.append((cardId, cardDescriptor, fieldName, None, listEntryKey))
											else:
												if listEntryValue != oldListEntry[listEntryKey]:
													cardChanges.append((cardId, cardDescriptor, fieldName, oldListEntry[listEntryKey], listEntryValue))
								else:
									raise ValueError(f"Unsupported list entry type '{type(newListEntry)}'")
					elif fieldValue != oldCard[fieldName]:
						cardChanges.append((cardId, cardDescriptor, fieldName, oldCard[fieldName], fieldValue))
	return (addedCards, cardChanges)

def createOutputIfNeeded(language: Language, onlyCreateOnNewCards: bool, cardFieldsToIgnore: List[str] = None, shouldShowImages: bool = False):
	cardCatalog = RavensburgerApiHandler.retrieveCardCatalog(language)
	addedCards, cardChanges = checkForNewCardData(language, cardCatalog, cardFieldsToIgnore, includeCardChanges=not onlyCreateOnNewCards)
	if not addedCards and (onlyCreateOnNewCards or not cardChanges):
		_logger.info("No catalog updates, not running output generator")
		return
	idsToParse = [entry[0] for entry in addedCards]
	idsToParse.extend([entry[0] for entry in cardChanges])
	RavensburgerApiHandler.saveCardCatalog(language, cardCatalog)
	RavensburgerApiHandler.downloadImages(language)
	DataFilesGenerator.createOutputFiles(language, idsToParse, shouldShowImages=shouldShowImages)
	createChangelog(language, addedCards, cardChanges)

def createChangelog(language: Language, addedCards: List[Tuple[int, str]], cardChanges, subVersion: str = "1"):
	if not addedCards and not cardChanges:
		return

	def createCardDescriptor(addedOrChangedCard) -> str:
		return f"{addedOrChangedCard[1]} (ID {addedOrChangedCard[0]})"

	currentDateString = datetime.datetime.now().strftime("%Y-%m-%d")
	indent = " " * 4
	doubleIndent = indent * 2
	tripleIndent = indent * 3
	changelogEntryDescriptor = f"{currentDateString}-{DataFilesGenerator.FORMAT_VERSION}-{subVersion}"
	with open("newChangelogEntry.txt", "w", encoding="utf-8") as newChangelogEntryFile:
		newChangelogEntryFile.write(f"<h4 id=\"{changelogEntryDescriptor}\">{currentDateString} - format version {DataFilesGenerator.FORMAT_VERSION}</h4>\n")
		newChangelogEntryFile.write("<ul>\n")
		if addedCards:
			addedCards.sort(key=lambda c: c[0])
			newChangelogEntryFile.write(f"{indent}<li>Added {len(addedCards):,} cards:\n")
			newChangelogEntryFile.write(f"{doubleIndent}<ul>\n")
			for addedCard in addedCards:
				newChangelogEntryFile.write(f"{tripleIndent}<li>{createCardDescriptor(addedCard)}</li>\n")
			newChangelogEntryFile.write(f"{doubleIndent}</ul>\n")
			newChangelogEntryFile.write(f"{indent}</li>\n")
		if cardChanges:
			# Aggregate field changes
			fieldNameToCardNames = {}
			for cardChange in cardChanges:
				fieldName = cardChange[2]
				if fieldName not in fieldNameToCardNames:
					fieldNameToCardNames[fieldName] = [createCardDescriptor(cardChange)]
				else:
					fieldNameToCardNames[fieldName].append(createCardDescriptor(cardChange))
			# Add a list to the changelog for each updated field
			for fieldName, cardNames in fieldNameToCardNames.items():
				newChangelogEntryFile.write(f"{indent}<li>Updated '{fieldName}' in {len(cardNames):,} cards: {'; '.join(cardNames)}</li>\n")
		newChangelogEntryFile.write(f"</ul>\n")
		filePrefix = f"files/{changelogEntryDescriptor}/{language.code}/"
		newChangelogEntryFile.write(f"Permanent links: <a href=\"{filePrefix}allCards.json.zip\">allCards.json.zip</a> (<a href=\"{filePrefix}allCards.json.zip.md5\">md5</a>), "
									f"<a href=\"{filePrefix}allSets.json.zip\">allSets.json.zip</a> (<a href=\"{filePrefix}allSets.json.zip.md5\">md5</a>)\n")
