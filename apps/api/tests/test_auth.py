import httpx

from tests.conftest import PASSWORD, sign_up

AUTH = "/api/v1/auth"


async def test_sign_up_signs_you_in_and_creates_your_organization(client: httpx.AsyncClient) -> None:
    me = await sign_up(client, name="Ali Hassan", email="Ali@Acme.dev")

    assert me["user"]["email"] == "ali@acme.dev"  # stored lowercase
    assert me["user"]["handle"] == "ali-hassan"
    assert [(org["name"], org["role"]) for org in me["organizations"]] == [("Ali's team", "owner")]
    assert "botdesk_session" in client.cookies

    response = await client.get(f"{AUTH}/me")
    assert response.status_code == 200
    assert response.json()["user"]["name"] == "Ali Hassan"


async def test_the_session_cookie_is_http_only(client: httpx.AsyncClient) -> None:
    response = await client.post(f"{AUTH}/sign-up", json={"name": "Ali", "email": "ali@acme.dev", "password": PASSWORD})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


async def test_signing_up_twice_with_one_email_is_refused(client: httpx.AsyncClient) -> None:
    await sign_up(client, email="ali@acme.dev")
    response = await client.post(
        f"{AUTH}/sign-up", json={"name": "Other", "email": "ALI@acme.dev", "password": PASSWORD}
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "An account with this email already exists. Sign in instead."


async def test_short_passwords_are_refused(client: httpx.AsyncClient) -> None:
    response = await client.post(f"{AUTH}/sign-up", json={"name": "Ali", "email": "ali@acme.dev", "password": "short"})
    assert response.status_code == 422


async def test_sign_in_with_the_right_password(client: httpx.AsyncClient) -> None:
    await sign_up(client)
    client.cookies.clear()

    response = await client.post(f"{AUTH}/sign-in", json={"email": "ALI@acme.dev", "password": PASSWORD})
    assert response.status_code == 200
    assert (await client.get(f"{AUTH}/me")).status_code == 200


async def test_a_wrong_password_or_unknown_email_gives_the_same_answer(client: httpx.AsyncClient) -> None:
    await sign_up(client)
    client.cookies.clear()

    wrong_password = await client.post(f"{AUTH}/sign-in", json={"email": "ali@acme.dev", "password": "nope-nope"})
    unknown_email = await client.post(f"{AUTH}/sign-in", json={"email": "who@acme.dev", "password": PASSWORD})
    for response in (wrong_password, unknown_email):
        assert response.status_code == 401
        assert response.json()["detail"] == "That email and password don't match."


async def test_sign_out_ends_the_session(client: httpx.AsyncClient) -> None:
    await sign_up(client)
    token = client.cookies["botdesk_session"]

    assert (await client.post(f"{AUTH}/sign-out")).status_code == 204
    # The old token no longer works, even if someone kept a copy.
    response = await client.get(f"{AUTH}/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_apps_can_use_a_bearer_token(client: httpx.AsyncClient) -> None:
    await sign_up(client)
    token = client.cookies["botdesk_session"]
    client.cookies.clear()

    response = await client.get(f"{AUTH}/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


async def test_me_without_signing_in(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{AUTH}/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Sign in to continue."


async def test_forgot_password_never_reveals_who_has_an_account(client: httpx.AsyncClient) -> None:
    await sign_up(client, email="ali@acme.dev")
    known = await client.post(f"{AUTH}/forgot-password", json={"email": "ali@acme.dev"})
    unknown = await client.post(f"{AUTH}/forgot-password", json={"email": "nobody@acme.dev"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


async def test_you_can_change_your_name_and_handle(client: httpx.AsyncClient) -> None:
    await sign_up(client, name="Ali", email="ali@acme.dev")
    me = (await client.patch(f"{AUTH}/me", json={"name": "Ali Hassan", "handle": "alihassan"})).json()
    assert (me["user"]["name"], me["user"]["handle"]) == ("Ali Hassan", "alihassan")


async def test_handles_are_unique_and_tidy(client: httpx.AsyncClient) -> None:
    await sign_up(client, name="Sara", email="sara@acme.dev")
    client.cookies.clear()
    await sign_up(client, name="Ali", email="ali@acme.dev")
    taken = await client.patch(f"{AUTH}/me", json={"handle": "sara"})
    assert taken.status_code == 409
    assert taken.json()["detail"] == "@sara is taken. Try another."
    assert (await client.patch(f"{AUTH}/me", json={"handle": "Not OK"})).status_code == 422


async def test_changing_your_password_signs_out_other_devices(client: httpx.AsyncClient) -> None:
    await sign_up(client)
    laptop = client.cookies["botdesk_session"]
    client.cookies.clear()
    await client.post(f"{AUTH}/sign-in", json={"email": "ali@acme.dev", "password": PASSWORD})
    phone = client.cookies["botdesk_session"]

    wrong = await client.post(
        f"{AUTH}/change-password", json={"currentPassword": "nope", "newPassword": "a-new-password"}
    )
    assert wrong.status_code == 401
    ok = await client.post(
        f"{AUTH}/change-password", json={"currentPassword": PASSWORD, "newPassword": "a-new-password"}
    )
    assert ok.status_code == 200

    client.cookies.clear()  # a cookie would win over the Bearer header
    me_on = {"laptop": laptop, "phone": phone}
    statuses = {
        device: (await client.get(f"{AUTH}/me", headers={"Authorization": f"Bearer {token}"})).status_code
        for device, token in me_on.items()
    }
    assert statuses == {"laptop": 401, "phone": 200}

    client.cookies.clear()
    old = await client.post(f"{AUTH}/sign-in", json={"email": "ali@acme.dev", "password": PASSWORD})
    new = await client.post(f"{AUTH}/sign-in", json={"email": "ali@acme.dev", "password": "a-new-password"})
    assert (old.status_code, new.status_code) == (401, 200)
