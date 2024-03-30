import logging, math, time
import re
from collections import namedtuple
from typing import Dict, List, Union

import cv2, tesserocr
from PIL import Image

import GlobalConfig
from OCR import ImageArea


EXERT_UNICODE = "⟳"  # Unicode \u27F3   HTML entities &#10227;  &#x27F3;
INK_UNICODE = "⬡"  # Unicode \u2B21  HTML entities &#11041;  &#x2B21;
LORE_UNICODE = "◊"  # Unicode \u25CA  HTML entities &#9674;  &#x25CA;  &loz;
STRENGTH_UNICODE = "¤"  # Unicode \u00A4  HTML entities &#164;  &#xA4;  &curren;
WILLPOWER_UNICODE = "⛉"  # Unicode \u26C9  HTML entities: &#9929;  &#x26C9;
SEPARATOR_UNICODE = "•"  # Unicode \u2022 HTML entities &#8226; &bull;

ImageAndText = namedtuple("ImageAndText", ("image", "text"))

_EFFECT_LABEL_MARGIN: int = 12

class ImageParser():
	def __init__(self, useLorcanaModel: bool = True):
		"""
		Creae an image parser
		:param useLorcanaModel: If True, a Lorcana-specific model will be used. If False, the generic model for the language will be used. Defaults to True
		"""
		self._logger = logging.getLogger("LorcanaJSON")
		if useLorcanaModel:
			modelName = f"Lorcana_{GlobalConfig.language.code}"
		else:
			modelName = GlobalConfig.language.threeLetterCode
		self._tesseractApi = tesserocr.PyTessBaseAPI(lang=modelName, path=GlobalConfig.tesseractPath, psm=tesserocr.PSM.SINGLE_BLOCK)

	def getImageAndTextDataFromImage(self, pathToImage: str, parseFully: bool, includeIdentifier: bool = False, isLocation: bool = None, hasCardText: bool = None, hasFlavorText: bool = None,
									 isEnchanted: bool = None, showImage: bool = False) -> Dict[str, Union[None, ImageAndText, List[ImageAndText]]]:
		startTime = time.perf_counter()
		result: Dict[str, Union[None, ImageAndText, List[ImageAndText]]] = {
			"flavorText": None,
			"effectLabels": [],
			"effectTexts": [],
			"remainingText": None,
			"subtypesText": []
		}
		if parseFully:
			result.update({
				"artist": None,
				"baseName": None,
				"cost": None,
				"identifier": None,
				"moveCost": None,
				"strength": None,
				"subtitle": None,
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

		# First determine the card (sub)type
		typesImage = self._getSubImage(greyCardImage, ImageArea.LOCATION_TYPE if isLocation else ImageArea.TYPE)
		typesImage = self._convertToThresholdImage(typesImage, ImageArea.TYPE.textColour)
		typesImageText = self._imageToString(typesImage).strip("\"'")
		self._logger.debug(f"Parsing types image finished at {time.perf_counter() - startTime} seconds in")
		if typesImageText not in ("Action", "Item", "Location"):
			# The type separator character is always the same, but often gets interpreted wrong; fix that
			if " " in typesImageText:
				typesImageText = re.sub(r" (\S )?", f" {SEPARATOR_UNICODE} ", typesImageText)
			result["subtypesText"] = ImageAndText(typesImage, typesImageText)
			self._logger.debug(f"{typesImageText=}")
			isCharacter = not isLocation and not typesImageText.startswith("Action") and not typesImageText.startswith("Item") and not typesImageText.startswith("Location")
		else:
			isCharacter = False
			self._logger.debug(f"Subtype is main type ({typesImageText=}, so not storing as subtypes")

		if isEnchanted is None:
			isEnchanted = not self._isImageBlack(self._getSubImage(cardImage, ImageArea.IS_BORDERLESS_CHECK))

		if parseFully or includeIdentifier:
			result["identifier"] = self._getSubImageAndText(greyCardImage, ImageArea.LOCATION_IDENTIFIER if isLocation else ImageArea.CARD_IDENTIFIER)
		if parseFully:
			# Parse from top to bottom
			if isCharacter:
				result["baseName"] = self._getSubImageAndText(greyCardImage, ImageArea.CHARACTER_NAME)
				result["subtitle"] = self._getSubImageAndText(greyCardImage, ImageArea.CHARACTER_SUBTITLE)
				result["strength"] = self._getSubImageAndText(greyCardImage, ImageArea.STRENGTH)
				result["willpower"] = self._getSubImageAndText(greyCardImage, ImageArea.WILLPOWER)
			elif isLocation:
				result["baseName"] = self._getSubImageAndText(greyCardImage, ImageArea.LOCATION_NAME)
				result["subtitle"] = self._getSubImageAndText(greyCardImage, ImageArea.LOCATION_SUBTITLE)
				result["moveCost"] = self._getSubImageAndText(greyCardImage, ImageArea.LOCATION_MOVE_COST)
				result["willpower"] = self._getSubImageAndText(greyCardImage, ImageArea.LOCATION_WILLPOWER)
			else:
				result["baseName"] = self._getSubImageAndText(greyCardImage, ImageArea.CARD_NAME)
			result["artist"] = self._getSubImageAndText(greyCardImage, ImageArea.LOCATION_ARTIST if isLocation else ImageArea.ARTIST)

		# Determine the textbox area, which is different between characters and non-characters, and between enchanted and non-enchanted characters
		textBoxImageArea = ImageArea.ENCHANTED_FULL_WIDTH_TEXT_BOX if isEnchanted else ImageArea.FULL_WIDTH_TEXT_BOX
		if isCharacter:
			textBoxImageArea = ImageArea.ENCHANTED_CHARACTER_TEXT_BOX if isEnchanted else ImageArea.CHARACTER_TEXT_BOX
		elif isLocation:
			textBoxImageArea = ImageArea.ENCHANTED_LOCATION_TEXT_BOX if isEnchanted else ImageArea.LOCATION_TEXTBOX

		# Greyscale images work better, so get one from just the textbox
		greyTextboxImage = self._getSubImage(greyCardImage, textBoxImageArea)
		textboxWidth = greyTextboxImage.shape[1]
		textboxHeight = greyTextboxImage.shape[0]

		# First get the effect label coordinates, so we know where we can find the flavor text separator
		# Then get the flavor text separator and the flavor text itself
		# Finally get the effect text, since that goes between the labels and the flavor text

		# Find where the effect name labels are, store them as the top y, bottom y and the right x, so we know where to get the text from
		labelCoords = []
		if hasCardText is not False:
			isCurrentlyInLabel: bool = False
			currentCoords = [0, 0, 0]
			for y in range(5, textboxHeight):
				pixelValue = greyTextboxImage[y, 0]
				if isCurrentlyInLabel:
					# Check if the pixel got lighter, indicating we left the label block
					if pixelValue > 100:
						isCurrentlyInLabel = False
						currentCoords[1] = y - 1
						labelCoords.append(tuple(currentCoords))  # Copy the coordinates list so we can't accidentally change a value anymore
				# Check if a label started here
				elif pixelValue < 100:
					isCurrentlyInLabel = True
					currentCoords[0] = y
					yToCheck = min(textboxHeight - 1, y + 2)  # Check a few lines down to prevent weirdness with the edge of the label box
					# Find the width of the label
					for x in range(textboxWidth):
						if greyTextboxImage[yToCheck, x] > 125:
							if x < 100:
								self._logger.debug(f"Skipping label at {currentCoords=} and {x=}, not wide enough to be a label")
								currentCoords[0] = 0
								currentCoords[1] = 0
								isCurrentlyInLabel = False
							else:
								currentCoords[2] = x - _EFFECT_LABEL_MARGIN
							break
					else:
						raise ValueError(f"Unable to find right side of label at {y=} in the cropped image")
			if isCurrentlyInLabel:
				self._logger.warning(f"Still in label when end of label check reached in card image '{pathToImage}'")
		self._logger.debug(f"Finished finding label coords at {time.perf_counter() - startTime} seconds in")

		# Find the line dividing the abilities from the flavor text, if needed
		flavorTextImage = None
		flavorTextStartY = textboxHeight
		flavorTextLineDetectionCroppedImage = None
		flavorTextEdgeDetectedImage = None
		flavorTextGreyscaleImageWithLines = None
		if hasFlavorText is not False:
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
				self._logger.debug("No flavour text separator found")
			else:
				self._logger.debug(f"{len(lines):,} lines found: {repr(lines)}")
				flavorTextStartY = 0
				for line in lines:
					if line[0][0] < 80 or line[0][1] < 25:
						# Too far to the left or to the top, probably a mistaken effect label
						self._logger.debug(f"Skipping line at {line[0]}, too close to the edge, probably a mistake")
						continue
					self._logger.debug(f"line length: {line[0][2] - line[0][0]}")
					# Draw the lines for debug purposes
					if showImage:
						cv2.line(flavorTextGreyscaleImageWithLines, (line[0][0], line[0][1]), (line[0][2], line[0][3]), (0, 0, 255), 3, cv2.LINE_AA)
					if line[0][1] > flavorTextStartY:
						flavorTextStartY = line[0][1]
				if flavorTextStartY == 0:
					# No suitable line found, so probably no flavor text section
					self._logger.debug("No flavor text separator line found")
					flavorTextStartY = textboxHeight
				else:
					flavorTextStartY += flavorTextImageTop
					flavorTextImage = self._convertToThresholdImage(greyTextboxImage[flavorTextStartY:textboxHeight, 0:textboxWidth], ImageArea.TEXT_COLOUR_BLACK)
					flavourText = self._imageToString(flavorTextImage)
					result["flavorText"] = ImageAndText(flavorTextImage, flavourText)
					self._logger.debug(f"{flavourText=}")
				self._logger.debug(f"Finding flavor text finished at {time.perf_counter() - startTime} seconds in")

		#Find the card text, one block at the time, separated by the effect label
		# We have to go from bottom to top, because non-labelled text is above labelled text
		effectLabelImage = None
		effectTextImage = None
		remainingTextImage = None
		if hasCardText is not False:
			labelCoords.reverse()
			previousBlockTopY = flavorTextStartY
			labelNumber = len(labelCoords)
			for labelCoord in labelCoords:
				# First get the label text itself. It's white on dark, so handle it the opposite way from the actual effect text
				effectLabelImage = self._convertToThresholdImage(greyTextboxImage[labelCoord[0]:labelCoord[1], 0:labelCoord[2]], ImageArea.TEXT_COLOUR_WHITE)
				effectLabelText = self._imageToString(effectLabelImage)
				result["effectLabels"].append(ImageAndText(effectLabelImage, effectLabelText))
				# Then get the effect text
				# Put a white rectangle over where the label was, because the thresholding sometimes leaves behind some pixels, which confuses Tesseract, leading to phantom letters
				effectTextImage = greyTextboxImage.copy()
				cv2.rectangle(effectTextImage, (0, 0), (labelCoord[2] + _EFFECT_LABEL_MARGIN, labelCoord[1]), (255, 255, 255), thickness=-1)  # -1 thickness fills the rectangle
				effectTextImage = self._convertToThresholdImage(effectTextImage[labelCoord[0]:previousBlockTopY, 0:textboxWidth], ImageArea.TEXT_COLOUR_BLACK)
				effectText = self._imageToString(effectTextImage)
				result["effectTexts"].append(ImageAndText(effectTextImage, effectText))
				self._logger.debug(f"{effectLabelText=} ({labelCoord[1] - labelCoord[0]} px high), {effectText=}")
				previousBlockTopY = labelCoord[0]
				labelNumber -= 1
			self._logger.debug(f"{len(labelCoords)} {labelCoords=}")
			self._logger.debug(f"Finding effects finished at {time.perf_counter() - startTime} seconds in")
			# Order the labels from top to bottom
			result["effectLabels"].reverse()
			result["effectTexts"].reverse()

			# There might be text above the label coordinates too (abilities text), especially if there aren't any labels. Get that text as well
			if previousBlockTopY > 35:
				remainingTextImage = self._convertToThresholdImage(greyTextboxImage[0:previousBlockTopY, 0:textboxWidth], ImageArea.TEXT_COLOUR_BLACK)
				remainingText = self._imageToString(remainingTextImage)
				if remainingText:
					result["remainingText"] = ImageAndText(remainingTextImage, remainingText)
					self._logger.debug(f"{remainingText=}")
				else:
					self._logger.debug("No remaining text found")
				self._logger.debug(f"Finding remaining text finished at {time.perf_counter() - startTime} seconds in")
			else:
				self._logger.debug(f"No text above effect labels, highest label is at y={previousBlockTopY}")

		self._logger.debug(f"Parsing image took {time.perf_counter() - startTime} seconds")
		if showImage:
			cv2.imshow("Card Image", cardImage)
			cv2.imshow("Greyscale card image", greyCardImage)
			cv2.imshow("Types threshold image", typesImage)
			cv2.imshow("Textbox crop greyscale", greyTextboxImage)
			if result.get("identifier", None) is not None:
				cv2.imshow("Card Identifier", result["identifier"].image)
			if flavorTextEdgeDetectedImage is not None:
				cv2.imshow("Flavortext edge detected greyscale image", flavorTextEdgeDetectedImage)
			if flavorTextGreyscaleImageWithLines is not None:
				cv2.imshow("Greyscale with lines drawn on top", flavorTextGreyscaleImageWithLines)
			if flavorTextLineDetectionCroppedImage is not None:
				cv2.imshow("Flavor Text Cropped Image From Effect Labels", flavorTextLineDetectionCroppedImage)
			if flavorTextImage is not None:
				cv2.imshow("Flavor Text Image", flavorTextImage)
			if effectLabelImage is not None:
				cv2.imshow("Effect label image", effectLabelImage)
			if effectTextImage is not None:
				cv2.imshow("Effect text image", effectTextImage)
			if remainingTextImage is not None:
				cv2.imshow("Remaining text image", remainingTextImage)
			if parseFully:
				cv2.imshow("Artist", result["artist"].image)
				cv2.imshow("Ink Cost", result["cost"].image)
				cv2.imshow("Card Name", result["baseName"].image)
				if result["subtitle"] is not None:
					cv2.imshow("Card Subtitle", result["subtitle"].image)
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

	def _imageToString(self, image: cv2.Mat, isNumeric: bool = False) -> str:
		self._tesseractApi.SetVariable("tessedit_char_whitelist", "0123456789" if isNumeric else "")
		# TesserOCR uses Pillow-format images, so convert our CV2-format image
		self._tesseractApi.SetImage(self._cv2ImageToPillowImage(image))
		return self._tesseractApi.GetUTF8Text().rstrip("\n")
		# return tesserocr.image_to_text(self._cv2ImageToPillowImage(image), lang="Lorcana_en", path=r"D:\Programs\Tesseract-OCR\tessdata", psm=tesserocr.PSM.SINGLE_BLOCK).rstrip("\n")

	def _getSubImageAndText(self, cardImage: cv2.Mat, imageArea: ImageArea) -> ImageAndText:
		subImage = self._getSubImage(cardImage, imageArea)
		# Numeric reading is more sensitive, so convert to a clearer threshold image
		if imageArea.isNumeric:
			subImage = self._convertToThresholdImage(subImage, imageArea.textColour)
		return ImageAndText(subImage, self._imageToString(subImage, imageArea.isNumeric))

	@staticmethod
	def _isImageBlack(image: cv2.Mat) -> bool:
		"""
		Check whether the whole provided image is black. Useful for border checks, to determine image type
		:param image: The image to check. Should usually be a sub image of a card image
		:return: True if the image is entirely black, False otherwise
		"""
		for y in range(image.shape[0]):
			for x in range(image.shape[1]):
				if sum(image[y, x]) > 10:  # Use 10 instead of a strict 1 or 0 for some leeway
					# This pixel isn't entirely black
					return False
		return True

