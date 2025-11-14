import logging, re
from typing import Dict, List, Union

import GlobalConfig
from util import CardUtil, Language, LorcanaSymbols

_logger = logging.getLogger("LorcanaJSON")

def correctText(cardText: str) -> str:
	"""
	Fix some re-occuring mistakes and errors in the text of the cards
	:param cardText: The text to correct
	:return: The card text with common problems fixed
	"""
	originalCardText = cardText
	cardText = re.sub("\n{2,}", "\n", cardText.strip())
	## First simple typos ##
	# Commas should always be followed by a space
	cardText = re.sub(",(?! |’|”|$)", ", ", cardText, flags=re.MULTILINE)
	# The 'Exert' symbol often gets read as a 6
	cardText = re.sub(r"^(G?6|fà)? ?,", f"{LorcanaSymbols.EXERT},", cardText)
	cardText = re.sub(r"^(6|fà) ?([-—])", f"{LorcanaSymbols.EXERT} \\2", cardText)
	# There's usually an ink symbol between a number and a dash
	cardText = re.sub(r"(^| )(\d) ?[0OÒQ©]{,2}( ?[-—]|,)", fr"\1\2 {LorcanaSymbols.INK}\3", cardText, flags=re.MULTILINE)
	# And word-number-number should be word-number-ink
	cardText = re.sub(r"^(\w+ \d) ?[OÒQ0©]$", f"\\1 {LorcanaSymbols.INK}", cardText)
	# Normally a closing quote mark should be preceded by a period, except mid-sentence
	cardText = re.sub(r"([^.,'!?’])”(?!,| \w)", "\\1.”", cardText)
	# An opening bracket shouldn't have a space after it
	cardText = cardText.replace("( ", "(")
	# Sometimes an extra character gets added after the closing quote mark or bracket from an inksplotch, remove that
	cardText = re.sub(r"(?<=[”’)])\s.$", "", cardText, flags=re.MULTILINE)
	# The 'exert' symbol often gets mistaken for a @ or G, correct that
	cardText = re.sub(r"(?<![0-9s])(^|[\"“„ ])[(@Gg©€]{1,3}[89]?([ ,])", fr"\1{LorcanaSymbols.EXERT}\2", cardText, flags=re.MULTILINE)
	cardText = re.sub(r"^([(&f]+[Àà]?)? ?[-—](?=\s)", f"{LorcanaSymbols.EXERT} —", cardText)
	# Some cards have a bulleted list, replace the start character with the separator symbol
	cardText = re.sub(r"^[-+*«»¢.,‚]{1,2}(?= \w{2,} \w+)", LorcanaSymbols.SEPARATOR, cardText, flags=re.MULTILINE)
	# Other weird symbols are probably strength symbols
	cardText = re.sub(r"(?<!\d)[ÇX]?[&@©%$*<>{}€£¥Ÿ]{1,2}[0-9yFÌPX+*%#“»]*(?=[.,)—-]|\s|$)", LorcanaSymbols.STRENGTH, cardText)
	cardText = re.sub(r"(?<=\d )[CÇDIQX]{1,2}2?\b", LorcanaSymbols.STRENGTH, cardText)
	# Make sure there's a period before a closing bracket
	cardText = re.sub(fr"([^.,'!?’{LorcanaSymbols.STRENGTH}])\)", r"\1.)", cardText)
	# Strip erroneously detected characters from the end
	cardText = re.sub(r" [‘‘;]$", "", cardText, flags=re.MULTILINE)
	# The Lore symbol often gets mistaken for a 4, À, or è, correct hat
	cardText = re.sub(r"(\d) ?[4Àè](?=[ \n.])", fr"\1 {LorcanaSymbols.LORE}", cardText)
	# It sometimes misses the strength symbol between a number and the closing bracket
	cardText = re.sub(r"^\+(\d)(\.\)?)$", f"+\\1 {LorcanaSymbols.STRENGTH}\\2", cardText, flags=re.MULTILINE)
	cardText = re.sub(r"^([-+]\d)0(\.\)?)$", fr"\1 {LorcanaSymbols.STRENGTH}\2", cardText, flags=re.MULTILINE)
	# A 7 often gets mistaken for a /, correct that
	cardText = re.sub(r" /(?=\.| |$)", " 7", cardText)
	cardText = re.sub(f"{LorcanaSymbols.INK}([-—])", fr"{LorcanaSymbols.INK} \1", cardText)
	# Negative numbers are always followed by a strength symbol, correct that
	cardText = re.sub(fr"(?<= )(-\d)( [^{LorcanaSymbols.STRENGTH}{LorcanaSymbols.LORE}a-z .]{{1,2}})?( \w{{2,}}|$)", fr"\1 {LorcanaSymbols.STRENGTH}\3", cardText, flags=re.MULTILINE)
	# Two numbers in a row never happens, or a digit followed by a loose capital lettter. The latter should probably be a Strength symbol
	cardText = re.sub(r"(\d) \(?[0-9DGOQ]{1,2}[%{}°»]?(?=\W|\.)", f"\\1 {LorcanaSymbols.STRENGTH}", cardText)
	# Letters after a quotemark at the start of a line should be capitalized
	cardText = re.sub("^“[a-z]", lambda m: m.group(0).upper(), cardText, flags=re.MULTILINE)
	while re.search(f"\\s[^?!.…”“0-9{LorcanaSymbols.INK}]$", cardText):
		cardText = cardText[:-2]
	cardText = re.sub(r"([.!?]”?)\s?([a-z][a-zA-Z ]{,2}|[0-9])$", "\\1", cardText)
	cardText = re.sub(r"(?<=\bTe[ -]K)a\b", "ā", cardText)
	# Floodborn characters have Shift, and a subtypes bar that drips ink, leading to erroneous character detection. Fix that
	cardText = re.sub(fr"^[^\n]{{,15}}\n(?=(?:[A-Z]\w+[ -])?{GlobalConfig.translation.shift})", "", cardText)
	# Cards can grant abilities, written in quotemarks. These can never start with a Strength symbol, that should be Exert
	cardText = cardText.replace(f"“{LorcanaSymbols.STRENGTH}", f"“{LorcanaSymbols.EXERT}")

	if GlobalConfig.language == Language.ENGLISH:
		cardText = re.sub("^‘", "“", cardText, flags=re.MULTILINE)
		# Somehow it reads 'Bodyquard' with a 'q' instead of or in addition to a 'g' a lot...
		cardText = re.sub("Bodyqg?uard", "Bodyguard", cardText)
		# Fix some common typos
		cardText = cardText.replace("-|", "-1").replace("|", "I")
		cardText = re.sub(r"“[LT\[]([ '’])", r"“I\1", cardText)
		cardText = cardText.replace("—l", "—I")
		cardText = re.sub(r"(?<=\w)!(?=,? ?[a-z])", "l", cardText)  # Replace exclamation mark followed by a lowercase letter by an 'l'
		cardText = re.sub(r"^(“)?! ", r"\1I ", cardText)
		cardText = re.sub(r"(^| |\n|“)[lIL!]([dlmM]l?)\b", r"\1I'\2", cardText, flags=re.MULTILINE)
		cardText = re.sub("^l", "I", cardText)
		cardText = re.sub(r"(?<=\s)l(?=\s)", "I", cardText)
		cardText = cardText.replace("Sing songs", "sing songs")
		# Correct some fancy quote marks at the end of some plural possessives. This is needed on a case-by-case basis, otherwise too much text is changed
		cardText = re.sub(r"\bteammates’(\s|$)", r"teammates'\1", cardText, flags=re.MULTILINE)
		cardText = re.sub(r"\bplayers’(\s|$)", r"players'\1", cardText, flags=re.MULTILINE)
		cardText = re.sub(r"\bopponents’(\s|$)", r"opponents'\1", cardText, flags=re.MULTILINE)
		cardText = re.sub(r"\bIllumineers’(\s|$)", r"Illumineers'\1", cardText, flags=re.MULTILINE)
		## Correct common phrases with symbols ##
		# Ink payment discounts
		cardText = re.sub(r"(?<=\bpay\s)(\d)[0Q]? .?to\b", f"\\1 {LorcanaSymbols.INK} to", cardText)
		cardText = re.sub(rf"pay(s?) ?(\d)\.? ?[^{LorcanaSymbols.INK}.]{{1,2}}( |\.|$)", f"pay\\1 \\2 {LorcanaSymbols.INK}\\3", cardText, flags=re.MULTILINE)
		cardText = re.sub(rf"pay(\s)(\d) [^{LorcanaSymbols.INK}] less", fr"pay\1\2 {LorcanaSymbols.INK} less", cardText)
		cardText = re.sub(r"(?<=\bpay\s)(\d+)O?(?=\sless\b)", f"\\1 {LorcanaSymbols.INK}", cardText)
		# It gets a bit confused about exert and payment, correct that
		cardText = re.sub(r"^\(20 ", f"{LorcanaSymbols.EXERT}, 2 {LorcanaSymbols.INK} ", cardText)
		# The Lore symbol after 'location's' often gets missed or misread as a '4'
		# cardText = cardText.replace("location's .", f"location's {LorcanaSymbols.LORE}.")
		cardText = re.sub("(?<=location's )4?\\.", f"{LorcanaSymbols.LORE}.", cardText)
		## Correct reminder text ##
		# Challenger
		cardText = re.sub(r"\(They get \+(\d)$", f"(They get +\\1 {LorcanaSymbols.STRENGTH}", cardText, flags=re.MULTILINE)
		# Shift
		cardText = re.sub(f"pay (\\d+) {LorcanaSymbols.INK} play this", f"pay \\1 {LorcanaSymbols.INK} to play this", cardText)
		cardText = re.sub(fr"(^Shift \d) ?[O{LorcanaSymbols.STRENGTH}]", fr"\1 {LorcanaSymbols.INK}", cardText)
		# Song
		cardText = re.sub(fr"(can|may)( [^{LorcanaSymbols.EXERT}]{{1,2}})?(?=\sto sing this)", f"\\1 {LorcanaSymbols.EXERT}", cardText)
		# Support, full line (not sure why it sometimes doesn't get cut into two lines
		if re.search(r"their\s\S{1,3}\sto another chosen character['’]s", cardText):
			cardText = re.sub(fr"(?<=their\s)[^{LorcanaSymbols.STRENGTH}]{{1,3}}(?=\sto)", LorcanaSymbols.STRENGTH, cardText)
		# Support, first line if split
		cardText = re.sub(fr"(^|\badd )their [^{LorcanaSymbols.STRENGTH}]{{1,2}} to", f"\\1their {LorcanaSymbols.STRENGTH} to", cardText, flags=re.MULTILINE)
		# Support, second line if split (prevent hit on 'of this turn.' or '+2 this turn', which is unrelated to what we're correcting)
		cardText = re.sub(rf"^([^{LorcanaSymbols.STRENGTH}of+]{{1,2}} )?this turn\.?\)$", f"{LorcanaSymbols.STRENGTH} this turn.)", cardText, flags=re.MULTILINE)
		cardText = re.sub(f"chosen character's( [^{LorcanaSymbols.LORE}{LorcanaSymbols.STRENGTH}]{{1,2}})? this turn", f"chosen character's {LorcanaSymbols.STRENGTH} this turn", cardText)
		# It frequently misreads the Ink symbol after 'Boost' (But not if was already fixed)
		cardText = re.sub(fr"(?<=^Boost \d) ?[^{LorcanaSymbols.INK}](?!{LorcanaSymbols.INK})", f" {LorcanaSymbols.INK}", cardText)
		# Common typos
		cardText = re.sub(r"\bluminary\b", "Illuminary", cardText)
		cardText = re.sub(r"\bI[I/]+l?um", "Illum", cardText)
		cardText = re.sub(r"([Dd])rawa ?card", r"\1raw a card", cardText)
		cardText = re.sub(r"\bL([ft])\b", "I\\1", cardText)
		cardText = re.sub(r"\b([Hh])ed\b", r"\1e'd", cardText)
		# Somehow 'a's often miss the space after it
		cardText = re.sub(r"\bina\b", "in a", cardText)
		cardText = re.sub(r"\bacard\b", "a card", cardText)
	elif GlobalConfig.language == Language.FRENCH:
		# Correct payment text
		cardText = re.sub(fr"\bpa(yer|ie) (\d+) (?:\W|D|O|Ô|Q|{LorcanaSymbols.STRENGTH})", f"pa\\1 \\2 {LorcanaSymbols.INK}", cardText)
		cardText = re.sub(fr"^(\d) ?[{LorcanaSymbols.STRENGTH}O0](\s)(pour|de moins)\b", fr"\1 {LorcanaSymbols.INK}\2\3", cardText, flags=re.MULTILINE)
		cardText = re.sub(r"(?<=payer \d)(?=\n)", f" {LorcanaSymbols.INK}", cardText)
		# Correct support reminder text
		cardText = re.sub(r"(?<=ajouter sa )\W+(?= à celle)", LorcanaSymbols.STRENGTH, cardText)
		cardText = re.sub(f"(?<=ajouter leur )[^{LorcanaSymbols.STRENGTH}](?= à celle)", LorcanaSymbols.STRENGTH, cardText)
		# Correct Challenger/Offensif reminder text
		cardText = re.sub(r"gagne \+(\d+) \.\)", fr"gagne +\1 {LorcanaSymbols.STRENGTH}.)", cardText)
		# Correct Shift/Alter with an ink symbol
		cardText = re.sub(fr"(^Alter \d) ?[O{LorcanaSymbols.STRENGTH}]", fr"\1 {LorcanaSymbols.INK}", cardText)
		# Correct Boost with an ink symbol
		cardText = re.sub(fr"(?<=^Boost \d) ?[^{LorcanaSymbols.INK}](?!{LorcanaSymbols.INK})", f" {LorcanaSymbols.INK}", cardText)
		# Cost discount text
		cardText = re.sub(r"coûte (\d)0 de moins", f"coûte \\1 {LorcanaSymbols.INK} de moins", cardText)
		cardText = re.sub(fr"(coûte(?:nt)? )(\d+) [^{LorcanaSymbols.INK} \nou]+", fr"\1\2 {LorcanaSymbols.INK}", cardText)
		# Fix punctuation by turning multiple periods into an ellipsis character, and correct ellipsis preceded or followed by periods
		cardText = re.sub(r"…?\.{2,}…?", "…", cardText)
		# Ellipsis get misread as periods often, try to recognize it by the first letter after a period not being capitalized
		cardText = re.sub(r"\.+ ([a-z])", r"… \1", cardText)
		cardText = re.sub(r"^‘", "“", cardText, flags=re.MULTILINE)
		# "Il" often gets misread as "I!" or "[|"
		cardText = re.sub(r"(?<![A-Z])[I|/![][!|/]", "Il", cardText)
		cardText = re.sub(r"(^|\s|')[/\[IH]+l+umin(arium|eur)", "\\1Illumin\\2", cardText)
		cardText = cardText.replace("IHum", "Illum")
		# French always has a space before punctuation marks
		cardText = re.sub(r"([^? ])!", r"\1 !", cardText)
		cardText = re.sub(r"!(\w)", r"! \1", cardText)
		cardText = re.sub(fr"((?:\bce personnage|\bil) gagne )\+(\d) [^{LorcanaSymbols.LORE}{LorcanaSymbols.STRENGTH}{LorcanaSymbols.WILLPOWER}]?\.", fr"\1+\2 {LorcanaSymbols.STRENGTH}.", cardText)
		# Fix second line of 'Challenger'/'Offensif' reminder text
		cardText = re.sub(r"^\+(\d) ?[^.]{0,2}\.\)$", fr"+\1 {LorcanaSymbols.STRENGTH}.)", cardText, flags=re.MULTILINE)
		# Sometimes a number before 'dommage' gets read as something else, correct that
		cardText = re.sub(r"\b[l|] dommage", "1 dommage", cardText)
		# Misc common mistakes
		cardText = cardText.replace("Ily", "Il y")
		cardText = re.sub(r"\bC[ao]\b", "Ça", cardText)
		cardText = cardText.replace("personhage", "personnage")
		cardText = re.sub("[—-]l['’]", "—L'", cardText)
	elif GlobalConfig.language == Language.GERMAN:
		# The Exert symbol sometimes gets missed at the start
		cardText = re.sub(r"^ ?[-–—]+", f"{LorcanaSymbols.EXERT} —", cardText)
		# It confuses some ink splats for a Strength symbol in Shift reminder text
		cardText = re.sub(f"diese[nh] ?.\n", "diesen\n", cardText)
		# Payment text
		cardText = re.sub(fr"(\d)[ .]?(?:\W|0|D|O|Ô|Q{LorcanaSymbols.STRENGTH}){{,2}}(\s)(mehr )?(be)?zahl(en|t)\b", f"\\1 {LorcanaSymbols.INK}\\2\\3\\4zahl\\5", cardText)
		cardText = re.sub(fr"zahlst(\sdu)?(\s)(\d) ?[0{LorcanaSymbols.STRENGTH}©]?(?=$| )", f"zahlst\\1\\2\\3 {LorcanaSymbols.INK}", cardText, flags=re.MULTILINE)
		# 'Challenger' reminder text
		cardText = re.sub(r"herausfordert, erhält er \+(\d+) \S+\.\)", f"herausfordert, erhält er +\\1 {LorcanaSymbols.STRENGTH}.)", cardText)
		# 'Support' reminder text
		cardText = re.sub(r"(seine|ihre)(\s)(?:\S{1,2} )?in diesem Zug zur(\s)\S{1,2}", f"\\1\\2{LorcanaSymbols.STRENGTH} in diesem Zug zur\\3{LorcanaSymbols.STRENGTH}", cardText)
		# Correct Shift/Gestaltwandel and Boost/Stärken with an ink symbol
		cardText = re.sub(fr"^(Gestaltwandel|Stärken) ?(\d) ?[0O{LorcanaSymbols.STRENGTH}]", fr"\1 \2 {LorcanaSymbols.INK}", cardText)
		# Song reminder text
		cardText = re.sub(fr"(?<=oder mehr kostet, )[^{LorcanaSymbols.EXERT}](?=, damit)", LorcanaSymbols.EXERT, cardText)
		# The Lore symbol gets read as a '+', correct that
		cardText = re.sub(r"(\d+) \+", f"\\1 {LorcanaSymbols.LORE}", cardText)
		# The 'Exert' symbol at the start sometimes gets read as a 'C' or 'G' followed by another letter, fix that
		cardText = re.sub("^[CG][A-Z0]?(?= )", LorcanaSymbols.EXERT, cardText)
		# Strength correction, since 'mehr _ hat' usually needs the strength symbol
		cardText = re.sub(fr"oder mehr [^{LorcanaSymbols.LORE}{LorcanaSymbols.STRENGTH}{LorcanaSymbols.WILLPOWER}] hat", f"oder mehr {LorcanaSymbols.STRENGTH} hat", cardText)
		# Correct simple wrong characters
		cardText = cardText.replace("ı", "i")
		cardText = re.sub(",$", ".", cardText)
		# Remove some trailing characters at the very end of the card text
		cardText = re.sub(r"(?<!\.)\. [.|]$", ".", cardText)
		# Make sure dash in ability cost and in quote attribution is always long-dash, while a dash in the middle of a line is an n-dash
		cardText = cardText.replace("—-", "—")
		cardText = re.sub(r"(?<=\s)[-—](?=\s[a-z])", "–", cardText)
		cardText = cardText.replace("(auch du.)", "(auch du)")
		# Quotemarks sometimes get read double
		cardText = re.sub("[’‘']{2,}", "'", cardText)
	elif GlobalConfig.language == Language.ITALIAN:
		# Correct pipe characters
		cardText = cardText.replace("|", "I")
		# Correct payment text
		cardText = re.sub(r"(paga(?:re)? \d) (in|per)", fr"\1 {LorcanaSymbols.INK} \2", cardText)
		cardText = re.sub(fr"(\b[Pp]ag(a(?:re)?|hi)\s\d )[^{LorcanaSymbols.INK} .]+", fr"\1{LorcanaSymbols.INK}", cardText)
		cardText = re.sub(r"(\b[Pp]aga(?:re)?\s\d)[0Q]", f"\\1 {LorcanaSymbols.INK}", cardText)
		# Correct Support reminder text
		cardText = re.sub(r"(?<=aggiungere\sla\ssua\s)(?:\S+)(\salla\s)(?:\S+)(?=\sdi\sun)", f"{LorcanaSymbols.STRENGTH}\\1{LorcanaSymbols.STRENGTH}", cardText)
		cardText = re.sub(fr"(?<=puoi aggiungere la sua )(?:. )?alla(?=\n[^{LorcanaSymbols.STRENGTH}])", f"{LorcanaSymbols.STRENGTH} alla {LorcanaSymbols.STRENGTH}", cardText)
		# Correct 'Evasive', it sometimes imagines a character between the 'S' and the 'f'
		cardText = re.sub(r"^S.fuggente\b", "Sfuggente", cardText)
		# In Song reminder text, it reads 'con costo 1 o' as 'con costo 10'
		cardText = re.sub(r"(?<=con costo \d)0(?= [^o])", " o", cardText)
		# Fix Song reminder Exert symbol
		cardText = re.sub(r"(?<=\d\so superiore può ).(?= per\scantare questa canzone gratis)", LorcanaSymbols.EXERT, cardText)
		# Correct Shift/Trasformazione and Boost/Potenziamento with an ink symbol
		cardText = re.sub(fr"^(Trasformazione|Potenziamento) (\d) ?[0ÈOÒ{LorcanaSymbols.STRENGTH}]", fr"\1 \2 {LorcanaSymbols.INK}", cardText)
		# It misses the Strength symbol if it's at the end of a line
		cardText = re.sub(r"(?<=Riceve \+\d)\n", f" {LorcanaSymbols.STRENGTH}\n", cardText)
		# It frequently reads the Strength symbol as 'XX or a percentage sign' or leaves a closing bracket
		cardText = cardText.replace("XX", LorcanaSymbols.STRENGTH)
		cardText = re.sub(r"\d?%(?=\s)", f" {LorcanaSymbols.STRENGTH}", cardText)
		cardText = cardText.replace(f"{LorcanaSymbols.STRENGTH})", LorcanaSymbols.STRENGTH)
		# It sometimes reads the Exert symbol as a bracket
		cardText = cardText.replace("(uno", f"{LorcanaSymbols.EXERT} uno")
		# It reads 'Iena' (Italian for 'Hyena'), as 'lena'
		cardText = re.sub(r"\blena", "Iena", cardText)
		# It sometimes read 'volta' on a new line as starting with a capital V
		cardText = re.sub("(?<=ogni\n)V(?=olta)", "v", cardText)
		cardText = re.sub(r"(?<=\suna\s)0(?=\spiù\s)", "o", cardText)
		# Fix misreadings of 'Il'
		cardText = re.sub(r"[1!][!/l]", "Il", cardText)
		# Fix misreading of 'lì'
		cardText = cardText.replace("Îì", "lì")
		# 'cè' should always have a quote inbetween
		cardText = re.sub(r"\bcè\b", "c'è", cardText)
		# For some reason it adds an extra 't' to 'sfidarli'
		cardText = re.sub(r"\bsfidatr?li\b", "sfidarli", cardText)
		# It sometimes imagines an extra 'i' at the start sometimes
		cardText = re.sub(r"^i I", "I", cardText)
		# 'l' at the start should be capitalized, either to an 'L' or an 'I'
		cardText = re.sub("^l'", "L'", cardText)
		cardText = re.sub("(^|\\. )lo", "\\1Io", cardText)
		# Instead of '1 o' it often reads '10'
		cardText = re.sub(r"(?<=costo \d)0(?=\sinferiore)", " o", cardText)
		# Misread of 'Illuminatore'
		cardText = cardText.replace("Ilumi", "Illumi")
		# Correct accent-less E at the start of lines to with an accent
		cardText = re.sub(r"^(“?)E\b", "\\1È", cardText)

	if GlobalConfig.language != Language.FRENCH:
		# Make sure dash in ability cost and in quote attribution is always long-dash
		cardText = re.sub(fr"(?<!\w|{LorcanaSymbols.LORE}|{LorcanaSymbols.STRENGTH})[-—~]+(?=\D|$)", r"—", cardText, flags=re.MULTILINE)
	if cardText != originalCardText:
		_logger.info(f"Corrected card text from {originalCardText!r} to {cardText!r}")
	return cardText

