# async_urequests

Asynchronous urequests for micropython. Optional urequests class to make usable synchronously.

Tested on MicroPython v1.21.0-dirty on 2023-10-11; Pimoroni Badger2040W 2MB with RP2040

Extension of parsing for non-chunked response, introduce reading content length and catch edge case.
Little code rewrite and (hopefully) optimizations.

Original desciption below:

Requires uasyncio V3.

Notes:
- to import synchronously (normal) :

  from async_urequests import urequests as requests
  
- to import asynchronously: 

  import async_urequests as requests
  
- Default HTTP version is 1.0, to change HTTP version do: 

  requests.HTTP__version__ = "1.1"
  
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

Known Issues:
- "memory allocation failed" occurs when reading large responses, will raise a ConnectionError.
