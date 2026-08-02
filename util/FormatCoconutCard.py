import re
from typing import Dict, Optional

_COCONUT_CARD_NUMBER_MATCHER = re.compile(r"/(\d+)_")

class FormatCoconutCard:

	def __init__(self, coconutData: Dict[str, str]):
		self.coconutData: Dict[str, str] = coconutData
		self.fullName: str = f"{coconutData['name']} - {coconutData['subtitle']}".replace("\u00ad", "")  # There's a 'Pocahontas' card with a random hyphen, remove it
		self.cleanFullName: str = self.fullName.replace("\"", "")
		numberMatch = _COCONUT_CARD_NUMBER_MATCHER.search(coconutData["card_detail_url"])
		if not numberMatch:
			raise ValueError(f"Unable to get coconut card number from '{coconutData['card_detail_url']}'")
		self.numberString = numberMatch.group(1).lstrip("0")
		self.number: int = int(self.numberString)

	def __str__(self) -> str:
		return f"{self.fullName} (nr {self.number})"
