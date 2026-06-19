import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.utils.sms import AfroMessageService
from src.config import settings

@pytest.mark.asyncio
async def test_send_otp_sms_mock_mode():
    # When AFROMESSAGES_API_KEY is empty, it should log a warning and return True
    with patch("src.config.settings.AFROMESSAGES_API_KEY", ""):
        res = await AfroMessageService.send_otp_sms("0912345678", "123456")
        assert res is True

@pytest.mark.asyncio
async def test_send_otp_sms_api_success():
    # When api key exists and API returns 200 with success acknowledgment
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"acknowledge": "success", "status": "sent"}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response

    with patch("src.config.settings.AFROMESSAGES_API_KEY", "fake-token"), \
         patch("httpx.AsyncClient", return_value=mock_client):
        
        res = await AfroMessageService.send_otp_sms("0912345678", "123456")
        assert res is True
        mock_client.get.assert_called_once()
        called_params = mock_client.get.call_args[1]["params"]
        assert called_params["to"] == "251912345678"
        assert "123456" in called_params["message"]

@pytest.mark.asyncio
async def test_send_otp_sms_api_failure():
    # When api key exists but API returns an error status
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized Token"

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_response

    with patch("src.config.settings.AFROMESSAGES_API_KEY", "invalid-token"), \
         patch("httpx.AsyncClient", return_value=mock_client):
        
        res = await AfroMessageService.send_otp_sms("0912345678", "123456")
        assert res is False
