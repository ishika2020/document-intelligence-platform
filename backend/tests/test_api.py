"""API-level integration tests using FastAPI's TestClient (no live server needed)."""


def test_health_endpoint(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_process_document_end_to_end(client, sample_docs_dir):
    file_path = sample_docs_dir / "balance_sheet_2020.pdf"
    with file_path.open("rb") as f:
        resp = client.post(
            "/api/v1/documents/process",
            files={"file": (file_path.name, f, "application/pdf")},
            data={"document_type": "balance_sheet"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["processing_status"] == "PASS"
    assert body["document_type"] == "balance_sheet"
    assert body["extracted_data"]["total_assets"]["value"] == 15_808_304_373.0
    assert body["file_validation"]["status"] == "PASS"
    assert "checks" in body["validation"]
    assert body["processing_metadata"]["ocr_used"] is True


def test_get_document_by_name_returns_latest_result(client, sample_docs_dir):
    file_path = sample_docs_dir / "invoice_template_sample.jpg"
    with file_path.open("rb") as f:
        client.post(
            "/api/v1/documents/process",
            files={"file": (file_path.name, f, "image/jpeg")},
            data={"document_type": "invoice"},
        )
    resp = client.get(f"/api/v1/documents/{file_path.name}")
    assert resp.status_code == 200
    assert resp.json()["document_name"] == file_path.name


def test_get_unknown_document_returns_404(client):
    resp = client.get("/api/v1/documents/does-not-exist.pdf")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_list_documents_endpoint(client, sample_docs_dir):
    file_path = sample_docs_dir / "cash_flow_statement_2020.pdf"
    with file_path.open("rb") as f:
        client.post(
            "/api/v1/documents/process",
            files={"file": (file_path.name, f, "application/pdf")},
            data={"document_type": "cash_flow_statement"},
        )
    resp = client.get("/api/v1/documents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    names = [d["document_name"] for d in body["documents"]]
    assert file_path.name in names


def test_unsupported_file_type_fails_gracefully(client):
    resp = client.post(
        "/api/v1/documents/process",
        files={"file": ("notes.txt", b"just plain text", "text/plain")},
        data={"document_type": "invoice"},
    )
    assert resp.status_code == 200  # graceful FAILED result, not a crash
    body = resp.json()
    assert body["processing_status"] == "FAILED"
    assert body["file_validation"]["status"] == "FAIL"


def test_invalid_document_type_returns_422(client):
    resp = client.post(
        "/api/v1/documents/process",
        files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
        data={"document_type": "not_a_real_type"},
    )
    assert resp.status_code == 422


def test_reprocessing_same_document_name_returns_latest(client, sample_docs_dir):
    file_path = sample_docs_dir / "profit_and_loss_2020.pdf"
    for _ in range(2):
        with file_path.open("rb") as f:
            client.post(
                "/api/v1/documents/process",
                files={"file": (file_path.name, f, "application/pdf")},
                data={"document_type": "profit_and_loss"},
            )
    resp = client.get(f"/api/v1/documents/{file_path.name}")
    assert resp.status_code == 200
    assert resp.json()["document_type"] == "profit_and_loss"
