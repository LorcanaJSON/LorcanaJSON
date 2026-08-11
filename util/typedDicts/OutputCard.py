from typing import Dict, List, NotRequired, TypedDict, Union

from util.typedDicts import Ability
from util.typedDicts.AllowedInFormat import AllowedInFormat
from util.typedDicts.ExternalLinks import ExternalLinks
from util.typedDicts.Images import Images


class HistoricDataEntry(TypedDict, total=False):
	usedUntil: str

class OutputCard(TypedDict, total=False):
	abilities: NotRequired[List[Ability.Ability]]
	allowedInFormats: Dict[str, AllowedInFormat]
	allowedInTournamentsFromDate: Union[str, None]
	artists: List[str]
	artistsNormalized: NotRequired[List[str]]
	artistsText: str
	baseId: NotRequired[int]
	clarifications: NotRequired[List[str]]
	code: str
	color: str
	colors: NotRequired[List[str]]
	cost: int
	effects: NotRequired[List[str]]
	enchantedId: NotRequired[int]
	epicId: NotRequired[int]
	errata: NotRequired[List[str]]
	externalLinks: ExternalLinks
	flavorText: NotRequired[str]
	foilEffectColors: NotRequired[List[str]]
	foilTypes: NotRequired[List[str]]
	fullIdentifier: str
	fullName: str
	fullText: str
	fullTextSections: List[str]
	historicData: NotRequired[List[HistoricDataEntry]]
	iconicId: NotRequired[int]
	id: int
	images: Images
	inkwell: bool
	isExternalReveal: NotRequired[bool]
	keywordAbilities: NotRequired[List[str]]
	lore: NotRequired[int]
	maxCopiesInDeck: NotRequired[Union[int, None]]
	moveCost: NotRequired[int]
	name: str
	names: NotRequired[List[str]]
	number: int
	promoGrouping: NotRequired[str]
	promoIds: NotRequired[List[int]]
	promoSource: NotRequired[str]
	promoSourceCategory: NotRequired[str]
	rarity: str
	reprintedAsIds: NotRequired[List[int]]
	reprintOfId: NotRequired[int]
	setCode: str
	simpleName: str
	story: str
	strength: NotRequired[int]
	subtypes: NotRequired[List[str]]
	subtypesText: NotRequired[str]
	type: str
	variant: NotRequired[str]
	variantIds: NotRequired[List[int]]
	varnishType: NotRequired[str]
	version: NotRequired[str]
	willpower: NotRequired[int]
