"""
This class can be used to count whether regular expressions actually change strings.
It's used by importing this class instead of the built-in 're' module, and by importing it 'as re' it works as a drop-in replacement.
It supports the StringReplaceCounter string wrapper
"""

import re
from re import DOTALL, MULTILINE  # Needed because some calling code uses the 're' flags
from typing import List, Optional, Tuple, Union

from util.StringReplaceCounter import StringReplaceCounter

_TYPE_SEARCH = "SEARCH"
_TYPE_SPLIT = "SPLIT"
_TYPE_SUB = "SUB"

# Counts organised by type, then by pattern. The first entry in the value list is how often the regex is called, the second how often a hit was found for SEARCH and how many changes were made for SUB
REGEX_COUNTS: dict[str, dict[str, list[int]]] = {_TYPE_SEARCH: {}, _TYPE_SPLIT: {}, _TYPE_SUB: {}}

def _addCount(pattern: str, regexType: str, count: int = 1):
	if pattern in REGEX_COUNTS[regexType]:
		REGEX_COUNTS[regexType][pattern][0] += 1
		REGEX_COUNTS[regexType][pattern][1] += count
	else:
		REGEX_COUNTS[regexType][pattern] = [1, count]

def hasCounts() -> bool:
	for regexType in REGEX_COUNTS:
		if len(REGEX_COUNTS[regexType]) > 0:
			return True
	return False


def subn(pattern: str, replacement: str, inputString: Union[str, StringReplaceCounter], flags=0) -> Tuple[Union[str, StringReplaceCounter], int]:
	isStringReplaceCounter = False
	if isinstance(inputString, StringReplaceCounter):
		inputString = str(inputString)
		isStringReplaceCounter = True
	outputString, replacementCount = re.subn(pattern, replacement, inputString, flags=flags)
	_addCount(pattern, _TYPE_SUB, replacementCount)
	if isStringReplaceCounter:
		outputString = StringReplaceCounter(outputString)
	return outputString, replacementCount

def sub(pattern: str, replacement: str, inputString: Union[str, StringReplaceCounter], flags=0) -> Union[str, StringReplaceCounter]:
	return subn(pattern, replacement, inputString, flags=flags)[0]

def match(pattern: str, inputString: Union[str, StringReplaceCounter], flags=0) -> Optional[re.Match[str]]:
	if isinstance(inputString, StringReplaceCounter):
		inputString = str(inputString)
	m = re.match(pattern, inputString, flags=flags)
	_addCount(pattern, _TYPE_SEARCH, 1 if m else 0)
	return m

def search(pattern: str, inputString: Union[str, StringReplaceCounter], flags=0) -> Optional[re.Match[str]]:
	if isinstance(inputString, StringReplaceCounter):
		inputString = str(inputString)
	m = re.search(pattern, inputString, flags=flags)
	_addCount(pattern, _TYPE_SEARCH, 1 if m else 0)
	return m

def compile(pattern: str) -> re.Pattern[str]:
	return re.compile(pattern)

def split(pattern: str, inputString: Union[str, StringReplaceCounter], maxsplit: int = 0, flags=0) -> List[Union[str, StringReplaceCounter]]:
	isStringReplaceCounter = False
	if isinstance(inputString, StringReplaceCounter):
		inputString = str(inputString)
		isStringReplaceCounter = True
	splits = re.split(pattern, inputString, maxsplit=maxsplit, flags=flags)
	_addCount(pattern, _TYPE_SPLIT, len(splits) - 1)
	if isStringReplaceCounter:
		splits = [StringReplaceCounter(s) for s in splits]
	return splits
