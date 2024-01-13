import logging, math, os, time
from collections import namedtuple
from typing import Dict, List, Union

import cv2, tesserocr
from PIL import Image

import Language
from OCR import ImageArea


EXERT_UNICODE = "⟳"  # Unicode \u27F3   HTML entities &#10227;  &#x27F3;
INK_UNICODE = "⬡"  # Unicode \u2B21  HTML entities &#11041;  &#x2B21;
LORE_UNICODE = "◊"  # Unicode \u25CA  HTML entities &#9674;  &#x25CA;  &loz;
STRENGTH_UNICODE = "¤"  # Unicode \u00A4  HTML entities &#164;  &#xA4;  &curren;

ImageAndText = namedtuple("ImageAndText", ("image", "text"))

_logger = logging.getLogger("LorcanaJSON")
_tesseractApi: tesserocr.PyTessBaseAPI = None

def initialize(language: Language.Language, useLorcanaModel: bool = True, tesseractPath: str = None):
	"""
	Set which language model and path Tesseract will use
	:param language: The Language instance to use
	:param useLorcanaModel: If True, a Lorcana-specific model will be used. If False, the generic model for the language will be used. Defaults to True
	:param tesseractPath: The optional path where Tesseract is installed, needed when Tesseract can't be found by default
	"""
	if useLorcanaModel:
		modelName = f"Lorcana_{language.code}"
	else:
		modelName = language.threeLetterCode
	global _tesseractApi
	_tesseractApi = tesserocr.PyTessBaseAPI(lang=modelName, path=tesseractPath, psm=tesserocr.PSM.SINGLE_BLOCK)

