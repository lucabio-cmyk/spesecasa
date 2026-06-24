"""Test della riorganizzazione dell'archivio: rinomina parlante dei file e
struttura di directory ordinata (anno/tipo). Livello smoke: niente DB, solo
filesystem temporaneo per LocalStorage."""

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.enums import DocumentType
from app.services import archive
from app.services.storage import LocalStorage


def _doc(**over):
    base = dict(
        household_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        doc_type=DocumentType.BOLLETTA,
        original_filename="scan 0001.PDF",
        mime_type="application/pdf",
        storage_path=None,
        file_hash="a1b2c3d4e5f6a7b8c9d0",
        doc_date=date(2025, 3, 15),
        issuer="Enel Energia S.p.A.",
        total_amount=Decimal("84.50"),
        currency="EUR",
        fiscal_year=2025,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_slugify_strips_accents_and_symbols():
    assert archive.slugify("Società Àcqua & Co.!!") == "societa-acqua-co"
    assert archive.slugify(None) == ""
    assert archive.slugify("   ") == ""


def test_archive_relpath_is_ordered_and_speaking():
    rel = archive.archive_relpath(_doc())
    assert rel == (
        "11111111-1111-1111-1111-111111111111/2025/bolletta/"
        "2025-03-15_enel-energia-s-p-a_84-50eur_a1b2c3d4.pdf"
    )


def test_archive_relpath_handles_missing_metadata():
    rel = archive.archive_relpath(
        _doc(
            doc_type=DocumentType.ALTRO,
            doc_date=None,
            issuer=None,
            total_amount=None,
            fiscal_year=None,
        )
    )
    # Anno sconosciuto, tipo "altro", nessun emittente/importo: restano data
    # ignota e hash, senza doppi separatori.
    assert rel == (
        "11111111-1111-1111-1111-111111111111/senza-anno/altro/"
        "data-ignota_a1b2c3d4.pdf"
    )


def test_year_falls_back_to_doc_date():
    rel = archive.archive_relpath(_doc(fiscal_year=None))
    assert "/2025/" in rel


def test_extension_falls_back_to_mime():
    rel = archive.archive_relpath(_doc(original_filename="senza-estensione"))
    assert rel.endswith(".pdf")


def test_organize_document_moves_and_renames(tmp_path):
    storage = LocalStorage(str(tmp_path))
    # Simula il file appena caricato con nome opaco.
    old_abs = storage.save("inbox/a1b2c3d4_scan.pdf", b"%PDF-1.4 contenuto")
    doc = _doc(storage_path=old_abs)

    moved = archive.organize_document(doc, storage)

    assert moved is True
    assert doc.storage_path != old_abs
    assert doc.storage_path.endswith(
        "/2025/bolletta/2025-03-15_enel-energia-s-p-a_84-50eur_a1b2c3d4.pdf"
    )
    # Il file è davvero stato spostato (vecchio percorso vuoto, nuovo presente).
    assert storage.read(doc.storage_path) == b"%PDF-1.4 contenuto"
    assert not (tmp_path / "inbox" / "a1b2c3d4_scan.pdf").exists()


def test_organize_document_is_idempotent(tmp_path):
    storage = LocalStorage(str(tmp_path))
    old_abs = storage.save("inbox/x.pdf", b"data")
    doc = _doc(storage_path=old_abs)

    assert archive.organize_document(doc, storage) is True
    settled = doc.storage_path
    # Seconda esecuzione: già al posto giusto, nessuno spostamento.
    assert archive.organize_document(doc, storage) is False
    assert doc.storage_path == settled


def test_organize_document_no_path_is_noop(tmp_path):
    storage = LocalStorage(str(tmp_path))
    doc = _doc(storage_path=None)
    assert archive.organize_document(doc, storage) is False
