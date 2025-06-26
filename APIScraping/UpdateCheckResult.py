from enum import Enum
from typing import Any, Dict, List, Union


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
		self.possibleChangedImages: List[ChangedCard] = []

	def addNewCard(self, newCard: Dict, nameOverride: Union[None, str] = None):
		self.newCards.append(BasicCard(newCard, nameOverride))

	def addCardChange(self, changedCard: Dict, changeType: ChangeType, fieldName: str, oldFieldValue: Any, newFieldValue: Any):
		self.changedCards.append(ChangedCard(changedCard, changeType, fieldName, oldFieldValue, newFieldValue))

	def addRemovedCard(self, removedCard: Dict):
		self.removedCards.append(BasicCard(removedCard))

	def addPossibleImageChange(self, card, oldImageUrl, newImageUrl):
		self.possibleChangedImages.append(ChangedCard(card, ChangeType.UPDATED_FIELD, "image_urls", oldImageUrl, newImageUrl))

	def hasChanges(self) -> bool:
		if self.newCards or self.changedCards or self.removedCards or self.possibleChangedImages:
			return True
		return False

	def listChangeCounts(self) -> str:
		return f"{len(self.newCards):,} new cards, {len(self.changedCards):,} changed cards, {len(self.possibleChangedImages):,} possible image changes"


class BasicCard:
	def __init__(self, card: Dict, nameOverride: Union[None, str] = None):
		self.id: int = card["culture_invariant_id"]
		if nameOverride:
			self.name = nameOverride
		else:
			self.name: str = card["name"]
			if "subtitle" in card:
				self.name += " - " + card["subtitle"]

	def toString(self) -> str:
		return f"{self.name} (ID {self.id})"

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
		return f"{self.id} {self.name}: Field {self.fieldName} had {self.changeType} change from {self.oldValue!r} to {self.newValue!r}"

	def __str__(self) -> str:
		return self.toString()

