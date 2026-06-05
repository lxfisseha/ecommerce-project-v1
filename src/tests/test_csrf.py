import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.features.auth.models import Seller
from sqlmodel import Session, create_engine, SQLModel
from sqlalchemy.pool import StaticPool

# Setup in-memory SQLite for testing
engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
SQLModel.metadata.create_all(engine)

def get_session_override():
    with Session(engine) as session:
        yield session

from src.database import get_session
app.dependency_overrides[get_session] = get_session_override

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_seller():
    with Session(engine) as session:
        # Check if seller exists to avoid duplicate
        seller = session.query(Seller).filter(Seller.phone == "0912345678").first()
        if not seller:
            session.add(Seller(store_name="Test Store", store_prefix="TEST", phone="0912345678"))
            session.commit()

def test_login_csrf_header_missing():
    # POST without CSRF token should fail
    response = client.post("/auth/login", data={"phone": "0912345678"})
    assert response.status_code == 403
    assert "CSRF" in response.text

def test_login_success_and_otp_verify():
    # 1. GET to get the cookie and token
    get_response = client.get("/auth/login")
    assert get_response.status_code == 200
    
    # Extract CSRF token from the response text (it's in the hidden input)
    import re
    match = re.search(r'name="csrf_token" value="([^"]+)"', get_response.text)
    assert match is not None
    token = match.group(1)
    
    # Get the csrftoken cookie
    csrf_cookie = get_response.cookies.get("csrftoken")
    assert csrf_cookie is not None
    
    # 2. POST login (OTP Generation)
    response = client.post(
        "/auth/login", 
        data={"phone": "0912345678"},
        headers={"X-CSRF-Token": token},
        cookies={"csrftoken": csrf_cookie}
    )
    assert response.status_code == 200
    assert "Verify OTP" in response.text
    
    # Extract OTP from debug log (we can't easily, so let's check DB)
    with Session(engine) as session:
        from src.features.auth.models import OtpCode
        otp = session.query(OtpCode).filter(OtpCode.phone == "0912345678").order_by(OtpCode.created_at.desc()).first()
        assert otp is not None
        code = otp.code

    # 3. POST verify-otp
    verify_response = client.post(
        "/auth/verify-otp",
        data={"phone": "0912345678", "code": code},
        headers={"X-CSRF-Token": token},
        cookies={"csrftoken": csrf_cookie, "session": response.cookies.get("session")}
    )
    assert verify_response.status_code == 200
    assert "HX-Redirect" in verify_response.headers
    assert verify_response.headers["HX-Redirect"] == "/dashboard"

def test_login_invalid_phone():
    get_response = client.get("/auth/login")
    match = re.search(r'name="csrf_token" value="([^"]+)"', get_response.text)
    token = match.group(1)
    csrf_cookie = get_response.cookies.get("csrftoken")

    response = client.post(
        "/auth/login", 
        data={"phone": "12345"},
        headers={"X-CSRF-Token": token},
        cookies={"csrftoken": csrf_cookie}
    )
    assert response.status_code == 422
    assert "Invalid phone number" in response.text
