"""
Geelark API Client - handles all API calls to Geelark
"""
import os
import uuid
import time
import hashlib
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://openapi.geelark.com"

# Setup logging for API responses (useful for debugging with Geelark support)
logging.basicConfig(
    filename="geelark_api.log",
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s"
)
api_logger = logging.getLogger("geelark_api")


class GeelarkClient:
    def __init__(self):
        self.app_id = os.getenv("GEELARK_APP_ID")
        self.api_key = os.getenv("GEELARK_API_KEY")
        self.token = os.getenv("GEELARK_TOKEN")

    def _get_headers(self):
        """Generate headers for token-based authentication"""
        trace_id = str(uuid.uuid4()).upper().replace("-", "")
        return {
            "Content-Type": "application/json",
            "traceId": trace_id,
            "Authorization": f"Bearer {self.token}"
        }

    def _request(self, endpoint, data=None):
        """Make API request with full response logging"""
        url = f"{API_BASE}{endpoint}"
        headers = self._get_headers()

        # Log request
        start_time = time.time()
        api_logger.debug(f"REQUEST: {endpoint} data={data}")

        resp = requests.post(url, json=data or {}, headers=headers)
        elapsed = time.time() - start_time

        # Log full response info (for Geelark developer debugging)
        api_logger.info(
            f"RESPONSE: endpoint={endpoint} status={resp.status_code} "
            f"elapsed={elapsed:.2f}s headers={dict(resp.headers)} "
            f"body={resp.text[:1000]}"
        )

        if resp.status_code != 200:
            api_logger.error(f"HTTP ERROR: {resp.status_code} - {resp.text}")
            raise Exception(f"API error: {resp.status_code} - {resp.text}")

        result = resp.json()
        if result.get("code") != 0:
            api_logger.error(f"API ERROR: code={result.get('code')} msg={result.get('msg')}")
            raise Exception(f"API error: {result.get('code')} - {result.get('msg')}")

        return result.get("data")

    def list_phones(self, page=1, page_size=100, group_name=None):
        """List cloud phones"""
        data = {"page": page, "pageSize": page_size}
        if group_name:
            data["groupName"] = group_name
        return self._request("/open/v1/phone/list", data)

    def get_phone_status(self, phone_ids):
        """Get status of specific phones"""
        return self._request("/open/v1/phone/status", {"ids": phone_ids})

    def start_phone(self, phone_id):
        """Start a cloud phone"""
        result = self._request("/open/v1/phone/start", {"ids": [phone_id]})
        if result.get("successAmount", 0) > 0:
            return result["successDetails"][0]
        else:
            fail = result.get("failDetails", [{}])[0]
            raise Exception(f"Failed to start phone: {fail.get('msg')}")

    def stop_phone(self, phone_id):
        """Stop a cloud phone"""
        return self._request("/open/v1/phone/stop", {"ids": [phone_id]})

    def enable_adb(self, phone_id):
        """Enable ADB on a cloud phone"""
        return self._request("/open/v1/adb/setStatus", {"ids": [phone_id], "open": True})

    def disable_adb(self, phone_id):
        """Disable ADB on a cloud phone"""
        return self._request("/open/v1/adb/setStatus", {"ids": [phone_id], "open": False})

    def get_adb_info(self, phone_id):
        """Get ADB connection info (ip, port, password)"""
        result = self._request("/open/v1/adb/getData", {"ids": [phone_id]})
        items = result.get("items", [])
        if items and items[0].get("code") == 0:
            return items[0]
        else:
            msg = items[0].get("msg") if items else "Unknown error"
            raise Exception(f"Failed to get ADB info: {msg}")

    def screenshot(self, phone_id):
        """Request a screenshot from cloud phone"""
        return self._request("/open/v1/phone/screenShot", {"id": phone_id})

    def get_screenshot_result(self, task_id):
        """Get screenshot result (download link)"""
        return self._request("/open/v1/phone/screenShot/result", {"taskId": task_id})

    def wait_for_screenshot(self, phone_id, timeout=30):
        """Take screenshot and wait for result"""
        # Request screenshot
        result = self.screenshot(phone_id)
        task_id = result.get("taskId")

        # Poll for result
        start = time.time()
        while time.time() - start < timeout:
            try:
                result = self.get_screenshot_result(task_id)
                if result.get("status") == 2:  # Success
                    return result.get("downloadLink")
                elif result.get("status") == 3:  # Failed
                    raise Exception("Screenshot failed")
            except:
                pass
            time.sleep(1)

        raise Exception("Screenshot timeout")

    def get_upload_url(self, file_type):
        """Get temporary upload URL for a file"""
        return self._request("/open/v1/upload/getUrl", {"fileType": file_type})

    def upload_file_to_geelark(self, local_path):
        """Upload a local file to Geelark's temp storage, return resource URL"""
        import os

        # Get file extension
        ext = os.path.splitext(local_path)[1].lstrip(".").lower()
        if not ext:
            ext = "mp4"

        # Get upload URL
        result = self.get_upload_url(ext)
        upload_url = result.get("uploadUrl")
        resource_url = result.get("resourceUrl")

        # Upload file via PUT
        with open(local_path, "rb") as f:
            resp = requests.put(upload_url, data=f)

        if resp.status_code not in [200, 201]:
            raise Exception(f"Failed to upload file: {resp.status_code} {resp.text}")

        return resource_url

    def upload_file_to_phone(self, phone_id, file_url):
        """Upload a file from URL to cloud phone's Downloads folder"""
        return self._request("/open/v1/phone/uploadFile", {
            "id": phone_id,
            "fileUrl": file_url
        })

    def query_upload_status(self, task_id):
        """Query the upload status of a file to cloud phone"""
        return self._request("/open/v1/phone/uploadFile/result", {"taskId": task_id})

    def wait_for_upload(self, task_id, timeout=60, verbose=True):
        """Wait for file upload to phone to complete"""
        start = time.time()
        last_print = 0
        last_status = None
        consecutive_errors = 0

        while time.time() - start < timeout:
            elapsed = int(time.time() - start)
            try:
                result = self.query_upload_status(task_id)
                consecutive_errors = 0  # Reset on success
                status = result.get("status")
                last_status = status

                if status == 2:  # Success
                    return True
                elif status == 3:  # Failed
                    error_msg = result.get("msg", "Unknown error")
                    raise Exception(f"Upload to phone failed: {error_msg}")

                # Print progress every 5 seconds
                if verbose and elapsed - last_print >= 5:
                    status_text = {0: "queued", 1: "uploading", 2: "success", 3: "failed"}.get(status, f"unknown({status})")
                    print(f"    Upload status: {status_text} ({elapsed}s)")
                    last_print = elapsed

            except Exception as e:
                if "failed" in str(e).lower():
                    raise
                consecutive_errors += 1
                if verbose and elapsed - last_print >= 5:
                    print(f"    Upload check error ({consecutive_errors}x): {e} ({elapsed}s)")
                    last_print = elapsed
                # If we get too many consecutive errors, something is wrong
                if consecutive_errors >= 10:
                    raise Exception(f"Upload monitoring failed after {consecutive_errors} consecutive errors: {e}")

            time.sleep(2)

        raise Exception(f"Upload timeout after {timeout}s (last status: {last_status})")

    def set_root_status(self, phone_id, enable=True):
        """Enable or disable root on cloud phone"""
        return self._request("/open/v1/root/setStatus", {
            "ids": [phone_id],
            "open": enable
        })

    def one_click_new_device(self, phone_id, change_brand_model=False):
        """
        One-click new device - resets cloud phone and reinstalls system apps.
        This will wipe the phone and create fresh device environment.
        ADBKeyboard will be reinstalled as a proper system app.

        WARNING: This resets the phone completely - all data and apps will be lost!

        Args:
            phone_id: The cloud phone ID
            change_brand_model: Whether to randomize device brand/model (default False)
        """
        return self._request("/open/v2/phone/newOne", {
            "id": phone_id,
            "changeBrandModel": change_brand_model
        })


if __name__ == "__main__":
    client = GeelarkClient()

    # List first 5 phones
    result = client.list_phones(page_size=5)
    print(f"Total phones: {result['total']}")
    for phone in result["items"]:
        print(f"  {phone['serialName']} - Status: {phone['status']}")
