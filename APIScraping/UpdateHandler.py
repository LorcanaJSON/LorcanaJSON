import datetime, json, logging, os
from typing import Dict, List

import GlobalConfig
from APIScraping import RavensburgerApiHandler
from APIScraping.UpdateCheckResult import ChangeType, UpdateCheckResult
from OutputGeneration import DataFilesGenerator


_logger = logging.getLogger("LorcanaJSON")

def checkForNewCardData(newCardCatalog: Dict = None, fieldsToIgnore: List[str] = None, includeCardChanges: bool = True, ignoreOrderChanges: bool = True) -> UpdateCheckResult:
	# We need to find the old cards by ID, so set up a dict
	oldCards: Dict[int, Dict] = {}
	# Keep track of known card fields, so we can notice if new cards add new fields
	knownCardFieldNames: List[str] = []
	pathToCardCatalog = os.path.join("downloads", "json", f"carddata.{GlobalConfig.language.code}.json")
	if os.path.isfile(pathToCardCatalog):
		with open(pathToCardCatalog, "r") as cardCatalogFile:
			oldCardCatalog = json.load(cardCatalogFile)
		for cardtype, cardlist in oldCardCatalog["cards"].items():
			for cardIndex in range(len(cardlist)):
				card = cardlist.pop()
				cardId = card["culture_invariant_id"]
				oldCards[cardId] = card
				for fieldName in card:
					if fieldName not in knownCardFieldNames:
						knownCardFieldNames.append(fieldName)
	else:
		_logger.info("No card catalog stored, so full update is needed")

	# Get the new card catalog, if needed
	if not newCardCatalog:
		newCardCatalog = RavensburgerApiHandler.retrieveCardCatalog()

	# Now go through all the new cards and see if the card exists in the old list, and if so, if the values are the same
	updateCheckResult: UpdateCheckResult = UpdateCheckResult()
	for cardType, cardList in newCardCatalog["cards"].items():
		for card in cardList:
			cardId = card["culture_invariant_id"]
			if cardId not in oldCards:
				updateCheckResult.addNewCard(card)
				# Check if this new card has fields we don't know about
				for fieldName in card:
					if fieldName not in knownCardFieldNames:
						updateCheckResult.newCardFields.append(fieldName)
						knownCardFieldNames.append(fieldName)
			elif includeCardChanges:
				# Remove the card from the old card dictionary, so we know which ones are left over (if any)
				oldCard = oldCards.pop(cardId)
				if not fieldsToIgnore or "image_urls" not in fieldsToIgnore:
					# Specifically check for image URLs, because if the checksum changed, we may need to redownload it
					imageUrl = None
					oldImageUrl = None
					for imageData in card["image_urls"]:
						if imageData["height"] == 2048:
							imageUrl = imageData["url"]
							break
					else:
						_logger.warning(f"Unable to find properly sized image in downloaded data for card ID {cardId}")
					for imageData in oldCard.get("image_urls", []):
						if imageData["height"] == 2048:
							oldImageUrl = imageData["url"]
							break
					else:
						_logger.warning(f"Unable to find properly sized image in old data for card ID {cardId}")
					if imageUrl != oldImageUrl:
						updateCheckResult.addPossibleImageChange(card, oldImageUrl, imageUrl)
				for fieldName, fieldValue in card.items():
					if fieldName == "image_urls":
						# Skip the image_urls field since we already checked it
						continue
					if fieldsToIgnore and fieldName in fieldsToIgnore:
						continue
					if fieldName not in oldCard:
						updateCheckResult.addCardChange(card, ChangeType.NEW_FIELD, fieldName, None, fieldValue)
					elif isinstance(fieldValue, list):
						if len(fieldValue) != len(oldCard[fieldName]):
							updateCheckResult.addCardChange(card, ChangeType.UPDATED_FIELD, fieldName, oldCard[fieldName], fieldValue)
						else:
							for listValueIndex in range(len(fieldValue)):
								oldListEntry = oldCard[fieldName][listValueIndex]
								newListEntry = fieldValue[listValueIndex]
								if isinstance(newListEntry, str) or isinstance(newListEntry, int):
									if ignoreOrderChanges:
										if newListEntry not in oldCard[fieldName]:
											updateCheckResult.addCardChange(card, ChangeType.NEW_ENTRY, fieldName, None, newListEntry)
									elif newListEntry != oldListEntry:
										updateCheckResult.addCardChange(card, ChangeType.UPDATED_ENTRY, fieldName, oldListEntry, newListEntry)
								elif isinstance(newListEntry, dict):
									if len(oldListEntry) != len(newListEntry):
										updateCheckResult.addCardChange(card, ChangeType.UPDATED_ENTRY, fieldName, oldListEntry, newListEntry)
									else:
										for listEntryKey, listEntryValue in newListEntry.items():
											if listEntryKey not in oldListEntry:
												updateCheckResult.addCardChange(card, ChangeType.NEW_ENTRY, fieldName, None, listEntryKey)
											else:
												if listEntryValue != oldListEntry[listEntryKey]:
													updateCheckResult.addCardChange(card, ChangeType.UPDATED_ENTRY, fieldName, oldListEntry[listEntryKey], listEntryValue)
								else:
									raise ValueError(f"Unsupported list entry type '{type(newListEntry)}'")
					elif fieldValue != oldCard[fieldName]:
						updateCheckResult.addCardChange(card, ChangeType.UPDATED_FIELD, fieldName, oldCard[fieldName], fieldValue)
	# If there are old cards left over, they were removed from the new cardstore; list those
	for cardId, card in oldCards.items():
		updateCheckResult.addRemovedCard(card)

	# Check if new cards have been added to the external reveals file
	externalRevealsFileName = f"externalCardReveals.{GlobalConfig.language.code}.json"
	if os.path.isfile(externalRevealsFileName):
		allCardsFilePath = os.path.join("output", "generated", GlobalConfig.language.code, "allCards.json")
		existingIds = set()
		if os.path.isfile(allCardsFilePath):
			with open(allCardsFilePath, "r", encoding="utf-8") as allCardsFile:
				allCards = json.load(allCardsFile)
			for card in allCards["cards"]:
				existingIds.add(card["id"])
		with open(externalRevealsFileName, "r", encoding="utf-8") as externalRevealsFile:
			externalReveals = json.load(externalRevealsFile)
			for card in externalReveals:
				if card["culture_invariant_id"] not in existingIds:
					updateCheckResult.addNewCard(card, "[external]")

	# Check if new sets have been added
	if len(oldCardCatalog["card_sets"]) != len(newCardCatalog["card_sets"]):
		oldNames = [s["name"] for s in oldCardCatalog["card_sets"]]
		for newSetData in newCardCatalog["card_sets"]:
			if newSetData["name"] not in oldNames:
				updateCheckResult.newSets.append(newSetData["name"])

	return updateCheckResult

