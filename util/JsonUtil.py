import json
from typing import Dict, Any

def convertStringKeysToNumberKeys(inputDict: Dict[str, Any]) -> Dict[int, Any]:
	"""
	Converts the provided dictionary with string keys to a dictionary with number keys
	:param inputDict: The dictionary to convert
	:return: The dictionary with number keys instead of string keys, with unchanged values
	"""
	return {int(k, 10): v for k, v in inputDict.items()}

def loadJsonWithNumberKeys(pathToJson: str) -> Dict[int, Any]:
	"""
	Load a JSON file that has keys that should be numbers but are strings because of JSON lmitations, and convert those keys to numbers
	:param pathToJson: The path to the JSON file to load and convert the keys of
	:return: A dictionary of the JSON specified by 'pathToJson', with the keys converted from strings to numbers
	"""
	with open(pathToJson, "r", encoding="utf-8") as jsonFile:
		return convertStringKeysToNumberKeys(json.load(jsonFile))
