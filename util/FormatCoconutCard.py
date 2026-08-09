import re
from typing import Dict

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

	def getOcrIdentifier(self) -> str:
		"""
		:return: The identifier used for this Format Coconut card in the OCR cache
		"""
		return f"coconut_{self.number}"

	def getImageUrl(self):
		return self.coconutData["card_detail_url"]

	def __str__(self) -> str:
		return f"{self.fullName} (nr {self.number})"
