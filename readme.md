# LorcanaJSON

LorcanaJSON is a project to collect card data for the *Disney Lorcana Trading Card Game* and to make that data available in a format that's easily accessible and parsable for *Lorcana*-related projects.  
This repository only contains the code to generate the datafiles. For the datafiles themselves and how to use them, please visit [https://lorcanajson.org](https://lorcanajson.org) 
## Initial setup
### Python
The code in this repository is written in Python 3. Supported Python versions are 3.8 and up.  
Make sure you have Python 3 installed, either from the [official website](https://www.python.org) or from your OS's package manager.  
Verify that Python works by running the command 'python --version' on the commandline.  
If you get an error that the command can't be found, try 'python3 --version' instead, and replace instances of the 'python' command in subsequent examples with 'python3'.   
### Tesseract model
This project uses a specially generated model for Tesseract, trained on *Lorcana* cards.  
Download the file 'Lorcana_en.traineddata' from the ['Releases' tab](https://github.com/LorcanaJSON/LorcanaJSON/releases), and place it somewhere easily accessible.    
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
### Commandline arguments
These arguments work with most or all of the actions described above. All of them are optional
* **--cardIds**: Limit which card IDs are used in the provided action. This only works with the 'parse' and 'show' actions. This is a space-separated list. Each value in the list should be either an ID number, a range of numbers ('5-25'), or a negative number to exclude it from a previously defined range. For example, '--cardIds 1 10-14 -12' would use card IDs 1, 10, 11, 13, and 14 in the provided action 
* **--language**: Specify which language to check or parse. Has to be one of 'en' (English), 'fr' (French), or 'de' (German). Only English is currently fully supported and verified, so 'en' is the default value when this argument is omitted
* **--loglevel**: Specify which loglevel to use. Has to be one of 'debug', 'info', 'warning', or 'error'. Specifying this commandline argument overrides the value specified in the config file (described above). If omitted, and no configfile value is set, this defaults to 'warning'
* **--show**: Adding this argument displays all the sub-images used during image parsing. This does nothing with the 'check' action. This slows down parsing a lot, because the program freezes when the sub-images are shown, until they are closed with a keypress, but it can be useful during debugging
* **--tesseractPath**: Specify where the *Lorcana* Tesseract model file is. Can also be specified in the config file, but specifying a path commandline argument overrides the config file value. If neither this argument nor the config file field isn't set, it defaults to the folder where this program is
* **--threads**: Specify how many threads should be used when executing multithreaded tasks. Specify a negative amount to use the maximum number of threads available minus the provided amount. If omitted, the optimal amount of threads is determined automatically

## Verifying the result
Because OCR isn't perfect, a manual check of the resulting datafiles is still necessary.  
'OutputFileViewer.html' in the 'output'-folder exists for this purpose. Open the file in a webbrowser, and drag either the 'allCards.json' or the 'parsedCards.json' onto the big green rectangle to load this data.  
The page should then show a card name, a card image, the card's parsed text, and the parsed data. This allows for easy comparison. Use the left and right arrows keys or the entry fields at the top to navigate through the cards.  
If you find a mistake, you can add a correction to the 'outputDataCorrections_en.json' file in the 'output'-folder. Keys here are a card ID (due to a JSON limitation these have to be strings instead of numbers). For each card ID, a dictionary with corrections is specified. The key is the name of the field to correct, and the value is a list with two entries: The first entry is the regular expression to match the error, the second entry is the correction.  
Once one or more corrections are added, you can rerun the pogram with just the corrected card IDs, and repeat this verification process, until there are no mistakes anymore.  

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
