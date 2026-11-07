import logging

import httpx


logger = logging.getLogger(__name__)


def _use_backup(request):
    if request.url.scheme != "https" or request.url.host != "api.vapeur.ai":
        return False
    request.url = request.url.copy_with(host="apiv2.vapeur.ai")
    request.headers["Host"] = request.url.netloc.decode("ascii")
    logger.warning("Vapeur connection failed; retrying via apiv2.vapeur.ai")
    return True


class VapeurClient(httpx.Client):
    def send(self, request, **kwargs):
        try:
            return super().send(request, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            if not _use_backup(request):
                raise
        return super().send(request, **kwargs)


class VapeurAsyncClient(httpx.AsyncClient):
    async def send(self, request, **kwargs):
        try:
            return await super().send(request, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            if not _use_backup(request):
                raise
        return await super().send(request, **kwargs)
