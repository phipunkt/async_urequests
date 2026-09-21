import gc

import uasyncio as asyncio

gc.enable()


__version__ = "0.2.0"
HTTP__version__ = "1.1"
MAX_RESPONSE_SIZE = 12 * 1024


class TimeoutError(Exception):
    pass


class ConnectionError(Exception):
    pass


class Response:
    def __init__(self, reader, chunked, charset, h, length):
        self.raw = reader
        self.chunked = chunked
        self.encoder = charset
        self.h = h
        self.content_length = length
        self.content = b""
        self.chunk_size = 0

    async def _read(self, sz=-1):
        content = bytearray()
        # keep reading chunked data
        if self.chunked:
            sz = 2 * 1024
            while 1:
                if self.chunk_size == 0:
                    line = await self.raw.readline()  # get Hex size
                    if not line:
                        raise ConnectionError("Connection closed: read chunk size")
                    line = line.split(b";", 1)[0].strip()
                    try:
                        self.chunk_size = int(line, 16)  # convert to int
                    except (ValueError, TypeError):
                        raise ConnectionError("Invalid HTTP chunk size")
                    if self.chunk_size < 0:
                        raise ConnectionError("Invalid HTTP chunk size")
                    if self.chunk_size == 0:  # end of message
                        trailer_size = 0
                        while 1:
                            line = await self.raw.readline()
                            if not line:
                                raise ConnectionError(
                                    "Connection closed while reading chunk trailers"
                                )
                            trailer_size += len(line)
                            if trailer_size > 1024:
                                raise ConnectionError("HTTP trailers too large")
                            if line == b"\r\n":
                                break
                        break
                if len(content) + self.chunk_size > MAX_RESPONSE_SIZE:
                    raise ConnectionError("HTTP response too large")
                data = await self.raw.read(min(sz, self.chunk_size))
                if not data:
                    raise ConnectionError("Connection closed while receiving chunks")
                self.chunk_size -= len(data)
                content.extend(data)
                if self.chunk_size == 0:
                    sep = await self.raw.read(2)
                    if sep != b"\r\n":
                        raise ConnectionError("Invalid HTTP chunk terminator")
                    break
        # non chunked data
        else:
            if self.content_length >= 0:
                if self.content_length > MAX_RESPONSE_SIZE:
                    raise ConnectionError("HTTP response too large")
                residual = self.content_length
                while residual > 0:
                    data = await self.raw.read(residual)
                    if not data:
                        raise ConnectionError("Connection closed before full content-length")
                    content.extend(data)
                    residual -= len(data)
            else:  # no content-length: read until EOF
                content = bytearray()
                while len(content) < MAX_RESPONSE_SIZE:
                    remaining = MAX_RESPONSE_SIZE - len(content)
                    data = await self.raw.read(min(2048, remaining))
                    if not data:
                        break
                    content.extend(data)
                if len(content) == MAX_RESPONSE_SIZE:
                    data = await self.raw.read(1)
                    if data:
                        raise ConnectionError("HTTP response too large")
        return content

    @property
    def text(self):
        return str(self.content, self.encoder)

    @property
    def headers(self):
        result = {}
        for i in self.h:
            h = i.decode(self.encoder).strip().split(":", 1)
            result[h[0]] = h[-1].strip()
        return result

    def json(self):
        import ujson

        return ujson.loads(self.content)

    def close(self):
        if self.raw:
            try:
                self.raw.close()
            except Exception:
                pass
            self.raw = None

    def __repr__(self):
        return f"<Response [{self.status_code}]>"


async def _request_raw(method, url, headers, data, json_data):
    reader = None
    try:
        proto, dummy, host, path = url.split("/", 3)
    except ValueError:
        proto, dummy, host = url.split("/", 2)
        path = ""
    try:
        host, port = host.split(":")
        if proto == "https:":
            ssl = True
        elif proto == "http:":
            ssl = False
        else:
            raise ValueError(f"Unsupported protocol: {proto}")
    except ValueError:
        if proto == "http:":
            port = 80
            ssl = False
        elif proto == "https:":
            port = 443
            ssl = True
        else:
            raise ValueError(f"Unsupported protocol: {proto}")
    try:
        query = (
            f"{method} /{path} HTTP/{HTTP__version__}\r\n"
            + f"Host: {host}\r\nConnection: close\r\n"
            + f"{headers}"
        )
        if "User-Agent:" not in query:
            query += "User-Agent: compat\r\n"
        if json_data is not None:
            assert data is None
            import ujson

            data = ujson.dumps(json_data)
            if "Content-Type:" not in query:
                query += "Content-Type: application/json\r\n"
        if data and "Content-Length:" not in query:
            query += "Content-Length: {len(data)}\r\n"
        query += "\r\n"

        reader, writer = await asyncio.open_connection(host, port, ssl)
        writer.write(query.encode())
        await writer.drain()
        # Send body separately to not have one large allocation
        if data:
            writer.write(data.encode())
            await writer.drain()
        return reader
    except Exception:
        if reader is not None:
            try:
                reader.close()
            except Exception:
                pass
            try:
                await reader.wait_closed()
            except Exception:
                pass
        raise


