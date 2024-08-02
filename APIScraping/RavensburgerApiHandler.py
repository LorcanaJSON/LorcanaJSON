import datetime, hashlib, json, logging, os, random, time
from typing import Any, Dict, List

import requests

import GlobalConfig
from util import DownloadUtil


_logger = logging.getLogger("LorcanaJSON")

def retrieveCardCatalog() -> Dict[str, Any]:
	# First get the token we need for the API, in the same way the official app does
	tokenResponse = requests.post("https://sso.ravensburger.de/token",
								  headers={
									  # API key captured from the official Lorcana app
									  "authorization": "Basic bG9yY2FuYS1hcGktcmVhZDpFdkJrMzJkQWtkMzludWt5QVNIMHc2X2FJcVZEcHpJenVrS0lxcDlBNXRlb2c5R3JkQ1JHMUFBaDVSendMdERkYlRpc2k3THJYWDl2Y0FkSTI4S096dw==",
									  "content-type": "application/x-www-form-urlencoded",
									  "user-agent": f"UnityPlayer / {DownloadUtil.UNITY_VERSION}(UnityWebRequest / 1.0, libcurl / 8.5.0 - DEV)",
									  "x-unity-version": DownloadUtil.UNITY_VERSION
								  },
								  data={"grant_type": "client_credentials"},
								  timeout=10)
	if tokenResponse.status_code != 200:
		raise ValueError(f"Non-success reply when retrieving token (status code {tokenResponse.status_code}): {tokenResponse.text=}")
	tokenData = tokenResponse.json()
	if "access_token" not in tokenData or "token_type" not in tokenData:
		raise ValueError(f"Missing access_token or token_type in token request: {tokenResponse.text}")

	# Now we can retrieve the card catalog, again just like the official app
	catalogResponse = DownloadUtil.retrieveFromUrl(f"https://api.lorcana.ravensburger.com/v2/catalog/{GlobalConfig.language.code}", additionalHeaderFields={"authorization": f"{tokenData['token_type']} {tokenData['access_token']}"})
	cardCatalog = catalogResponse.json()
	if "cards" not in cardCatalog:
		raise ValueError(f"Invalid data in catalog response: {catalogResponse.text}")
	return cardCatalog

def retrieveAndSaveCardCatalog(pathToSaveTo: str = None) -> Dict[str, Any]:
	cardCatalog = retrieveCardCatalog()
	saveCardCatalog(cardCatalog, True, pathToSaveTo)
	return cardCatalog

def saveCardCatalog(cardCatalog: Dict, shouldSaveDatedFile: bool = True, pathToSaveTo: str = None):
	if not pathToSaveTo:
		pathToSaveTo = os.path.join("downloads", "json")
	os.makedirs(pathToSaveTo, exist_ok=True)
	mainCardCatalogPath = os.path.join(pathToSaveTo, f"carddata.{GlobalConfig.language.code}.json")
	with open(mainCardCatalogPath, "w", encoding="utf-8") as cardfile:
		json.dump(cardCatalog, cardfile, indent=2)
	if shouldSaveDatedFile:
		datedCardCatalogPath = os.path.join(pathToSaveTo, f"carddata.{GlobalConfig.language.code}.{datetime.datetime.now().strftime('%Y-%m-%d.%H-%M-%S')}.json")
		with open(datedCardCatalogPath, "w", encoding="utf-8") as cardfile:
			json.dump(cardCatalog, cardfile, indent=2)


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

def downloadImagesIfUpdated(cardIdsToCheck: List[int]) -> List[int]:
	with open(os.path.join("downloads", "json", f"carddata.{GlobalConfig.language.code}.json"), "r", encoding="utf-8") as cardCatalogFile:
		cardCatalog = json.load(cardCatalogFile)
	cardIdsWithUpdatedImage: List[int] = []
	for cardType, cardList in cardCatalog["cards"].items():
		for card in cardList:
			cardId = card["culture_invariant_id"]
			if cardId not in cardIdsToCheck:
				continue
			localImagePath = os.path.join("downloads", "images", GlobalConfig.language.code, f"{cardId}.jpg")
			with open(localImagePath, "rb") as localImageFile:
				localImageChecksum = hashlib.md5(localImageFile.read()).hexdigest()
			for imageData in card["image_urls"]:
				if imageData["height"] == 2048:
					remoteImageRequest = DownloadUtil.retrieveFromUrl(imageData["url"])
					remoteImageBytes = remoteImageRequest.content
					remoteImageChecksum = hashlib.md5(remoteImageBytes).hexdigest()
					if localImageChecksum != remoteImageChecksum:
						# Images actually differ, save the new version
						with open(localImagePath, "wb") as localImageFile:
							localImageFile.write(remoteImageBytes)
						cardIdsWithUpdatedImage.append(cardId)
					break
	return cardIdsWithUpdatedImage

def downloadImages(shouldOverwriteImages: bool = False, pathToCardCatalog: str = None):
	startTime = time.perf_counter()
	if not pathToCardCatalog:
		pathToCardCatalog = os.path.join("downloads", "json")
	cardCatalogPath = os.path.join(pathToCardCatalog, f"carddata.{GlobalConfig.language.code}.json")
	if not os.path.isfile(cardCatalogPath):
		retrieveAndSaveCardCatalog(pathToCardCatalog)
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
			for imageUrlDict in card["image_urls"]:
				if imageUrlDict["height"] == 2048:
					imagesFound += 1
					imageSavePath = os.path.join("downloads", "images", GlobalConfig.language.code, f"{card['culture_invariant_id']}.jpg")
					wasImageDownloaded = downloadImage(imageUrlDict["url"], imageSavePath, shouldOverwriteImages)
					if wasImageDownloaded:
						imagesDownloaded += 1
						time.sleep(2 * random.random())
					break
	# Download the external images too
	externalCardRevealsFileName = f"externalCardReveals.{GlobalConfig.language.code}.json"
	if os.path.isfile(externalCardRevealsFileName):
		with open(externalCardRevealsFileName, "r", encoding="utf-8") as externalCardRevealsFile:
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
	_logger.info(f"Downloading {imagesDownloaded} of {imagesFound} {GlobalConfig.language.englishName} card images took {time.perf_counter() - startTime} seconds")
