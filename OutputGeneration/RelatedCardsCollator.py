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
		self.epicCardIdsBySet: Dict[str, int] = {}
		self.enchantedCardIdsBySet: Dict[str, int] = {}
		self.iconicCardIdsBySet: Dict[str, int] = {}
		self.promoCardIds: List[int] = []
		self.variantCardIds: List[int] = []
		self.printedInSets: List[str] = []  # List of set codes

	def addCard(self, card: Dict):
		cardId: int = card["culture_invariant_id"]
		parsedIdentifier = IdentifierParser.parseIdentifier(card["card_identifier"])
		if parsedIdentifier.setCode not in self.printedInSets:
			self.printedInSets.append(parsedIdentifier.setCode)
		if parsedIdentifier.isQuest():
			# Quest cards are never a promo or Enchanted, or in other sets
			return
		isNotVariantCard: bool = True
		# Always keep track of variants separately
		if parsedIdentifier.variant:
			isNotVariantCard = False
			self.variantCardIds.append(cardId)
		if parsedIdentifier.isPromo():
			self.promoCardIds.append(cardId)
		elif card["rarity"] == "EPIC":
			self._addFancyArtBySet(card, parsedIdentifier.setCode, self.epicCardIdsBySet)
		elif card["rarity"] == "ENCHANTED":
			self._addFancyArtBySet(card, parsedIdentifier.setCode, self.enchantedCardIdsBySet)
		elif card["rarity"] == "ICONIC":
			self._addFancyArtBySet(card, parsedIdentifier.setCode, self.iconicCardIdsBySet)
		elif parsedIdentifier.number > 204:
			# A card numbered higher than the normal 204 that isn't an Enchanted is also most likely a promo card (F.i. the special Q1 cards like ID 1179)
			self.promoCardIds.append(cardId)
		else:
			# Store the non-Enchanted non-Promo card with the lowest ID as the 'original', so Enchanted and Promo cards, and reprints, can reference it
			if not self.firstNormalCardId or cardId < self.firstNormalCardId:
				self.firstNormalCardId = cardId
			# Don't store variant cards as normal cards
			if isNotVariantCard:
				if parsedIdentifier.setCode in self.normalCardIdsBySet:
					_logger.warning(f"Card {CardUtil.createCardIdentifier(card)} from set {parsedIdentifier.setCode} is normal, but a normal card for this set is already stored, pointing to ID {self.normalCardIdsBySet[parsedIdentifier.setCode]}; not storing the ID")
				else:
					self.normalCardIdsBySet[parsedIdentifier.setCode] = cardId

	@staticmethod
	def _addFancyArtBySet(card: Dict, setCode: str, fancyArtBySet: Dict[str, int]):
		if setCode in fancyArtBySet:
			_logger.warning(f"Card {CardUtil.createCardIdentifier(card)} from set {setCode} is rarity {card['rarity']}, but a {card['rarity']}-rarity for this set is already stored, pointing to ID {fancyArtBySet[setCode]}; not storing the ID")
		else:
			fancyArtBySet[setCode] = card["culture_invariant_id"]

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
		isNotFancyArt: bool = True
		isNotVariant: bool = True
		if self.promoCardIds:
			if cardId in self.promoCardIds:
				isNotPromo = False
				otherRelatedCards.nonPromoId = self.getNormalCard(setCode)
			else:
				otherRelatedCards.promoIds = self.promoCardIds.copy()

		if isNotPromo:
			if setCode in self.epicCardIdsBySet:
				if cardId == self.epicCardIdsBySet[setCode]:
					isNotFancyArt = False
					otherRelatedCards.nonEpicId = self.getNormalCard(setCode)
				else:
					otherRelatedCards.epicId = self.epicCardIdsBySet[setCode]
			if setCode in self.enchantedCardIdsBySet:
				if cardId == self.enchantedCardIdsBySet[setCode]:
					isNotFancyArt = False
					otherRelatedCards.nonEnchantedId = self.getNormalCard(setCode)
				else:
					otherRelatedCards.enchantedId = self.enchantedCardIdsBySet[setCode]
			if setCode in self.iconicCardIdsBySet:
				if cardId == self.iconicCardIdsBySet[setCode]:
					isNotFancyArt = False
					otherRelatedCards.nonIconicId = self.getNormalCard(setCode)
				else:
					otherRelatedCards.iconicId = self.iconicCardIdsBySet[setCode]

		if self.variantCardIds and cardId in self.variantCardIds:
			isNotVariant = False
			otherRelatedCards.otherVariantIds = [i for i in self.variantCardIds if i != cardId]
		if isNotPromo and isNotFancyArt and len(self.normalCardIdsBySet) > 0:
			# More than one normal card means this is or has a reprint
			if cardId == self.firstNormalCardId:
				otherRelatedCards.reprintedAsIds = [i for i in self.normalCardIdsBySet.values() if i != cardId]
			elif isNotVariant:
				otherRelatedCards.reprintOfId = self.firstNormalCardId
		return otherRelatedCards

	def getNormalCard(self, setCode):
		if setCode in self.normalCardIdsBySet:
			return self.normalCardIdsBySet[setCode]
		return self.firstNormalCardId


class OtherRelatedCards:
	def __init__(self):
		self.epicId: Optional[int] = None
		self.nonEpicId: Optional[int] = None
		self.enchantedId: Optional[int] = None
		self.nonEnchantedId: Optional[int] = None
		self.iconicId: Optional[int] = None
		self.nonIconicId: Optional[int] = None
		self.promoIds: Optional[List[int]] = None
		self.nonPromoId: Optional[int] = None
		self.otherVariantIds: Optional[List[int]] = None
		self.reprintOfId: Optional[int] = None
		self.reprintedAsIds: Optional[List[int]] = None
