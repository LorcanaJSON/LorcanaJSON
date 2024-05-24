import argparse, datetime, json, logging, logging.handlers, os, re, sys, time

import DataFilesGenerator, GlobalConfig, Language, UpdateHandler
from APIScraping import RavensburgerApiHandler
from OCR.ImageParser import ImageParser


if __name__ == '__main__':
	argumentParser = argparse.ArgumentParser(description="Handle LorcanaJSON data, depending on the action argument")
	argumentParser.add_argument("action", choices=("check", "update", "download", "parse", "show"), help="Specify the action to take. "
																										 "'check' checks if new card data is available, 'update' actually updates the local card datafiles. "
																										 "'download' downloads missing images. "
																										 "'parse' parses the images specified in the 'cardIds' argument. "
																										 "'show' shows the image(s) specified in the 'cardIds' argument along with subimages used in parsing")
	argumentParser.add_argument("--loglevel", dest="loglevel", choices=("debug", "info", "warning", "error"), default=None, help="Specify the log level. If omitted, defaults to 'warning'")
	argumentParser.add_argument("--tesseractPath", help="Specify the path to Tesseract. This is needed if Tesseract can't just be called with 'tesseract' from the commandline")
	argumentParser.add_argument("--language", help="Specify the language to use by its two-letter code. Defaults to 'en'", default="en")
	argumentParser.add_argument("--cardIds", nargs="*", help="List the card IDs to parse. For the 'show' action, specify one or more card IDs to show. "
															 "For the 'parse' action, specify one or more card IDs to parse, or omit this argument to parse all cards. "
															 "For other actions, this field is ignored")
	argumentParser.add_argument("--ignoreFields", nargs="*", help="Specify one or more card fields to ignore when checking for updates. Only used with the 'check' action", default=["foil_mask_url", "image_urls"])
	argumentParser.add_argument("--show", action="store_true", dest="shouldShowSubimages", help="If added, the program shows all the subimages used during parsing. It stops processing until the displayed images are closed, so this is a slow option")
	argumentParser.add_argument("--threads", type=int, help="Specify how many threads should be used when executing multithreaded tasks. Specify a negative amount to use the maximum number of threads available minus the provided amount. "
															"Leave empty to have the amount be determined automatically")
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
	if not os.path.isdir("logs"):
		os.mkdir("logs")
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

	GlobalConfig.tesseractPath = os.path.dirname(__file__)
	if parsedArguments.tesseractPath:
		GlobalConfig.tesseractPath = parsedArguments.tesseractPath
	elif config.get("tesseractPath", None):
		GlobalConfig.tesseractPath = config["tesseractPath"]

	GlobalConfig.language = Language.getLanguageByCode(parsedArguments.language)
	logger.info(f"Using language '{GlobalConfig.language.englishName}'")

	if parsedArguments.threads:
		GlobalConfig.threadCount = parsedArguments.threads
		if GlobalConfig.threadCount < 0:
			GlobalConfig.threadCount = os.cpu_count() + GlobalConfig.threadCount

	cardIds = None
	if parsedArguments.cardIds:
		cardIds = []
		for inputCardId in parsedArguments.cardIds:
			if "-" in inputCardId:
				# This is either a negative number or a range
				if inputCardId.startswith("-"):
					# Negative number, remove the ID from the to-parse list, if it's there
					cardIdToRemove = int(inputCardId, 10) * -1
					if cardIdToRemove in cardIds:
						cardIds.remove(cardIdToRemove)
					else:
						logger.warning(f"Asked to remove card ID {cardIdToRemove} from parsing, but it already wasn't in the parse list. Verify the '--cardIds' parameter list")
				else:
					# Range, add all the IDs in the range
					cardIdRangeMatch = re.match(r"(\d+)-(\d+)", inputCardId)
					if cardIdRangeMatch:
						lowerBound = int(cardIdRangeMatch.group(1), 10)
						upperBound = int(cardIdRangeMatch.group(2), 10)
						cardIds.extend(list(range(lowerBound, upperBound + 1)))
					else:
						raise ValueError(f"Invalid range value '{inputCardId}' in the '--cardIds' list")
			else:
				# Normal number, add it to the to-parse list
				try:
					cardIds.append(int(inputCardId, 10))
				except ValueError:
					raise ValueError(f"Invalid value '{inputCardId}' in the '--cardIds' list, should be numeric")

	startTime = time.perf_counter()
	if parsedArguments.action == "check":
		addedCards, cardChanges = UpdateHandler.checkForNewCardData(fieldsToIgnore=parsedArguments.ignoreFields)
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
		UpdateHandler.createOutputIfNeeded(False, cardFieldsToIgnore=parsedArguments.ignoreFields, shouldShowImages=parsedArguments.shouldShowSubimages)
	elif parsedArguments.action == "download":
		# Make sure we download from an up-to-date card catalog
		cardCatalog = RavensburgerApiHandler.retrieveCardCatalog()
		addedCards, changedCards = UpdateHandler.checkForNewCardData(cardCatalog, fieldsToIgnore=parsedArguments.ignoreFields)
		if addedCards or changedCards:
			print(f"Card catalog for language '{GlobalConfig.language.englishName}' was updated, saving")
			RavensburgerApiHandler.saveCardCatalog(cardCatalog)
		else:
			print(f"No new version of the card catalog for language '{GlobalConfig.language.englishName}' found")
		RavensburgerApiHandler.downloadImages()
	elif parsedArguments.action == "parse":
		DataFilesGenerator.createOutputFiles(cardIds, shouldShowImages=parsedArguments.shouldShowSubimages)
	elif parsedArguments.action == "show":
		if not cardIds:
			print("ERROR: Please provide one or more card IDs to show with the '--cardIds' argument")
			sys.exit(-3)
		baseImagePath = os.path.join("downloads", "images", GlobalConfig.language.code)
		for cardId in cardIds:
			cardPath = os.path.join(baseImagePath, f"{cardId}.jpg")
			if not os.path.isfile(cardPath):
				cardPath = os.path.join(baseImagePath, "external", f"{cardId}.png")
			if not os.path.isfile(cardPath):
				cardPath = os.path.join(baseImagePath, "external", f"{cardId}.jpg")
			if not os.path.isfile(cardPath):
				print(f"ERROR: Unable to find local image for card ID {cardId}. Please run the 'download' command first, and make sure you didn't make a typo in the ID")
				sys.exit(-4)
			parsedImageAndTextData = ImageParser().getImageAndTextDataFromImage(cardPath, True, showImage=True)
			print(f"Card ID {cardId}")
			for fieldName, fieldResult in parsedImageAndTextData.items():
				if fieldResult is None:
					print(f"{fieldName} is empty")
				elif isinstance(fieldResult, list):
					for fieldResultIndex, fieldResultItem in enumerate(fieldResult):
						print(f"{fieldName} index {fieldResultIndex}: {fieldResultItem.text!r}")
				else:
					print(f"{fieldName}: {fieldResult.text!r}")
			print("")
	else:
		print(f"Unknown action '{parsedArguments.action}', please (re)read the help or the readme")
		sys.exit(-10)

	print(f"Action '{parsedArguments.action}' for language '{GlobalConfig.language.englishName}' finished after {time.perf_counter() - startTime:.2f} seconds at {datetime.datetime.now()}")
