import datetime, hashlib, json, logging, os, random, time
from typing import Any, Dict, List, Tuple, Union

import requests

import GlobalConfig
from APIScraping import ApiScrapingUtil
from util import DownloadUtil, Language
from util.FormatCoconutCard import FormatCoconutCard


_logger = logging.getLogger("LorcanaJSON")

def retrieveCardCatalog() -> Dict[str, Any]:
	# First get the token we need for the API, in the same way the official app does
	headers = DownloadUtil.DEFAULT_HEADERS.copy()
	# API key captured from the official Lorcana app
	headers["authorization"] = "Basic bG9yY2FuYS1hcGktcmVhZDpFdkJrMzJkQWtkMzludWt5QVNIMHc2X2FJcVZEcHpJenVrS0lxcDlBNXRlb2c5R3JkQ1JHMUFBaDVSendMdERkYlRpc2k3THJYWDl2Y0FkSTI4S096dw=="
	headers["content-type"] = "application/x-www-form-urlencoded"
	tokenResponse = requests.post("https://sso.ravensburger.de/token", headers=headers, data={"grant_type": "client_credentials"}, timeout=10)
	if tokenResponse.status_code != 200:
		raise ValueError(f"Non-success reply when retrieving token (status code {tokenResponse.status_code}): {tokenResponse.text=}")
	tokenData = tokenResponse.json()
	if "access_token" not in tokenData or "token_type" not in tokenData:
		raise ValueError(f"Missing access_token or token_type in token request: {tokenResponse.text}")

	# Now we can retrieve the card catalog, again just like the official app
	catalogResponse = DownloadUtil.retrieveFromUrl(f"https://api.lorcana.ravensburger.com/v3/catalog/{GlobalConfig.language.code}", additionalHeaderFields={"authorization": f"{tokenData['token_type']} {tokenData['access_token']}"})
	cardCatalog = catalogResponse.json()
	if "cards" not in cardCatalog:
		raise ValueError(f"Invalid data in catalog response: {catalogResponse.text}")
	return cardCatalog

def retrieveAndSaveCardCatalog() -> Dict[str, Any]:
	cardCatalog = retrieveCardCatalog()
	ApiScrapingUtil.saveCardCatalog(cardCatalog, True)
	return cardCatalog

def downloadImage(imageUrl: str, savePath: str, shouldOverwriteImage: bool = False) -> bool:
	if not shouldOverwriteImage and os.path.isfile(savePath):
		_logger.debug(f"Image '{savePath}' already exists, skipping download")
		return False
	imageResponse = DownloadUtil.retrieveFromUrl(imageUrl)
	os.makedirs(os.path.dirname(savePath), exist_ok=True)
	with open(savePath, "wb") as imageFile:
		imageFile.write(imageResponse.content)
	_logger.info(f"Successfully downloaded '{savePath}'")
	return True

def downloadImagesIfUpdated(cardCatalog: Dict, cardIdsToCheck: List[int], formatCoocnutCardsToCheck: List[FormatCoconutCard]) -> Tuple[List[int], List[FormatCoconutCard]]:
	cardIdsWithUpdatedImage: List[int] = []
	baseImagePath = os.path.join("downloads", "images", GlobalConfig.language.code)
	imageBackupFolderPath = os.path.join(baseImagePath, "backups")
	if not os.path.isdir(imageBackupFolderPath):
		os.makedirs(imageBackupFolderPath)
	today: str = datetime.datetime.today().strftime("%Y-%m-%d")
	for cardType, cardList in cardCatalog["cards"].items():
		for card in cardList:
			cardId = card["culture_invariant_id"]
			if cardId not in cardIdsToCheck:
				continue
			if GlobalConfig.language.uppercaseCode not in card["card_identifier"]:
				continue
			for imageData in card["variants"]:
				if imageData["variant_id"] == "Regular":
					if _backupAndDownloadImageIfNeeded(baseImagePath, cardId, imageData["detail_image_url"], imageBackupFolderPath, today):
						cardIdsWithUpdatedImage.append(cardId)
					break
			else:
				_logger.warning(f"Unable to find correct 2048-high image for card ID {cardId}, unable to check if image changed")
	# Also check for changed Format Coconut cards, if needed
	formatCoconutCardsWithUpdatedImage: List[FormatCoconutCard] = []
	if GlobalConfig.language == Language.ENGLISH and formatCoocnutCardsToCheck:
		baseImagePath = os.path.join(baseImagePath, "coconut")
		imageBackupFolderPath = os.path.join(baseImagePath, "backup")
		if not os.path.isdir(imageBackupFolderPath):
			os.makedirs(imageBackupFolderPath)
		for formatCoconutCard in formatCoocnutCardsToCheck:
			if _backupAndDownloadImageIfNeeded(baseImagePath, formatCoconutCard.number, formatCoconutCard.getImageUrl(), imageBackupFolderPath, today):
				formatCoconutCardsWithUpdatedImage.append(formatCoconutCard)
	return cardIdsWithUpdatedImage, formatCoconutCardsWithUpdatedImage

