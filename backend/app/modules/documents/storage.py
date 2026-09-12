"""Encrypted filesystem storage for confidential documents.

This module has no FastAPI or SQLAlchemy dependency. Callers provide a
seekable binary stream and only persist the opaque storage key returned here.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from base64 import urlsafe_b64decode
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from PIL import Image, UnidentifiedImageError


_MAGIC = b"ROSDOC1"
_NONCE_SIZE = 12
_TAG_SIZE = 16
_CHUNK_SIZE = 256 * 1024

_MIME_EXTENSIONS = {
    "application/pdf": {".pdf"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
}


class DocumentStorageError(RuntimeError):
    """Base storage failure safe to translate at the HTTP boundary."""


class InvalidDocumentFileError(DocumentStorageError):
    """The upload is unsupported, malformed, or exceeds its limit."""


class DocumentIntegrityError(DocumentStorageError):
    """Stored ciphertext or plaintext integrity validation failed."""


@dataclass(frozen=True)
class StoredDocument:
    storage_key: str
    mime_type: str
    size_bytes: int
    sha256: str


def _derive_key(field_encryption_key: str) -> bytes:
    try:
        master_key = urlsafe_b64decode(field_encryption_key.encode())
    except Exception as exc:  # pragma: no cover - defensive config guard
        raise DocumentStorageError("مفتاح تشفير الوثائق غير صالح") from exc
    if len(master_key) != 32:
        raise DocumentStorageError("مفتاح تشفير الوثائق غير صالح")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"resort-os/private-document-v1",
    ).derive(master_key)


def _safe_path(storage_root: str, storage_key: str) -> Path:
    root = Path(storage_root).expanduser().resolve()
    candidate = (root / storage_key).resolve()
    if root != candidate and root not in candidate.parents:
        raise DocumentStorageError("مسار تخزين الوثيقة غير صالح")
    return candidate


def _detect_mime(header: bytes) -> str | None:
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
        return "image/webp"
    return None


def _normalize_content_type(value: str | None) -> str:
    normalized = (value or "").split(";", 1)[0].strip().lower()
    return "image/jpeg" if normalized == "image/jpg" else normalized


def _validate_source(
    source: BinaryIO,
    *,
    original_filename: str,
    declared_content_type: str | None,
    max_size_bytes: int,
) -> tuple[str, int]:
    try:
        source.seek(0, os.SEEK_END)
        size_bytes = source.tell()
        source.seek(0)
    except (AttributeError, OSError) as exc:
        raise InvalidDocumentFileError("تعذر قراءة الملف المرفوع") from exc

    if size_bytes <= 0:
        raise InvalidDocumentFileError("الملف المرفوع فارغ")
    if size_bytes > max_size_bytes:
        raise InvalidDocumentFileError(
            f"حجم الملف يتجاوز الحد المسموح ({max_size_bytes // (1024 * 1024)} MB)"
        )

    header = source.read(16)
    source.seek(0)
    detected_mime = _detect_mime(header)
    if detected_mime is None:
        raise InvalidDocumentFileError("نوع الملف غير مسموح؛ ارفع PDF أو صورة JPEG/PNG/WebP")

    declared_mime = _normalize_content_type(declared_content_type)
    if declared_mime != detected_mime:
        raise InvalidDocumentFileError("نوع محتوى الملف لا يطابق محتواه الفعلي")

    extension = Path(original_filename).suffix.lower()
    if extension not in _MIME_EXTENSIONS[detected_mime]:
        raise InvalidDocumentFileError("امتداد الملف لا يطابق محتواه الفعلي")

    if detected_mime == "application/pdf":
        source.seek(max(0, size_bytes - 2048))
        tail = source.read()
        source.seek(0)
        if b"%%EOF" not in tail:
            raise InvalidDocumentFileError("ملف PDF غير مكتمل أو تالف")
    else:
        try:
            with Image.open(source) as image:
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise InvalidDocumentFileError("ملف الصورة غير صالح أو تالف") from exc
        finally:
            source.seek(0)

    return detected_mime, size_bytes


def store_encrypted(
    source: BinaryIO,
    *,
    storage_root: str,
    storage_key: str,
    public_id: str,
    original_filename: str,
    declared_content_type: str | None,
    field_encryption_key: str,
    max_size_bytes: int,
) -> StoredDocument:
    """Validate, encrypt, and atomically publish one document."""
    mime_type, size_bytes = _validate_source(
        source,
        original_filename=original_filename,
        declared_content_type=declared_content_type,
        max_size_bytes=max_size_bytes,
    )
    target = _safe_path(storage_root, storage_key)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(target.parent, 0o700)
    except OSError:
        pass

    nonce = os.urandom(_NONCE_SIZE)
    encryptor = Cipher(
        algorithms.AES(_derive_key(field_encryption_key)),
        modes.GCM(nonce),
    ).encryptor()
    encryptor.authenticate_additional_data(public_id.encode())
    digest = hashlib.sha256()
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            prefix=".upload-",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as temp_file:
            temp_name = temp_file.name
            os.chmod(temp_name, 0o600)
            temp_file.write(_MAGIC)
            temp_file.write(nonce)
            source.seek(0)
            while chunk := source.read(_CHUNK_SIZE):
                digest.update(chunk)
                temp_file.write(encryptor.update(chunk))
            temp_file.write(encryptor.finalize())
            temp_file.write(encryptor.tag)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_name, target)
        temp_name = None
    except Exception:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
        raise

    return StoredDocument(
        storage_key=storage_key,
        mime_type=mime_type,
        size_bytes=size_bytes,
        sha256=digest.hexdigest(),
    )


def decrypt_verified_to_spooled_file(
    *,
    storage_root: str,
    storage_key: str,
    public_id: str,
    expected_size: int,
    expected_sha256: str,
    field_encryption_key: str,
) -> BinaryIO:
    """Decrypt to a bounded spool and verify before any response bytes leave."""
    source_path = _safe_path(storage_root, storage_key)
    if not source_path.is_file():
        raise DocumentIntegrityError("ملف الوثيقة غير موجود في التخزين الخاص")

    encrypted_size = source_path.stat().st_size
    minimum_size = len(_MAGIC) + _NONCE_SIZE + _TAG_SIZE
    if encrypted_size <= minimum_size:
        raise DocumentIntegrityError("ملف الوثيقة المشفر تالف")

    output = tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    digest = hashlib.sha256()
    plaintext_size = 0
    try:
        with source_path.open("rb") as encrypted:
            if encrypted.read(len(_MAGIC)) != _MAGIC:
                raise DocumentIntegrityError("صيغة ملف الوثيقة المشفر غير معروفة")
            nonce = encrypted.read(_NONCE_SIZE)
            encrypted.seek(-_TAG_SIZE, os.SEEK_END)
            tag = encrypted.read(_TAG_SIZE)
            ciphertext_end = encrypted_size - _TAG_SIZE
            encrypted.seek(len(_MAGIC) + _NONCE_SIZE)

            decryptor = Cipher(
                algorithms.AES(_derive_key(field_encryption_key)),
                modes.GCM(nonce, tag),
            ).decryptor()
            decryptor.authenticate_additional_data(public_id.encode())
            remaining = ciphertext_end - encrypted.tell()
            while remaining > 0:
                chunk = encrypted.read(min(_CHUNK_SIZE, remaining))
                if not chunk:
                    raise DocumentIntegrityError("ملف الوثيقة المشفر غير مكتمل")
                remaining -= len(chunk)
                plaintext = decryptor.update(chunk)
                output.write(plaintext)
                digest.update(plaintext)
                plaintext_size += len(plaintext)
            final = decryptor.finalize()
            output.write(final)
            digest.update(final)
            plaintext_size += len(final)
    except (InvalidTag, OSError) as exc:
        output.close()
        raise DocumentIntegrityError("فشل التحقق من سلامة الوثيقة المشفرة") from exc
    except Exception:
        output.close()
        raise

    if plaintext_size != expected_size or digest.hexdigest() != expected_sha256:
        output.close()
        raise DocumentIntegrityError("بصمة الوثيقة لا تطابق البيانات المسجلة")
    output.seek(0)
    return output


def delete_stored_file(*, storage_root: str, storage_key: str) -> None:
    _safe_path(storage_root, storage_key).unlink(missing_ok=True)


def stored_file_exists(*, storage_root: str, storage_key: str) -> bool:
    return _safe_path(storage_root, storage_key).is_file()
