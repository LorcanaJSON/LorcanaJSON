import json

def loadJsonWithNumberKeys(pathToJson):
	"""
	Load a JSON file that has keys that should be numbers but are strings because of JSON lmitations, and convert those keys to numbers
	:param pathToJson: The path to the JSON file to load and convert the keys of
	:return: A dictionary of the JSON specified by 'pathToJson', with the keys converted from strings to numbers
	"""
	with open(pathToJson, "r", encoding="utf-8") as jsonFile:
		return {int(k, 10): v for k, v in json.load(jsonFile).items()}
