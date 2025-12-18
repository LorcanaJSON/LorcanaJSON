import json, os
from typing import Dict, List, Optional


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
