from typing import NotRequired, TypedDict


class ExternalLinks(TypedDict, total=True):
	cardTraderId: NotRequired[int]
	cardTraderUrl: NotRequired[str]
	cardmarketId: NotRequired[int]
	cardmarketUrl: NotRequired[str]
	tcgPlayerId: NotRequired[int]
	tcgPlayerUrl: NotRequired[str]
