from dataclasses import dataclass
from typing import List, Optional

from OCR.ParseSettings.ParseSettings import ParseSettings

@dataclass
class OcrResult:
	parseSettingsUsed: ParseSettings
	# Always parsed
	abilityLabels: Optional[List[str]]
	abilityTexts: Optional[List[str]]
	artistsText: str
	# Some fields might not be used on the card
	flavorText: Optional[str] = None
	remainingText: Optional[str] = None
	subtypesText: Optional[str] = None
	# Optionally parsed
	cost: Optional[str] = None
	identifier: Optional[str] = None
	moveCost: Optional[str] = None
	name: Optional[str] = None
	strength: Optional[str] = None
	version: Optional[str] = None
	willpower: Optional[str] = None

	def __getitem__(self, item) -> str:
		# This allows the use of item subscription (myOcrResult['cost'])
		return self.__getattribute__(item)
