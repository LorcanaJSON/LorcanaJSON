import json, os, re
from typing import Dict, List, Optional

import GlobalConfig
from util import Language


class ArtistsHandler:
	def __init__(self):
		self._nameToNormalizedName: Dict[str, str] = {}
		with open(os.path.join("OutputGeneration", "data", "artistAliases.json"), "r", encoding="utf-8") as artistAliasesFile:
			for normalizedName, aliases in json.load(artistAliasesFile).items():
				for alias in aliases:
					self._nameToNormalizedName[alias] = normalizedName

	def getNormalizedNames(self, cardArtists: List[str]) -> Optional[List[str]]:
		"""
		Get a list of normalized artist names based on the list of names on the card.
		A normalized name is either fixing a typo, using the artist's new or preferred name, or expanding a shortened name
		If all the normalized names would be the same as the card names, this returns None
		:param cardArtists: The list of artists names as listed on the card
		:return: A list of the card artist names but normalized, or None if normalization isn't necessary
		"""
		normalizedNames: Optional[List[str]] = None
		for cardArtistIndex in range(len(cardArtists)):
			cardArtist = cardArtists[cardArtistIndex]
			if cardArtist in self._nameToNormalizedName:
				if normalizedNames is None:
					normalizedNames = cardArtists.copy()
				normalizedNames[cardArtistIndex] = self._nameToNormalizedName[cardArtist]
		return normalizedNames

	@staticmethod
	def correctArtistName(inputArtistText: str) -> str:
		correctedArtistText = inputArtistText.lstrip(". ").replace("’", "'").replace("|", "l").replace("NM", "M")
		correctedArtistText = re.sub(r"(^l|\[)", "I", correctedArtistText)
		correctedArtistText = correctedArtistText.replace(" 0. ", " O. ")
		while re.search(r" [a-zAè0-9ÿI|(){\\/_+*%.,;'‘”#¥©=—-]{1,2}$", correctedArtistText):
			correctedArtistText = correctedArtistText.rsplit(" ", 1)[0]
		correctedArtistText = correctedArtistText.rstrip(".")
		if "ggman-Sund" in correctedArtistText:
			correctedArtistText = re.sub("H[^ä]ggman-Sund", "Häggman-Sund", correctedArtistText)
		# elif "Toziim" in correctedArtistText or "Tôzüm" in correctedArtistText or "Toztim" in correctedArtistText or "Tézim" in correctedArtistText:
		elif re.search(r"T[eéoô]z[iüt]{1,2}m\b", correctedArtistText):
			correctedArtistText = re.sub(r"\bT\w+z\w+m\b", "Tözüm", correctedArtistText)
		elif re.match(r"Jo[^ã]o\b", correctedArtistText):
			correctedArtistText = re.sub("Jo[^ã]o", "João", correctedArtistText)
		elif re.search(r"Krysi.{1,2}ski", correctedArtistText):
			correctedArtistText = re.sub(r"Krysi.{1,2}ski", "Krysiński", correctedArtistText)
		elif "Cesar Vergara" in correctedArtistText:
			correctedArtistText = correctedArtistText.replace("Cesar Vergara", "César Vergara")
		elif "Roger Perez" in correctedArtistText:
			correctedArtistText = re.sub(r"\bPerez\b", "Pérez", correctedArtistText)
		elif correctedArtistText.startswith("Niss ") or correctedArtistText.startswith("Nilica "):
			correctedArtistText = "M" + correctedArtistText[1:]
		elif GlobalConfig.language == Language.GERMAN:
			# For some bizarre reason, the German parser reads some artist names as something completely different
			if re.match(r"^ICHLER[GS]I?EN$", correctedArtistText):
				correctedArtistText = "Jenna Gray"
			elif correctedArtistText == "ES" or correctedArtistText == "ET":
				correctedArtistText = "Lauren Levering"
			correctedArtistText = correctedArtistText.replace("Dösiree", "Désirée")
			correctedArtistText = re.sub(r"Man[6e]+\b", "Mané", correctedArtistText)
		correctedArtistText = re.sub(r"\bAime\b", "Aimé", correctedArtistText)
		correctedArtistText = re.sub(r"\blvan\b", "Ivan", correctedArtistText)
		correctedArtistText = re.sub("Le[éòöô]n", "León", correctedArtistText)
		correctedArtistText = re.sub(r"^N(?=ichael)", "M", correctedArtistText)
		correctedArtistText = re.sub(r"\bPe[^ñ]+a\b", "Peña", correctedArtistText)
		if "“" in correctedArtistText:
			# Simplify quotemarks
			correctedArtistText = correctedArtistText.replace("“", "\"").replace("”", "\"")
		return correctedArtistText