async def _requests(
    method,
    url,
    params=None,
    data=None,
    headers=None,
    cookies=None,
    files=None,
    auth=None,
    timeout=None,
    allow_redirects=True,
    proxies=None,
    hooks=None,
    stream=None,
    verify=None,
    cert=None,
    json=None,
):
    reader = None
    try:
        # headers support
        h = ""
        if headers:
            for k in headers:
                h += f"{k}: {headers[k]}\r\n"
        # params support
        if params:
            url = url.rstrip("?") + "?"
            first = True
            for p in params:
                if not first:
                    url += "&"
                url += f"{p}={params[p]}"
                first = False
    except Exception as e:
        raise e
    try:
        # build in redirect support
        redir_cnt = 0
        redir_url = None
        while redir_cnt < 2:
            reader = await _request_raw(
                method=method, url=url, headers=h, data=data, json_data=json
            )
            sline = await reader.readline()
            sline = sline.split(None, 2)
            if len(sline) < 2:
                raise ConnectionError("Invalid HTTP status line")
            try:
                status_code = int(sline[1])
            except ValueError:
                raise ConnectionError("Invalid HTTP status code")
            reason = ""
            if len(sline) >= 3:
                reason = sline[2].decode().rstrip()
            chunked = False
            json = None
            headers = []
            charset = "utf-8"
            content_length = -1
            # read headers
            while True:
                line = await reader.readline()
                if not line or line == b"\r\n":
                    break
                headers.append(line)
                line = line.lower()
                if line.startswith(b"transfer-encoding"):
                    if b"chunked" in line:
                        chunked = True
                elif line.startswith(b"location:"):
                    url = line.rstrip().split(None, 1)[1].decode()
                elif line.startswith(b"content-length:"):
                    if not chunked:
                        try:
                            content_length = int(line.rstrip().split(None, 1)[1].decode())
                            if content_length < 0:
                                raise ValueError
                        except (ValueError, TypeError):
                            pass
                elif line.startswith(b"content-type:"):
                    if b"application/json" in line:
                        json = True
                    if b"charset" in line:
                        # get decoder
                        c_string = line.rstrip().decode()
                        pos = c_string.find("charset")
                        try:
                            charset = c_string[pos + 8 :].split(";", 1)[0].strip(' "')
                        except Exception:
                            pass
            # look for redirects
            if allow_redirects is False:
                break
            if 301 <= status_code <= 303:
                redir_cnt += 1
                reader.close()
                try:
                    await reader.wait_closed()
                except Exception:
                    pass
                reader = None
                continue
            break

        resp = Response(reader, chunked, charset, headers, content_length)
        if method == "HEAD" or status_code in (204, 304):
            resp.content = b""
        else:
            resp.content = await resp._read()
        resp.status_code = status_code
        resp.reason = reason
        resp.url = url
        return resp

    except MemoryError:
        raise
    except ConnectionError:
        raise
    except Exception as e:
        raise ConnectionError(e)
    finally:
        if reader is not None:
            try:
                reader.close()
            except Exception:
                pass
            try:
                await reader.wait_closed()
            except Exception:
                pass
            reader = None
        gc.collect()


async def get(url, timeout=10, **kwargs):
    try:
        return await asyncio.wait_for(_requests("GET", url, **kwargs), timeout=timeout)
    except asyncio.TimeoutError as e:
        raise TimeoutError(e)


async def head(url, timeout=10, **kwargs):
    try:
        return await asyncio.wait_for(_requests("HEAD", url, **kwargs), timeout=timeout)
    except asyncio.TimeoutError as e:
        raise TimeoutError(e)


async def post(url, timeout=10, **kwargs):
    try:
        return await asyncio.wait_for(_requests("POST", url, **kwargs), timeout=timeout)
    except asyncio.TimeoutError as e:
        raise TimeoutError(e)


async def put(url, timeout=10, **kwargs):
    try:
        return await asyncio.wait_for(_requests("PUT", url, **kwargs), timeout=timeout)
    except asyncio.TimeoutError as e:
        raise TimeoutError(e)


async def delete(url, timeout=10, **kwargs):
    try:
        return await asyncio.wait_for(_requests("DELETE", url, **kwargs), timeout=timeout)
    except asyncio.TimeoutError as e:
        raise TimeoutError(e)


# Makes it usable synchronously, but cannot use this class asynchronously
class urequests:
    @staticmethod
    def get(url, **kwargs):
        return asyncio.run(get(url, **kwargs))

    @staticmethod
    def head(url, **kwargs):
        return asyncio.run(head(url, **kwargs))

    @staticmethod
    def post(url, **kwargs):
        return asyncio.run(post(url, **kwargs))

    @staticmethod
    def put(url, **kwargs):
        return asyncio.run(put(url, **kwargs))

    @staticmethod
    def delete(url, **kwargs):
        return asyncio.run(delete(url, **kwargs))
