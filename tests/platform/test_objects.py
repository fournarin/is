"""Content-addressed storage (ADR-019).

The cases worth having are the ones about identity and about what happens when
a write does not finish. Everything ADR-019 chose the filesystem for rests on
two properties: the name of a blob is the hash of its contents, always, and a
half-written upload can never become a blob. If either fails the failure is
silent - a citation to "page 47" quietly pointing at a different document.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pytest

from pdm.contracts import DocumentId
from pdm.platform.objects import (
    STORAGE_ENV,
    FilesystemObjectStore,
    ObjectNotFound,
    ObjectStore,
    storage_root,
)

MANUAL = b"%PDF-1.7\nsynthetic manual, page 47\n"
OTHER = b"%PDF-1.7\na different manual\n"


@pytest.fixture
def store(tmp_path: Path) -> FilesystemObjectStore:
    return FilesystemObjectStore(tmp_path)


class TestIdentityIsContent:
    def test_the_id_is_the_sha256_of_the_bytes(self, store: FilesystemObjectStore) -> None:
        assert store.put(MANUAL) == hashlib.sha256(MANUAL).hexdigest()

    def test_the_same_bytes_are_the_same_document(self, store: FilesystemObjectStore) -> None:
        """The point of ADR-019 point 3: an operator uploading the same file
        twice under two names has uploaded one manual, not two."""
        assert store.put(MANUAL) == store.put(MANUAL)

    def test_different_bytes_are_different_documents(self, store: FilesystemObjectStore) -> None:
        assert store.put(MANUAL) != store.put(OTHER)

    def test_a_second_upload_does_not_rewrite_the_file(self, store: FilesystemObjectStore) -> None:
        """Rewriting would truncate a file another request is streaming, and
        there is nothing to gain: the contents are identical by definition."""
        document_id = store.put(MANUAL)
        written_at = store.path_for(document_id).stat().st_mtime_ns

        assert store.put(MANUAL) == document_id
        assert store.path_for(document_id).stat().st_mtime_ns == written_at

    def test_the_file_is_stored_under_its_own_hash(self, store: FilesystemObjectStore) -> None:
        document_id = store.put(MANUAL)
        path = store.path_for(document_id)

        assert path.name == document_id
        assert hashlib.sha256(path.read_bytes()).hexdigest() == document_id


class TestWritesAreAtomic:
    def test_an_interrupted_upload_stores_nothing(self, store: FilesystemObjectStore) -> None:
        """The property the temp-and-rename exists for. A blob whose contents do
        not match its name is the one state that must never reach disk, because
        every citation in the system trusts that they match."""

        class Fails(BytesIO):
            def read(self, size: int | None = -1) -> bytes:
                raise OSError("the upload was cut off")

        with pytest.raises(OSError, match="cut off"):
            store.put_stream(Fails(MANUAL))

        stored = [path for path in store.root.rglob("*") if path.is_file()]
        assert stored == []

    def test_a_failed_upload_leaves_no_temporary_file(self, store: FilesystemObjectStore) -> None:
        class Fails(BytesIO):
            def read(self, size: int | None = -1) -> bytes:
                raise OSError("the upload was cut off")

        with pytest.raises(OSError):
            store.put_stream(Fails(MANUAL))

        assert list((store.root / "incoming").iterdir()) == []

    def test_a_stored_blob_is_read_only(self, store: FilesystemObjectStore) -> None:
        """Not a security boundary - a determined chmod defeats it. It turns
        "never modify or delete a stored blob" from something to remember into
        an error somebody has to explain."""
        path = store.path_for(store.put(MANUAL))
        with pytest.raises(PermissionError):
            path.open("wb")


class TestReading:
    def test_get_returns_what_was_put(self, store: FilesystemObjectStore) -> None:
        assert store.get(store.put(MANUAL)) == MANUAL

    def test_open_serves_a_byte_range_without_reading_the_rest(
        self, store: FilesystemObjectStore
    ) -> None:
        """What ADR-019 requires for citations. Serving "page 47" of a scanned
        manual must not mean reading the other two hundred pages into memory."""
        document_id = store.put(MANUAL)
        with store.open(document_id) as handle:
            handle.seek(9)
            assert handle.read(9) == b"synthetic"

    def test_size_comes_from_the_file(self, store: FilesystemObjectStore) -> None:
        assert store.size(store.put(MANUAL)) == len(MANUAL)

    def test_exists_answers_both_ways(self, store: FilesystemObjectStore) -> None:
        document_id = store.put(MANUAL)
        assert store.exists(document_id)
        assert not store.exists(DocumentId("0" * 64))

    def test_a_missing_blob_raises_rather_than_returning_nothing(
        self, store: FilesystemObjectStore
    ) -> None:
        """Every caller holds a document row saying the blob should be there, so
        its absence is corruption, not an ordinary miss."""
        missing = DocumentId("0" * 64)
        with pytest.raises(ObjectNotFound):
            store.get(missing)
        with pytest.raises(ObjectNotFound):
            store.size(missing)
        with pytest.raises(ObjectNotFound), store.open(missing):
            pass


class TestLayout:
    def test_blobs_are_spread_over_two_levels_of_prefix(self, store: FilesystemObjectStore) -> None:
        """A flat hex directory degrades on several filesystems once it holds
        tens of thousands of entries, and is unusable for a person looking at
        the volume after an incident."""
        document_id = store.put(MANUAL)
        relative = store.path_for(document_id).relative_to(store.root)

        assert relative.parts == (document_id[:2], document_id[2:4], document_id)

    def test_the_store_satisfies_the_port(self, store: FilesystemObjectStore) -> None:
        assert isinstance(store, ObjectStore)


class TestConfiguration:
    def test_the_storage_root_has_no_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Same reasoning as the database DSN: a default lets the service start
        against the wrong directory and look healthy while writing documents
        somewhere nobody backs up."""
        monkeypatch.delenv(STORAGE_ENV, raising=False)
        with pytest.raises(RuntimeError, match=STORAGE_ENV):
            storage_root()

    def test_the_storage_root_comes_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(STORAGE_ENV, str(tmp_path))
        assert storage_root() == tmp_path


def test_a_large_upload_is_never_held_in_memory_whole(tmp_path: Path) -> None:
    """put_stream must consume its source in chunks. A scanned manual is tens of
    megabytes and several can arrive at once; reading each one entirely into
    memory first is how a 2 GB on-premise box falls over."""
    store = FilesystemObjectStore(tmp_path)
    reads: list[int] = []

    class Counted(BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            # None means "read to the end", which is exactly what must not
            # happen here, so it is recorded as such rather than skipped.
            reads.append(-1 if size is None else size)
            return super().read(size)

    content = b"x" * (3 * 1024 * 1024)
    source: BinaryIO = Counted(content)
    document_id = store.put_stream(source)

    assert store.get(document_id) == content
    assert reads and all(size > 0 for size in reads), "the source was read whole"
    assert max(reads) <= 1024 * 1024
