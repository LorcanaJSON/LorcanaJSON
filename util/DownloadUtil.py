import logging
from typing import Dict

import requests

_logger = logging.getLogger("LorcanaJSON")
UNITY_VERSION = "2022.3.21f1"
DEFAULT_HEADERS = {"user-agent": "Lorcana/2023.1", "x-unity-version": UNITY_VERSION}


class DownloadException(BaseException):
	pass

def retrieveFromUrl(url: str, maxAttempts: int = 5, additionalHeaderFields: Dict[str, str] = None) -> requests.api.request:
	"""
	Since downloading from the Ravensburger API and CDN can sometimes take a few attempts, this helper method exists.
	It downloads the provided URL, tries a few times if it somehow fails, and if if succeeds, it returns the request
	:param url: The URL to retrieve
	:param maxAttempts: How many times to try to download the file
	:param additionalHeaderFields: Optional extra header fieldss to pass along with the call, on top of the default header fields
	:return: The Requests request with the data from the provided URL
	:raises DowloadException: Raised if the retrieval failed even after several attempts
	"""
	headers = DEFAULT_HEADERS
	if additionalHeaderFields:
		headers = DEFAULT_HEADERS.copy()
		headers.update(additionalHeaderFields)
	request = None
	lastRequestThrewException: bool = False
	for attempt in range(1, maxAttempts + 1):
		try:
			request = requests.get(url, headers=headers, timeout=10)
			lastRequestThrewException = False
			if request.status_code == 200:
				_logger.debug(f"Retrieval of '{url}' succeeded on attempt {attempt}")
				return request
		except requests.exceptions.SSLError:
			_logger.debug(f"Retrieval of '{url}' threw an SSL error on attempt {attempt}")
			lastRequestThrewException = True
		except requests.exceptions.Timeout:
			_logger.debug(f"Retrieval of '{url}' timed out on attempt {attempt}")
			lastRequestThrewException = True
	raise DownloadException(f"Download of '{url}' failed after {maxAttempts:,} attempts ({lastRequestThrewException=}, last attempt's status code: {request.status_code if request else 'missing'}")
