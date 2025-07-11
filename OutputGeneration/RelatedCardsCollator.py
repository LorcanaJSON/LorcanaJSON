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
		self.enchantedCardId: int = 0
		self.promoCardIds: List[int] = []
		self.variantCardIds: List[int] = []

	def addCard(self, card: Dict):
		if "Q" in card["card_identifier"]:
			return
		cardId: int = card["culture_invariant_id"]
		parsedIdentifier = IdentifierParser.parseIdentifier(card["card_identifier"])
		if parsedIdentifier.isPromo():
			self.promoCardIds.append(cardId)
		elif card["rarity"] == "ENCHANTED":
			if self.enchantedCardId != 0:
				_logger.warning(f"Card {CardUtil.createCardIdentifier(card)} is Enchanted, but its deckbuilding ID already exists in the Enchanteds list, pointing to ID {self.enchantedCardId}, not storing the ID")
			else:
				self.enchantedCardId = cardId
		elif parsedIdentifier.number > 204:
			# A card numbered higher than the normal 204 that isn't an Enchanted is also most likely a promo card (F.i. the special Q1 cards like ID 1179)
			self.promoCardIds.append(cardId)
		elif not self.firstNormalCardId:
			# Store the first non-Enchanted non-Promo card, so Enchanted and Promo cards can reference it
			self.firstNormalCardId = cardId
		# Always keep track of variants separately
		if parsedIdentifier.variant:
			self.variantCardIds.append(cardId)

	def hasSpecialCards(self) -> bool:
		if self.enchantedCardId or self.promoCardIds or self.variantCardIds:
			return True
		return False

	def getOtherRelatedCards(self, cardId: int) -> "OtherRelatedCards":
		"""
		:param cardId: The ID of the card to get the other related cards of
		:return: An OtherRelatedCards instance that contains card relations for the provided card, if any
		"""
		otherRelatedCards = OtherRelatedCards()
		isNotPromo = True
		if self.promoCardIds:
			if cardId in self.promoCardIds:
				isNotPromo = False
				otherRelatedCards.nonPromoId = self.firstNormalCardId
			else:
				otherRelatedCards.promoIds = self.promoCardIds.copy()
		if isNotPromo and self.enchantedCardId:
			if cardId == self.enchantedCardId:
				otherRelatedCards.nonEnchantedId = self.firstNormalCardId
			else:
				otherRelatedCards.enchantedId = self.enchantedCardId
		if self.variantCardIds and cardId in self.variantCardIds:
			otherRelatedCards.otherVariantIds = [i for i in self.variantCardIds if i != cardId]
		return otherRelatedCards


class OtherRelatedCards:
	def __init__(self):
		self.enchantedId: Optional[int] = None
		self.nonEnchantedId: Optional[int] = None
		self.promoIds: Optional[List[int]] = None
		self.nonPromoId: Optional[int] = None
		self.otherVariantIds: Optional[List[int]] = None