def correctPunctuation(textToCorrect: str) -> str:
	"""
	Corrects some punctuation, like fixing weirdly spaced ellipses, or quote marks
	Mainly useful to correct flavor text
	:param textToCorrect: The text to correct. Can be multiline
	:return: The fixed text, or the original text if there was nothing to fix
	"""
	correctedText = textToCorrect.strip()
	# Simplify quote mark if it's used in a contraction
	correctedText = re.sub(r"(?<=\w)['‘’]+(?=\w)", "'", correctedText)
	# It frequently misses the dash before a quote attribution
	correctedText = re.sub(r"\n([A-Z]\w+)$", "\n—\\1", correctedText)
	# Fix some erroneous extra punctuation
	correctedText = re.sub(r"\? [.;]$", "?", correctedText)
	# Ellipses get parsed weird, with spaces between periods where they don't belong. Fix that
	if correctedText.count(".") > 2:
		correctedText = correctedText.replace(". ...", "...")
		correctedText = re.sub(r"([\xa0 ]?\.[\xa0 ]?){3}", "..." if GlobalConfig.language == Language.ENGLISH else "…", correctedText)
	if "…" in correctedText:
		correctedText = re.sub(r"\.*…( ?\.+)?", "…", correctedText)
	# Replace non-breaking spaces with normal spaces, for consistency
	if "\xa0" in correctedText:
		correctedText = correctedText.replace("\xa0", " ")
	if correctedText.startswith("‘"):
		correctedText = "“" + correctedText[1:]
	if correctedText.endswith(","):
		correctedText = correctedText[:-1] + "."
	if GlobalConfig.language == Language.ENGLISH:
		correctedText = re.sub(r"\b([Tt]hey|[Yy]ou) ?(ll|re|ve)\b", r"\1'\2", correctedText)
		correctedText = re.sub(r"\bIAM\b", "I AM", correctedText)
		correctedText = re.sub(r"\bl'm\b", "I'm", correctedText)
		# Correct fancy quotemarks when they're used in shortenings (f.i. "'em", "comin'", etc.)
		correctedText = re.sub(r"(?<=\s)[‘’](?=(cause|em|til)([,.?!]|\s|$))", "'", correctedText, flags=re.IGNORECASE)
		correctedText = re.sub(r"(?<=\win)[‘’](?=[,.?!]|\s|$)", "'", correctedText, flags=re.IGNORECASE)
		correctedText = re.sub(r"(?<=\sol)[‘’](?=\s|$)", "'", correctedText, flags=re.IGNORECASE)
	elif GlobalConfig.language == Language.GERMAN:
		# In German, ellipsis always have a space between words before and after it
		if "…" in correctedText:
			correctedText = re.sub(r"(\w)…", r"\1 …", correctedText)
			correctedText = re.sub(r"…(\w)", r"… \1", correctedText)
		# Fix closing quote mark
		correctedText = correctedText.replace("”", "“")
		# Quotemarks used as letter replacements should be simple quotemarks
		correctedText = re.sub(r"((?:^|\s)h(?:ab|ätt|ör))[‘’](?=\s|$)", "\\1'", correctedText, flags=re.IGNORECASE)
		correctedText = re.sub(r"(?<=\s)[‘’](?=ne[nm]?\s)", "'", correctedText)
	elif GlobalConfig.language == Language.ITALIAN:
		# Make sure there's a space after ellipses
		correctedText = re.sub(r"…(?=\w)", r"… ", correctedText)
		# There shouldn't be a space between a quote attribution dash and the name
		correctedText = re.sub(r"(?<=”\s—) (?=[A-Z])", "", correctedText)
		# It has some trouble recognising exclamation marks
		correctedText = re.sub(r" ?\.””", "!”", correctedText)
		# Quotemarks used as letter replacements should be simple quotemarks
		correctedText = re.sub(r"(?<=\spo)’(?=\.|\s)", "'", correctedText)

	correctedText = correctedText.rstrip(" -_")
	correctedText = correctedText.replace("““", "“")
	if correctedText.startswith("\""):
		correctedText = "“" + correctedText[1:]
	if correctedText != textToCorrect:
		_logger.info(f"Corrected punctuation from {textToCorrect!r} to {correctedText!r}")
	return correctedText

