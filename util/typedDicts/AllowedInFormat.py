from typing import NotRequired, TypedDict


class AllowedInFormat(TypedDict, total=True):
	allowed: bool
	allowedUntilDate: NotRequired[str]
	bannedSinceDate: NotRequired[str]
