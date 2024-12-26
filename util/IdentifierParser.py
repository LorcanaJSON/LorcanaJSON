import logging, re
from dataclasses import dataclass
from typing import Union

from util import LorcanaSymbols

_IDENTIFIER_REGEX = re.compile(r"^(?P<number>\d+)(?P<variant>[a-z])?[/1](?P<grouping>[A-Z]?\d+)( ?[-+<]{1,2} ?| (. )?)(?P<language>\w+)( ?[-+<]{1,2} ?| (. )?)(?P<setCode>\S+)$")
_LOGGER = logging.getLogger("LorcanaJSON")

@dataclass
class Identifier:
	"""
	This class represents a card identifier as it's printed at the bottom-left of a card. It contains the card number, language, set code, etc
	"""
	grouping: str  # 'P1', 'Q1', 'D23, etc. This is '204' for 'normal' and Enchanted cards
	language: str
	number: int
	setCode: str
	variant: str = None

	def __post_init__(self):
		# 'Q1' setcode sometimes gets read as '01', correct that
		if self.setCode == "01":
			self.setCode = "Q1"

	def isPromo(self) -> bool:
		"""
		:return: True if this identifier is for a Promo card, False otherwise
		"""
		# 'Normal' cards have a grouping of '204' (or '31' for Q1 cards), so anything that doesn't have that grouping is special in some way
		return not self.grouping.isdigit()

	def isQuest(self) -> bool:
		"""
		:return: True if this identifier is from a Quest card, False otherwise
		"""
		return self.setCode == "Q1"

	def _toString(self):
		return f"{self.number}{self.variant if self.variant else ''}/{self.grouping} {LorcanaSymbols.SEPARATOR} {self.language} {LorcanaSymbols.SEPARATOR} {self.setCode}"

	def __str__(self):
		return self._toString()

	def __repr__(self):
		return self._toString()


def parseIdentifier(identifierString: str) -> Union[None, Identifier]:
	"""
	Parse an identifier string as retrieved from the bottom-left of a card into something more easily usable
	:param identifierString: The identifier string to parse
	:return: A parsed Identifier instance, or None if the identifier string couldn't be parsed
	"""
	parsedIdentifier = _IDENTIFIER_REGEX.match(identifierString)
	if not parsedIdentifier:
		_LOGGER.warning(f"Unable to parse identifier {identifierString}")
		return None

	return Identifier(parsedIdentifier.group("grouping"), parsedIdentifier.group("language"), int(parsedIdentifier.group("number"), 10), parsedIdentifier.group("setCode"), parsedIdentifier.group("variant"))
