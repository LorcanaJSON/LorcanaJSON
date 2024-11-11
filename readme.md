# LorcanaJSON

LorcanaJSON is a project to collect card data for the *Disney Lorcana Trading Card Game* and to make that data available in a format that's easily accessible and parsable for *Lorcana*-related projects.  
This repository only contains the code to generate the datafiles. For the datafiles themselves and how to use them, please visit [https://lorcanajson.org](https://lorcanajson.org) 
## Initial setup
### Python
The code in this repository is written in Python 3. Supported Python versions are 3.8 and up.  
Make sure you have Python 3 installed, either from the [official website](https://www.python.org) or from your OS's package manager.  
Verify that Python works by running the command 'python --version' on the commandline.  
If you get an error that the command can't be found, try 'python3 --version' instead, and replace instances of the 'python' command in subsequent examples with 'python3'.   
### Tesseract models
This project uses a specially generated model for Tesseract, trained on *Lorcana* cards.  
Download the file 'Lorcana_en.traineddata' from the ['Releases' tab](https://github.com/LorcanaJSON/LorcanaJSON/releases), and place it somewhere easily accessible.  
For languages other than English, you also need to download the Tesseract model for that language (indicated by its three-letter code) from the official repository [here](https://github.com/tesseract-ocr/tessdata_best/tree/e12c65a915945e4c28e237a9b52bc4a8f39a0cec), and place it in the same place as where you put 'Lorcana_en.traineddata'.    
### Libraries
This project needs some libraries to work. These are listed in the 'requirements.txt' file.  
To install these libraries, run the command 'python -m pip install -r requirements.txt'.  
#### Windows
tesserocr doesn't properly install out of the box on Windows. Use one of the listed solutions in [tesserocr's Readme](https://github.com/sirfz/tesserocr#windows) to install this library on Windows.  
### Configfile
The configfile allows you to set some standard values, so they don't need to always be provided through commandline arguments (though those arguments can still override config values).  
Copy the file 'config.json.example', and rename it to 'config.json'.  
Open 'config.json' in a text editor, and set the value for 'tesseractPath' to where you placed the *Lorcana* Tesseract model downloaded in a previous Setup step. If neither this field nor the commandline argument (see further down) isn't set, it defaults to the folder where this program is.  
You can also change the value for 'loglevel' to one of 'debug', 'info', 'warning', or 'error' to set a default log level.  

## Running the program
Run the program by calling the command 'python -m main [action] (arguments)'. Providing an action is mandatory,  arguments are optional. The possible actions and arguments are described below.  
These commandline options are also described when you run the program without any arguments or with just the '--help' argument
### Commandline actions:
* **check**: With this action, LorcanaJSON checks whether the input datafile from the official Lorcana app differs from the local one, to see if cards got changed or added. It reports those changes, if any, and then quits. This only works if a local datafile already exists. Use the '--ignoreFields' argument followed by a space-separated list of card fields to ignore changes in the specified fields (this defaults to 'foil_mask_url' and 'image_urls' because the image checksums in the URLs change frequently without any changes to the images)
* **update**: This action does the same update check as with 'check', but it also processed the new and changed cards to create a new output datafile in the 'output/generated' subfolder. It also creates a file called 'parsedCards.json' with just the new or changed cards, for easy verification. If there is no local datafile, all cards will get parsed
* **download**: This action downloads the latest input datafile and all the card images that don't exist locally, into the 'downloads/json' and 'downloads/images' subfolders respectively
* **parse**: Parses all the cards, regardless of whether an update is needed. Supports the '--cardIds' argument to limit which cards are parsed; data of cards not in the '--cardIds' list will be copied from the last parse
* **show**: Shows the sub-images used during the parsing of a card. Supports the '--cardIds' argument to limit which cards are shown
* **verify**: Compare the effects, abilities, and flavor text between the input file from the official app with our parsed data, and list the differences. Be sure to run a 'download' action and a 'parse' action before running this action. Both input and output are modified a bit to prevent a lot of false positives, so it's not perfect, but it's a useful way to catch easily-missable mistakes
### Commandline arguments
These arguments work with most or all of the actions described above. All of them are optional
* **--cardIds**: Limit which card IDs are used in the provided action. This only works with the 'parse', 'show', and 'verify' actions. This is a space-separated list. Each value in the list should be either an ID number, a range of numbers ('5-25'), or a negative number to exclude it from a previously defined range. For example, '--cardIds 1 10-14 -12' would use card IDs 1, 10, 11, 13, and 14 in the provided action 
* **--language**: Specify which language to check or parse. Has to be one of 'en' (English), 'fr' (French), or 'de' (German). Only English is currently fully supported and verified, so 'en' is the default value when this argument is omitted
* **--loglevel**: Specify which loglevel to use. Has to be one of 'debug', 'info', 'warning', or 'error'. Specifying this commandline argument overrides the value specified in the config file (described above). If omitted, and no configfile value is set, this defaults to 'warning'
* **--show**: Adding this argument displays all the sub-images used during image parsing. This only works with the 'parse' and 'update' actions. This slows down parsing a lot, because the program freezes when the sub-images are shown, until they are closed with a keypress, but it can be useful during debugging
* **--tesseractPath**: Specify where the *Lorcana* Tesseract model file is. Can also be specified in the config file, but specifying a path commandline argument overrides the config file value. If neither this argument nor the config file field isn't set, it defaults to the folder where this program is
* **--threads**: Specify how many threads should be used when executing multithreaded tasks. Specify a negative amount to use the maximum number of threads available minus the provided amount. If omitted, the optimal amount of threads is determined automatically

## Verifying the result
Because OCR isn't perfect, a manual check of the resulting datafiles is still necessary.  
'OutputFileViewer.html' in the 'output'-folder exists for this purpose. Open the file in a webbrowser, and drag either an 'allCards.json' or the 'parsedCards.json' onto the big green rectangle to load this data.  
The page should then show a card name, a card image, the card's parsed text, and the parsed data. This allows for easy comparison.  
Use the left and right arrows keys or the entry fields at the top to navigate through the cards. Press 'E' for the English card image, 'F' for French, 'D' or 'G' for German, and 'I' for Italian.
### Output data corrections
If you find a mistake in the generated data, you can add a correction to one of the 'outputDataCorrections' JSON files in the 'output'-folder.  
The general 'outputDataCorrections.json' file is applied to every lanugage, and each language can have its own corrections file called 'outputDataCorrections_[languagecode].json' (So for English it'd be 'outputDataCorrections_en.json'). The general corrections are applied before language-specific ones.  
In these corrections files, keys are a card ID (due to a JSON limitation these have to be strings instead of numbers), and the values are a dictionary with corrections for that card.  
The correction entry key is the name of the field to correct, and the value is a list with two entries: The first entry is the regular expression that should match the text error, the second entry is the correction. The matched text will get replaced in the card data with the correction.  
It's also possible to remove erroneously generated fields by specifying 'null' for both the first matching entry and the correction.  
Adding fields that weren't generated is done by specifying 'null' for the match, and the value to add as the correction.  
Adding a value to a list is done by providing 'null' as the matching regex, and the value to add as the correction.  
Removing a value from a list is done by providing a matching regex as the match, and then 'null' for the correction.
Changing a value in a dictionary also works, the entry that matches the correction will get changed with the correction.  
If a correction match can't be found in the card's generated text, a warning will be printed to the log.  
There are also some special correction entry keys to fix issues not easily matched with a regular expression, prefixed with an underscore so they stand out and don't match existing fields:
* '_effectAtIndexIsAbility': For some Special cards, the label doesn't get detected properly, so the named ability is stored as an effect. Set this field to the index of the effect, and the effect will be moved to the 'abilities' field, so it can more easily be corrected.  
* '_forceAbilityIndexToTriggered': Determining the type of an ability is done by careful language matching, since the phrasing of each type is usually pretty clear. For some French cards, this matching doesn't quite work, and the ability gets wrongly determined as a 'static' ability type. Adding '_forceAbilityIndexToTriggered' and setting it to the ability index that should be 'triggered' type instead of 'static' fixes this problem (Note that indexes start at 0).  
* '_forceAbilityIndexToStatic': This works like the '_forceAbilityIndexToTriggered' correction above, except it forces the type to 'static'.
* '_mergeEffectIndexWithPrevious': Sometimes a single effect gets parsed into multiple effects. Setting this field to the erroneously split effect index merges it with the previous effect index
* '_moveKeywordsLast': On most cards, keyword abilities come before named abilities. There are a few cards where this isn't true (f.i. 'Madam Mim - Fox' ID 262; 'Slightly - Lost Boy' ID 560). Due to how the parsing code works, the keyword ability on these cards gets added to the named ability. Adding '_moveKeywordsLast' and setting it to 'true' in the correction file fixes this problem by making the keyword ability be detected separately, and having it listed last in the 'fullTextSections' field.  
* '_newlineAfterLabelIndex': In some languages, the ability label can be as wide as the card itself. This means a newline isn't added between the label text and the effect text. If this field exists and is set to the ability index, a newline will be added after the label text to correct this.  

Once one or more corrections are added, you can rerun the 'parse' action with just the corrected card IDs, and repeat this verification process, until there are no mistakes anymore.  

## External early reveals
In the weeks before a new set is released, new cards from that set get teased, and it can sometimes take a while before they get added to the official app.  
The 'externalCardReveals.[language].json' file can contain a list of those externally revealed cards, with identical keys to the official card data.  
Not all those keys are mandatory, since most information can be extracted from the image. Some fields can't or it's hard to do accurate, so they have to get put in the external reveal file. These fields are:
* **imageUrl**: This should be the URL of the externally revealed image
* **culture_invariant_id**: The ID of the card as a number
* **magic_ink_color**: The card color as a string
* **ink_convertible**: Whether the card is inkable, as a boolean
* **rarity**: The card's rarity as a string
* **type**: The card type. This is used in determining how to parse some cards, so it's needed before parsing begins  

Other fields can be added to the JSON entry too, and as long as they have the same name as the field in the official app data, it will get used instead of what's parsed from the image