def getImageAndTextDataFromImage(pathToImage: str, hasCardText: bool = None, hasFlavorText: bool = None, isEnchanted: bool = None, showImage: bool = False) -> Dict[str, Union[None, ImageAndText, List[ImageAndText]]]:
	startTime = time.perf_counter()
	result = {
		"flavorText": None,
		"effectLabels": [],
		"effectTexts": [],
		"remainingText": None,
		"subtypesText": []
	}
	cardImage: cv2.Mat = cv2.imread(pathToImage)
	_logger.debug(f"Reading finished at {time.perf_counter() - startTime} seconds in")
	imageBaseName = os.path.basename(pathToImage)
	_logger.debug(f"Parsing {pathToImage=}; {imageBaseName=}")
	if cardImage is None:
		raise ValueError(f"Card image '{pathToImage}' could not be loaded, possibly because it doesn't exist")

	# First determine the card (sub)type
	typesImage = cv2.cvtColor(_getSubImage(cardImage, ImageArea.TYPE), cv2.COLOR_BGR2RGB)
	typesImage = _convertToThresholdImage(typesImage, ImageArea.TYPE.textColour)
	typesImageText = _imageToString(typesImage)
	_logger.debug(f"Parsing types image finished at {time.perf_counter() - startTime} seconds in")
	if typesImageText != "Action" and typesImageText != "Item":
		result["subtypesText"] = ImageAndText(typesImage, typesImageText)
		_logger.debug(f"{typesImageText=}")
	else:
		_logger.debug(f"Subtype is main type ({typesImageText=}, so not storing as subtypes")

	if isEnchanted is None:
		borderSubImage = _getSubImage(cardImage, ImageArea.IS_BORDERLESS_CHECK)
		# Check if the whole border area is entirely black
		for y in range(borderSubImage.shape[0]):
			for x in range(borderSubImage.shape[1]):
				if sum(borderSubImage[y, x]) > 10:  # Use 10 instead of a strict 1 or 0 for some leeway
					# Border isn't entirely black, so assume it's an Enchanted card
					isEnchanted = True
					break
			if isEnchanted is not None:
				break
		if isEnchanted is None:
			isEnchanted = False
		del borderSubImage

	# Determine the textbox area, which is different between characters and non-characters, and between enchanted and non-enchanted characters
	textBoxImageArea = ImageArea.FULL_WIDTH_TEXT_BOX
	if isEnchanted:
		textBoxImageArea = ImageArea.ENCHANTED_CHARACTER_TEXT_BOX
	elif not typesImageText.startswith("Action") and not typesImageText.startswith("Item"):
		textBoxImageArea = ImageArea.CHARACTER_TEXT_BOX

	# Greyscale images work better, so get one from just the textbox
	croppedImage = _getSubImage(cardImage, textBoxImageArea)
	imageWidth = croppedImage.shape[1]
	imageHeight = croppedImage.shape[0]
	greyscaleImage = cv2.cvtColor(croppedImage, cv2.COLOR_BGR2GRAY)

	# First get the effect label coordinates, so we know where we can find the flavor text separator
	# Then get the flavor text separator and the flavor text itself
	# Finally get the effect text, since that goes between the labels and the flavor text

	# Find where the effect name labels are, store them as the top y, bottom y and the right x, so we know where to get the text from
	labelCoords = []
	if hasCardText is not False:
		isCurrentlyInLabel: bool = False
		currentCoords = [0, 0, 0]
		for y in range(5, imageHeight):
			pixelValue = greyscaleImage[y, 0]
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
				# Find the width of the label
				for x in range(imageWidth):
					if greyscaleImage[y, x] > 100:
						if x < 100:
							_logger.debug(f"Skipping label at {currentCoords=} and {x=}, not wide enough to be a label")
							currentCoords[0] = 0
							currentCoords[1] = 0
							isCurrentlyInLabel = False
						else:
							currentCoords[2] = x
						break
				else:
					raise ValueError(f"Unable to find right side of label at {y=} in the cropped image")
		if isCurrentlyInLabel:
			_logger.warning("Still in label when end of label check reached")
	_logger.debug(f"Finished finding label coords at {time.perf_counter() - startTime} seconds in")

	# Find the line dividing the abilities from the flavor text, if needed
	flavorTextImage = None
	flavorTextStartY = imageHeight
	flavorTextLineDetectionCroppedImage = None
	edgeDetectedImage = None
	greyscaleImageWithLines = None
	if hasFlavorText is not False:
		flavorTextImageTop = 0
		flavorTextLineDetectionCroppedImage = greyscaleImage
		if labelCoords:
			flavorTextImageTop = labelCoords[-1][1] + 5
			flavorTextLineDetectionCroppedImage = greyscaleImage[flavorTextImageTop:imageHeight, 0:imageWidth]
		edgeDetectedImage = cv2.Canny(flavorTextLineDetectionCroppedImage, 50, 200)
		lines = cv2.HoughLinesP(edgeDetectedImage, 1, math.pi / 180, 150, minLineLength=100)
		greyscaleImageWithLines = flavorTextLineDetectionCroppedImage.copy() if showImage else None
		_logger.debug(f"Parsing flavor text images finished at {time.perf_counter() - startTime} seconds in")
		if lines is None:
			_logger.debug("No flavour text separator found")
		else:
			_logger.debug(f"{len(lines):,} lines found: {repr(lines)}")
			flavorTextStartY = 0
			for line in lines:
				if line[0][0] < 80 or line[0][1] < 25:
					# Too far to the left or to the top, probably a mistaken effect label
					_logger.debug(f"Skipping line at {line[0]}, too close to the edge, probably a mistake")
					continue
				_logger.debug(f"line length: {line[0][2] - line[0][0]}")
				# Draw the lines for debug purposes
				if showImage:
					cv2.line(greyscaleImageWithLines, (line[0][0], line[0][1]), (line[0][2], line[0][3]), (0, 0, 255), 3, cv2.LINE_AA)
				if line[0][1] > flavorTextStartY:
					flavorTextStartY = line[0][1]
			if flavorTextStartY == 0:
				# No suitable line found, so probably no flavor text section
				_logger.debug("No flavor text separator line found")
				flavorTextStartY = imageHeight
			else:
				flavorTextStartY += flavorTextImageTop
				flavorTextImage = _convertToThresholdImage(greyscaleImage[flavorTextStartY:imageHeight, 0:imageWidth], ImageArea.TEXT_COLOUR_BLACK)
				flavourText = _imageToString(flavorTextImage)
				result["flavorText"] = ImageAndText(flavorTextImage, flavourText)
				_logger.debug(f"{flavourText=}")
			_logger.debug(f"Finding flavor text finished at {time.perf_counter() - startTime} seconds in")

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
			effectLabelImage = _convertToThresholdImage(greyscaleImage[labelCoord[0]:labelCoord[1], 0:labelCoord[2]], ImageArea.TEXT_COLOUR_WHITE)
			effectLabelText = _imageToString(effectLabelImage)
			result["effectLabels"].append(ImageAndText(effectLabelImage, effectLabelText))
			# Then get the effect text
			# Put a white rectangle over where the label was, because the thresholding sometimes leaves behind some pixels, which confuses Tesseract, leading to phantom letters
			effectTextImage = greyscaleImage.copy()
			cv2.rectangle(effectTextImage, (0, 0), (labelCoord[2], labelCoord[1]), (255, 255, 255), thickness=-1)  # -1 thickness fills the rectangle
			effectTextImage = _convertToThresholdImage(effectTextImage[labelCoord[0]:previousBlockTopY, 0:imageWidth], ImageArea.TEXT_COLOUR_BLACK)
			effectText = _imageToString(effectTextImage)
			result["effectTexts"].append(ImageAndText(effectTextImage, effectText))
			_logger.debug(f"{effectLabelText=} ({labelCoord[1] - labelCoord[0]} px high), {effectText=}")
			previousBlockTopY = labelCoord[0]
			labelNumber -= 1
		_logger.debug(f"{len(labelCoords)} {labelCoords=}")
		_logger.debug(f"Finding effects finished at {time.perf_counter() - startTime} seconds in")
		# Order the labels from top to bottom
		result["effectLabels"].reverse()
		result["effectTexts"].reverse()

		# There might be text above the label coordinates too (abilities text), especially if there aren't any labels. Get that text as well
		if previousBlockTopY > 35:
			remainingTextImage = _convertToThresholdImage(greyscaleImage[0:previousBlockTopY, 0:imageWidth], ImageArea.TEXT_COLOUR_BLACK)
			remainingText = _imageToString(remainingTextImage)
			if remainingText:
				result["remainingText"] = ImageAndText(remainingTextImage, remainingText)
				_logger.debug(f"{remainingText=}")
			else:
				_logger.debug("No remaining text found")
			_logger.debug(f"Finding remaining text finished at {time.perf_counter() - startTime} seconds in")
		else:
			_logger.debug(f"No text above effect labels, highest label is at y={previousBlockTopY}")

	_logger.debug(f"Parsing image took {time.perf_counter() - startTime} seconds")
	if showImage:
		cv2.imshow("Card Image", cardImage)
		cv2.imshow("Types greyscale", typesImage)
		cv2.imshow("Textbox crop greyscale", greyscaleImage)
		if edgeDetectedImage is not None:
			cv2.imshow("Edge detected greyscale image", edgeDetectedImage)
		if greyscaleImageWithLines is not None:
			cv2.imshow("Greyscale with lines drawn on top", greyscaleImageWithLines)
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
		cv2.waitKey(0)
		cv2.destroyAllWindows()
	# Done!
	return result

def _getSubImage(image, imageArea: ImageArea.ImageArea):
	return image[imageArea.coords.top:imageArea.coords.bottom, imageArea.coords.left:imageArea.coords.right]

def _convertToThresholdImage(greyscaleImage, textColour: ImageArea.TextColour):
	threshold, thresholdImage = cv2.threshold(greyscaleImage, textColour.thresholdValue, 255, textColour.thresholdType)
	return thresholdImage

def _cv2ImageToPillowImage(cv2Image) -> Image.Image:
	return Image.fromarray(cv2.cvtColor(cv2Image, cv2.COLOR_BGR2RGB))

def _imageToString(image: cv2.Mat) -> str:
	# TesserOCR uses Pillow-format images, so convert our CV2-format image
	_tesseractApi.SetImage(_cv2ImageToPillowImage(image))
	return _tesseractApi.GetUTF8Text().rstrip("\n")
