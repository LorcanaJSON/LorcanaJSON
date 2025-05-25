import logging, math, os, re, time
from collections import namedtuple
from typing import Dict, List, Union

import cv2, tesserocr
from PIL import Image

import GlobalConfig
from OCR import ImageArea, ParseSettings
from OCR.OcrResult import OcrResult
from util import IdentifierParser, LorcanaSymbols


ImageAndText = namedtuple("ImageAndText", ("image", "text"))

_ABILITY_LABEL_MARGIN: int = 12
_FLAVORTEXT_MARGIN: int = 14
_ASSUMED_LABEL_HEIGHT: int = 73


class ImageParser:
	def __init__(self):
		"""
		Create an image parser
		:param forceGenericModel: If True, force the use of the generic Tesseract model for the language, even if a Lorcana-specific one exists. If False or not provided, uses the Lorcana model if available for the current language. Defaults to False
		"""
		self._logger = logging.getLogger("LorcanaJSON")
		self.nonCharacterTypes = (GlobalConfig.translation.Action, GlobalConfig.translation.Item, GlobalConfig.translation.Location)
		self._tesseractApi = tesserocr.PyTessBaseAPI(lang=GlobalConfig.language.threeLetterCode, path=GlobalConfig.tesseractPath, psm=tesserocr.PSM.SINGLE_BLOCK)
		self._tesseractApi.SetVariable("textord_tabfind_find_tables", "0")
		self._tesseractApi.SetVariable("textord_tabfind_vertical_text", "0")
		self._tesseractApi.SetVariable("textord_disable_pitch_test", "1")
		self._tesseractApi.SetVariable("textord_restore_underlines", "0")
		self._tesseractApi.SetVariable("tessedit_single_match", "1")
		self._tesseractApi.SetVariable("il1_adaption_test", "0")
		self._tesseractApi.SetVariable("tessedit_page_number", "0")
		self._tesseractApi.SetVariable("permute_only_top", "1")
		self._tesseractApi.SetVariable("tessedit_enable_bigram_correction", "0")
		self._tesseractApi.SetVariable("enable_noise_removal", "0")
		self._tesseractApi.SetVariable("tessedit_fix_fuzzy_spaces", "0")
		self._tesseractApi.SetVariable("tessedit_fix_hyphens", "0")
		self._tesseractApi.SetVariable("crunch_early_convert_bad_unlv_chs", "1")

	def getImageAndTextDataFromImage(self, cardId: int, baseImagePath: str, parseFully: bool, parsedIdentifier: IdentifierParser.Identifier = None, cardType: str = None, hasCardText: bool = None, hasFlavorText: bool = None,
									 isEnchanted: bool = None, showImage: bool = False) -> OcrResult:
		startTime = time.perf_counter()
		result: Dict[str, Union[None, ImageAndText, List[ImageAndText]]] = {
			"flavorText": None,
			"abilityLabels": [],
			"abilityTexts": [],
			"remainingText": None,
			"subtypesText": None,
			"artist": None
		}
		if parseFully:
			result.update({
				"cost": None,
				"identifier": None,
				"moveCost": None,
				"name": None,
				"strength": None,
				"version": None,
				"willpower": None
			})
		imagePath = os.path.join(baseImagePath, f"{cardId}.jpg")
		if not os.path.isfile(imagePath):
			imagePath = os.path.join(baseImagePath, f"{cardId}.png")
		if not os.path.isfile(imagePath):
			raise FileNotFoundError(f"Unable to find image for card ID {cardId}")
		cardImage: cv2.Mat = cv2.imread(imagePath)
		if cardImage is None:
			raise ValueError(f"Card image '{imagePath}' could not be loaded, possibly because it doesn't exist")
		cardImageHeight = cardImage.shape[0]
		cardImageWidth = cardImage.shape[1]
		if cardImageHeight != ImageArea.IMAGE_HEIGHT or cardImageWidth != ImageArea.IMAGE_WIDTH:
			# The image isn't the expected size
			# If it's a small difference, assume it's just some small extra black borders and remove those
			heightDifference = cardImageHeight - ImageArea.IMAGE_HEIGHT
			widthDifference = cardImageWidth - ImageArea.IMAGE_WIDTH
			if 30 < heightDifference < 35 and 17 < widthDifference < 23:
				halfHeightDifference = heightDifference // 2
				halfWidthDifference = widthDifference // 2
				self._logger.debug(f"Image is a bit too large, assuming there are extra black borders, removing {halfHeightDifference} height on both sides and {halfWidthDifference} width")
				cardImage = cardImage[halfHeightDifference: cardImageHeight - halfHeightDifference, halfWidthDifference: cardImageWidth - halfWidthDifference]
			else:
				# Otherwise, resize it so it matches our image areas
				self._logger.debug(f"Image is {cardImage.shape}, while it should be {ImageArea.IMAGE_HEIGHT} by {ImageArea.IMAGE_WIDTH}, resizing")
				cardImage = cv2.resize(cardImage, (ImageArea.IMAGE_WIDTH, ImageArea.IMAGE_HEIGHT), interpolation=cv2.INTER_AREA)
		self._logger.debug(f"Reading {imagePath=} finished at {time.perf_counter() - startTime} seconds in")

		# Parse card cost first, since that's always in the top left, regardless of whether the card should later be rotated
		if parseFully:
			result["cost"] = self._getSubImageAndText(cardImage, ImageArea.INK_COST)

		parseSettings = ParseSettings.getParseSetingsById(cardId)

		if parseSettings and parseSettings.isLocationOverride is not None:
			isLocation = parseSettings.isLocationOverride
		elif cardType is None:
			# Figure out whether this is a Location card or not. We need to do this as soon as possible, because Location cards need to be rotated
			# Location cards, both Enchanted and not Enchanted, have a thick black border at their bottom, so the right side of a non-rotated image, thicker than a non-Enchanted non-Location card. Check for that
			isLocation = self._isImageBlack(self._getSubImage(cardImage, ImageArea.IS_LOCATION_CHECK))
		else:
			isLocation = cardType == GlobalConfig.translation.Location

		if isLocation:
			# Location cards are horizontal, so the image should be rotated for proper OCR
			cardImage = cv2.rotate(cardImage, cv2.ROTATE_90_CLOCKWISE)
		greyCardImage: cv2.Mat = cv2.cvtColor(cardImage, cv2.COLOR_BGR2GRAY)

		if isEnchanted is None:
			isEnchanted = not self._isImageBlack(self._getSubImage(cardImage, ImageArea.IS_BORDERLESS_CHECK))
			#TODO Add way to determine whether this is old- or new-style Enchanted (from set 5 onward the Enchanted design changed)

		# Check if we need to retrieve the identifier
		if parsedIdentifier is None or parseFully:
			result["identifier"] = self._getSubImageAndText(greyCardImage, ImageArea.LOCATION_IDENTIFIER if isLocation else ImageArea.CARD_IDENTIFIER)
			if parsedIdentifier is None:
				parsedIdentifier = IdentifierParser.parseIdentifier(result["identifier"].text)
				if not parsedIdentifier:
					raise ValueError(f"Unable to parse identifier for card ID {cardId}, OCR'ed identifier text is {result['identifier'].text!r}")

		# Now we can determine the parse settings, if we hadn't found them already
		if parseSettings is None:
			parseSettings = ParseSettings.getParseSettings(cardId, parsedIdentifier, isEnchanted)

		isCharacter = None
		if cardType:
			isCharacter = cardType == GlobalConfig.translation.Character
		# First determine the card (sub)type
		typesImageArea = (parseSettings.locationCardLayout if isLocation else parseSettings.cardLayout).types
		typesImage = self._getSubImage(greyCardImage, typesImageArea)
		typesImage = self._convertToThresholdImage(typesImage, typesImageArea.textColour)
		typesImageText = self._imageToString(typesImage).strip("\"'‘-1|{} ")
		if "\n" in typesImageText:
			self._logger.debug(f"Removing part before newline character from types image text {typesImageText!r}")
			typesImageText = typesImageText.rsplit("\n", 1)[1]
		self._logger.debug(f"Parsing types image finished at {time.perf_counter() - startTime} seconds in")
		if typesImageText not in self.nonCharacterTypes:
			# The type separator character is always the same, but often gets interpreted wrong; fix that
			if " " in typesImageText:
				typesImageText = re.sub(r" (\S )?", f" {LorcanaSymbols.SEPARATOR} ", typesImageText)
			result["subtypesText"] = ImageAndText(typesImage, typesImageText)
			self._logger.debug(f"{typesImageText=}")
			if parseSettings.isItemOverride:
				isCharacter = False
			elif isCharacter is None:
				isCharacter = not isLocation and typesImageText not in self.nonCharacterTypes and typesImageText.split(" ", 1)[0] not in self.nonCharacterTypes
		else:
			if isCharacter is None:
				isCharacter = False
			self._logger.debug(f"Subtype is main type ({typesImageText=}), so not storing as subtypes")

		if isCharacter:
			cardLayout = parseSettings.characterCardLayout
		elif isLocation:
			cardLayout = parseSettings.locationCardLayout
		else:
			cardLayout = parseSettings.cardLayout

		result["artist"] = self._getSubImageAndText(greyCardImage, cardLayout.artist)
		if parseFully:
			# Parse from top to bottom
			result["name"] = self._getSubImageAndText(greyCardImage, cardLayout.name)
			if isCharacter:
				result["version"] = self._getSubImageAndText(greyCardImage, cardLayout.version)
				result["strength"] = self._getSubImageAndText(greyCardImage, cardLayout.strength)
				result["willpower"] = self._getSubImageAndText(greyCardImage, cardLayout.willpower)
			elif isLocation:
				result["version"] = self._getSubImageAndText(greyCardImage, cardLayout.version)
				result["moveCost"] = self._getSubImageAndText(greyCardImage, cardLayout.moveCost)
				result["willpower"] = self._getSubImageAndText(greyCardImage, cardLayout.willpower)

		if parseSettings.getIdentifierFromCard and result.get("identifier", None) is None:
			result["identifier"] = self._getSubImageAndText(greyCardImage, cardLayout.identifier)

		# Greyscale images work better, so get one from just the textbox
		greyTextboxImage = self._getSubImage(greyCardImage, cardLayout.textbox)
		textboxWidth = greyTextboxImage.shape[1]
		textboxHeight = greyTextboxImage.shape[0]

		# First get the ability label coordinates, so we know where we can find the flavor text separator
		# Then get the flavor text separator and the flavor text itself
		# Finally get the ability text, since that goes between the labels and the flavor text

		# Find where the ability name labels are, store them as the top y, bottom y and the right x, so we know where to get the text from
		# New-style Enchanted cards get parsed differently because this method doesn't find labels on those, it's handled in the 'remainingText' parsing section
		textboxEdgeDetectedImage: Image.Image = None
		textboxLinesImage: Image.Image = None
		labelCoords = []
		if hasCardText is not False:
			if parseSettings.labelParsingMethod == ParseSettings.LABEL_PARSING_METHODS.DEFAULT:
				isCurrentlyInLabel: bool = False
				currentCoords = [0, 0, 0]
				for y in range(textboxHeight):
					pixelValue = greyTextboxImage[y, parseSettings.textboxOffset]
					if isCurrentlyInLabel:
						# Check if the pixel got lighter, indicating we left the label block
						if pixelValue > 110:
							isCurrentlyInLabel = False
							if y - currentCoords[0] < 50:
								self._logger.debug(f"Skipping possible label starting at y={currentCoords[0]} and ending at {y=}, not high enough to be a label")
							else:
								currentCoords[1] = y - 1
								labelCoords.append(tuple(currentCoords))  # Copy the coordinates list so we can't accidentally change a value anymore
					# Check if a label started here
					elif pixelValue < 105:
						isCurrentlyInLabel = True
						currentCoords[0] = y
						yToCheck = min(textboxHeight - 1, y + 1)  # Check a few lines down to prevent weirdness with the edge of the label box
						# Find the width of the label. Since accented characters can reach the top of the label, we need several light pixels in succession to be sure the label ended
						successiveLightPixels: int = 0
						for x in range(parseSettings.textboxOffset, textboxWidth - parseSettings.textboxRightOffset):
							checkValue = greyTextboxImage[yToCheck, x]
							if checkValue > 120:
								successiveLightPixels += 1
								if successiveLightPixels > 5:
									if x < 100:
										self._logger.debug(f"Skipping label at {currentCoords=} and {x=}, not wide enough to be a label")
										currentCoords[0] = 0
										currentCoords[1] = 0
										isCurrentlyInLabel = False
									else:
										currentCoords[2] = x - _ABILITY_LABEL_MARGIN - 6
									break
							else:
								successiveLightPixels = 0
						else:
							#raise ValueError(f"Unable to find right side of label at {y=} in the cropped image")
							# 'ability label' is as wide as the image, disqualify it
							# Don't raise an exception, because this is sometimes hit in Quest cards
							self._logger.debug(f"Reached right side of image in ability label check at {y=}, assuming it's not a label")
							currentCoords = [0, 0, 0]
							isCurrentlyInLabel = False
				if isCurrentlyInLabel:
					self._logger.warning(f"Still in label when end of label check reached in card image '{imagePath}'")
			elif parseSettings.labelParsingMethod == ParseSettings.LABEL_PARSING_METHODS.FALLBACK_BY_LINES:
				# Find labels by trying to find their top and/or bottom horizontal edge
				textboxEdgeDetectedImage = cv2.Canny(greyTextboxImage, 50, 200)
				lines = cv2.HoughLinesP(textboxEdgeDetectedImage, 1, math.pi / 180, 150, minLineLength=125, maxLineGap=3)
				if lines is None:
					self._logger.debug("Not found any abiltylabel lines, trying a shorter minimum length")
					lines = cv2.HoughLinesP(textboxEdgeDetectedImage, 1, math.pi / 180, 150, minLineLength=100, maxLineGap=3)
				if lines is None:
					self._logger.warning(f"Expected card to have lines but none were found in card image '{imagePath}'")
				else:
					# Sort lines from top to bottom
					lines = sorted(lines, key=lambda l: l[0][1])
					self._logger.debug(f"In line fallback method found {len(lines):,} lines")
					if showImage:
						textboxLinesImage = greyTextboxImage.copy()
						for line in lines:
							cv2.line(textboxLinesImage, (line[0][0], line[0][1]), (line[0][2], line[0][3]), (255, 255, 255), 2, cv2.LINE_AA)
					lastBottomY = 0
					for line in lines:
						# Check if this is a line at the top or bottom of a label
						lineRightX = line[0][2]
						lineRightY = line[0][3]
						if lineRightY < 10:
							self._logger.warning(f"Found line at x={lineRightX} y={lineRightY} for card ID {cardId} but that is too close to the top, skipping")
							continue
						# If this line is too close to the previous one, it's probably the bottom line of the previous top line of the same label; skip it
						if lastBottomY and lineRightY - lastBottomY < 80:
							if hasFlavorText and labelCoords and lineRightY - lastBottomY < 10:
								# It confused the flavor text separator for the start of an ability name label, remove the last added label
								del labelCoords[-1]
							continue
						isTopLine = greyTextboxImage[lineRightY - 1, lineRightX] > greyTextboxImage[lineRightY + 1, lineRightX]  # Images use y,x
						topY = bottomY = lineRightY
						# Assume the height of the average label (it can vary based on font size, but accurately determining it is complicated, error-prone, and not really necessary)
						if isTopLine:
							bottomY += _ASSUMED_LABEL_HEIGHT
						else:
							topY -= _ASSUMED_LABEL_HEIGHT
							lineRightX += _ABILITY_LABEL_MARGIN
						labelCoords.append((topY, bottomY, lineRightX))
						lastBottomY = bottomY
		self._logger.debug(f"Finished finding label coords at {time.perf_counter() - startTime} seconds in")

		# Find the line dividing the abilities from the flavor text, if needed
		flavorTextImage = None
		flavorTextSeparatorY = textboxHeight
		flavorTextLineDetectionCroppedImage: Union[None, cv2.Mat] = None
		flavorTextEdgeDetectedImage = None
		flavorTextGreyscaleImageWithLines = None
		if (parseSettings.hasFlavorTextOverride or (parseSettings.hasFlavorTextOverride is None and hasFlavorText is not False)) and parseSettings.labelParsingMethod != ParseSettings.LABEL_PARSING_METHODS.FALLBACK_BY_LINES:
			flavorTextImageTop = 0
			flavorTextLineDetectionCroppedImage = greyTextboxImage
			if labelCoords:
				flavorTextImageTop = labelCoords[-1][1] + 5
				flavorTextLineDetectionCroppedImage = greyTextboxImage[flavorTextImageTop:textboxHeight, 0:textboxWidth]
			if parseSettings.textboxOffset or parseSettings.textboxRightOffset:
				flavorTextLineDetectionCroppedImage = flavorTextLineDetectionCroppedImage[0:flavorTextLineDetectionCroppedImage.shape[0], parseSettings.textboxOffset:flavorTextLineDetectionCroppedImage.shape[1] - parseSettings.textboxRightOffset]
			flavorTextEdgeDetectedImage = cv2.Canny(flavorTextLineDetectionCroppedImage, 50, 200)
			lines = cv2.HoughLinesP(flavorTextEdgeDetectedImage, 1, math.pi / 180, 150, minLineLength=70)
			if lines is None and hasFlavorText is True:
				# Sometimes it can't find the full separator line, try to find a section of it instead
				lines = cv2.HoughLinesP(flavorTextEdgeDetectedImage, 1, math.pi / 180, 100, minLineLength=25, maxLineGap=0)
			if showImage:
				flavorTextGreyscaleImageWithLines = flavorTextLineDetectionCroppedImage.copy()
			self._logger.debug(f"Parsing flavor text images finished at {time.perf_counter() - startTime} seconds in")
			if lines is None:
				hasFlavorText = False
				self._logger.debug("No flavour text separator found")
			else:
				self._logger.debug(f"{len(lines):,} lines found: {lines!r}")
				flavorTextSeparatorY = 0
				for line in lines:
					if line[0][0] < 80 or line[0][1] < 20:
						# Too far to the left or to the top, probably a mistaken label
						self._logger.debug(f"Skipping line at {line[0]}, too close to the edge, probably a mistake")
						continue
					self._logger.debug(f"line length: {line[0][2] - line[0][0]}")
					# Draw the lines for debug purposes
					if showImage:
						cv2.line(flavorTextGreyscaleImageWithLines, (line[0][0], line[0][1]), (line[0][2], line[0][3]), (0, 0, 0), 3, cv2.LINE_AA)
					if line[0][1] > flavorTextSeparatorY:
						flavorTextSeparatorY = line[0][1]
				if flavorTextSeparatorY == 0:
					# No suitable line found, so probably no flavor text section
					hasFlavorText = False
					self._logger.debug("No flavor text separator line found")
					flavorTextSeparatorY = textboxHeight
				else:
					hasFlavorText = True
					flavorTextSeparatorY += flavorTextImageTop
					if flavorTextSeparatorY + _FLAVORTEXT_MARGIN >= textboxHeight:
						self._logger.warning(f"Flavortext separator Y {flavorTextSeparatorY} plus margin {_FLAVORTEXT_MARGIN} is larger than textbox height {textboxHeight} in card {cardId}")
						hasFlavorText = False
					else:
						flavorTextImage = self._convertToThresholdImage(greyTextboxImage[flavorTextSeparatorY + _FLAVORTEXT_MARGIN:textboxHeight, parseSettings.textboxOffset:textboxWidth - parseSettings.textboxRightOffset], parseSettings.thresholdTextColor)
						flavourText = self._imageToString(flavorTextImage)
						result["flavorText"] = ImageAndText(flavorTextImage, flavourText)
						self._logger.debug(f"{flavourText=}")
				self._logger.debug(f"Finding flavor text finished at {time.perf_counter() - startTime} seconds in")

		#Find the card text, one block at the time, separated by the ability name label
		# We have to go from bottom to top, because non-labelled text is above labelled text
		abilityLabelImage = None
		abilityTextImage = None
		remainingTextImage = None
		if hasCardText is not False:
			labelCoords.reverse()
			previousBlockTopY = flavorTextSeparatorY - (_FLAVORTEXT_MARGIN + 1 if hasFlavorText else 0)
			labelNumber = len(labelCoords)
			for labelCoord in labelCoords:
				# First get the label text itself. It's white on dark, so handle it the opposite way from the actual ability text
				abilityLabelImage = self._convertToThresholdImage(greyTextboxImage[labelCoord[0]:labelCoord[1], 0:labelCoord[2]], parseSettings.labelTextColor)
				abilityLabelText = self._imageToString(abilityLabelImage)
				result["abilityLabels"].append(ImageAndText(abilityLabelImage, abilityLabelText))
				# Then get the ability text
				# Put a white rectangle over where the label was, because the thresholding sometimes leaves behind some pixels, which confuses Tesseract, leading to phantom letters
				abilityTextImage = greyTextboxImage.copy()
				cv2.rectangle(abilityTextImage, (0, 0), (labelCoord[2] + _ABILITY_LABEL_MARGIN, labelCoord[1]), parseSettings.labelMaskColor, thickness=-1)  # -1 thickness fills the rectangle
				abilityTextImage = self._convertToThresholdImage(abilityTextImage[labelCoord[0]:previousBlockTopY, 0:textboxWidth], parseSettings.thresholdTextColor)
				abilityText = self._imageToString(abilityTextImage)
				result["abilityTexts"].append(ImageAndText(abilityTextImage, abilityText))
				self._logger.debug(f"{abilityLabelText=} ({labelCoord[1] - labelCoord[0]} px high), {abilityText=}")
				previousBlockTopY = labelCoord[0]
				labelNumber -= 1
			self._logger.debug(f"{len(labelCoords)} {labelCoords=}")
			self._logger.debug(f"Finding abilities finished at {time.perf_counter() - startTime} seconds in")
			# Order the labels from top to bottom
			result["abilityLabels"].reverse()
			result["abilityTexts"].reverse()

			# There might be text above the label coordinates too (abilities text), especially if there aren't any labels. Get that text as well
			if previousBlockTopY > 35:
				remainingTextImage = self._convertToThresholdImage(greyTextboxImage[0:previousBlockTopY, parseSettings.textboxOffset:textboxWidth - parseSettings.textboxRightOffset], parseSettings.thresholdTextColor)
				remainingText = self._imageToString(remainingTextImage)
				if remainingText:
					if parseSettings.labelParsingMethod == ParseSettings.LABEL_PARSING_METHODS.FALLBACK_WHITE_ABILITY_TEXT and re.search("[A-Z]{2,}", remainingText):
						# Detecting labels on new-style Enchanted cards is hard, so for those the full card text is 'remainingText'
						# Try to get the labels and effects out
						labelMatch = re.search("([AÀÈI] |I['’]M )?[A-ZÈÉÊÜ]{2}", remainingText)
						if labelMatch:
							labelAndEffectText = remainingText[labelMatch.start():]
							remainingText = remainingText[:labelMatch.start()].rstrip()
							while labelAndEffectText:
								effectMatch = re.search(fr"(([A-Z]|[ÀI|] )[a-z]|[0-9{LorcanaSymbols.EXERT}@©&]|G,)", labelAndEffectText, flags=re.DOTALL)
								if effectMatch:
									labelText = labelAndEffectText[:effectMatch.start()]
									effectText = labelAndEffectText[effectMatch.start():]
								else:
									labelText = ""
									effectText = ""
								nextLabelMatch = re.search("\n([AÀÈI] |I['’]M )?[A-ZÉÊÜ]{2}", effectText)
								if nextLabelMatch:
									labelAndEffectText = effectText[nextLabelMatch.start():].lstrip()
									effectText = effectText[:nextLabelMatch.start()].rstrip()
									self._logger.debug("Correcting effect text on new-style Enchanted card to ability label and text")
								else:
									labelAndEffectText = None
								result["abilityLabels"].append(ImageAndText(remainingTextImage, labelText))
								result["abilityTexts"].append(ImageAndText(remainingTextImage, effectText))

					if remainingText:
						result["remainingText"] = ImageAndText(remainingTextImage, remainingText)
						self._logger.debug(f"{remainingText=}")
				else:
					self._logger.debug("No remaining text found")
				self._logger.debug(f"Finding remaining text finished at {time.perf_counter() - startTime} seconds in")
			else:
				self._logger.debug(f"No text above ability labels, highest label is at y={previousBlockTopY}")

		self._logger.debug(f"Parsing image took {time.perf_counter() - startTime} seconds")
		if showImage:
			cv2.imshow("Card Image", cardImage)
			cv2.imshow("Greyscale card image", greyCardImage)
			cv2.imshow("Types threshold image", typesImage)
			cv2.imshow("Textbox crop greyscale", greyTextboxImage)
			if result.get("identifier", None) is not None:
				cv2.imshow("Card Identifier", result["identifier"].image)
			if textboxEdgeDetectedImage is not None:
				cv2.imshow("Textbox edge detected image", textboxEdgeDetectedImage)
			if textboxLinesImage is not None:
				cv2.imshow("Textbox with lines", textboxLinesImage)
			if flavorTextEdgeDetectedImage is not None:
				cv2.imshow("Flavortext edge detected greyscale image", flavorTextEdgeDetectedImage)
			if flavorTextGreyscaleImageWithLines is not None:
				cv2.imshow("Greyscale with lines drawn on top", flavorTextGreyscaleImageWithLines)
			if flavorTextLineDetectionCroppedImage is not None:
				cv2.imshow("Flavor Text Cropped Image From Ability Labels", flavorTextLineDetectionCroppedImage)
			if flavorTextImage is not None:
				cv2.imshow("Flavor Text Image", flavorTextImage)
			if result["abilityLabels"]:
				for index, abilityLabelEntry in enumerate(result["abilityLabels"]):
					cv2.imshow(f"Ability label image {index}", abilityLabelEntry.image)
			if result["abilityTexts"]:
				for index, abilityTextEntry in enumerate(result["abilityTexts"]):
					cv2.imshow(f"Ability text image {index}", abilityTextEntry.image)
			if abilityTextImage is not None:
				cv2.imshow("Ability text image", abilityTextImage)
			if remainingTextImage is not None:
				cv2.imshow("Remaining text image", remainingTextImage)
			cv2.imshow("Artist", result["artist"].image)
			if parseFully:
				cv2.imshow("Ink Cost", result["cost"].image)
				cv2.imshow("Card Name", result["name"].image)
				if result["moveCost"] is not None:
					cv2.imshow("Card Move Cost", result["moveCost"].image)
				if result["strength"] is not None:
					cv2.imshow("Card Strength", result["strength"].image)
				if result["version"] is not None:
					cv2.imshow("Card Subtitle", result["version"].image)
				if result["willpower"] is not None:
					cv2.imshow("Card Willpower", result["willpower"].image)
			cv2.waitKey(0)
			cv2.destroyAllWindows()
		# Done with parsing, build result object
		ocrResult = OcrResult([iat.text for iat in result["abilityLabels"]], [iat.text for iat in result["abilityTexts"]], result["artist"].text, result["flavorText"].text if result.get("flavorText", None) else None,
							  result["remainingText"].text if result.get("remainingText", None) else None, result["subtypesText"].text if result["subtypesText"] else None)
		# Identifier might be set by 'parseFully' or by a specific boolean
		if result.get("identifier", None):
			ocrResult.identifier = result["identifier"].text
		if parseFully:
			ocrResult.cost = result["cost"].text
			ocrResult.moveCost = result["moveCost"].text if result["moveCost"] else None
			ocrResult.name = result["name"].text
			ocrResult.strength = result["strength"].text if result["strength"] else None
			ocrResult.version = result["version"].text if result["version"] else None
			ocrResult.willpower = result["willpower"].text if result["willpower"] else None
		return ocrResult

	@staticmethod
	def _getSubImage(image, imageArea: ImageArea.ImageArea) -> cv2.Mat:
		return image[imageArea.coords.top:imageArea.coords.bottom, imageArea.coords.left:imageArea.coords.right]

	@staticmethod
	def _convertToThresholdImage(greyscaleImage, textColour: ImageArea.TextColour) -> cv2.Mat:
		threshold, thresholdImage = cv2.threshold(greyscaleImage, textColour.thresholdValue, 255, textColour.thresholdType)
		return thresholdImage

	@staticmethod
	def _cv2ImageToPillowImage(cv2Image: cv2.Mat) -> Image.Image:
		return Image.fromarray(cv2.cvtColor(cv2Image, cv2.COLOR_BGR2RGB))

	def _imageToString(self, image: cv2.Mat, isNumeric: bool = False, imageAreaName: str = None) -> str:
		# TesserOCR uses Pillow-format images, so convert our CV2-format image
		self._tesseractApi.SetImage(self._cv2ImageToPillowImage(image))
		result: str = self._tesseractApi.GetUTF8Text().rstrip("\n")
		if isNumeric and not result.isnumeric():
			# Forcing Tesseract to only recognise numbers for isNumeric often leads to empty results
			# Instead correct common mistaken numbers ourselves, if possible
			originalResult = result
			if result == "O":
				result = "0"
			elif result == "l" or result == "|" or result == "]":
				result = "1"
			elif result == "A":
				result = "4"
			elif result == "b":
				result = "6"
			elif result == "Q":
				result = "9"
			if originalResult == result:
				self._logger.error(f"Asked to find number in image area '{imageAreaName}' but found non-numeric result '{result}'")
				return "-1"
			else:
				self._logger.info(f"Corrected non-numeric result '{originalResult}' to '{result}' for image area '{imageAreaName}'")
		return result

	def _getSubImageAndText(self, cardImage: cv2.Mat, imageArea: ImageArea) -> ImageAndText:
		subImage = self._getSubImage(cardImage, imageArea)
		# Numeric reading is more sensitive, so convert to a clearer threshold image
		if imageArea.isNumeric or imageArea.textColour == ImageArea.TEXT_COLOUR_WHITE_LIGHT_BACKGROUND:
			subImage = self._convertToThresholdImage(subImage, imageArea.textColour)
		return ImageAndText(subImage, self._imageToString(subImage, imageArea.isNumeric, imageArea.keyName))

	@staticmethod
	def _isImageBlack(image: cv2.Mat) -> bool:
		"""
		Check whether the whole provided image is black. Useful for border checks, to determine image type
		:param image: The image to check. Should usually be a sub image of a card image
		:return: True if the image is entirely black, False otherwise
		"""
		for y in range(image.shape[0]):
			for x in range(image.shape[1]):
				pixel = image[y, x]
				if pixel[0] > 15 or pixel[1] > 15 or pixel[2] > 15:  # Use 15 instead of a strict 1 or 0 for some leeway
					# This pixel isn't entirely black
					return False
		return True

