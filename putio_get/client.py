import logging
import httpx
from typing import Optional, List, Dict, Any
from .config import Config

log = logging.getLogger("rich")


class PutioClient:
    def __init__(self, config: Config):
        self.config = config
        self.headers = {
            "Authorization": f"Bearer {self.config.auth['oauth_token']}",
            "Accept": "application/json"
        }
        self.base_url = self.config.general['api_url'].rstrip("/")

    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.request(method, url, headers=self.headers, params=params, data=data)
                resp.raise_for_status()
                json_resp = resp.json()
                return json_resp
        except httpx.HTTPStatusError as e:
            log.error(f"API Error {e.response.status_code} for {method} {endpoint}: {e.response.text}")
            raise
        except Exception as e:
            log.error(f"Request failed for {method} {endpoint}: {e}")
            raise

    def list_files(self) -> List[Dict]:
        """
        List all files recursively using parent_id=-1.
        """
        files = []
        try:
            params = {
                "parent_id": -1,
                "per_page": 1000,
                "stream_url": False,
                "mp4_status": False,
                "hidden": True
            }

            cursor = None
            while True:
                if cursor:
                    endpoint = "/files/list/continue"
                    data = {"cursor": cursor, "per_page": 1000}
                    resp = self._request("POST", endpoint, data=data)
                else:
                    endpoint = "/files/list"
                    resp = self._request("GET", endpoint, params=params)

                if "files" in resp:
                    files.extend(resp["files"])

                cursor = resp.get("cursor")
                if not cursor:
                    break

        except Exception as e:
            log.error(f"Failed to list files: {e}")

        return files

    def get_file_url(self, file_id: int) -> Optional[str]:
        try:
            resp = self._request("GET", f"/files/{file_id}/url")
            return resp.get("url")
        except Exception:
            return None

    def delete_files(self, file_ids: List[int]):
        if not file_ids: return
        try:
            # This moves to trash
            self._request("POST", "/files/delete", data={"file_ids": ",".join(map(str, file_ids))})
            log.info(f"Moved {len(file_ids)} files to trash.")
        except Exception:
            pass

    def empty_trash(self):
        try:
            self._request("POST", "/trash/empty")
            log.info("Emptied trash.")
        except Exception as e:
            log.error(f"Failed to empty trash: {e}")
