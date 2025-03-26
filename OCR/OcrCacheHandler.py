import hashlib, json, logging, os, pickle, shutil
from typing import Dict, Union

import GlobalConfig
from OCR.OcrResult import OcrResult


_logger = logging.getLogger("LorcanaJSON")
_cachePath = os.path.join("output", "generated", "cachedOcr")
_cacheHashesFilePath = os.path.join(_cachePath, "cacheHashes")
_cacheRelevantFilePaths = (os.path.join("OCR", "ImageArea.py"), os.path.join("OCR", "ImageParser.py"), os.path.join("OCR", "ParseSettings.py"))

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

def _buildCachedOcrResultPath(cardId: int):
	return os.path.join(_cachePath, GlobalConfig.language.code, f"{cardId}.cachedOcr")

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
	else:
		_infoOrPrint("OCR Cache hashes file is missing, rebuilding OCR cache")
		shouldClearCache = True

	if shouldClearCache:
		clearOcrCache(currentHashes)
	return not shouldClearCache

def clearOcrCache(fileHashes: Union[None, Dict[str, str]] = None):
	"""
	Clear the OCR cache
	:param fileHashes: The MD5 hashes of relevant files. If this is None, it will be generated
	"""
	if fileHashes is None:
		fileHashes = _buildFileHashes()
	with os.scandir(_cachePath) as cacheFolderIterator:
		for ocrCacheEntry in cacheFolderIterator:
			if ocrCacheEntry.is_dir():
				shutil.rmtree(ocrCacheEntry.path)
			else:
				os.remove(ocrCacheEntry.path)
	# Create the hash file, so subsequent runs don't keep clearing the cache
	with open(_cacheHashesFilePath, "w", encoding="utf-8") as cacheHashesFile:
		json.dump(fileHashes, cacheHashesFile)

def getCachedOcrResult(cardId: int) -> Union[OcrResult, None]:
	"""
	Retrieve the OCR result for the provided card ID from the OCR cache, if it exists
	:param cardId: The ID of the card to get the cached OCR result for
	:return: The cached OCR result for the provided card ID, or None if it couldn't be found or loaded
	"""
	cachedOcrResultPath = _buildCachedOcrResultPath(cardId)
	if os.path.isfile(cachedOcrResultPath):
		try:
			with open(cachedOcrResultPath, "rb") as cachedCardOcrFile:
				return pickle.load(cachedCardOcrFile)
		except Exception as e:
			_logger.error(f"Unable to load cached OCR result for card ID {cardId}")
	return None

def storeOcrResult(cardId: int, ocrResult: OcrResult):
	with open(_buildCachedOcrResultPath(cardId), "wb") as cachedOcrResultFile:
		pickle.dump(ocrResult, cachedOcrResultFile)
