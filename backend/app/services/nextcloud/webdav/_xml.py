from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import unquote, urlparse

import defusedxml.ElementTree as ET  # noqa: N817

from app.schemas.files import NCItem

from ._constants import _DAV_NS


def parse_propfind(xml_body: bytes, root_url: str) -> list[NCItem]:
    root = ET.fromstring(xml_body)
    items: list[NCItem] = []
    root_url_norm = root_url.rstrip("/")
    root_path_norm = unquote(urlparse(root_url_norm).path).rstrip("/")

    for resp in root.iter(f"{{{_DAV_NS}}}response"):
        href_el = resp.find(f"{{{_DAV_NS}}}href")
        if href_el is None or href_el.text is None:
            continue
        href = href_el.text

        prop = resp.find(f".//{{{_DAV_NS}}}prop")
        if prop is None:
            continue

        is_dir_el = prop.find(f"{{{_DAV_NS}}}resourcetype/{{{_DAV_NS}}}collection")
        is_dir = is_dir_el is not None

        size_el = prop.find(f"{{{_DAV_NS}}}getcontentlength")
        size = int(size_el.text or "0") if size_el is not None and size_el.text else 0

        mime_el = prop.find(f"{{{_DAV_NS}}}getcontenttype")
        mime = mime_el.text if mime_el is not None else None

        lm_el = prop.find(f"{{{_DAV_NS}}}getlastmodified")
        last_modified: datetime | None = None
        if lm_el is not None and lm_el.text:
            with contextlib.suppress(Exception):
                lm = parsedate_to_datetime(lm_el.text)
                if lm.tzinfo is None:

                    lm = lm.replace(tzinfo=UTC)
                last_modified = lm

        etag_el = prop.find(f"{{{_DAV_NS}}}getetag")
        etag = (etag_el.text or "").strip('"') if etag_el is not None else None

        href_decoded = unquote(href)
        name = href_decoded.rstrip("/").rsplit("/", 1)[-1]

        href_path_norm = unquote(urlparse(href_decoded).path).rstrip("/")
        if href_path_norm == root_path_norm:
            continue

        nc_path = href_decoded

        items.append(
            NCItem(
                name=name,
                nc_path=nc_path,
                is_dir=is_dir,
                size_bytes=size,
                mime_type=mime,
                last_modified=last_modified,
                etag=etag,
            )
        )
    return items
