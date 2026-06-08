"""Тесты чистых DTO-мапперов из app/services/photos_serializers.py.

Покрытие:
- folder_to_public: маппинг полей + counts/permission
- _resolve_folder_path: folder_path → folder → None (все ветки)
- photo_to_public / photo_to_public_anon: маппинг + folder_path-резолв + blurhash
- zip_job_to_public: download_url для status==done и иначе None
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.photos_serializers import (
    _resolve_folder_path,
    folder_to_public,
    photo_to_public,
    photo_to_public_anon,
    zip_job_to_public,
)

NOW = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)


def _folder(**over):
    base = {
        "id": uuid.uuid4(),
        "parent_id": None,
        "name": "Album",
        "slug": "album",
        "path": "Album",
        "description": "desc",
        "cover_photo_id": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    base.update(over)
    return SimpleNamespace(**base)


def _photo(**over):
    base = {
        "id": uuid.uuid4(),
        "folder_id": uuid.uuid4(),
        "filename": "a.jpg",
        "original_name": "Original.jpg",
        "size_bytes": 123,
        "mime_type": "image/jpeg",
        "width": 800,
        "height": 600,
        "taken_at": NOW,
        "description": "pic",
        "processed": True,
        "blurhash": "LKO2",
        "uploaded_by": uuid.uuid4(),
        "created_at": NOW,
    }
    base.update(over)
    return SimpleNamespace(**base)


class TestFolderToPublic:
    def test_maps_all_fields_with_counts_and_permission(self):
        f = _folder()
        dto = folder_to_public(
            f, photos_count=5, children_count=2, permission="manager"
        )
        assert dto.id == f.id
        assert dto.name == "Album"
        assert dto.slug == "album"
        assert dto.path == "Album"
        assert dto.description == "desc"
        assert dto.photos_count == 5
        assert dto.children_count == 2
        assert dto.permission == "manager"

    def test_defaults_when_optional_args_omitted(self):
        dto = folder_to_public(_folder())
        assert dto.photos_count == 0
        assert dto.children_count == 0
        assert dto.permission is None


class TestResolveFolderPath:
    def test_explicit_folder_path_wins(self):
        assert _resolve_folder_path(_folder(path="X"), "explicit") == "explicit"

    def test_falls_back_to_folder_path_attr(self):
        assert _resolve_folder_path(_folder(path="FromFolder"), None) == "FromFolder"

    def test_none_when_no_inputs(self):
        assert _resolve_folder_path(None, None) is None


class TestPhotoToPublic:
    def test_maps_fields_and_resolves_path_from_folder(self):
        p = _photo()
        folder = _folder(path="MyAlbum")
        dto = photo_to_public(p, folder)
        assert dto.id == p.id
        assert dto.folder_id == p.folder_id
        assert dto.folder_path == "MyAlbum"
        assert dto.original_name == "Original.jpg"
        assert dto.blurhash == "LKO2"
        assert dto.processed is True

    def test_explicit_folder_path_overrides(self):
        dto = photo_to_public(_photo(), folder=None, folder_path="Forced")
        assert dto.folder_path == "Forced"

    def test_missing_blurhash_attr_defaults_none(self):
        p = _photo()
        del p.blurhash
        dto = photo_to_public(p)
        assert dto.blurhash is None
        assert dto.folder_path is None


class TestPhotoToPublicAnon:
    def test_omits_uploaded_by_and_resolves_path(self):
        p = _photo()
        dto = photo_to_public_anon(p, folder=None, folder_path="Pub")
        assert not hasattr(dto, "uploaded_by")
        assert dto.folder_path == "Pub"
        assert dto.original_name == "Original.jpg"

    def test_missing_blurhash_defaults_none(self):
        p = _photo()
        del p.blurhash
        dto = photo_to_public_anon(p, _folder(path="P"))
        assert dto.blurhash is None
        assert dto.folder_path == "P"


class TestZipJobToPublic:
    def test_done_status_has_download_url(self):
        job = SimpleNamespace(
            id=uuid.uuid4(),
            folder_id=uuid.uuid4(),
            status="done",
            created_at=NOW,
            expires_at=None,
        )
        dto = zip_job_to_public(job)
        assert dto.download_url == f"/api/v1/photos/zip-jobs/{job.id}/download"

    def test_non_done_status_no_url(self):
        job = SimpleNamespace(
            id=uuid.uuid4(),
            folder_id=uuid.uuid4(),
            status="pending",
            created_at=NOW,
            expires_at=NOW,
        )
        dto = zip_job_to_public(job)
        assert dto.download_url is None
        assert dto.status == "pending"