def correctCardField(card: Dict, fieldName: str, regexMatchString: str, correction: str) -> None:
	"""
	Correct card-specific mistakes in the fieldName field of the provided card
	:param card: The output card as parsed so far
	:param fieldName: The fieldname to correct
	:param regexMatchString: A regex that matches the card's mistake, this text will get replaced with the 'correction' string. Can be None if the field doesn't exist yet. To remove a field, set this and 'correction' to None
	:param correction: The correction for the mistake matched by 'regexMatchString', or the value to set if the field doesn't exist. To remove a field, set this and 'regexMatchString' to None
	"""
	if fieldName not in card:
		if regexMatchString is not None:
			_logger.warning(f"Trying to correct field '{fieldName}' in card {CardUtil.createCardIdentifier(card)} from {regexMatchString!r} to {correction!r} but the field does not exist. Set the match string to 'null' if you want to add a field")
		elif correction is None:
			_logger.warning(f"Trying to remove field '{fieldName}' but it already doesn't exist in card {CardUtil.createCardIdentifier(card)}")
		else:
			card[fieldName] = correction
	elif regexMatchString is None:
		if correction is None:
			_logger.info(f"Removing field '{fieldName}' (value {card[fieldName]!r}) from card {CardUtil.createCardIdentifier(card)}")
			del card[fieldName]
		elif fieldName in card:
			if isinstance(card[fieldName], list):
				if isinstance(card[fieldName][0], type(correction)):
					_logger.info(f"Appending value {correction} to list field {fieldName} in card {CardUtil.createCardIdentifier(card)}")
					card[fieldName].append(correction)
				else:
					_logger.warning(f"Trying to add value {correction!r} of type {type(correction)} to list of {type(card[fieldName][0])} types in card {CardUtil.createCardIdentifier(card)}, skipping")
			else:
				_logger.warning(f"Trying to add field '{fieldName}' to card {CardUtil.createCardIdentifier(card)}, but that field already exists (value {card[fieldName]!r})")
	elif isinstance(card[fieldName], str):
		preCorrectedText = card[fieldName]
		card[fieldName] = re.sub(regexMatchString, correction, preCorrectedText, flags=re.DOTALL)
		if card[fieldName] == preCorrectedText:
			_logger.warning(f"Correcting field '{fieldName}' in card {CardUtil.createCardIdentifier(card)} with regex {regexMatchString!r} didn't change anything, value is still {preCorrectedText!r}")
		else:
			_logger.info(f"Corrected field '{fieldName}' from {preCorrectedText!r} to {card[fieldName]!r} for card {CardUtil.createCardIdentifier(card)}")
	elif isinstance(card[fieldName], list):
		matchFound = False
		if isinstance(card[fieldName][0], dict):
			# The field is a list of dicts, apply the correction to each entry if applicable
			for fieldIndex, fieldEntry in enumerate(card[fieldName]):
				for fieldKey, fieldValue in fieldEntry.items():
					if not isinstance(fieldValue, str):
						continue
					match = re.search(regexMatchString, fieldValue, flags=re.DOTALL)
					if match:
						matchFound = True
						preCorrectedText = fieldValue
						fieldEntry[fieldKey] = re.sub(regexMatchString, correction, fieldValue, flags=re.DOTALL)
						if fieldEntry[fieldKey] == preCorrectedText:
							_logger.warning(f"Correcting index {fieldIndex} of field '{fieldName}' in card {CardUtil.createCardIdentifier(card)} with regex {regexMatchString!r} didn't change anything, value is still {preCorrectedText!r}")
						else:
							_logger.info(f"Corrected index {fieldIndex} of field '{fieldName}' from {preCorrectedText!r} to {fieldEntry[fieldKey]!r} for card {CardUtil.createCardIdentifier(card)}")
		elif isinstance(card[fieldName][0], str):
			for fieldIndex in range(len(card[fieldName]) - 1, -1, -1):
				fieldValue = card[fieldName][fieldIndex]
				match = re.search(regexMatchString, fieldValue, flags=re.DOTALL)
				if match:
					matchFound = True
					if correction is None:
						# Delete the value
						_logger.info(f"Removing index {fieldIndex} value {fieldValue!r} from field '{fieldName}' in card {CardUtil.createCardIdentifier(card)}")
						card[fieldName].pop(fieldIndex)
						if len(card[fieldName]) == 0:
							_logger.info(f"After correction, list field '{fieldName}' is now empty, deleting from card {CardUtil.createCardIdentifier(card)}")
							del card[fieldName]
					else:
						preCorrectedText = fieldValue
						card[fieldName][fieldIndex] = re.sub(regexMatchString, correction, fieldValue, flags=re.DOTALL)
						if card[fieldName][fieldIndex] == preCorrectedText:
							_logger.warning(f"Correcting index {fieldIndex} of field '{fieldName}' in card {CardUtil.createCardIdentifier(card)} with regex {regexMatchString!r} didn't change anything")
						else:
							_logger.info(f"Corrected index {fieldIndex} of field '{fieldName}' from {preCorrectedText!r} to {card[fieldName][fieldIndex]!r} for card {CardUtil.createCardIdentifier(card)}")
		else:
			_logger.error(f"Unhandled type of list entries ({type(card[fieldName][0])}) in card {CardUtil.createCardIdentifier(card)}")
		if not matchFound:
			_logger.warning(f"Correction regex {regexMatchString!r} for field '{fieldName}' in card {CardUtil.createCardIdentifier(card)} didn't match any of the entries in that field")
	elif isinstance(card[fieldName], int):
		if card[fieldName] != regexMatchString:
			_logger.warning(f"Expected value of field '{fieldName}' in card {CardUtil.createCardIdentifier(card)} is {regexMatchString!r}, but actual value is {card[fieldName]!r}, skipping correction")
		else:
			_logger.info(f"Corrected numerical value of field '{fieldName}' in card {CardUtil.createCardIdentifier(card)} from {card[fieldName]} to {correction}")
			card[fieldName] = correction
	elif isinstance(card[fieldName], bool):
		if card[fieldName] == correction:
			_logger.warning(f"Corrected value for boolean field '{fieldName}' is the same as the existing value '{card[fieldName]}' for card {CardUtil.createCardIdentifier(card)}")
		else:
			_logger.info(f"Corrected boolean field '{fieldName}' in card {CardUtil.createCardIdentifier(card)} from {card[fieldName]} to {correction}")
			card[fieldName] = correction
	elif isinstance(card[fieldName], dict):
		# Go through each key-value pair to try and find a matching entry
		isStringMatch = isinstance(regexMatchString, str)
		for key in card[fieldName]:
			value = card[fieldName][key]
			if value == regexMatchString or (isStringMatch and isinstance(value, str) and re.search(regexMatchString, value, flags=re.DOTALL)):
				card[fieldName][key] = re.sub(regexMatchString, correction, value) if isStringMatch else correction
				if value == card[fieldName][key]:
					_logger.warning(f"Correcting value for key '{key}' in dictionary field '{fieldName}' of card {CardUtil.createCardIdentifier(card)} with regex {regexMatchString!r} didn't change anything, value is still '{value}'")
				else:
					_logger.info(f"Corrected value '{value}' to '{card[fieldName][key]}' in key '{key}' of dictionary field '{fieldName}' in card {CardUtil.createCardIdentifier(card)}")
				break
		else:
			_logger.warning(f"Correction {regexMatchString!r} for dictionary field '{fieldName}' in card {CardUtil.createCardIdentifier(card)} didn't match any of the values")
	else:
		raise ValueError(f"Card correction {regexMatchString!r} for field '{fieldName}' in card {CardUtil.createCardIdentifier(card)} is of unsupported type '{type(card[fieldName])}'")

def correctCardFieldFromList(card: Dict, fieldName: str, correctionsList: List[Union[int, str]]):
	"""
	Correct card-specific mistakes in the fieldName field of the provided card
	:param card: The output card as parsed so far
	:param fieldName: The fieldname to correct
	:param correctionsList: A list of corrections. This list should be of an even-numbered length, with the first entry being the error to match, the second entry the fix for the error, the (optional) third another match, etc
	"""
	if len(correctionsList) > 2:
		for correctionIndex in range(0, len(correctionsList), 2):
			correctCardField(card, fieldName, correctionsList[correctionIndex], correctionsList[correctionIndex + 1])
	else:
		correctCardField(card, fieldName, correctionsList[0], correctionsList[1])
