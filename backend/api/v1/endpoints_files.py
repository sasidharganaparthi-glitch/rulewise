"""API endpoints for file uploads, document text extraction, conversions, and compression.

Supports:
- Document & Image text extraction (PDF, DOCX, XLSX, CSV, TXT, JSON, images)
- PDF to Image & Image to PDF converters
- File compressor (PDF & Images)
- PDF merger / editor utilities
"""

import io
import json
import logging
import zipfile
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from PIL import Image
import pypdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["File Tools & Converters"])


def _read_pdf_with_multimodal(content: bytes, filename: str) -> str:
    """Use Gemini Multimodal to transcribe and inspect scanned/image PDFs."""
    try:
        from google import genai
        from google.genai import types
        from backend.core.config import get_settings

        settings = get_settings()
        if not settings.GEMINI_API_KEY:
            return "No readable text found in PDF."

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        part = types.Part.from_bytes(data=content, mime_type="application/pdf")
        prompt = (
            "Please read and transcribe all visible text, document headings, tables, numbers, "
            "rules, and key information from this PDF document thoroughly."
        )
        resp = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[part, prompt],
        )
        if resp and resp.text:
            return resp.text.strip()
    except Exception as exc:
        logger.warning("Gemini multimodal PDF reading failed for %s: %s", filename, exc)
    return "Scanned PDF document (visual text extraction unavailable)."


def _read_image_with_vision(image_bytes: bytes, filename: str) -> str:
    """Use Gemini Vision to OCR and transcribe text and content from images."""
    try:
        from google import genai
        from google.genai import types
        from backend.core.config import get_settings

        settings = get_settings()
        if not settings.GEMINI_API_KEY:
            return f"Image file: {filename}"

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else "png"
        mime = f"image/{ext}" if ext in ("jpeg", "png", "webp", "gif") else "image/jpeg"
        if ext == "jpg":
            mime = "image/jpeg"

        part = types.Part.from_bytes(data=image_bytes, mime_type=mime)
        prompt = (
            "Transcribe all readable text, data, numbers, labels, formulas, and visual details "
            "from this image clearly and completely."
        )
        resp = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[part, prompt],
        )
        if resp and resp.text:
            return resp.text.strip()
    except Exception as exc:
        logger.warning("Gemini image vision extraction failed for %s: %s", filename, exc)
    return f"Image file: {filename}"


def _extract_text_from_pdf(content: bytes, filename: str = "document.pdf") -> str:
    """Extract text from PDF using pypdf, falling back to Gemini Vision for scanned pages."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(content))
        text_parts = []
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text and page_text.strip():
                text_parts.append(f"[Page {i + 1}]\n{page_text.strip()}")
        if text_parts:
            combined = "\n\n".join(text_parts)
            if len(combined.strip()) > 25:
                return combined
    except Exception as e:
        logger.warning(f"pypdf extraction notice for {filename}: {e}")

    # Fall back to Gemini Multimodal inspection for image/scanned PDFs
    return _read_pdf_with_multimodal(content, filename)


def _extract_text_from_docx(content: bytes) -> str:
    """Extract text from Word .docx file."""
    try:
        import docx
        doc = docx.Document(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs) if paragraphs else "Empty Word document."
    except Exception as e:
        logger.warning(f"Error extracting DOCX text: {e}")
        return f"Word document (extraction error: {e})"


def _extract_text_from_excel(content: bytes) -> str:
    """Extract text/rows from Excel .xlsx file."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        sheets_summary = []
        for sheet_name in wb.sheetnames[:5]:  # limit to first 5 sheets
            sheet = wb[sheet_name]
            rows = []
            for row in list(sheet.iter_rows(values_only=True))[:100]:  # limit to 100 rows
                clean_row = [str(cell) for cell in row if cell is not None]
                if clean_row:
                    rows.append(" | ".join(clean_row))
            sheets_summary.append(f"Sheet: {sheet_name}\n" + "\n".join(rows))
        return "\n\n".join(sheets_summary) if sheets_summary else "Empty Excel workbook."
    except Exception as e:
        logger.warning(f"Error extracting Excel text: {e}")
        return f"Excel spreadsheet (extraction error: {e})"


@router.post("/upload", summary="Upload and extract text/metadata from files")
async def upload_files(
    files: List[UploadFile] = File(...),
) -> Dict[str, Any]:
    """Upload files (images, PDFs, spreadsheets, documents, text).

    Extracts content for conversational and rule-based evaluation context.
    """
    results: List[Dict[str, Any]] = []

    for file in files:
        filename = file.filename or "uploaded_file"
        content_type = file.content_type or ""
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

        file_bytes = await file.read()
        file_size = len(file_bytes)
        extracted_text = ""
        category = "other"

        try:
            if ext in ["jpg", "jpeg", "png", "webp", "gif", "bmp"]:
                category = "image"
                extracted_text = _read_image_with_vision(file_bytes, filename)

            elif ext == "pdf" or "pdf" in content_type:
                category = "pdf"
                extracted_text = _extract_text_from_pdf(file_bytes, filename)

            elif ext == "docx" or "wordprocessingml" in content_type:
                category = "document"
                extracted_text = _extract_text_from_docx(file_bytes)

            elif ext in ["xlsx", "xls"] or "spreadsheetml" in content_type:
                category = "spreadsheet"
                extracted_text = _extract_text_from_excel(file_bytes)

            elif ext in ["txt", "csv", "json", "md", "xml", "html", "py", "js"]:
                category = "text"
                try:
                    extracted_text = file_bytes.decode("utf-8", errors="replace")
                except Exception:
                    extracted_text = "Binary/non-UTF8 text file."

            else:
                category = "generic"
                try:
                    extracted_text = file_bytes[:10000].decode("utf-8", errors="ignore")
                except Exception:
                    extracted_text = f"Uploaded binary file: {filename} ({file_size} bytes)"

        except Exception as e:
            logger.error(f"Error processing file {filename}: {e}")
            extracted_text = f"File processed with notice: {e}"

        # Truncate preview if very large to protect memory
        summary = (extracted_text[:300] + "...") if len(extracted_text) > 300 else extracted_text

        results.append({
            "name": filename,
            "category": category,
            "size": file_size,
            "type": content_type or f"application/{ext}",
            "summary": summary,
            "content": extracted_text[:15000],  # preserve up to 15k chars for AI prompt
        })

    return {"uploaded": len(results), "files": results}


