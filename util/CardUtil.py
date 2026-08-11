from typing import Dict, Union

from util.typedDicts.OutputCard import OutputCard

def createCardIdentifier(card: Union[Dict, OutputCard], addIdentifierNumberGroup: bool = False) -> str:
	"""
	Create an identifier string for an input or output card, consisting of the full name and the ID
	:param card: The card dictionary
	:param addIdentifierNumberGroup Whether to add the first part of the identifier to the output (f.i. '3/204', '1/P1'). If not provided, defaults to False
	:return: A string with the full card name and the card ID
	"""
	if "id" in card:
		# Output card
		result = f"'{card['fullName']}' (ID {card['id']}"
		if addIdentifierNumberGroup:
			result += f", {card['fullIdentifier'].split(' ', 1)[0]}"
		result += ")"
		return result
	# Input card
	if "culture_invariant_id" in card:
		return f"'{card['name']} - {card.get('subtitle', None)}' (ID {card['culture_invariant_id']})"
	# Probably a coconut card
	return str(card)

def createOutputCardIdentifier(outputCard: OutputCard, addIdentifierNumberGroup: bool = False) -> str:
	result = f"'{outputCard['fullName']}' (ID {outputCard['id']}"
	if addIdentifierNumberGroup:
		result += f", {outputCard['fullIdentifier'].split(' ', 1)[0]}"
	result += ")"
	return result
