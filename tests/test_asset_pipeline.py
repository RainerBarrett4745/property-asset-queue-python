from asset_pipeline import MaintenanceRequest, queue_asset_processing


class FakeClient:
    def __init__(self):
        self.calls = []

    def ensure_bucket(self, name):
        self.calls.append(("bucket", name))

    def presign_upload(self, bucket, key):
        self.calls.append(("presign", bucket, key))
        return {"url": "https://upload.example/signed"}

    def publish(self, payload):
        self.calls.append(("publish", payload))


def test_upload_is_handed_to_queue_before_processing():
    fake = FakeClient()
    result = queue_asset_processing(fake, "assets", "p/1/photo.jpg", MaintenanceRequest("p", "1", "window"))
    assert result["queued"] is True
    assert [call[0] for call in fake.calls] == ["bucket", "presign", "publish"]
    assert fake.calls[-1][1]["key"] == "p/1/photo.jpg"
