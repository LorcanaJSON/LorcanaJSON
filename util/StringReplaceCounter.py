from typing import List

COUNTS: dict[str, list[int]] = {}


def _count(whatToCount: str, amount: int):
	if whatToCount not in COUNTS:
		COUNTS[whatToCount] = [1, amount]
	else:
		COUNTS[whatToCount][0] += 1
		COUNTS[whatToCount][1] += amount


class StringReplaceCounter:
	"""
	This class is a wrapper around a string that counts every manipulation done to it
	The goal of this is to make sure that every correction that is done to the underlying string is useful and changes something
	Usage: At the start of the code that manipulates your string, instantiate this class with that string as the parameter. At the end of the code, conert it back to a normal string
	At the end of program execution, the string change stats will be printed
	"""

	def __init__(self, underlyingString: str):
		self.s: str = underlyingString

	def replace(self, whatToReplace: str, replacement: str) -> "StringReplaceCounter":
		replaceCount = self.s.count(whatToReplace)
		self.s = self.s.replace(whatToReplace, replacement)
		_count(whatToReplace, replaceCount)
		return self

	def strip(self, stripChars: str = None) -> "StringReplaceCounter":
		beforeLength = len(self.s)
		self.s = self.s.strip(stripChars)
		_count(f"strip_{stripChars}", beforeLength - len(self.s))
		return self

	def lstrip(self, stripChars: str = None) -> "StringReplaceCounter":
		beforeLength = len(self.s)
		self.s = self.s.lstrip(stripChars)
		_count(f"lstrip_{stripChars}", beforeLength - len(self.s))
		return self

	def rstrip(self, stripChars: str = None) -> "StringReplaceCounter":
		beforeLength = len(self.s)
		self.s = self.s.rstrip(stripChars)
		_count(f"rstrip_{stripChars}", beforeLength - len(self.s))
		return self

	def startswith(self, stringToCheck: str) -> bool:
		startsWith = self.s.startswith(stringToCheck)
		_count(f"startsWith_{stringToCheck}", 1 if startsWith else 0)
		return startsWith

	def endswith(self, stringToCheck: str) -> bool:
		endsWith = self.s.endswith(stringToCheck)
		_count(f"endsWith_{stringToCheck}", 1 if endsWith else 0)
		return endsWith

	def count(self, substringToCount):
		return self.s.count(substringToCount)

	def split(self, splitOn: str, splitCount = -1) -> List["StringReplaceCounter"]:
		splits = self.s.split(splitOn, splitCount)
		_count(f"split_{splitOn}", len(splits) - 1)
		return [StringReplaceCounter(s) for s in splits]

	def rsplit(self, splitOn: str, splitCount = -1) -> List["StringReplaceCounter"]:
		splits = self.s.rsplit(splitOn, splitCount)
		_count(f"rsplit_{splitOn}", len(splits) - 1)
		return [StringReplaceCounter(s) for s in splits]

	def __contains__(self, item):
		contains = item in self.s
		_count(f"contains_{item}", 1 if contains else 0)
		return contains

	def __getitem__(self, item):
		_count(f"getitem_{item}", 1)
		return self.s.__getitem__(item)

	def __str__(self):
		return self.s

	def __repr__(self):
		return repr(self.s)

	def __unicode__(self):
		return self.s
