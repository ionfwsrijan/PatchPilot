from unittest.mock import AsyncMock, patch

import pytest

from app.main import _record_fixes_to_db
from app.models import Fix


@pytest.mark.anyio
async def test_record_fixes_to_db():
    mock_db = AsyncMock()
    fixes = [
        Fix(
            finding_id="semgrep:test-1",
            status="suggested",
            summary="Test fix",
            files_changed=["app/main.py"],
            diff="--- a/app/main.py\n+++ b/app/main.py\n-old_line\n+new_line",
        )
    ]

    with patch("app.main.get_db", AsyncMock(return_value=mock_db)):
        await _record_fixes_to_db("job_123", fixes)

    assert mock_db.executemany.called
    args, kwargs = mock_db.executemany.call_args
    # Verify diff parsing results: adds=1, dels=1 -> mixed
    assert args[1][0][3] == 2  # diff_line_count
    assert args[1][0][4] == 1  # diff_file_count
    assert args[1][0][5] == "mixed"  # fix_type
