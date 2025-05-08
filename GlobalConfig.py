from util import Language, Translations

language: Language.Language = None
translation: Translations.Translation = None
tesseractPath: str = None
threadCount: int = 1
skipOcrCache: bool = False
useCachedOcr: bool = False
limitedBuild: bool = False
