import logging, time

from typing import Dict, List, Optional

from util import CardUtil, IdentifierParser

_logger = logging.getLogger("LorcanaJSON")


class RelatedCardCollator:
	"""
	Enchanted-rarity and promo cards are special versions of existing cards. This classs parses and stores their shared ID so we can add a linking field to both versions
	Also, some cards have identical-rarity variants ("Dalmation Puppy", ID 436-440), store those so each can reference the others
	"""
	def __init__(self, cardstore: Dict):
		startTime = time.perf_counter()
		self.deckbuildingIdToRelatedCards: Dict[str, RelatedCards] = {}
		for cardtype, cardlist in cardstore["cards"].items():
			for card in cardlist:
				groupId = card["deck_building_id"]
				if groupId not in self.deckbuildingIdToRelatedCards:
					self.deckbuildingIdToRelatedCards[groupId] = RelatedCards()
				self.deckbuildingIdToRelatedCards[groupId].addCard(card)
		_logger.info(f"Collating all the related cards took {time.perf_counter() - startTime:.4f} seconds")

	def getRelatedCards(self, card: Dict) -> "RelatedCards":
		return self.deckbuildingIdToRelatedCards[card["deck_building_id"]]


class RelatedCards:
	def __init__(self):
		self.firstNormalCardId: int = 0
		self.normalCardIdsBySet: Dict[str, int] = {}
		self.firstEnchantedCardId: int = 0
		self.enchantedCardIdsBySet: Dict[str, int] = {}
		self.promoCardIds: List[int] = []
		self.variantCardIds: List[int] = []

	def addCard(self, card: Dict):
		if "Q" in card["card_identifier"]:
			return
		cardId: int = card["culture_invariant_id"]
		parsedIdentifier = IdentifierParser.parseIdentifier(card["card_identifier"])
		isNotVariantCard: bool = True
		# Always keep track of variants separately
		if parsedIdentifier.variant:
			isNotVariantCard = False
			self.variantCardIds.append(cardId)
		if parsedIdentifier.isPromo():
			self.promoCardIds.append(cardId)
		elif card["rarity"] == "ENCHANTED":
			if not self.firstEnchantedCardId:
				self.firstEnchantedCarId = cardId
			if parsedIdentifier.setCode in self.enchantedCardIdsBySet:
				_logger.warning(f"Card {CardUtil.createCardIdentifier(card)} from set {parsedIdentifier.setCode} is Enchanted, but an Enchanted for this set is already stored, pointing to ID {self.enchantedCardIdsBySet[parsedIdentifier.setCode]}; not storing the ID")
			else:
				self.enchantedCardIdsBySet[parsedIdentifier.setCode] = cardId
		elif parsedIdentifier.number > 204:
			# A card numbered higher than the normal 204 that isn't an Enchanted is also most likely a promo card (F.i. the special Q1 cards like ID 1179)
			self.promoCardIds.append(cardId)
		else:
			if not self.firstNormalCardId:
				# Store the first non-Enchanted non-Promo card, so Enchanted and Promo cards can reference it
				self.firstNormalCardId = cardId
			# Don't store variant cards as normal cards
			if isNotVariantCard:
				if parsedIdentifier.setCode in self.normalCardIdsBySet:
					_logger.warning(f"Card {CardUtil.createCardIdentifier(card)} from set {parsedIdentifier.setCode} is normal, but a normal card for this set is already stored, pointing to ID {self.normalCardIdsBySet[parsedIdentifier.setCode]}; not storing the ID")
				else:
					self.normalCardIdsBySet[parsedIdentifier.setCode] = cardId

	def hasSpecialCards(self) -> bool:
		if self.enchantedCardIdsBySet or self.promoCardIds or self.variantCardIds:
			return True
		return False

	def getOtherRelatedCards(self, setCode: str, cardId: int) -> "OtherRelatedCards":
		"""
		:param setCode: The code of the set that this card belongs to
		:param cardId: The ID of the card to get the other related cards of
		:return: An OtherRelatedCards instance that contains card relations for the provided card, if any
		"""
		otherRelatedCards = OtherRelatedCards()
		isNotPromo: bool = True
		isNotEnchanted: bool = True
		isNotVariant: bool = True
		if self.promoCardIds:
			if cardId in self.promoCardIds:
				isNotPromo = False
				otherRelatedCards.nonPromoId = self.firstNormalCardId
			else:
				otherRelatedCards.promoIds = self.promoCardIds.copy()
		if isNotPromo and setCode in self.enchantedCardIdsBySet:
			if cardId == self.enchantedCardIdsBySet[setCode]:
				isNotEnchanted = False
				otherRelatedCards.nonEnchantedId = self.firstNormalCardId
			else:
				otherRelatedCards.enchantedId = self.enchantedCardIdsBySet[setCode]
		if self.variantCardIds and cardId in self.variantCardIds:
			isNotVariant = False
			otherRelatedCards.otherVariantIds = [i for i in self.variantCardIds if i != cardId]
		if isNotPromo and isNotEnchanted and len(self.normalCardIdsBySet) > 0:
			# More than one normal card means this is or has a reprint
			if cardId == self.firstNormalCardId:
				otherRelatedCards.reprintedAsIds = [i for i in self.normalCardIdsBySet.values() if i != cardId]
			elif isNotVariant:
				otherRelatedCards.reprintOfId = self.firstNormalCardId
		return otherRelatedCards


class OtherRelatedCards:
	def __init__(self):
		self.enchantedId: Optional[int] = None
		self.nonEnchantedId: Optional[int] = None
		self.promoIds: Optional[List[int]] = None
		self.nonPromoId: Optional[int] = None
		self.otherVariantIds: Optional[List[int]] = None
		self.reprintOfId: Optional[int] = None
		self.reprintedAsIds: Optional[List[int]] = None
