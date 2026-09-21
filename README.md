# async_urequests

Asynchronous urequests for micropython. Optional urequests class to make usable synchronously.

Tested on MicroPython v1.23.0-dirty on Pimoroni Badger2040W 2MB with RP2040

Extension of parsing for non-chunked response, introduce reading content length and catch edge cases.
Major rewrite to catch server and network errors.

Introduce new `MAX_RESPONSE_SIZE` to prevent memory runout on large response size.

Original desciption below:

Requires uasyncio V3.

Notes:
- to import synchronously (normal) :

  from async_urequests import urequests as requests
  
- to import asynchronously: 

  import async_urequests as requests
  
- Default HTTP version is 1.1, to change HTTP version do: 

  requests.HTTP__version__ = "1.0"
  
- supported HTTP methods: GET, HEAD, POST, PUT, DELETE.
- Returns response with the following properties: 

  content, status_code, reason, url, text, headers, encoder.
  
- json from response by calling json() method:

  r.json()
  
- supports headers
- supports params
- supports HTTP & HTTPS.
- supports Chunked data.
- supports redirects: 
- supports timeout, default timeout set to 10 seconds.
- Raises ConnectionError on any socket errors and TimeoutError on timeouts. To catch errors: requests.ConnectionError & requests.TimeoutError.
- supports custom ports:

  r = requests.get("https://192.168.1.100:1234")
  
  *tested with Plex Server