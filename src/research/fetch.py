import hashlib
import http.client
import ipaddress
import socket
import ssl
import base64
from datetime import datetime,timezone
from urllib.parse import urlsplit,urljoin

from research.documents import decode_document
from research.quality import canonical_url
from state.errors import StudioError,ErrorCode


class PublicHTTPFetcher:
    """Public-IP pinned fetches, verified TLS, bounded redirects/bytes; no scripts."""
    def __init__(self,max_bytes=8_000_000,timeout=15):self.max_bytes,self.timeout=max_bytes,timeout

    def fetch(self,url):
        current=canonical_url(url)
        requests=0
        for _ in range(6):
            parsed=urlsplit(current);port=parsed.port or (443 if parsed.scheme=="https" else 80)
            if port not in {80,443}:raise StudioError(ErrorCode.SECURITY_BLOCK,"Nonstandard fetch ports are forbidden")
            try:addresses=socket.getaddrinfo(parsed.hostname,port,type=socket.SOCK_STREAM)
            except OSError as exc:raise StudioError(ErrorCode.SOURCE_ACCESS_ERROR,"Source DNS lookup failed") from exc
            if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
                raise StudioError(ErrorCode.SECURITY_BLOCK,"Source resolves to a private, local or reserved address")
            connection=http.client.HTTPConnection(parsed.hostname,port,timeout=self.timeout)
            try:
                connection.sock=socket.create_connection((addresses[0][4][0],port),timeout=self.timeout)
                if parsed.scheme=="https":connection.sock=ssl.create_default_context().wrap_socket(connection.sock,server_hostname=parsed.hostname)
                path=parsed.path or "/"
                if parsed.query:path+="?"+parsed.query
                connection.request("GET",path,headers={"Host":parsed.netloc,"User-Agent":"AI-Presentation-Studio/0.0 research","Accept-Encoding":"identity"})
                response=connection.getresponse();requests+=1
                if response.status in {301,302,303,307,308}:
                    location=response.getheader("Location")
                    if not location:raise StudioError(ErrorCode.SOURCE_ACCESS_ERROR,"Research redirect has no target")
                    current=canonical_url(urljoin(current,location));continue
                if response.status!=200:raise StudioError(ErrorCode.SOURCE_ACCESS_ERROR,"Source fetch returned a non-success status",status=response.status)
                length=response.getheader("Content-Length")
                if length and int(length)>self.max_bytes:raise StudioError(ErrorCode.SECURITY_BLOCK,"Research source exceeds byte budget")
                data=response.read(self.max_bytes+1)
                if len(data)>self.max_bytes:raise StudioError(ErrorCode.SECURITY_BLOCK,"Research source exceeds byte budget")
                content_type=response.getheader("Content-Type","").split(";")[0].lower()
                return {**decode_document(data,content_type,current),"url":current,"requested_url":url,"raw_base64":base64.b64encode(data).decode(),"retrieved_at":datetime.now(timezone.utc).isoformat(),"http_requests":requests,"mime":content_type,"trust":"untrusted_data"}
            except (OSError,ssl.SSLError,http.client.HTTPException) as exc:raise StudioError(ErrorCode.SOURCE_ACCESS_ERROR,"Source could not be fetched with verified transport") from exc
            finally:connection.close()
        raise StudioError(ErrorCode.SOURCE_ACCESS_ERROR,"Source redirect budget exhausted")
