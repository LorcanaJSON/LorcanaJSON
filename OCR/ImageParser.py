import logging, math, re, time
from collections import namedtuple
from typing import Dict, List, Union

import cv2, tesserocr
from PIL import Image

import GlobalConfig
from OCR import ImageArea
from util import LorcanaSymbols


ImageAndText = namedtuple("ImageAndText", ("image", "text"))

_ABILITY_LABEL_MARGIN: int = 12
_FLAVORTEXT_MARGIN: int = 14

_BLACK = (0, 0, 0)
_WHITE = (255, 255, 255)

class ImageParser():
	def __init__(self, forceGenericModel: bool = False):
		"""
		Creae an image parser
		:param forceGenericModel: If True, force the use of the generic Tesseract model for the language, even if a Lorcana-specific one exists. If False or not provided, uses the Lorcana model if available for the current language. Defaults to False
		"""
		self._logger = logging.getLogger("LorcanaJSON")
		if forceGenericModel or not GlobalConfig.language.hasLorcanaTesseractModel:
			modelName = GlobalConfig.language.threeLetterCode
		else:
			modelName = f"Lorcana_{GlobalConfig.language.code}"
		self.nonCharacterTypes = (GlobalConfig.translation.Action, GlobalConfig.translation.Item, GlobalConfig.translation.Location)
		self._tesseractApi = tesserocr.PyTessBaseAPI(lang=modelName, path=GlobalConfig.tesseractPath, psm=tesserocr.PSM.SINGLE_BLOCK)

	def getImageAndTextDataFromImage(self, pathToImage: str, parseFully: bool, includeIdentifier: bool = False, isLocation: bool = None, hasCardText: bool = None, hasFlavorText: bool = None,
									 isEnchanted: bool = None, isQuest: bool = None, useNewEnchanted: bool = False, showImage: bool = False) -> Dict[str, Union[None, ImageAndText, List[ImageAndText]]]:
		startTime = time.perf_counter()
		result: Dict[str, Union[None, ImageAndText, List[ImageAndText]]] = {
			"flavorText": None,
			"abilityLabels": [],
			"abilityTexts": [],
			"remainingText": None,
			"subtypesText": []
		}
		if parseFully:
			result.update({
				"artist": None,
				"cost": None,
				"identifier": None,
				"moveCost": None,
				"name": None,
				"strength": None,
				"version": None,
				"willpower": None
			})
		cardImage: cv2.Mat = cv2.imread(pathToImage)
		if cardImage is None:
			raise ValueError(f"Card image '{pathToImage}' could not be loaded, possibly because it doesn't exist")
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
		self._logger.debug(f"Reading {pathToImage=} finished at {time.perf_counter() - startTime} seconds in")

		# Parse card cost first, since that's always in the top left, regardless of whether the card should later be rotated
		if parseFully:
			result["cost"] = self._getSubImageAndText(cardImage, ImageArea.INK_COST)

		if isLocation is None:
			# Figure out whether this is a Location card or not. We need to do this as soon as possible, because Location cards need to be rotated
			# Location cards, both Enchanted and not Enchanted, have a thick black border at their bottom, so the right side of a non-rotated image, thicker than a non-Enchanted non-Location card. Check for that
			isLocation = self._isImageBlack(self._getSubImage(cardImage, ImageArea.IS_LOCATION_CHECK))

		if isLocation:
			# Location cards are horizontal, so the image should be rotated for proper OCR
			cardImage = cv2.rotate(cardImage, cv2.ROTATE_90_CLOCKWISE)
		greyCardImage: cv2.Mat = cv2.cvtColor(cardImage, cv2.COLOR_BGR2GRAY)

		if isEnchanted is None:
			isEnchanted = not self._isImageBlack(self._getSubImage(cardImage, ImageArea.IS_BORDERLESS_CHECK))
			#TODO Add way to determine whether this is old- or new-style Enchanted (from set 5 onward the Enchanted design changed)

		# First determine the card (sub)type
		if isEnchanted and useNewEnchanted:
			typesImageArea = ImageArea.NEW_ENCHANTED_LOCATION_TYPE if isLocation else ImageArea.NEW_ENCHANTED_TYPE
		elif isLocation:
			typesImageArea = ImageArea.LOCATION_TYPE
		else:
			typesImageArea = ImageArea.TYPE
		typesImage = self._getSubImage(greyCardImage, typesImageArea)
		typesImage = self._convertToThresholdImage(typesImage, typesImageArea.textColour)
		typesImageText = self._imageToString(typesImage).strip("\"'- ")
		self._logger.debug(f"Parsing types image finished at {time.perf_counter() - startTime} seconds in")
		if typesImageText not in self.nonCharacterTypes:
			# The type separator character is always the same, but often gets interpreted wrong; fix that
			if " " in typesImageText:
				typesImageText = re.sub(r" (\S )?", f" {LorcanaSymbols.SEPARATOR} ", typesImageText)
			result["subtypesText"] = ImageAndText(typesImage, typesImageText)
			self._logger.debug(f"{typesImageText=}")
			isCharacter = not isLocation and typesImageText not in self.nonCharacterTypes and typesImageText.split(" ", 1)[0] not in self.nonCharacterTypes
		else:
			isCharacter = False
			self._logger.debug(f"Subtype is main type ({typesImageText=}), so not storing as subtypes")

		result["artist"] = self._getSubImageAndText(greyCardImage, ImageArea.LOCATION_ARTIST if isLocation else ImageArea.ARTIST)
		if parseFully or includeIdentifier or isQuest is None:
			result["identifier"] = self._getSubImageAndText(greyCardImage, ImageArea.LOCATION_IDENTIFIER if isLocation else ImageArea.CARD_IDENTIFIER)
			if isQuest is None:
				lastIdentifierPart = result["identifier"].text.rsplit(" ", 1)[1]
				isQuest = lastIdentifierPart.startswith("Q") or lastIdentifierPart.startswith("0")  # Also check for '0' because the 'Q' sometimes gets misread
		if parseFully:
			# Parse from top to bottom
			if isCharacter:
				result["name"] = self._getSubImageAndText(greyCardImage, ImageArea.CHARACTER_NAME)
				result["version"] = self._getSubImageAndText(greyCardImage, ImageArea.CHARACTER_VERSION)
				result["strength"] = self._getSubImageAndText(greyCardImage, ImageArea.STRENGTH)
				result["willpower"] = self._getSubImageAndText(greyCardImage, ImageArea.WILLPOWER)
			elif isLocation:
				result["name"] = self._getSubImageAndText(greyCardImage, ImageArea.LOCATION_NAME)
				result["version"] = self._getSubImageAndText(greyCardImage, ImageArea.LOCATION_VERSION)
				result["moveCost"] = self._getSubImageAndText(greyCardImage, ImageArea.LOCATION_MOVE_COST)
				result["willpower"] = self._getSubImageAndText(greyCardImage, ImageArea.LOCATION_WILLPOWER)
			else:
				result["name"] = self._getSubImageAndText(greyCardImage, ImageArea.CARD_NAME)

		# Determine the textbox area, which is different between characters and non-characters, and between enchanted and non-enchanted characters
		if isQuest:
			textBoxImageArea = ImageArea.QUEST_TEXTBOX if isCharacter else ImageArea.QUEST_FULL_WIDTH_TEXT_BOX
		elif isCharacter:
			if isEnchanted:
				textBoxImageArea = ImageArea.NEW_ENCHANTED_CHARACTER_TEXT_BOX if useNewEnchanted else ImageArea.ENCHANTED_CHARACTER_TEXT_BOX
			else:
				textBoxImageArea = ImageArea.CHARACTER_TEXT_BOX
		elif isLocation:
			if isEnchanted:
				textBoxImageArea = ImageArea.NEW_ENCHANTED_LOCATION_TEXT_BOX if useNewEnchanted else ImageArea.ENCHANTED_LOCATION_TEXT_BOX
			else:
				textBoxImageArea = ImageArea.LOCATION_TEXTBOX
		else:
			if isEnchanted:
				textBoxImageArea = ImageArea.NEW_ENCHANTED_FULL_WIDTH_TEXT_BOX if useNewEnchanted else ImageArea.ENCHANTED_FULL_WIDTH_TEXT_BOX
			else:
				textBoxImageArea = ImageArea.FULL_WIDTH_TEXT_BOX

		# Greyscale images work better, so get one from just the textbox
		greyTextboxImage = self._getSubImage(greyCardImage, textBoxImageArea)
		colorTextboxImage = self._getSubImage(cardImage, textBoxImageArea) if isQuest else None
		textboxWidth = greyTextboxImage.shape[1]
		textboxHeight = greyTextboxImage.shape[0]

		# First get the ability label coordinates, so we know where we can find the flavor text separator
		# Then get the flavor text separator and the flavor text itself
		# Finally get the ability text, since that goes between the labels and the flavor text

		# Find where the ability name labels are, store them as the top y, bottom y and the right x, so we know where to get the text from
		labelCoords = []
		if hasCardText is not False and (not isEnchanted or not useNewEnchanted):
			isCurrentlyInLabel: bool = False
			currentCoords = [0, 0, 0]
			textBoxImageToCheck = colorTextboxImage if isQuest else greyTextboxImage
			for y in range(textboxHeight):
				pixelValue = textBoxImageToCheck[y, 0]
				if isCurrentlyInLabel:
					# Check if the pixel got lighter, indicating we left the label block
					if (isQuest and pixelValue[0] > 60 and pixelValue[1] > 35) or (not isQuest and pixelValue > 100):
						isCurrentlyInLabel = False
						if y - currentCoords[0] < 50:
							self._logger.debug(f"Skipping possible label starting at y={currentCoords[0]} and ending at {y=}, not high enough to be a label")
						else:
							currentCoords[1] = y - 1
							labelCoords.append(tuple(currentCoords))  # Copy the coordinates list so we can't accidentally change a value anymore
				# Check if a label started here
				elif (isQuest and 42 < pixelValue[0] < 54 and 22 < pixelValue[1] < 32) or (not isQuest and pixelValue < 100):
					isCurrentlyInLabel = True
					currentCoords[0] = y
					yToCheck = min(textboxHeight - 1, y + 1)  # Check a few lines down to prevent weirdness with the edge of the label box
					# Find the width of the label. Since accented characters can reach the top of the label, we need several light pixels in succession to be sure the label ended
					successiveLightPixels: int = 0
					for x in range(textboxWidth):
						checkValue = textBoxImageToCheck[yToCheck, x]
						if (isQuest and checkValue[0] > 60 and checkValue[1] > 35) or (not isQuest and checkValue > 120):
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
				self._logger.warning(f"Still in label when end of label check reached in card image '{pathToImage}'")
		self._logger.debug(f"Finished finding label coords at {time.perf_counter() - startTime} seconds in")

		thresholdTextColor = ImageArea.TEXT_COLOUR_WHITE if isQuest else ImageArea.TEXT_COLOUR_BLACK

		# Find the line dividing the abilities from the flavor text, if needed
		flavorTextImage = None
		flavorTextSeparatorY = textboxHeight
		flavorTextLineDetectionCroppedImage = None
		flavorTextEdgeDetectedImage = None
		flavorTextGreyscaleImageWithLines = None
		if hasFlavorText is not False and (not isEnchanted or not useNewEnchanted):
			flavorTextImageTop = 0
			flavorTextLineDetectionCroppedImage = greyTextboxImage
			if labelCoords:
				flavorTextImageTop = labelCoords[-1][1] + 5
				flavorTextLineDetectionCroppedImage = greyTextboxImage[flavorTextImageTop:textboxHeight, 0:textboxWidth]
			flavorTextEdgeDetectedImage = cv2.Canny(flavorTextLineDetectionCroppedImage, 50, 200)
			lines = cv2.HoughLinesP(flavorTextEdgeDetectedImage, 1, math.pi / 180, 150, minLineLength=70)
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
						cv2.line(flavorTextGreyscaleImageWithLines, (line[0][0], line[0][1]), (line[0][2], line[0][3]), (0, 0, 255), 3, cv2.LINE_AA)
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
						self._logger.warning(f"Flavortext separator Y {flavorTextSeparatorY} plus margin {_FLAVORTEXT_MARGIN} is larger than textbox height {textboxHeight}")
						hasFlavorText = False
					else:
						flavorTextImage = self._convertToThresholdImage(greyTextboxImage[flavorTextSeparatorY + _FLAVORTEXT_MARGIN:textboxHeight, 0:textboxWidth], thresholdTextColor)
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
				abilityLabelImage = self._convertToThresholdImage(greyTextboxImage[labelCoord[0]:labelCoord[1], 0:labelCoord[2]], ImageArea.TEXT_COLOUR_WHITE)
				abilityLabelText = self._imageToString(abilityLabelImage)
				result["abilityLabels"].append(ImageAndText(abilityLabelImage, abilityLabelText))
				# Then get the ability text
				# Put a white rectangle over where the label was, because the thresholding sometimes leaves behind some pixels, which confuses Tesseract, leading to phantom letters
				abilityTextImage = greyTextboxImage.copy()
				labelMaskColor = _BLACK if textBoxImageArea.textColour == ImageArea.TEXT_COLOUR_WHITE else _WHITE
				cv2.rectangle(abilityTextImage, (0, 0), (labelCoord[2] + _ABILITY_LABEL_MARGIN, labelCoord[1]), labelMaskColor, thickness=-1)  # -1 thickness fills the rectangle
				abilityTextImage = self._convertToThresholdImage(abilityTextImage[labelCoord[0]:previousBlockTopY, 0:textboxWidth], thresholdTextColor)
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
				remainingTextImage = self._convertToThresholdImage(greyTextboxImage[0:previousBlockTopY, 0:textboxWidth], thresholdTextColor)
				if isEnchanted and useNewEnchanted:
					# New-style Enchanted cards have white text with a dark outline, which confuses Tesseract. Making the whole background black vastly improves accuracy
					remainingTextImage = cv2.floodFill(remainingTextImage, None, (0, 0), (0,))[1]
				remainingText = self._imageToString(remainingTextImage)
				if remainingText:
					if isEnchanted and useNewEnchanted and re.search("[A-Z]{2,}", remainingText):
						# Detecting labels on new-style Enchanted cards is hard, so for those the full card text is 'remainingText'
						# Try to get the labels and effects out
						labelMatch = re.search("([AI] )?[A-Z]{2}", remainingText)
						if labelMatch:
							labelAndEffectText = remainingText[labelMatch.start():]
							remainingText = remainingText[:labelMatch.start()].rstrip()
							while labelAndEffectText:
								effectMatch = re.search(r"\b[A-Z][a-z]", labelAndEffectText, flags=re.DOTALL)
								labelText = labelAndEffectText[:effectMatch.start()]
								effectText = labelAndEffectText[effectMatch.start():]
								nextLabelMatch = re.search("([AI] )?[A-Z]{2}", effectText)
								if nextLabelMatch:
									labelAndEffectText = effectText[nextLabelMatch.start():]
									effectText = effectText[:nextLabelMatch.start()].rstrip()
									self._logger.info("Correcting effect text on new-style Enchanted card to ability label and text")
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
			if colorTextboxImage is not None:
				cv2.imshow("Textbox crop color", colorTextboxImage)
			if result.get("identifier", None) is not None:
				cv2.imshow("Card Identifier", result["identifier"].image)
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
			if parseFully:
				cv2.imshow("Artist", result["artist"].image)
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
		# Done!
		return result

	@staticmethod
	def _getSubImage(image, imageArea: ImageArea.ImageArea):
		return image[imageArea.coords.top:imageArea.coords.bottom, imageArea.coords.left:imageArea.coords.right]

	@staticmethod
	def _convertToThresholdImage(greyscaleImage, textColour: ImageArea.TextColour):
		threshold, thresholdImage = cv2.threshold(greyscaleImage, textColour.thresholdValue, 255, textColour.thresholdType)
		return thresholdImage

	@staticmethod
	def _cv2ImageToPillowImage(cv2Image) -> Image.Image:
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
			elif result == "l" or result == "|":
				result = "1"
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
		else:
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