def _backupAndDownloadImageIfNeeded(basePath: str, cardIdentifier: int, remoteImageUrl: str, backupFolderPath: str, today: str) -> bool:
	localImagePath = os.path.join(basePath, f"{cardIdentifier}.jpg")
	if not os.path.isfile(localImagePath):
		_logger.warning(f"Image '{localImagePath}' for card identifier {cardIdentifier} doesn't exist locally, while it was expected to exist. Skipping")
		return False
	with open(localImagePath, "rb") as localImageFile:
		localImageBytes = localImageFile.read()
		localImageChecksum = hashlib.md5(localImageBytes).hexdigest()
	remoteImageResponse = DownloadUtil.retrieveFromUrl(remoteImageUrl)
	remoteImageBytes = remoteImageResponse.content
	remoteImageChecksum = hashlib.md5(remoteImageBytes).hexdigest()
	if localImageChecksum == remoteImageChecksum:
		return False
	# Images actually differ
	_logger.debug(f"Image for card with Identifier {cardIdentifier} has changed, backing up old version and saving new version")
	# Backup the original image first
	with open(os.path.join(backupFolderPath, f"{cardIdentifier}_until_{today}.jpg"), "wb") as backupImageFile:
		backupImageFile.write(localImageBytes)
	# Then save the new version
	with open(localImagePath, "wb") as localImageFile:
		localImageFile.write(remoteImageBytes)
	return True

def downloadImages(shouldOverwriteImages: bool = False):
	startTime = time.perf_counter()
	cardCatalogPath = os.path.join("downloads", "json", f"carddata.{GlobalConfig.language.code}.json")
	if not os.path.isfile(cardCatalogPath):
		retrieveAndSaveCardCatalog()
	with open(cardCatalogPath, "r", encoding="utf-8") as cardCatalogFile:
		cardCatalog = json.load(cardCatalogFile)
	imagesFound = 0
	imagesDownloaded = 0
	languageCodeToCheck = f" {GlobalConfig.language.code.upper()} "
	for cardType, cardList in cardCatalog["cards"].items():
		for card in cardList:
			if languageCodeToCheck not in card["card_identifier"]:
				_logger.debug(f"Skipping card with ID {card['culture_invariant_id']} because it's not in the requested language")
				continue
			if "variants" not in card:
				_logger.error(f"Card ID {card['culture_invariant_id']} does not have an 'variants' key, can't download images")
				continue
			for imageUrlDict in card["variants"]:
				if imageUrlDict["variant_id"] == "Regular":
					imagesFound += 1
					imageSavePath = os.path.join("downloads", "images", GlobalConfig.language.code, f"{card['culture_invariant_id']}.jpg")
					wasImageDownloaded = downloadImage(imageUrlDict["detail_image_url"], imageSavePath, shouldOverwriteImages)
					if wasImageDownloaded:
						imagesDownloaded += 1
						time.sleep(2 * random.random())
					break
	# Download the external images too
	externalCardRevealsFilePath = os.path.join("output", f"externalCardReveals.{GlobalConfig.language.code}.json")
	if os.path.isfile(externalCardRevealsFilePath):
		with open(externalCardRevealsFilePath, "r", encoding="utf-8") as externalCardRevealsFile:
			externalCardReveals = json.load(externalCardRevealsFile)
		if externalCardReveals:
			externalSavePath = os.path.join("downloads", "images", GlobalConfig.language.code, "external")
			os.makedirs(externalSavePath, exist_ok=True)
			for externalCardReveal in externalCardReveals:
				imagesFound += 1
				imageExtension = externalCardReveal["imageUrl"].rsplit(".", 1)[1]
				if "?" in imageExtension:
					imageExtension = imageExtension.split("?", 1)[0]
				imageSavePath = os.path.join(externalSavePath, f"{externalCardReveal['culture_invariant_id']}.{imageExtension}")
				wasImageDownloaded = downloadImage(externalCardReveal["imageUrl"], imageSavePath, shouldOverwriteImages)
				if wasImageDownloaded:
					imagesDownloaded += 1

	# Download Coconut cards, if relevant (Coconut cards for now only exist in English)
	if GlobalConfig.language == Language.ENGLISH and "coconut_cards" in cardCatalog:
		baseCoconutImagePath = os.path.join("downloads", "images", GlobalConfig.language.code, "coconut")
		for coconutCardData in cardCatalog["coconut_cards"]:
			coconutCard = FormatCoconutCard(coconutCardData)
			imageSavePath = os.path.join(baseCoconutImagePath, f"{coconutCard.number}.jpg")
			wasImageDownloaded = downloadImage(coconutCardData["card_detail_url"], imageSavePath, shouldOverwriteImages)
			if wasImageDownloaded:
				imagesDownloaded += 1
			# Also download the closeup images, in case they disappear at some point
			imageSavePath = os.path.join(baseCoconutImagePath, f"{coconutCard.number}_closeup.jpg")
			downloadImage(coconutCardData["settings_thumbnail_url"], imageSavePath, shouldOverwriteImages)

	_logger.info(f"Downloading {imagesDownloaded} of {imagesFound} {GlobalConfig.language.englishName} card images took {time.perf_counter() - startTime} seconds")