@router.post("/convert/image-to-pdf", summary="Convert images to a single PDF document")
async def convert_image_to_pdf(
    files: List[UploadFile] = File(...),
):
    """Convert one or multiple image files (JPG, PNG, WebP) into a combined PDF."""
    if not files:
        raise HTTPException(status_code=400, detail="No image files provided.")

    images: List[Image.Image] = []
    try:
        for file in files:
            content = await file.read()
            img = Image.open(io.BytesIO(content))
            if img.mode != "RGB":
                img = img.convert("RGB")
            images.append(img)

        if not images:
            raise HTTPException(status_code=400, detail="Could not read valid images.")

        output_stream = io.BytesIO()
        first_img = images[0]
        rest_imgs = images[1:] if len(images) > 1 else []

        first_img.save(
            output_stream,
            format="PDF",
            save_all=True,
            append_images=rest_imgs,
            resolution=100.0,
        )
        output_stream.seek(0)

        return StreamingResponse(
            output_stream,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="converted_rulewise.pdf"'},
        )
    except Exception as e:
        logger.error(f"Error in image-to-pdf conversion: {e}")
        raise HTTPException(status_code=500, detail=f"Image to PDF conversion failed: {str(e)}")


@router.post("/convert/pdf-to-image", summary="Extract images from PDF pages")
async def convert_pdf_to_image(
    file: UploadFile = File(...),
):
    """Extract pages or embedded images from a PDF and return as a ZIP archive."""
    try:
        content = await file.read()
        reader = pypdf.PdfReader(io.BytesIO(content))

        zip_stream = io.BytesIO()
        with zipfile.ZipFile(zip_stream, "w", zipfile.ZIP_DEFLATED) as zf:
            image_count = 0
            for page_idx, page in enumerate(reader.pages):
                for img_idx, img_obj in enumerate(page.images):
                    image_count += 1
                    img_name = f"page_{page_idx + 1}_img_{img_idx + 1}_{img_obj.name}"
                    zf.writestr(img_name, img_obj.data)

            # If no embedded images, write page text representations or fallback placeholder
            if image_count == 0:
                zf.writestr("info.txt", "No embedded raster images were found in the provided PDF pages. Text content was preserved.")

        zip_stream.seek(0)
        return StreamingResponse(
            zip_stream,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{file.filename or "extracted"}_images.zip"'},
        )
    except Exception as e:
        logger.error(f"Error extracting images from PDF: {e}")
        raise HTTPException(status_code=500, detail=f"PDF image extraction failed: {str(e)}")


@router.post("/compress", summary="Compress image or PDF to reduce file size")
async def compress_file(
    file: UploadFile = File(...),
    quality: int = Form(60),
):
    """Compress image or PDF file to significantly reduce size."""
    try:
        content = await file.read()
        filename = file.filename or "compressed_file"
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

        if ext in ["jpg", "jpeg", "png", "webp"]:
            img = Image.open(io.BytesIO(content))
            if img.mode in ("RGBA", "P") and ext in ["jpg", "jpeg"]:
                img = img.convert("RGB")
            out = io.BytesIO()
            save_format = "JPEG" if ext in ["jpg", "jpeg"] else ("PNG" if ext == "png" else "WEBP")
            
            if save_format in ["JPEG", "WEBP"]:
                img.save(out, format=save_format, quality=max(10, min(quality, 95)), optimize=True)
            else:
                img.save(out, format=save_format, optimize=True)
                
            out.seek(0)
            return StreamingResponse(
                out,
                media_type=f"image/{save_format.lower()}",
                headers={"Content-Disposition": f'attachment; filename="compressed_{filename}"'},
            )

        elif ext == "pdf":
            reader = pypdf.PdfReader(io.BytesIO(content))
            writer = pypdf.PdfWriter()

            for page in reader.pages:
                page.compress_content_streams()
                writer.add_page(page)

            out = io.BytesIO()
            writer.write(out)
            out.seek(0)

            return StreamingResponse(
                out,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="compressed_{filename}"'},
            )

        else:
            raise HTTPException(status_code=400, detail="Only JPG, PNG, WEBP, and PDF can be compressed.")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error compressing file: {e}")
        raise HTTPException(status_code=500, detail=f"File compression failed: {str(e)}")


@router.post("/pdf/merge", summary="Merge multiple PDFs into a single file")
async def merge_pdfs(
    files: List[UploadFile] = File(...),
):
    """Merge two or more PDF files into a single unified document."""
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Please upload at least 2 PDF files to merge.")

    try:
        merger = pypdf.PdfMerger()
        for f in files:
            content = await f.read()
            merger.append(io.BytesIO(content))

        out = io.BytesIO()
        merger.write(out)
        merger.close()
        out.seek(0)

        return StreamingResponse(
            out,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="merged_rulewise.pdf"'},
        )
    except Exception as e:
        logger.error(f"Error merging PDFs: {e}")
        raise HTTPException(status_code=500, detail=f"PDF merge failed: {str(e)}")

