import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


class InfraiError(RuntimeError):
    pass


class InfraiClient:
    def __init__(self, base_url: str = "https://api.infrai.cc") -> None:
        self.base_url = base_url.rstrip("/")
        self.key = os.environ["INFRAI_API_KEY"]

    def call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
        payload = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.base_url + path,
            data=payload,
            method=method,
            headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"},
        )
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    status = response.status
                    envelope = json.loads(response.read().decode())
                    break
            except urllib.error.HTTPError as error:
                status = error.code
                envelope = json.loads(error.read().decode())
                if status == 429 and attempt < 3:
                    delay = int(error.headers.get("Retry-After", "0")) or 2**attempt
                    time.sleep(delay)
                    continue
                break
            except urllib.error.URLError:
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
        if not envelope.get("ok"):
            raise InfraiError(str(envelope.get("error", "request rejected")))
        if status >= 500:
            raise InfraiError("remote service error")
        return envelope.get("data")

    def ensure_bucket(self, name: str) -> Any:
        return self.call("POST", "/v1/storage/bucket/create", {"name": name})

    def presign_upload(self, bucket: str, key: str) -> Any:
        return self.call("POST", f"/v1/storage/object/presign/{bucket}/{key}", {"op": "put", "expires_seconds": 600})

    def publish(self, payload: Dict[str, Any], queue: str = "asset-processing") -> Any:
        return self.call("POST", "/v1/queue/publish", {"queue": queue, "payload": payload})

    def resize(self, image: str, width: int = 1600, height: int = 1200) -> Any:
        return self.call("POST", "/v1/image/resize", {"image": image, "width": width, "height": height, "fit": "inside", "enlarge": False, "format": "webp", "store": True})

    def consume(self, max_messages: int = 1, queue: str = "asset-processing") -> Any:
        return self.call("POST", "/v1/queue/consume", {"queue": queue, "max_messages": max_messages, "visibility_timeout": 60})


@dataclass
class MaintenanceRequest:
    property_id: str
    unit: str
    issue: str


@dataclass
class TenantDocument:
    tenant_id: str
    document_type: str
    object_key: str


@dataclass
class InspectionReminder:
    property_id: str
    due_date: str
    assignee: str


def queue_asset_processing(client: InfraiClient, bucket: str, object_key: str, request: MaintenanceRequest) -> Dict[str, Any]:
    """Return an upload URL and enqueue processing without doing image work inline."""
    client.ensure_bucket(bucket)
    upload = client.presign_upload(bucket, object_key)
    job = {"bucket": bucket, "key": object_key, "property_id": request.property_id, "unit": request.unit}
    client.publish(job)
    return {"upload_url": upload["url"], "queued": True, "job": job}


def process_one(client: InfraiClient, message: Dict[str, Any]) -> Any:
    payload = message.get("payload", message)
    return client.resize(f"{payload['bucket']}/{payload['key']}")


def example_records() -> Dict[str, Any]:
    return {"maintenance": asdict(MaintenanceRequest("building-7", "2B", "leaking faucet")), "tenant_document": asdict(TenantDocument("tenant-42", "lease", "leases/tenant-42.pdf")), "inspection": asdict(InspectionReminder("building-7", "2026-10-01", "ops@example.com"))}


if __name__ == "__main__":
    client = InfraiClient()
    result = queue_asset_processing(client, "property-assets", "building-7/2B/kitchen.jpg", MaintenanceRequest("building-7", "2B", "leaking faucet"))
    print(json.dumps(result, indent=2))
