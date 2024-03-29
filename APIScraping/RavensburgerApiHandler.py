import datetime, json, logging, os, random, time
from typing import Any, Dict

import requests

import Language


_logger = logging.getLogger("LorcanaJSON")

def retrieveCardCatalog(language: Language) -> Dict[str, Any]:
	# First get the token we need for the API, in the same way the official app does
	tokenResponse = requests.post("https://sso.ravensburger.de/token",
								  headers={
									  # API key captured from the official Lorcana app
									  "authorization": "Basic bG9yY2FuYS1hcGktcmVhZDpFdkJrMzJkQWtkMzludWt5QVNIMHc2X2FJcVZEcHpJenVrS0lxcDlBNXRlb2c5R3JkQ1JHMUFBaDVSendMdERkYlRpc2k3THJYWDl2Y0FkSTI4S096dw==",
									  "content-type": "application/x-www-form-urlencoded",
									  "user-agent": "UnityPlayer/2021.3.23f1 (UnityWebRequest/1.0, libcurl/7.84.0-DEV)",
									  "x-unity-version": "2021.3.23f1"
								  },
								  data={"grant_type": "client_credentials"},
								  timeout=10)
	if tokenResponse.status_code != 200:
		raise ValueError(f"Non-success reply when retrieving token (status code {tokenResponse.status_code}): {tokenResponse.text=}")
	tokenData = tokenResponse.json()
	if "access_token" not in tokenData or "token_type" not in tokenData:
		raise ValueError(f"Missing access_token or token_type in token request: {tokenResponse.text}")

	# Now we can retrieve the card catalog, again just like the official app
	catalogResponse = requests.get(f"https://api.lorcana.ravensburger.com/v1/catalog/{language.code}",
								   headers={
									   "user-agent": "Lorcana/2023.1",
									   "authorization": f"{tokenData['token_type']} {tokenData['access_token']}",
									   "x-unity-version": "2021.3.23f1"
								   },
								   timeout=10)
	if catalogResponse.status_code != 200:
		raise ValueError(f"Non-success reply when retrieving card catalog (status code {catalogResponse.status_code}); {tokenResponse.text=}")
	cardCatalog = catalogResponse.json()
	if "cards" not in cardCatalog:
		raise ValueError(f"Invalid data in catalog response: {catalogResponse.text}")
	return cardCatalog

def retrieveAndSaveCardCatalog(language: Language.Language, pathToSaveTo: str = None) -> Dict[str, Any]:
	cardCatalog = retrieveCardCatalog(language)
	saveCardCatalog(language, cardCatalog, True, pathToSaveTo)
	return cardCatalog

def retrieveAndSaveAllCardCatalogs(pathToSaveTo: str = None):
	for language in Language.ALL:
		print(json.dumps(retrieveAndSaveCardCatalog(language, pathToSaveTo), indent=2))

def saveCardCatalog(language: Language, cardCatalog: Dict, shouldSaveDatedFile: bool = True, pathToSaveTo: str = None):
	if not pathToSaveTo:
		pathToSaveTo = os.path.join("downloads", "json")
	os.makedirs(pathToSaveTo, exist_ok=True)
	mainCardCatalogPath = os.path.join(pathToSaveTo, f"carddata.{language.code}.json")
	with open(mainCardCatalogPath, "w", encoding="utf-8") as cardfile:
		json.dump(cardCatalog, cardfile, indent=2)
	if shouldSaveDatedFile:
		datedCardCatalogPath = os.path.join(pathToSaveTo, f"carddata.{language.code}.{datetime.datetime.now().strftime('%Y-%m-%d.%H-%M-%S')}.json")
		with open(datedCardCatalogPath, "w", encoding="utf-8") as cardfile:
			json.dump(cardCatalog, cardfile, indent=2)


def downloadImage(imageUrl: str, savePath: str, shouldOverwriteImage: bool = False) -> bool:
	if not shouldOverwriteImage and os.path.isfile(savePath):
		_logger.debug(f"Image '{savePath}' already exists, skipping download")
		return False
	# Sometimes the server returns a 502 error, so try a few times
	attemptsLeft = 5
	imageResponse = None
	while attemptsLeft > 0:
		imageResponse = requests.get(imageUrl, headers={"user-agent": "Lorcana/2023.1", "x-unity-version": "2021.3.23f1"})
		if imageResponse.status_code == 200:
			break
		elif imageResponse.status_code != 200:
			attemptsLeft -= 1
	else:
		raise ValueError(f"Unable to download image '{imageUrl}' after several attempts, last response status code is {imageResponse.status_code if imageResponse else 'missing'}")
	os.makedirs(os.path.dirname(savePath), exist_ok=True)
	with open(savePath, "wb") as imageFile:
		imageFile.write(imageResponse.content)
	_logger.info(f"Successfully downloaded '{savePath}'")
	return True

def downloadImages(language: Language.Language, shouldOverwriteImages: bool = False, pathToCardCatalog: str = None):
	startTime = time.perf_counter()
	if not pathToCardCatalog:
		pathToCardCatalog = os.path.join("downloads", "json")
	cardCatalogPath = os.path.join(pathToCardCatalog, f"carddata.{language.code}.json")
	if not os.path.isfile(cardCatalogPath):
		retrieveAndSaveCardCatalog(language, pathToCardCatalog)
	with open(cardCatalogPath, "r", encoding="utf-8") as cardCatalogFile:
		cardCatalog = json.load(cardCatalogFile)
	imagesFound = 0
	imagesDownloaded = 0
	for cardType, cardList in cardCatalog["cards"].items():
		for card in cardList:
			for imageUrlDict in card["image_urls"]:
				if imageUrlDict["height"] == 2048:
					imagesFound += 1
					imageSavePath = os.path.join("downloads", "images", language.code, f"{card['culture_invariant_id']}.jpg")
					wasImageDownloaded = downloadImage(imageUrlDict["url"], imageSavePath, shouldOverwriteImages)
					if wasImageDownloaded:
						imagesDownloaded += 1
						time.sleep(2 * random.random())
					break
	# Download the external images too
	externalCardRevealsFileName = f"externalCardReveals.{language.code}.json"
	if os.path.isfile(externalCardRevealsFileName):
		with open(externalCardRevealsFileName, "r", encoding="utf-8") as externalCardRevealsFile:
			externalCardReveals = json.load(externalCardRevealsFile)
		if externalCardReveals:
			externalSavePath = os.path.join("downloads", "images", language.code, "external")
			os.makedirs(externalSavePath, exist_ok=True)
			for externalCardReveal in externalCardReveals:
				imagesFound += 1
				imageExtension = externalCardReveal["imageUrl"].rsplit(".", 1)[1]
				imageSavePath = os.path.join(externalSavePath, f"{externalCardReveal['culture_invariant_id']}.{imageExtension}")
				wasImageDownloaded = downloadImage(externalCardReveal["imageUrl"], imageSavePath, shouldOverwriteImages)
				if wasImageDownloaded:
					imagesDownloaded += 1
	_logger.info(f"Downloading {imagesDownloaded} of {imagesFound} {language.englishName} card images took {time.perf_counter() - startTime} seconds")

def downloadAllImages(shouldOverwriteImages: bool = False, pathToCardCatalog: str = None):
	startTime = time.perf_counter()
	for language in Language.ALL:
		downloadImages(language, shouldOverwriteImages, pathToCardCatalog)
	_logger.info(f"Downloading all card images took {time.perf_counter() - startTime} seconds")
