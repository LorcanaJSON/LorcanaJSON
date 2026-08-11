import json, os
from typing import Dict, List, Optional, TypedDict


class AllowedInFormatsHandler:
	def __init__(self):
		with open(os.path.join("OutputGeneration", "data", "CardBans.json"), "r", encoding="utf-8") as cardBansFile:
			# Each format has a dict with the card ID string as a key
			self.cardBans: dict[str, dict[str, str]] = json.load(cardBansFile)
		with open(os.path.join("OutputGeneration", "data", "baseSetData.json"), "r", encoding="utf-8") as setsFile:
			self.allowedInFormatsBySetCode: Dict[str, Dict[str, _AllowedForFormatInputData]] = {}  # For each set-code, a dictionary with as key the format name and as value a dictionary with allowed boolean and dates
			self.allowedFromDateBySetCode: Dict[str, Optional[str]] = {}
			for setCode, setData in json.load(setsFile).items():
				self.allowedInFormatsBySetCode[setCode]: Dict[str, _AllowedForFormatInputData] = setData["allowedInFormats"]
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
		allowedInOldestSet: Dict[str, _AllowedForFormatInputData] = self.allowedInFormatsBySetCode[oldestSetCode]
		allowedInNewestSet: Dict[str, _AllowedForFormatInputData] = self.allowedInFormatsBySetCode[newestSetCode]

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


class _AllowedForFormatInputData(TypedDict, total=False):
	allowed: bool
	allowedUntilDate: str
	rotationGroup: int


class AllowedInFormat:
	def __init__(self):
		self.allowed: bool = False
		self.allowedUntil: Optional[str] = None
		self.bannedSince: Optional[str] = None


class AllowedInFormats:
	def __init__(self, allowedInTournamentsFromDate: Optional[str]):
		self.allowedInTournamentsFromDate: Optional[str] = allowedInTournamentsFromDate
		self.allowedInCore: AllowedInFormat = AllowedInFormat()
		self.allowedInInfinity: AllowedInFormat = AllowedInFormat()
