import datetime, json, os

import GlobalConfig

from typing import Dict

def saveCardCatalog(cardCatalog: Dict, shouldSaveDatedFile: bool = True):
	pathToSaveTo = os.path.join("downloads", "json")
	os.makedirs(pathToSaveTo, exist_ok=True)
	with open(os.path.join(pathToSaveTo, f"carddata.{GlobalConfig.language.code}.json"), "w", encoding="utf-8") as cardfile:
		json.dump(cardCatalog, cardfile, indent=2)
	if shouldSaveDatedFile:
		now = datetime.datetime.now()
		pathToSaveTo = os.path.join(pathToSaveTo, str(now.year), GlobalConfig.language.code)
		os.makedirs(pathToSaveTo, exist_ok=True)
		datedCardCatalogPath = os.path.join(pathToSaveTo, f"carddata.{GlobalConfig.language.code}.{now.strftime('%Y-%m-%d.%H-%M-%S')}.json")
		with open(datedCardCatalogPath, "w", encoding="utf-8") as cardfile:
			json.dump(cardCatalog, cardfile, indent=2)
