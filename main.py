import argparse, json, logging, logging.handlers, os, sys

import pytesseract

import DataFilesGenerator, Language, UpdateHandler
from APIScraping import RavensburgerApiHandler
from OCR import ImageParser


if __name__ == '__main__':
	argumentParser = argparse.ArgumentParser(description="Handle LorcanaJSON data, depending on the action argument")
	argumentParser.add_argument("action", choices=("check", "update", "download", "parse", "show"), help="Specify the action to take. "
																										 "'check' checks if new card data is available, 'update' actually updates the local card datafiles. "
																										 "'download' downloads missing images. "
																										 "'parse' parses the images specified in the 'cardIds' argument. "
																										 "'show' shows the image(s) specified in the 'cardIds' argument along with subimages used in parsing")
	argumentParser.add_argument("--loglevel", dest="loglevel", choices=("debug", "info", "warning", "error"), default=None, help="Specify the log level. If omitted, defaults to 'warning'")
	argumentParser.add_argument("--tesseractPath", help="Specify the path to Tesseract. This is needed if Tesseract can't just be called with 'tesseract' from the commandline")
	argumentParser.add_argument("--language", help="Specify the language to use by its two-letter code. Defaults to 'en'", default="en", choices=[lang.code for lang in Language.ALL])
	argumentParser.add_argument("--cardIds", nargs="*", help="List the card IDs to parse. For the 'show' action, specify one or more card IDs to show. "
															 "For the 'parse' action, specify one or more card IDs to parse, or omit this argument to parse all cards. "
															 "For other actions, this field is ignored")
	argumentParser.add_argument("--ignoreFields", nargs="*", help="Specify one or more card fields to ignore when checking for updates. Only used with the 'check' action", default=["foil_mask_url", "image_urls"])
	argumentParser.add_argument("--show", action="store_true", dest="shouldShowSubimages", help="If added, the program shows all the subimages used during parsing. It stops processing until the displayed images are closed, so this is a slow option")
	parsedArguments = argumentParser.parse_args()

	config = {}
	if os.path.isfile("config.json"):
		with open("config.json", "r") as configFile:
			config = json.load(configFile)

	# Set up logging
	logger = logging.getLogger("LorcanaJSON")
	loglevelName = "warning"
	if parsedArguments.loglevel:
		loglevelName = parsedArguments.loglevel
	elif "loglevel" in config:
		loglevelName = config["loglevel"]
	if loglevelName == "debug":
		loglevel = logging.DEBUG
	elif loglevelName == "info":
		loglevel = logging.INFO
	elif loglevelName == "warning":
		loglevel = logging.WARNING
	elif loglevelName == "error":
		loglevel = logging.ERROR
	else:
		print(f"ERROR: Invalid loglevel '{loglevelName}' provided")
		sys.exit(-1)
	logger.setLevel(loglevel)

	loggingFormatter = logging.Formatter('%(asctime)s (%(levelname)s) %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
	#Log everything to a file. Use a new file each time the program is launched
	logfilePath = os.path.join("logs", "LorcanaJSON.log")
	loggingFileHandler = logging.handlers.RotatingFileHandler(logfilePath, mode="w", backupCount=10, encoding="utf-8", delay=True)
	loggingFileHandler.setLevel(logging.DEBUG)
	loggingFileHandler.setFormatter(loggingFormatter)
	if os.path.isfile(logfilePath):
		loggingFileHandler.doRollover()
	logger.addHandler(loggingFileHandler)

	#Also print everything to the console
	loggingStreamHandler = logging.StreamHandler(sys.stdout)
	loggingStreamHandler.setLevel(logging.DEBUG)
	loggingStreamHandler.setFormatter(loggingFormatter)
	logger.addHandler(loggingStreamHandler)

	# Make sure PyTesseract can find the Tesseract executable, if it isn't in the Path
	if parsedArguments.tesseractPath:
		pytesseract.pytesseract.tesseract_cmd = parsedArguments.tesseractPath
	elif config.get("tesseractPath", None):
		pytesseract.pytesseract.tesseract_cmd = config["tesseractPath"]

	for language in Language.ALL:
		if parsedArguments.language == language.code:
			break
	else:
		print(f"Invalid language code '{parsedArguments.language}'")
		sys.exit(-2)
	ImageParser.setModel(language, True)

	if parsedArguments.action == "check":
		addedCards, cardChanges = UpdateHandler.checkForNewCardData(language, fieldsToIgnore=parsedArguments.ignoreFields)
		print(f"{len(addedCards):,} added cards: {addedCards}")
		# Count which fields changed
		fieldsChanged = {}
		for cardChange in cardChanges:
			fieldChanged = cardChange[2]
			if fieldChanged not in fieldsChanged:
				fieldsChanged[fieldChanged] = 1
			else:
				fieldsChanged[fieldChanged] += 1
		print(f"{len(cardChanges):,} changes {fieldsChanged}:")
		for cardChange in cardChanges:
			print(cardChange)
	elif parsedArguments.action == "update":
		UpdateHandler.createOutputIfNeeded(language, False, cardFieldsToIgnore=parsedArguments.ignoreFields, shouldShowImages=parsedArguments.shouldShowSubimages)
	elif parsedArguments.action == "download":
		RavensburgerApiHandler.downloadImages(language)
	elif parsedArguments.action == "parse":
		idsToParse = None
		if parsedArguments.cardIds:
			idsToParse = [int(v) for v in parsedArguments.cardIds]
		DataFilesGenerator.createOutputFiles(language, idsToParse, shouldShowImages=parsedArguments.shouldShowSubimages)
	elif parsedArguments.action == "show":
		if not parsedArguments.cardIds:
			print("ERROR: Please provide one or more card IDs to show with the '--cardIds' argument")
			sys.exit(-3)
		baseImagePath = os.path.join("downloads", "images", language.code)
		for cardId in parsedArguments.cardIds:
			cardPath = os.path.join(baseImagePath, f"{cardId}.jpg")
			if not os.path.isfile(cardPath):
				print(f"ERROR: Unable to find local image for card ID {cardId}. Please run the 'download' command first, and make sure you didn't make a typo in the ID")
				sys.exit(-4)
			parsedImageAndTextData = ImageParser.getImageAndTextDataFromImage(cardPath, showImage=True)
			print(f"Card ID {cardId}:")
			print(parsedImageAndTextData)
	else:
		print(f"Unknown action '{parsedArguments.action}', please (re)read the help")
		sys.exit(-10)
