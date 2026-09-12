import hashlib, json, logging, os, pickle, shutil, time
from typing import Dict, List, Optional, Union, TypedDict

import tesserocr

import GlobalConfig
from OCR.OcrResult import OcrResult
from OCR.ParseSettings.ParseSettings import ParseSettings

class _Metadata(TypedDict):
	dataVersion: int
	fileHashes: Dict[str, str]
	tesseractLibraryVersions: str
	tesserocrVersion: str


_DATA_VERSION: int = 1
_logger = logging.getLogger("LorcanaJSON")
_cacheRelevantFilePaths = (os.path.join("OCR", "CardLayout.py"), os.path.join("OCR", "ImageArea.py"), os.path.join("OCR", "ImageParser.py"), os.path.join("OCR", "ParseSettings", "ParseSettingConstants.py"),
						   os.path.join("OCR", "ParseSettings", "ParseSettings.py"))
__metadata: Optional[_Metadata] = None  # Don't use this directly, use '_getMetadata()'

def _infoOrPrint(message: str):
	if _logger.level <= logging.INFO:
		_logger.info(message)
	else:
		print(message)

def _buildCacheBasePath() -> str:
	return os.path.join("output", "cachedOcr", GlobalConfig.language.code)

def _getMetadata() -> _Metadata:
	global __metadata
	if __metadata is None:
		currentHashes: Dict[str, str] = {}
		for cacheRelevantFilePath in _cacheRelevantFilePaths:
			with open(cacheRelevantFilePath, "rb") as cacheRelevantFile:
				currentHashes[cacheRelevantFilePath] = hashlib.file_digest(cacheRelevantFile, "md5").hexdigest()
		tesserocrVersion: str = tesserocr.__version__
		__metadata = {"dataVersion": _DATA_VERSION, "fileHashes": currentHashes, "tesseractLibraryVersions": tesserocr.tesseract_version(), "tesserocrVersion": tesserocrVersion}
	return __metadata

def _buildCachedOcrResultPath(resultIdentifier: Union[int, str], basePath: Optional[str] = None) -> str:
	return os.path.join(basePath if basePath else _buildCacheBasePath(), f"{resultIdentifier}.cachedOcr")

def validateOcrCache() -> bool:
	"""
	Check if the OCR cache is still valid. If it isn't, the cache will be cleared
	:return: True if the cache was valid, False if it wasn't and was cleared
	"""
	basePath = _buildCacheBasePath()
	metadataFilePath = os.path.join(basePath, "metadata.json")
	if not os.path.isfile(metadataFilePath):
		_infoOrPrint("OCR cache path doesn't exist, creating it for future checks")
		clearOcrCache()
		return False

	currentMetadata = _getMetadata()
	shouldClearCache = False
	with open(metadataFilePath, 'r', encoding="utf-8") as metadataFile:
		storedMetadata: _Metadata = json.load(metadataFile)
	if storedMetadata["dataVersion"] != currentMetadata["dataVersion"]:
		_infoOrPrint("OCR Cache data version mismatch, clearing OCR cache")
		shouldClearCache = True
	elif storedMetadata["tesserocrVersion"] != currentMetadata["tesserocrVersion"]:
		_infoOrPrint(f"Existing cache was made with tesserocr {storedMetadata['tesserocrVersion']}, current tesserocr version is {currentMetadata['tesserocrVersion']}; Clearing OCR cache")
		shouldClearCache = True
	elif storedMetadata["tesseractLibraryVersions"] != currentMetadata["tesseractLibraryVersions"]:
		_infoOrPrint(f"Existing cache was made with Tesseract version {storedMetadata['tesseractLibraryVersions']!r}, current Tesseract version is {currentMetadata['tesseractLibraryVersions']!r}; Clearing OCR cache")
		shouldClearCache = True
	else:
		for cacheHashCheckFilePath in _cacheRelevantFilePaths:
			if cacheHashCheckFilePath in storedMetadata["fileHashes"]:
				# Check if the stored MD5 hash matches the current MD5 hash
				if storedMetadata["fileHashes"][cacheHashCheckFilePath] != currentMetadata["fileHashes"][cacheHashCheckFilePath]:
					_infoOrPrint(f"MD5 mismatch for '{cacheHashCheckFilePath}', clearing OCR cache")
					shouldClearCache = True
					break
			else:
				_infoOrPrint(f"File '{cacheHashCheckFilePath}' is missing from OCR cache hashes file, clearing OCR cache")
				shouldClearCache = True
				break

	if shouldClearCache:
		clearOcrCache()
	return not shouldClearCache

def clearOcrCache():
	startTime = time.perf_counter()
	basePath = _buildCacheBasePath()
	if os.path.isdir(basePath):
		with os.scandir(basePath) as cacheFolderIterator:
			for ocrCacheEntry in cacheFolderIterator:
				if ocrCacheEntry.is_dir():
					shutil.rmtree(ocrCacheEntry.path)
				else:
					os.remove(ocrCacheEntry.path)
	# Create the hash file, so subsequent runs don't keep clearing the cache
	os.makedirs(basePath, exist_ok=True)
	with open(os.path.join(basePath, "metadata.json"), "w") as metadataFile:
		json.dump(_getMetadata(), metadataFile)
	_logger.info(f"Clearing OCR cache took {time.perf_counter() - startTime:.4f} seconds")

def clearOcrCacheForCards(resultIdentifiersToClear: List[Union[int, str]]):
	basePath = _buildCacheBasePath()
	for resultIdentifierToClear in resultIdentifiersToClear:
		clearOcrCacheForCard(resultIdentifierToClear, basePath)
	_logger.info(f"Cleared OCR cache for {len(resultIdentifiersToClear):,} cards")

def clearOcrCacheForCard(resultIdentifierToClear: Union[int, str], basepath: Optional[str] = None):
	cachedOcrResultPath = _buildCachedOcrResultPath(resultIdentifierToClear, basepath)
	if os.path.isfile(cachedOcrResultPath):
		os.remove(cachedOcrResultPath)
		_logger.info(f"Cleared OCR cache result for identifier '{resultIdentifierToClear}'")

def getCachedOcrResult(resultIdentifier: Union[int, str], parseSettings: ParseSettings) -> Optional[OcrResult]:
	"""
	Retrieve the OCR result for the provided result identifier from the OCR cache, if it exists
	:param resultIdentifier: The identifier under which an OCR Result was previously saved
	:param parseSettings: The ParseSettings with which this card should be parsed. Needed to see if the stored result used the same ParseSettings, if not it's invalid
	:return: The cached OCR result for the provided identifier, or None if it couldn't be found or loaded
	"""
	cachedOcrResultPath = _buildCachedOcrResultPath(resultIdentifier)
	if not os.path.isfile(cachedOcrResultPath):
		return None
	try:
		with open(cachedOcrResultPath, "rb") as cachedCardOcrFile:
			storedOcrResult: OcrResult = pickle.load(cachedCardOcrFile)
		if parseSettings != storedOcrResult.parseSettingsUsed:
			clearOcrCacheForCard(resultIdentifier)
			return None
		return storedOcrResult
	except Exception as e:
		_logger.error(f"Unable to load cached OCR result for result identifier {resultIdentifier!r}: {e}")
		return None

def storeOcrResult(resultIdentifier: Union[int, str], ocrResult: OcrResult):
	cachedOcrResultPath = _buildCachedOcrResultPath(resultIdentifier)
	with open(cachedOcrResultPath, "wb") as cachedOcrResultFile:
		pickle.dump(ocrResult, cachedOcrResultFile)
