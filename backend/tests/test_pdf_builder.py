from app.models import Finding, Location, ScanResponse
from app.reports.pdf_builder import generate_audit_pdf


def test_generate_audit_pdf_success():
    """Ensure the PDF builder correctly parses findings and outputs a valid PDF byte stream."""
    mock_scan = ScanResponse(
        job_id="test_job_999",
        project_name="Compliance_Test_Repo",
        repo_path="/var/www/secure-repo",
        scanners={"semgrep": {"ok": True, "count": 2}},
        findings=[
            Finding(
                id="vuln-001",
                category="sast",
                severity="CRITICAL",
                title="Unsanitized SQL Input",
                location=Location(path="db/query.py", start_line=42),
                description="Potential SQL injection detected.",
            ),
            Finding(
                id="vuln-002",
                category="secret",
                severity="INFO",
                title="Development API Key",
                location=Location(path="config/settings.py", start_line=12),
                description="Non-production key found in plaintext.",
            ),
        ],
    )

    pdf_bytes = generate_audit_pdf(mock_scan)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")
