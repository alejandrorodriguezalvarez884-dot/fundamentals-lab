"""Sign-in through Market Hub: the tool admits only requests with a valid hub session cookie."""

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from conftest import FakeAnthropic, FakeFmp
from fundamentals.api import create_app
from fundamentals.budget import Budget
from fundamentals.config import PER_IP_PER_HOUR
from fundamentals.hubauth import read_user
from fundamentals.reading import Reader
from fundamentals.report import Reporter

SECRET = "hub-secret"
HUB = "https://themarkethub.app"
USER = {"id": "1001", "email": "ana@gmail.com", "name": "Ana", "picture": ""}


def hub_cookie(secret: str = SECRET, user: dict | None = USER) -> str:
    """A session cookie made exactly as the hub makes it (Starlette's SessionMiddleware)."""
    def login(request):
        if user:
            request.session["user"] = user
        return PlainTextResponse("ok")

    hub = Starlette(routes=[Route("/", login)],
                    middleware=[Middleware(SessionMiddleware, secret_key=secret, session_cookie="mh_session")])
    return TestClient(hub).get("/").cookies.get("mh_session", "")


def gated(directory, store):
    reader = Reader(store, Budget(store, 1.0, 5.0, 0.15), client=FakeAnthropic())
    app = create_app(store=store, directory=directory, reporter=Reporter(store, FakeFmp()), reader=reader,
                     hub=(HUB, SECRET))
    return TestClient(app, base_url="https://fundamentals.themarkethub.app", follow_redirects=False)


def test_read_user_checks_the_signature_and_age():
    cookie = hub_cookie()
    assert read_user(cookie, SECRET) == USER
    assert read_user(cookie, "another-secret") is None
    assert read_user(cookie[:-2] + "xx", SECRET) is None
    assert read_user(cookie, SECRET, max_age=-1) is None
    assert read_user(None, SECRET) is None
    assert read_user(hub_cookie(user=None), SECRET) is None  # signed in nobody


def test_signed_out_visitors_go_to_the_hub(directory, store):
    c = gated(directory, store)
    assert c.get("/api/health").status_code == 200
    page = c.get("/stock/", params={"t": "AAPL"})
    assert page.status_code == 302
    target = urlparse(page.headers["location"])
    assert f"{target.scheme}://{target.netloc}{target.path}" == f"{HUB}/signin/"
    assert parse_qs(target.query)["next"] == ["https://fundamentals.themarkethub.app/stock/?t=AAPL"]
    api = c.get("/api/search", params={"q": "apple"})
    assert api.status_code == 401 and api.json()["signin"].startswith(f"{HUB}/signin/")
    c.cookies.set("mh_session", hub_cookie(secret="forged"))
    assert c.get("/api/me").status_code == 401


def test_signed_in_users_get_in_without_a_per_address_limit(directory, store):
    c = gated(directory, store)
    c.cookies.set("mh_session", hub_cookie())
    assert c.get("/api/me").json() == {"user": USER, "hub": HUB}
    for _ in range(PER_IP_PER_HOUR * 4 + 5):
        assert c.get("/api/stock/AAPL").status_code == 200


def test_without_hub_settings_the_tool_stays_public(directory, store):
    app = create_app(store=store, directory=directory, reporter=Reporter(store, FakeFmp()), hub=None)
    c = TestClient(app)
    assert c.get("/api/me").json() == {"user": None, "hub": None}
    assert c.get("/api/search", params={"q": "apple"}).status_code == 200
