"""Payment Gateway Services (VNPay & MoMo)."""

import hashlib
import hmac
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings


class VNPayService:
    """VNPay payment gateway service."""

    def __init__(self):
        self.vnp_url = settings.VNPAY_URL
        self.merchant_id = settings.VNPAY_MERCHANT_ID
        self.hash_secret = settings.VNPAY_HASH_SECRET
        self.return_url = settings.VNPAY_RETURN_URL

    def create_payment_url(
        self,
        amount: int,
        transaction_id: str,
        order_info: str,
        ip_address: str
    ) -> str:
        """Create VNPay payment URL."""
        params = {
            "vnp_Version": "2.1.0",
            "vnp_Command": "pay",
            "vnp_TmnCode": self.merchant_id,
            "vnp_Amount": str(amount * 100),
            "vnp_CurrCode": "VND",
            "vnp_TxnRef": transaction_id,
            "vnp_OrderInfo": order_info,
            "vnp_OrderType": "education",
            "vnp_Locale": "vn",
            "vnp_ReturnUrl": self.return_url,
            "vnp_IpAddr": ip_address,
            "vnp_CreateDate": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        }

        sorted_params = dict(sorted(params.items()))
        query_string = urllib.parse.urlencode(sorted_params)

        if self.hash_secret:
            hash_data = hmac.new(
                self.hash_secret.encode(),
                query_string.encode(),
                hashlib.sha256
            ).hexdigest()
        else:
            hash_data = ""

        payment_url = f"{self.vnp_url}?{query_string}&vnp_SecureHash={hash_data}"
        return payment_url

    def verify_return(self, params: dict) -> dict[str, Any]:
        """Verify VNPay return/callback parameters using constant-time digest comparison."""
        params_copy = dict(params)
        secure_hash = params_copy.pop("vnp_SecureHash", "")
        params_copy.pop("vnp_SecureHashType", None)

        if self.hash_secret and secure_hash:
            sorted_params = dict(sorted(params_copy.items()))
            query_string = urllib.parse.urlencode(sorted_params)
            expected_hash = hmac.new(
                self.hash_secret.encode(),
                query_string.encode(),
                hashlib.sha256
            ).hexdigest()
            is_valid = hmac.compare_digest(str(secure_hash).lower(), str(expected_hash).lower())
        else:
            is_valid = False

        response_code = params.get("vnp_ResponseCode", "99")

        return {
            "is_valid": is_valid,
            "is_success": response_code == "00",
            "transaction_id": params.get("vnp_TxnRef"),
            "amount": int(params.get("vnp_Amount", 0)) / 100,
            "response_code": response_code,
            "message": self._get_response_message(response_code),
            "bank_code": params.get("vnp_BankCode"),
            "pay_date": params.get("vnp_PayDate"),
        }

    def _get_response_message(self, code: str) -> str:
        messages = {
            "00": "Giao dịch thành công",
            "07": "Trừ tiền thành công. Giao dịch bị nghi ngờ (liên quan tới lừa đảo, gian lận)",
            "09": "Thẻ không đủ số dư",
            "10": "Thẻ hết hạn",
            "11": "Sai OTP",
            "12": "Thẻ bị khóa",
            "13": "Sai thông tin thẻ",
            "24": "Khách hàng hủy giao dịch",
            "51": "Tài khoản không đủ số dư",
            "65": "Vượt quá hạn mức ngày",
            "99": "Lỗi khác",
        }
        return messages.get(code, "Lỗi không xác định")


