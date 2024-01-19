# LorcanaJSON

LorcanaJSON is a project to collect card data for the *Disney Lorcana Trading Card Game* and to make that data available in a format that's easily accessible and parsable for *Lorcana*-related projects.  
This repository only contains the code to generate the datafiles. For the datafiles themselves and how to use them, please visit [https://lorcanajson.org](https://lorcanajson.org) 
## Initial setup
### Python
The code in this repository is written in Python 3. Supported Python versions are 3.8 to 3.11.  
Make sure you have Python 3 installed, either from the [official website](https://www.python.org) or from your OS's package manager.  
Verify that Python works by running the command 'python --version' on the commandline.  
If you get an error that the command can't be found, try 'python3 --version' instead, and replace instances of the 'python' command in subsequent examples with 'python3'.   
### Tesseract
This project uses version 5 of the Tesseract OCR library to parse the text on the card images. 
Tesseract is a separate program that needs to be installed first. It can be downloaded [here](https://tesseract-ocr.github.io/tessdoc/Downloads.html).
### Tesseract model
This project uses a specially generated model for Tesseract, trained on *Lorcana* cards.  
Download the file 'Lorcana_en.traineddata' from the ['Releases' tab](https://github.com/LorcanaJSON/LorcanaJSON/releases), and place it in the 'tessdata' subfolder of your Tesseract install.  
### Libraries
This project needs some libraries to work. These are listed in the 'requirements.txt' file.  
To install these libraries, run the command 'python -m pip install -r requirements.txt'.  
#### Windows
tesserocr doesn't properly install out of the box on Windows. Use one of the listed solutions in [tesserocr's Readme](https://github.com/sirfz/tesserocr#windows) to install this library on Windows.  
### Configfile
If you're using Windows, Tesseract won't be added to the Path, so this program can't find it. You can either use a commandline argument to specify the path (see the next section), or you can use a config file. Make sure to point to the 'tessdata' subfolder of your Tesseract install.    
The configfile also contains a field for the standard log level, which can also be overridden with a commandline argument.  
Copy the file 'config.json.example', and rename it to 'config.json'.  
Open 'config.json' in a text editor, and change the value for 'tesseractPath' to where you installed Tesseract.  
You can also change the value for 'loglevel' to one of 'debug', 'info', 'warning', or 'error' to set a default log level

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
* **--tesseractPath**: Specify where Tesseract is installed. Needed when Tesseract-OCR isn't added to the OS's path (usually on Windows). Can also be specified in the config file, but specifying a path commandline argument overrides the config file value. Make sure to point to the 'tessdata' subfolder of your Tesseract install  

## Verifying the result
Because OCR isn't perfect, a manual check of the resulting datafiles is still necessary.  
'OutputFileViewer.html' in the 'output'-folder exists for this purpose. Open the file in a webbrowser, and drag either the 'allCards.json' or the 'parsedCards.json' onto the big green rectangle to load this data.  
The page should then show a card name, a card image, the card's parsed text, and the parsed data. This allows for easy comparison. Use the left and right arrows keys or the entry fields at the top to navigate through the cards.  
If you find a mistake, you can add a correction to the 'outputDataCorrections_en.json' file in the 'output'-folder. Keys here are a card ID (due to a JSON limitation these have to be strings instead of numbers). For each card ID, a dictionary with corrections is specified. The key is the name of the field to correct, and the value is a list with two entries: The first entry is the regular expression to match the error, the second entry is the correction.  
Once one or more corrections are added, you can rerun the pogram with just the corrected card IDs, and repeat this verification process, until there are no mistakes anymore.  
