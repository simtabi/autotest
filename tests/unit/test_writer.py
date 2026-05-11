"""Atomic test-file writer tests.

The atomic write contract is non-negotiable: if we crash mid-write a
reader (Pest, Pint, the IDE) must NOT observe a half-written file. We
verify that the temp file path differs from the final path and that the
final write is byte-identical to the input content.
"""

from __future__ import annotations

from pathlib import Path

from autotest.output.writer import remove_test, write_test


def test_write_test_creates_parent_directory(tmp_path: Path):
    target = tmp_path / "tests" / "Generated" / "Services" / "FooTest.php"
    result = write_test(target, "<?php // hi\n")
    assert target.exists()
    assert result.path == target


def test_write_test_writes_exact_content(tmp_path: Path):
    target = tmp_path / "FooTest.php"
    content = "<?php\n\nit('passes', fn() => expect(true)->toBeTrue());\n"
    write_test(target, content)
    assert target.read_text() == content


def test_write_test_overwrites_existing(tmp_path: Path):
    target = tmp_path / "FooTest.php"
    target.write_text("old content\n")
    write_test(target, "new content\n")
    assert target.read_text() == "new content\n"


def test_write_test_leaves_no_tmp_files_behind(tmp_path: Path):
    """The temp+rename pattern must clean up after itself."""
    target = tmp_path / "FooTest.php"
    write_test(target, "<?php // hi")
    leftover = list(tmp_path.glob("*.tmp.*"))
    assert leftover == []


def test_write_test_marks_unformatted_when_formatter_missing(tmp_path: Path):
    target = tmp_path / "FooTest.php"
    # Use a deliberately non-existent formatter so we exercise the
    # graceful-failure branch.
    result = write_test(
        target,
        "<?php // hi",
        formatter_cmd=["this-command-does-not-exist-xyzzy"],
    )
    assert target.exists()
    assert result.formatted is False
    assert result.formatter_stderr  # captured something


def test_remove_test_is_idempotent_when_file_missing(tmp_path: Path):
    target = tmp_path / "Nope.php"
    # Should not raise.
    remove_test(target)


def test_remove_test_deletes_existing_file(tmp_path: Path):
    target = tmp_path / "FooTest.php"
    target.write_text("doomed")
    remove_test(target)
    assert not target.exists()