class MoMoService:
    """MoMo payment gateway service."""

    def __init__(self):
        self.momo_url = settings.MOMO_URL
        self.partner_code = settings.MOMO_PARTNER_CODE
        self.access_key = settings.MOMO_ACCESS_KEY
        self.secret_key = settings.MOMO_SECRET_KEY
        self.return_url = settings.MOMO_RETURN_URL

    async def create_payment_url(
        self,
        amount: int,
        transaction_id: str,
        order_info: str,
        ip_address: str
    ) -> str:
        """Create MoMo payment URL (API V2)."""
        import logging

        import httpx

        request_id = str(uuid.uuid4())
        order_id = transaction_id
        request_type = "captureWallet"

        # Format string raw_data for MoMo V2 signature (sorted alphabetically)
        raw_data = (
            f"accessKey={self.access_key}&amount={amount}&extraData=&"
            f"ipnUrl={self.return_url}&orderId={order_id}&orderInfo={order_info}&"
            f"partnerCode={self.partner_code}&redirectUrl={self.return_url}&"
            f"requestId={request_id}&requestType={request_type}"
        )

        signature = ""
        if self.secret_key:
            signature = hmac.new(
                self.secret_key.encode(),
                raw_data.encode(),
                hashlib.sha256
            ).hexdigest()

        payload = {
            "partnerCode": self.partner_code,
            "partnerName": "Learning Hub",
            "storeId": "LearningHub",
            "requestId": request_id,
            "amount": amount,
            "orderId": order_id,
            "orderInfo": order_info,
            "redirectUrl": self.return_url,
            "ipnUrl": self.return_url,
            "requestType": request_type,
            "extraData": "",
            "signature": signature,
            "lang": "vi"
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.momo_url, json=payload)
                response.raise_for_status()
                res_data = response.json()
                if res_data.get("resultCode") == 0:
                    return res_data.get("payUrl")
                logging.error(f"MoMo API creation error: {res_data.get('message')} (code: {res_data.get('resultCode')})")
                raise ValueError(res_data.get("message") or "Failed to create MoMo payment")
        except Exception as e:
            logging.error(f"Failed to communicate with MoMo gateway: {e}")
            # Fallback URL for test/local environments
            return f"https://test-payment.momo.vn/v2/gateway/api/create?partnerCode={self.partner_code}&orderId={order_id}&amount={amount}"

    def verify_callback(self, params: dict) -> dict[str, Any]:
        """Verify MoMo callback parameters using constant-time digest comparison."""
        received_signature = params.get("signature", "")

        raw_data = (
            f"access_key={self.access_key}&amount={params.get('amount')}&"
            f"extraData={params.get('extraData', '')}&message={params.get('message', '')}&"
            f"orderId={params.get('orderId')}&orderInfo={params.get('orderInfo', '')}&"
            f"partnerCode={self.partner_code}&requestId={params.get('requestId')}&"
            f"responseTime={params.get('responseTime')}&resultCode={params.get('resultCode')}&"
            f"transId={params.get('transId')}"
        )

        if self.secret_key and received_signature:
            expected_signature = hmac.new(
                self.secret_key.encode(),
                raw_data.encode(),
                hashlib.sha256
            ).hexdigest()
            is_valid = hmac.compare_digest(str(received_signature).lower(), str(expected_signature).lower())
        else:
            is_valid = False

        result_code = params.get("resultCode", 99)

        return {
            "is_valid": is_valid,
            "is_success": result_code == 0,
            "transaction_id": params.get("transId"),
            "amount": params.get("amount"),
            "result_code": result_code,
            "message": self._get_result_message(result_code),
            "order_id": params.get("orderId"),
        }

    def _get_result_message(self, code: int) -> str:
        messages = {
            0: "Giao dịch thành công",
            1000: "Giao dịch đang xử lý",
            1001: "Giao dịch bị từ chối bởi MoMo",
            1002: "Giao dịch bị giả mạo",
            1003: "Giao dịch bị duplicate",
            1004: "Giao dịch bị revert",
            1005: "Giao dịch bị refund",
            1006: "Giao dịch chưa complete",
            1007: "Giao dịch timeout",
            1008: "Giao dịch bị cancel",
            99: "Lỗi khác",
        }
        return messages.get(code, "Lỗi không xác định")


def get_vnpay_service() -> VNPayService:
    return VNPayService()


def get_momo_service() -> MoMoService:
    return MoMoService()