def createOutputIfNeeded(onlyCreateOnNewCards: bool, cardFieldsToIgnore: List[str] = None, shouldShowImages: bool = False):
	cardCatalog = RavensburgerApiHandler.retrieveCardCatalog()
	updateCheckResult: UpdateCheckResult = checkForNewCardData(cardCatalog, cardFieldsToIgnore, includeCardChanges=not onlyCreateOnNewCards)
	if not updateCheckResult.hasCardChanges():
		_logger.info(f"No card updates, not running output generator")
		return
	_logger.info(f"Found {updateCheckResult.listChangeCounts()}")
	idsToParse = [card.id for card in updateCheckResult.newCards]
	idsToParse.extend([card.id for card in updateCheckResult.changedCards])
	# Not all possible image changes are actual changes, update only the changed images
	if updateCheckResult.possibleChangedImages:
		actualImageChanges = RavensburgerApiHandler.downloadImagesIfUpdated(cardCatalog, [card.id for card in updateCheckResult.possibleChangedImages])
		_logger.info(f"{len(actualImageChanges):,} actual image changes: {actualImageChanges}")
		if actualImageChanges:
			GlobalConfig.useCachedOcr = False
			_logger.info("Image(s) changed, skipping using OCR cache")
		idsToParse.extend(actualImageChanges)
	RavensburgerApiHandler.saveCardCatalog(cardCatalog)
	RavensburgerApiHandler.downloadImages()
	DataFilesGenerator.createOutputFiles(idsToParse, shouldShowImages=shouldShowImages)
	createChangelog(updateCheckResult)

