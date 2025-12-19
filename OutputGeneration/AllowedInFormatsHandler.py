import json, os
from typing import Dict, List, Optional, Union


class AllowedInFormatsHandler:
	def __init__(self):
		with open(os.path.join("OutputGeneration", "data", "CardBans.json"), "r", encoding="utf-8") as cardBansFile:
			# Each format has a dict with the card ID string as a key
			self.cardBans: dict[str, dict[str, str]] = json.load(cardBansFile)
		with open(os.path.join("OutputGeneration", "data", "baseSetData.json"), "r", encoding="utf-8") as setsFile:
			self.allowedInFormatsBySetCode: Dict[str, Dict[str, Dict[str, Union[bool, str]]]] = {}  # For each set-code, a dictionary with as key the format name and as value a dictionary with allowed boolean and dates
			self.allowedFromDateBySetCode: Dict[str, str] = {}
			for setCode, setData in json.load(setsFile).items():
				self.allowedInFormatsBySetCode[setCode] = setData["allowedInFormats"]
				self.allowedFromDateBySetCode[setCode] = setData["allowedInTournamentsFromDate"]

	def getAllowedInFormatsForCard(self, cardId: str, printedInSets: List[str]) -> "AllowedInFormats":
		"""
		Get whether the provided card is allowed in various play formats
		:param cardId: The ID of the card to get the allowed-data for, as a string
		:param printedInSets: A list of setcodes that this card was printed in
		:return: An 'AllowedInFormats' instance with allowed-data for formas
		"""
		oldestSetCode = min(printedInSets)
		newestSetCode = max(printedInSets)
		allowedInOldestSet: Dict[str, Dict[str, Union[bool, str]]] = self.allowedInFormatsBySetCode[oldestSetCode]
		allowedInNewestSet: Dict[str, Dict[str, Union[bool, str]]] = self.allowedInFormatsBySetCode[newestSetCode]

		allowedInFormats: AllowedInFormats = AllowedInFormats(self.allowedFromDateBySetCode[oldestSetCode])
		# Fill in Core values
		if "allowedUntilDate" in allowedInNewestSet["Core"]:
			allowedInFormats.allowedInCore.allowedUntil = allowedInNewestSet["Core"]["allowedUntilDate"]
		if cardId in self.cardBans["Core"]:
			allowedInFormats.allowedInCore.allowed = False
			allowedInFormats.allowedInCore.bannedSince = self.cardBans["Core"][cardId]
			if allowedInFormats.allowedInCore.allowedUntil and allowedInFormats.allowedInCore.allowedUntil > allowedInFormats.allowedInCore.bannedSince:
				allowedInFormats.allowedInCore.allowedUntil = allowedInFormats.allowedInCore.bannedSince
		else:
			allowedInFormats.allowedInCore.allowed = allowedInOldestSet["Core"]["allowed"] or allowedInNewestSet["Core"]["allowed"]

		# Fill in Infinity values
		if cardId in self.cardBans["Infinity"]:
			allowedInFormats.allowedInInfinity.allowed = False
			allowedInFormats.allowedInInfinity.bannedSince = self.cardBans["Infinity"][cardId]
		else:
			allowedInFormats.allowedInInfinity.allowed = allowedInOldestSet["Infinity"]["allowed"] or allowedInNewestSet["Infinity"]["allowed"]

		return allowedInFormats


class AllowedInFormat:
	def __init__(self):
		self.allowed: bool = False
		self.allowedUntil: Optional[str] = None
		self.bannedSince: Optional[str] = None


class AllowedInFormats:
	def __init__(self, allowedInTournamentsFromDate: str):
		self.allowedInTournamentsFromDate: str = allowedInTournamentsFromDate
		self.allowedInCore: AllowedInFormat = AllowedInFormat()
		self.allowedInInfinity: AllowedInFormat = AllowedInFormat()
