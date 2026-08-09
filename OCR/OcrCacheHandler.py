import hashlib, json, logging, os, pickle, shutil, time
from typing import Dict, List, Optional, Union

import GlobalConfig
from OCR.OcrResult import OcrResult
from OCR.ParseSettings import ParseSettingsPicker
from OCR.ParseSettings.ParseSettings import ParseSettings


_logger = logging.getLogger("LorcanaJSON")
_cachePath = os.path.join("output", "cachedOcr")
_cacheHashesFilePath = os.path.join(_cachePath, "cacheHashes")
_cacheRelevantFilePaths = (os.path.join("OCR", "CardLayout.py"), os.path.join("OCR", "ImageArea.py"), os.path.join("OCR", "ImageParser.py"), os.path.join("OCR", "ParseSettings", "ParseSettingConstants.py"),
						   os.path.join("OCR", "ParseSettings", "ParseSettings.py"))

def _infoOrPrint(message: str):
	if _logger.level <= logging.INFO:
		_logger.info(message)
	else:
		print(message)

def _buildFileHashes() -> Dict[str, str]:
	currentHashes = {}
	for cacheRelevantFilePath in _cacheRelevantFilePaths:
		with open(cacheRelevantFilePath, "rb") as cacheRelevantFile:
			currentHashes[cacheRelevantFilePath] = hashlib.file_digest(cacheRelevantFile, "md5").hexdigest()
	return currentHashes

def _buildCachedOcrResultPath(resultIdentifier: Union[int, str]):
	return os.path.join(_cachePath, GlobalConfig.language.code, f"{resultIdentifier}.cachedOcr")

def validateOcrCache() -> bool:
	"""
	Check if the OCR cache is still valid. If it isn't, the cache will be cleared
	:return: True if the cache was valid, False if it wasn't and was cleared
	"""
	if not os.path.isdir(_cachePath):
		_infoOrPrint("OCR cache path doesn't exist, creating it and hashes file for future checks")
		os.makedirs(_cachePath)
		with open(_cacheHashesFilePath, "w", encoding="utf-8") as cacheHashesFile:
			json.dump(_buildFileHashes(), cacheHashesFile)
		return False

	currentHashes = _buildFileHashes()
	shouldClearCache = False
	if os.path.isfile(_cacheHashesFilePath):
		with open(_cacheHashesFilePath, 'r', encoding="utf-8") as cacheHashesFile:
			cacheHashes = json.load(cacheHashesFile)
			for cacheHashCheckFilePath in _cacheRelevantFilePaths:
				if cacheHashCheckFilePath in cacheHashes:
					# Check if the stored MD5 hash matches the current MD5 hash
					if cacheHashes[cacheHashCheckFilePath] != currentHashes[cacheHashCheckFilePath]:
						_infoOrPrint(f"MD5 mismatch for '{cacheHashCheckFilePath}', clearing OCR cache")
						shouldClearCache = True
						break
				else:
					_infoOrPrint(f"File '{cacheHashCheckFilePath}' is missing from OCR cache hashes file, clearing OCR cache")
					shouldClearCache = True
					break
	else:
		_infoOrPrint("OCR Cache hashes file is missing, rebuilding OCR cache")
		shouldClearCache = True

	if shouldClearCache:
		clearOcrCache(currentHashes)
	return not shouldClearCache

def clearOcrCache(fileHashes: Optional[Dict[str, str]] = None):
	"""
	Clear the OCR cache
	:param fileHashes: The MD5 hashes of relevant files. If this is None, it will be generated
	"""
	startTime = time.perf_counter()
	if fileHashes is None:
		fileHashes = _buildFileHashes()
	if os.path.isdir(_cachePath):
		with os.scandir(_cachePath) as cacheFolderIterator:
			for ocrCacheEntry in cacheFolderIterator:
				if ocrCacheEntry.is_dir():
					shutil.rmtree(ocrCacheEntry.path)
				else:
					os.remove(ocrCacheEntry.path)
	else:
		os.makedirs(_cachePath, exist_ok=True)
	# Create the hash file, so subsequent runs don't keep clearing the cache
	with open(_cacheHashesFilePath, "w", encoding="utf-8") as cacheHashesFile:
		json.dump(fileHashes, cacheHashesFile)
	_logger.info(f"Clearing OCR cache took {time.perf_counter() - startTime:.4f} seconds")

def clearOcrCacheForCards(resultIdentifiersToClear: List[Union[int, str]]):
	for resultIdentifierToClear in resultIdentifiersToClear:
		clearOcrCacheForCard(resultIdentifierToClear)
	_logger.info(f"Cleared OCR cache for {len(resultIdentifiersToClear):,} cards")

def clearOcrCacheForCard(resultIdentifierToClear: Union[int, str]):
	cachedOcrResultPath = _buildCachedOcrResultPath(resultIdentifierToClear)
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
	os.makedirs(os.path.dirname(cachedOcrResultPath), exist_ok=True)
	with open(cachedOcrResultPath, "wb") as cachedOcrResultFile:
		pickle.dump(ocrResult, cachedOcrResultFile)
