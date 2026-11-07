import asyncio
import io
import unittest

import httpx

from _loader import import_module

fallback = import_module("py.api.fallback")


class FallbackTests(unittest.TestCase):
    def request(self, asynchronous, handler, url="https://api.vapeur.ai/v1/images/edits?test=1"):
        options = {
            "headers": {"Authorization": "Bearer test-key"},
            "data": {"model": "test-model"},
            "files": {"image": ("test.png", io.BytesIO(b"image-bytes"), "image/png")},
        }
        transport = httpx.MockTransport(handler)
        if asynchronous:
            async def run():
                async with fallback.VapeurAsyncClient(transport=transport) as client:
                    return await client.post(url, **options)
            return asyncio.run(run())
        with fallback.VapeurClient(transport=transport) as client:
            return client.post(url, **options)

    def test_connection_failure_preserves_upload_and_auth_on_backup(self):
        for asynchronous in (False, True):
            for error in (httpx.ConnectError, httpx.ConnectTimeout):
                with self.subTest(asynchronous=asynchronous, error=error):
                    seen = []
                    def handler(request):
                        seen.append((str(request.url), dict(request.headers), request.content))
                        if len(seen) == 1:
                            raise error("connection failed", request=request)
                        return httpx.Response(200, json={"ok": True})
                    self.assertEqual(self.request(asynchronous, handler).status_code, 200)
                    self.assertEqual([item[0] for item in seen], [
                        "https://api.vapeur.ai/v1/images/edits?test=1",
                        "https://apiv2.vapeur.ai/v1/images/edits?test=1",
                    ])
                    self.assertEqual(seen[1][1]["host"], "apiv2.vapeur.ai")
                    self.assertEqual(seen[1][1]["authorization"], "Bearer test-key")
                    self.assertEqual(seen[0][2], seen[1][2])
                    self.assertIn(b"image-bytes", seen[1][2])

    def test_http_responses_do_not_trigger_fallback(self):
        for asynchronous in (False, True):
            for status in (200, 400, 401, 429, 503):
                with self.subTest(asynchronous=asynchronous, status=status):
                    seen = []
                    def handler(request):
                        seen.append(request.url.host)
                        return httpx.Response(status)
                    self.assertEqual(self.request(asynchronous, handler).status_code, status)
                    self.assertEqual(seen, ["api.vapeur.ai"])

    def test_errors_after_connection_do_not_trigger_fallback(self):
        for asynchronous in (False, True):
            for error in (httpx.ReadTimeout, httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError):
                with self.subTest(asynchronous=asynchronous, error=error):
                    seen = []
                    def handler(request):
                        seen.append(request.url.host)
                        raise error("request failed", request=request)
                    with self.assertRaises(error):
                        self.request(asynchronous, handler)
                    self.assertEqual(seen, ["api.vapeur.ai"])

    def test_other_endpoints_are_not_redirected(self):
        for asynchronous in (False, True):
            for url in ("https://custom.example/v1", "https://apiv2.vapeur.ai/v1", "http://api.vapeur.ai/v1"):
                with self.subTest(asynchronous=asynchronous, url=url):
                    seen = []
                    def handler(request):
                        seen.append(str(request.url))
                        raise httpx.ConnectError("connection failed", request=request)
                    with self.assertRaises(httpx.ConnectError):
                        self.request(asynchronous, handler, url)
                    self.assertEqual(seen, [url])

    def test_backup_failure_is_returned_without_looping(self):
        for asynchronous in (False, True):
            with self.subTest(asynchronous=asynchronous):
                seen = []
                def handler(request):
                    seen.append(request.url.host)
                    raise httpx.ConnectError(request.url.host, request=request)
                with self.assertRaisesRegex(httpx.ConnectError, "apiv2.vapeur.ai"):
                    self.request(asynchronous, handler)
                self.assertEqual(seen, ["api.vapeur.ai", "apiv2.vapeur.ai"])

    def test_next_request_tries_primary_again(self):
        for asynchronous in (False, True):
            with self.subTest(asynchronous=asynchronous):
                seen = []
                def handler(request):
                    seen.append(request.url.host)
                    if len(seen) == 1:
                        raise httpx.ConnectError("connection failed", request=request)
                    return httpx.Response(200)
                transport = httpx.MockTransport(handler)
                if asynchronous:
                    async def run():
                        async with fallback.VapeurAsyncClient(transport=transport) as client:
                            await client.get("https://api.vapeur.ai/v1/models")
                            await client.get("https://api.vapeur.ai/v1/models")
                    asyncio.run(run())
                else:
                    with fallback.VapeurClient(transport=transport) as client:
                        client.get("https://api.vapeur.ai/v1/models")
                        client.get("https://api.vapeur.ai/v1/models")
                self.assertEqual(seen, ["api.vapeur.ai", "apiv2.vapeur.ai", "api.vapeur.ai"])
