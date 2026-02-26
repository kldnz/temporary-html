import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler

from database import engine, get_db, Base, SessionLocal
from models import HTMLPage

# Configuration
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 5 * 1024 * 1024))  # 5MB default
EXPIRATION_OPTIONS = {
    "1": 1,
    "7": 7,
    "30": 30,
    "0": None,  # Indefinite
}

templates = Jinja2Templates(directory="templates")


def cleanup_expired_pages():
    """Delete expired pages from database."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        deleted = db.query(HTMLPage).filter(
            HTMLPage.expires_at.isnot(None),
            HTMLPage.expires_at < now
        ).delete()
        db.commit()
        if deleted > 0:
            print(f"Cleaned up {deleted} expired page(s)")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)

    scheduler = BackgroundScheduler()
    scheduler.add_job(cleanup_expired_pages, 'interval', hours=1)
    scheduler.start()

    yield

    # Shutdown
    scheduler.shutdown()


app = FastAPI(title="Webpage Upload", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the upload form."""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "base_url": BASE_URL,
        "max_size_mb": MAX_UPLOAD_SIZE / (1024 * 1024),
    })


@app.post("/upload")
async def upload_html(
    request: Request,
    html_content: str = Form(None),
    html_file: UploadFile = File(None),
    expiration: str = Form("7"),
    db: Session = Depends(get_db),
):
    """
    Upload HTML content via form or file.
    Returns JSON with the generated link.
    """
    # Get content from either form field or file
    content = None
    if html_file and html_file.filename:
        content = await html_file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE / (1024*1024):.1f}MB"
            )
        content = content.decode('utf-8')
    elif html_content:
        content = html_content
        if len(content.encode('utf-8')) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Content too large. Maximum size is {MAX_UPLOAD_SIZE / (1024*1024):.1f}MB"
            )

    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="No HTML content provided")

    # Validate expiration option
    if expiration not in EXPIRATION_OPTIONS:
        raise HTTPException(status_code=400, detail="Invalid expiration option")

    days = EXPIRATION_OPTIONS[expiration]

    # Create the page
    page = HTMLPage(
        id=HTMLPage.generate_id(),
        content=content,
        expires_at=HTMLPage.calculate_expiration(days),
        content_size=len(content.encode('utf-8')),
    )
    db.add(page)
    db.commit()

    link = f"{BASE_URL}/link/{page.id}"

    # Check if request wants JSON (curl) or HTML (browser)
    accept = request.headers.get("accept", "")
    if "application/json" in accept or "text/plain" in accept:
        return JSONResponse({
            "success": True,
            "link": link,
            "id": page.id,
            "expires_at": page.expires_at.isoformat() if page.expires_at else None,
            "size_bytes": page.content_size,
        })

    # Browser response - show success page
    return templates.TemplateResponse("index.html", {
        "request": request,
        "base_url": BASE_URL,
        "max_size_mb": MAX_UPLOAD_SIZE / (1024 * 1024),
        "success": True,
        "link": link,
        "expires_at": page.expires_at,
        "time_remaining": page.time_remaining,
    })


@app.post("/api/upload")
async def api_upload_html(
    html_file: UploadFile = File(None),
    expiration: int = Form(7),
    db: Session = Depends(get_db),
):
    """
    API endpoint for curl uploads.

    Usage:
        curl -X POST -F "html_file=@myfile.html" -F "expiration=7" https://example.com/api/upload
        curl -X POST -F "html_file=@-" -F "expiration=1" https://example.com/api/upload < myfile.html
    """
    if not html_file:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await html_file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE / (1024*1024):.1f}MB"
        )

    try:
        content_str = content.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be valid UTF-8 text")

    if not content_str.strip():
        raise HTTPException(status_code=400, detail="Empty file")

    # Map expiration days
    if expiration <= 0:
        days = None  # Indefinite
    else:
        days = expiration

    page = HTMLPage(
        id=HTMLPage.generate_id(),
        content=content_str,
        expires_at=HTMLPage.calculate_expiration(days),
        content_size=len(content),
    )
    db.add(page)
    db.commit()

    return {
        "success": True,
        "link": f"{BASE_URL}/link/{page.id}",
        "id": page.id,
        "expires_at": page.expires_at.isoformat() if page.expires_at else None,
        "size_bytes": page.content_size,
    }


@app.get("/link/{page_id}", response_class=HTMLResponse)
async def view_page(page_id: str, db: Session = Depends(get_db)):
    """Serve the uploaded HTML content."""
    page = db.query(HTMLPage).filter(HTMLPage.id == page_id).first()

    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    if page.is_expired:
        # Clean up expired page
        db.delete(page)
        db.commit()
        raise HTTPException(status_code=404, detail="Page has expired")

    return HTMLResponse(content=page.content)


@app.get("/api/info/{page_id}")
async def page_info(page_id: str, db: Session = Depends(get_db)):
    """Get information about a page."""
    page = db.query(HTMLPage).filter(HTMLPage.id == page_id).first()

    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    if page.is_expired:
        db.delete(page)
        db.commit()
        raise HTTPException(status_code=404, detail="Page has expired")

    return {
        "id": page.id,
        "created_at": page.created_at.isoformat(),
        "expires_at": page.expires_at.isoformat() if page.expires_at else None,
        "time_remaining": page.time_remaining,
        "size_bytes": page.content_size,
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}
