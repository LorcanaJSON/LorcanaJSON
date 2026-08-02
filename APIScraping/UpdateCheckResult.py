from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from util.FormatCoconutCard import FormatCoconutCard


class ChangeType(Enum):
	NEW_FIELD = "newField"
	NEW_ENTRY = "newEntry"
	UPDATED_FIELD = "updatedField"
	UPDATED_ENTRY = "updatedEntry"


class UpdateCheckResult:
	def __init__(self):
		self.newCards: List[BasicCard] = []
		self.changedCards: List[ChangedCard] = []
		self.removedCards: List[BasicCard] = []
		self.newCardFields: List[str] = []
		self.newCardVariantFields: List[str] = []
		self.possibleChangedImages: List[ChangedCard] = []
		self.newSets: List[str] = []
		self.appVersionChange: Optional[Tuple[str, str]] = None  # First Tuple entry is old app version number string, second entry is new
		self.newTopLevelFields: List[str] = []  # Any newly added fields besides the cardlist, setlist, app version data, etc
		self.removedTopLevelFields: List[str] = []  # Even though it's unlikely, also track possible removed top-level fields
		# Fields for the cards for 'Format Coconut'
		self.newFormatCoconutCards: List[FormatCoconutCard] = []
		self.changedFormatCoconutCards: Dict[FormatCoconutCard, List[str]] = {}  # For each changed Coconut Card, a list of fieldnames that changed
		self.removedFormatCoconutCards: List[FormatCoconutCard] = []

	def addNewCard(self, newCard: Dict, nameOverride: Optional[str] = None):
		self.newCards.append(BasicCard(newCard, nameOverride))

	def addCardChange(self, changedCard: Dict, changeType: ChangeType, fieldName: str, oldFieldValue: Any, newFieldValue: Any):
		self.changedCards.append(ChangedCard(changedCard, changeType, fieldName, oldFieldValue, newFieldValue))

	def addRemovedCard(self, removedCard: Dict):
		self.removedCards.append(BasicCard(removedCard))

	def addPossibleImageChange(self, card, oldImageUrl, newImageUrl):
		self.possibleChangedImages.append(ChangedCard(card, ChangeType.UPDATED_FIELD, "variants", oldImageUrl, newImageUrl))

	def hasCardChanges(self) -> bool:
		"""
		:return: True if there are any changes to cards specfically, False otherwise
		"""
		if self.newCards or self.changedCards or self.removedCards or self.possibleChangedImages:
			return True
		return False

	def hasCoconutCardChanges(self) -> bool:
		"""
		:return: True if the cards for 'Format Coconut' have changed, False otherwise
		"""
		if self.newFormatCoconutCards or self.changedFormatCoconutCards or self.removedFormatCoconutCards:
			return True
		return False

	def hasChanges(self) -> bool:
		"""
		:return: True if there are any updates, False otherwise
		"""
		if self.newSets or self.appVersionChange or self.newTopLevelFields or self.removedTopLevelFields or self.newCardFields or self.newCardVariantFields or self.hasCardChanges() or self.hasCoconutCardChanges():
			return True
		return False

	def listChangeCounts(self) -> str:
		countStrings: List[str] = []
		for fieldName, fieldValue in vars(self).items():
			if isinstance(fieldValue, list) or isinstance(fieldValue, dict):
				countStrings.append(f"{fieldName}: {len(fieldValue):,}")
		return ", ".join(countStrings)


class BasicCard:
	def __init__(self, card: Dict, nameOverride: Optional[str] = None):
		self.id: int = card["culture_invariant_id"]
		self.identifier = card["card_identifier"]
		if nameOverride:
			self.name = nameOverride
		else:
			self.name: str = card["name"]
			if "subtitle" in card:
				self.name += " - " + card["subtitle"]

	def toString(self) -> str:
		return f"{self.name} ({self.identifier}, ID {self.id})"

	def __str__(self) -> str:
		return self.toString()


class ChangedCard(BasicCard):
	def __init__(self, card: Dict, changeType: ChangeType, fieldName: str, oldValue: Any, newValue: Any):
		super().__init__(card)
		self.changeType = changeType
		self.fieldName = fieldName
		self.oldValue = oldValue
		self.newValue = newValue

	def getCardDescriptor(self):
		return super().toString()

	def toString(self) -> str:
		return f"{self.id} {self.name}: Field {self.fieldName} had {self.changeType.value} change from {self.oldValue!r} to {self.newValue!r}"

	def __str__(self) -> str:
		return self.toString()
