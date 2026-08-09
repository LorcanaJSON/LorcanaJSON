from enum import auto, StrEnum

class LABEL_PARSING_METHODS(StrEnum):
	DEFAULT = auto()
	FALLBACK_WHITE_ABILITY_TEXT = auto()
	FALLBACK_BY_LINES = auto()
	NONE = auto()
