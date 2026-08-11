from typing import TypedDict


class Images(TypedDict, total=False):  # 'total=False' because the dict can be built up in steps, and this prevents wrong warnings
	foilMask: str
	full: str
	fullFoil: str
	thumbnail: str
	varnishMask: str
	varnishMask2: str