def createChangelog(updateCheckResult: UpdateCheckResult, subVersion: str = "1"):
	if not updateCheckResult.newCards and not updateCheckResult.changedCards:
		return

	currentDateString = datetime.datetime.now().strftime("%Y-%m-%d")
	indent = " " * 4
	doubleIndent = indent * 2
	tripleIndent = indent * 3
	changelogEntryDescriptor = f"{currentDateString}-{DataFilesGenerator.FORMAT_VERSION}-{subVersion}"
	with open("newChangelogEntry.txt", "w", encoding="utf-8") as newChangelogEntryFile:
		newChangelogEntryFile.write(f"<h4 id=\"{changelogEntryDescriptor}\">{currentDateString} - format version {DataFilesGenerator.FORMAT_VERSION}</h4>\n")
		newChangelogEntryFile.write("<ul>\n")
		if updateCheckResult.newCards:
			updateCheckResult.newCards.sort(key=lambda c: c[0])
			newChangelogEntryFile.write(f"{indent}<li>Added {len(updateCheckResult.newCards):,} cards:\n")
			newChangelogEntryFile.write(f"{doubleIndent}<ul>\n")
			for addedCard in updateCheckResult.newCards:
				newChangelogEntryFile.write(f"{tripleIndent}<li>{addedCard}</li>\n")
			newChangelogEntryFile.write(f"{doubleIndent}</ul>\n")
			newChangelogEntryFile.write(f"{indent}</li>\n")
		if updateCheckResult.changedCards:
			# Aggregate field changes
			fieldNameToCardDescriptors = {}
			for changedCard in updateCheckResult.changedCards:
				if changedCard.fieldName not in fieldNameToCardDescriptors:
					fieldNameToCardDescriptors[changedCard.fieldName] = [changedCard.getCardDescriptor()]
				else:
					fieldNameToCardDescriptors[changedCard.fieldName].append(changedCard.getCardDescriptor())
			# Add a list to the changelog for each updated field
			for fieldName, cardDescriptors in fieldNameToCardDescriptors.items():
				newChangelogEntryFile.write(f"{indent}<li>Updated '{fieldName}' in {len(cardDescriptors):,} cards:\n")
				newChangelogEntryFile.write(f"{doubleIndent}<ul>\n")
				for cardDescriptor in cardDescriptors:
					newChangelogEntryFile.write(f"{tripleIndent}<li>{cardDescriptor}</li>\n")
				newChangelogEntryFile.write(f"{doubleIndent}</ul>\n")
				newChangelogEntryFile.write(f"{indent}</li>\n")
		newChangelogEntryFile.write(f"</ul>\n")
		filePrefix = f"files/{changelogEntryDescriptor}/{GlobalConfig.language.code}/"
		newChangelogEntryFile.write(f"Permanent links: <a href=\"{filePrefix}allCards.json.zip\">allCards.json.zip</a> (<a href=\"{filePrefix}allCards.json.zip.md5\">md5</a>), "
									f"<a href=\"{filePrefix}allSets.json.zip\">allSets.json.zip</a> (<a href=\"{filePrefix}allSets.json.zip.md5\">md5</a>)\n")
