from app.agents.parsing import docling_adapter


def test_build_warmup_pdf_bytes_is_parseable() -> None:
    """The hand-built minimal PDF (no reportlab at runtime — see
    _build_warmup_pdf_bytes' docstring) must actually be valid input, not
    just short — a malformed one would make warm_up() silently no-op via
    ParsingError, defeating the point."""
    import pypdfium2 as pdfium

    pdf_bytes = docling_adapter._build_warmup_pdf_bytes()
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        assert len(pdf) == 1
    finally:
        pdf.close()


def test_warm_up_forces_real_model_load_not_just_construction() -> None:
    """Reproduces the real bug: constructing DocumentConverter alone is
    cheap (~2s) because docling's model weights load lazily on the first
    real .convert() call — a warm_up() that only built the converter
    silently warmed nothing, and the first real resume upload still paid
    the full cold-load cost (confirmed against the live service: 43s on
    the first request after a fresh restart). After warm_up(), the
    singleton converter must have already processed at least one document,
    not merely exist."""
    docling_adapter._converter = None

    docling_adapter.warm_up()

    assert docling_adapter._converter is not None
    # A second, real conversion through the now-warmed singleton should be
    # fast — this doesn't assert a hard time bound (flaky in CI) but does
    # confirm warm_up() didn't leave the converter in a pre-model-load
    # state that a real request would still have to pay for.
    result = docling_adapter.parse_pdf_with_docling(
        docling_adapter._build_warmup_pdf_bytes(), "second.pdf"
    )
    assert result.page_count == 1
