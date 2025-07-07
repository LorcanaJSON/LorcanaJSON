from typing import Dict

def createCardIdentifier(card: Dict) -> str:
	"""
	Create an identifier string for an input or output card, consisting of the full name and the ID
	:param card: The card dictionary
	:return: A string with the full card name and the card ID
	"""
	if "id" in card:
		# Output card
		return f"'{card['fullName']}' (ID {card['id']})"
	# Input card
	return f"'{card['name']} - {card.get('subtitle', None)}' (ID {card['culture_invariant_id']})"
