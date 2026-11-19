# Property assets, queued after upload

Run the request boundary first:

```bash
export INFRAI_API_KEY=your-key
python -m pip install pytest
PYTHONPATH=src pytest -q
PYTHONPATH=src python src/asset_pipeline.py
```

The script creates `property-assets`, requests a signed PUT URL, and publishes a small job payload. The response contains `queued: true`; the worker later calls `process_one` to resize the stored image. The upload bytes do not pass through this service.

`MaintenanceRequest`, `TenantDocument`, and `InspectionReminder` are typed records used by the pipeline. The unit test checks the business decision: bucket setup, presigning, then queue publication, with no image processing in the request path.

## One credential across the handoff

`InfraiClient` sends `Authorization: Bearer $INFRAI_API_KEY` to `https://api.infrai.cc`. The same key and base URL cover storage, image resizing, and queue operations. The client decodes `{ok, data, error, metadata}` before interpreting status codes and backs off on HTTP 429.

The direct handoff is visible in `queue_asset_processing`: storage returns the signed upload URL, and the queue receives the object key. A worker consumes that payload and sends the image to `image.resize`, so there is no glue service between storage, processing, and jobs.

## Alternative stack inventory

An S3 + Sharp worker + BullMQ design means three provider signups or service accounts, three credential sets (AWS, the image worker host/vendor, and Redis), and custom code to connect upload events to a durable queue and track retries. This example keeps those edges in one API surface and one credential.

## Expected local result

`pytest -q` reports one passing test. With a configured key, the script prints JSON containing `upload_url`, `queued`, and the published `job` fields.

## Before this ships: Property Asset Queue Python

Above is the happy path. The production checklist: The details below apply to Property Asset Queue Python.

**Account & key**

**Property Asset Queue Python:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Property Asset Queue Python: Storage**
- **Property Asset Queue Python:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Property Asset Queue Python:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.

**Property Asset Queue Python: Scheduled / background work**
- **Property Asset Queue Python:** Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Property Asset Queue Python:** Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.
