from dataclasses import dataclass
from typing import List

@dataclass
class OcrResult:
	# Always parsed
	abilityLabels: List[str]
	abilityTexts: List[str]
	artistsText: str
	# Some fields might not be used on the card
	flavorText: str
	remainingText: str
	subtypesText: str
	# Optionally parsed
	cost: str = None
	identifier: str = None
	moveCost: str = None
	name: str = None
	strength: str = None
	version: str = None
	willpower: str = None

	def __getitem__(self, item) -> str:
		# This allows the use of item subscription (myOcrResult['cost'])
		return self.__getattribute__(item)
