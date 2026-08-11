from typing import List, TypedDict


class Ability(TypedDict, total=False):  # 'total=False' because the dict can be built up in steps, and this prevents wrong warnings
	costs: List[str]
	costsText: str
	effect: str
	fullText: str
	name: str
	type: str
	keyword: str
	keywordValue: str
	keywordValueNumber: int
	reminderText: str
