import ssl
from typing import Tuple
from bs4 import BeautifulSoup
import httpx


BASE_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "content-type": "application/x-www-form-urlencoded",
    "sec-ch-ua": '" Not;A Brand";v="99", "Google Chrome";v="97", "Chromium";v="97"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
}


class SIAKError(BaseException):
    def __init__(self, message: str):
        self.message = message


class Unauthorized(SIAKError):
    pass


class SIAKSession:
    BASE_URL = "https://academic.ui.ac.id"

    def __init__(self, username, passwd):
        ssl_context = httpx.create_ssl_context()
        ssl_context.set_ciphers("DEFAULT@SECLEVEL=1")
        ssl_context.options |= ssl.OP_NO_TLSv1_3
        ssl_context.load_verify_locations("ui-ac-id.pem")

        self._username = username
        self._passwd = passwd
        self._client = httpx.AsyncClient(
            follow_redirects=False,
            headers=BASE_HEADERS,
            verify=ssl_context,
        )

    def _check_response(self, response: httpx.Response):
        if response.status_code == 302:
            target = (
                response.headers.get("Location")
                or response.headers.get("location")
                or ""
            )
            if "Authentication" in target:
                raise Unauthorized("Unauthorized.")
        else:
            return False
        return True

    async def login(self):
        form = {
            "u": self._username,
            "p": self._passwd,
        }
        resp, _ = await self.request(
            "POST",
            "/main/Authentication/Index",
            data=form,
        )
        if "Login Failed" in resp.text or not self._client.cookies.get("siakng_cc"):
            raise Exception("Failed to log in.")

        await self.request("GET", "/main/Authentication/ChangeRole")

    async def request(
        self, method: str, path: str, *, data: dict = None
    ) -> Tuple[httpx.Response, BeautifulSoup]:
        retry_count = 5
        while retry_count > 0:
            url = self.BASE_URL + path
            response = await self._client.request(
                method,
                url,
                data=data,
            )
            try:
                if not self._check_response(response):
                    raise SIAKError("Unexpected response.")
                break
            except Unauthorized:
                await self.login()
                continue
            except SIAKError as e:
                raise e
            except BaseException:
                retry_count -= 1
                continue

        return (response, self.parse_html(response.text))

    def parse_html(self, html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")
