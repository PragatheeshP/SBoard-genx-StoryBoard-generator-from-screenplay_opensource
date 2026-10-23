"""
FastAPI routes for the Screenplay-to-Storyboard Generator.
All API endpoints are mounted under /api.
"""
import logging
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException,
    Depends,
    Response,
    Cookie,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import (
    get_db,
    Project,
    Export as DBExport,
)
from backend.session import get_or_create_session
from backend import ocr, voice, parser, character, imagegen, consistency, assembly, export

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models for request/response schemas
# ─────────────────────────────────────────────────────────────────────────────


class ProjectResponse(BaseModel):
    id: str
    title: Optional[str]
    screenplay_text: Optional[str]
    characters: List[Dict[str, Any]]
    shots: List[Dict[str, Any]]


class CharacterCreateRequest(BaseModel):
    name: str
    reference_type: str  # uploaded, generated, default
    description: Optional[str] = None
    sketch_id: Optional[str] = None


class ShotUpdateRequest(BaseModel):
    action: Optional[str] = None
    shot_type: Optional[str] = None
    camera_angle: Optional[str] = None
    mood: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Helper: get or create project for session
# ─────────────────────────────────────────────────────────────────────────────


def get_or_create_project(session_id: str, db: Session) -> Project:
    """Get existing project for session or create new one."""
    project = db.query(Project).filter(Project.id == session_id).first()
    if not project:
        project = Project(id=session_id)
        db.add(project)
        db.commit()
        db.refresh(project)
        logger.info(f"Created new project: {session_id}")
    return project


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "screenplay-to-storyboard"}


@router.get("/template")
async def get_template():
    """Return the screenplay template documentation."""
    return {"template": parser.get_template_documentation()}


@router.get("/default-sketches")
async def get_default_sketches():
    """Return the built-in character sketch library."""
    char_service = character.get_character_service()
    return {"sketches": char_service.get_default_sketches()}


# ───────────────────────────── Project ───────────────────────────────────────


@router.get("/project", response_model=ProjectResponse)
async def get_project(
    response: Response,
    db: Session = Depends(get_db),
    session_id: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
):
    """Get or create the current project for this session."""
    session_id = get_or_create_session(response, session_id)
    project = get_or_create_project(session_id, db)

    return ProjectResponse(
        id=project.id,
        title=project.title,
        screenplay_text=project.screenplay_text,
        characters=project.get_characters(),
        shots=project.get_shots(),
    )


# ───────────────────────────── Upload ─────────────────────────────────────────


@router.post("/upload/text")
async def upload_text(
    text: str = Form(...),
    response: Response = None,
    db: Session = Depends(get_db),
    session_id: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
):
    """Upload screenplay as pasted text."""
    session_id = get_or_create_session(response, session_id)
    project = get_or_create_project(session_id, db)

    project.screenplay_text = text
    project.screenplay_source = "text"
    db.commit()

    logger.info(f"Text uploaded for project {session_id}")
    return {"status": "ok", "project_id": project.id}


@router.post("/upload/file")
async def upload_file(
    file: UploadFile = File(...),
    response: Response = None,
    db: Session = Depends(get_db),
    session_id: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
):
    """Upload screenplay as PDF or image file."""
    session_id = get_or_create_session(response, session_id)
    project = get_or_create_project(session_id, db)

    # Save uploaded file
    upload_dir = settings.upload_dir / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / file.filename
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Determine if it's an image/PDF requiring OCR
    ext = file.filename.lower().split(".")[-1]
    if ext in ["png", "jpg", "jpeg", "bmp", "tiff", "pdf"]:
        try:
            ocr_service = ocr.get_ocr_service()
            extracted_text = ocr_service.extract_text(str(file_path))
            project.screenplay_text = extracted_text
            project.screenplay_source = "image"
            logger.info(f"OCR extracted {len(extracted_text)} characters")
        except ocr.OCRError as e:
            logger.error(f"OCR failed: {e}")
            raise HTTPException(status_code=400, detail=str(e))
    else:
        # Plain text file
        project.screenplay_text = content.decode("utf-8")
        project.screenplay_source = "file"

    db.commit()
    return {"status": "ok", "project_id": project.id, "text_length": len(project.screenplay_text or "")}


@router.post("/upload/voice")
async def upload_voice(
    file: UploadFile = File(...),
    language: str = Form("hi-IN"),
    response: Response = None,
    db: Session = Depends(get_db),
    session_id: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
):
    """Upload screenplay as voice recording."""
    session_id = get_or_create_session(response, session_id)
    project = get_or_create_project(session_id, db)

    # Save audio file
    upload_dir = settings.upload_dir / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    audio_path = upload_dir / file.filename
    with open(audio_path, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        voice_service = voice.get_voice_service()
        transcribed_text = voice_service.transcribe_screenplay(audio_path, language)
        project.screenplay_text = transcribed_text
        project.screenplay_source = "voice"
        db.commit()
        logger.info(f"Voice transcribed: {len(transcribed_text)} characters")
        return {"status": "ok", "project_id": project.id, "text": transcribed_text}
    except voice.VoiceInputError as e:
        logger.error(f"Voice transcription failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────── Parse ───────────────────────────────────────────


@router.post("/parse")
async def parse_screenplay(
    response: Response,
    db: Session = Depends(get_db),
    session_id: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
):
    """Parse screenplay into structured shot list."""
    session_id = get_or_create_session(response, session_id)
    project = get_or_create_project(session_id, db)

    if not project.screenplay_text:
        raise HTTPException(status_code=400, detail="No screenplay text to parse")

    try:
        parser_service = parser.get_parser_service()
        parsed = parser_service.parse(project.screenplay_text, validate=True)

        # Store structured data
        project.title = parsed.get("title", "Untitled Storyboard")
        project.structured_template = str(parsed)

        # Flatten scenes into shots
        all_shots = []
        shot_counter = 1
        for scene in parsed.get("scenes", []):
            for shot_data in scene.get("shots", []):
                all_shots.append(
                    {
                        "shot_number": shot_counter,
                        "shot_type": shot_data.get("shot_type"),
                        "camera_angle": shot_data.get("camera_angle"),
                        "characters": shot_data.get("characters", []),
                        "action": shot_data.get("action"),
                        "mood": shot_data.get("mood"),
                        "image_path": None,
                    }
                )
                shot_counter += 1

        project.set_shots(all_shots)

        # Extract unique characters
        all_character_names = set()
        for shot in all_shots:
            all_character_names.update(shot.get("characters", []))

        existing_chars = project.get_characters()
        existing_names = {c["name"] for c in existing_chars}
        new_chars = []
        for name in all_character_names:
            if name not in existing_names:
                new_chars.append({"name": name, "reference_type": None})

        project.set_characters(existing_chars + new_chars)
        db.commit()

        logger.info(f"Parsed {len(all_shots)} shots, {len(all_character_names)} characters")
        return {
            "status": "ok",
            "title": project.title,
            "shots": all_shots,
            "characters": list(all_character_names),
        }

    except parser.ParserError as e:
        logger.error(f"Parsing failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ────────────────────────── Characters ───────────────────────────────────────


@router.post("/characters")
async def create_character(
    name: str = Form(...),
    reference_type: str = Form(...),
    description: Optional[str] = Form(None),
    sketch_id: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    response: Response = None,
    db: Session = Depends(get_db),
    session_id: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
):
    """Create or update a character reference."""
    session_id = get_or_create_session(response, session_id)
    project = get_or_create_project(session_id, db)

    char_service = character.get_character_service()
    img_service = imagegen.get_image_service()

    try:
        if reference_type == "uploaded":
            if not file:
                raise HTTPException(status_code=400, detail="No file uploaded")
            # Save uploaded file
            upload_dir = settings.upload_dir / session_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            temp_path = upload_dir / file.filename
            with open(temp_path, "wb") as f:
                f.write(await file.read())
            char_data = char_service.save_uploaded_reference(session_id, name, temp_path)

        elif reference_type == "default":
            if not sketch_id:
                raise HTTPException(status_code=400, detail="No sketch_id provided")
            char_data = char_service.save_default_sketch_reference(session_id, name, sketch_id)

        elif reference_type == "generated":
            if not description:
                raise HTTPException(status_code=400, detail="No description provided")
            char_data = char_service.save_description_reference(session_id, name, description)
            # Generate the reference image
            ref_image = img_service.generate_character_reference(description)
            ref_path = char_service.update_reference_image(session_id, char_data["id"], ref_image)
            char_data["reference_image_path"] = ref_path

        else:
            raise HTTPException(status_code=400, detail=f"Unknown reference_type: {reference_type}")

        # Extract embedding
        if char_data.get("reference_image_path"):
            ref_img = char_service.load_reference_image(char_data["reference_image_path"])
            if ref_img:
                embedding = img_service.extract_embedding(ref_img)
                emb_path = char_service.store_embedding(session_id, char_data["id"], embedding)
                char_data["embedding_path"] = emb_path

        # Update project characters
        chars = project.get_characters()
        # Remove existing entry with same name
        chars = [c for c in chars if c.get("name") != name]
        chars.append(char_data)
        project.set_characters(chars)
        db.commit()

        logger.info(f"Character '{name}' created/updated")
        return {"status": "ok", "character": char_data}

    except character.CharacterError as e:
        logger.error(f"Character creation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error creating character: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────── Generation ───────────────────────────────────────


@router.post("/generate")
async def generate_storyboard(
    response: Response,
    db: Session = Depends(get_db),
    session_id: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
):
    """Generate all storyboard panels."""
    session_id = get_or_create_session(response, session_id)
    project = get_or_create_project(session_id, db)

    if not project.get_shots():
        raise HTTPException(status_code=400, detail="No shots to generate. Parse a screenplay first.")

    try:
        img_service = imagegen.get_image_service()
        char_service = character.get_character_service()

        # Load character references and embeddings
        char_refs = {}
        char_embeds = {}
        for char_data in project.get_characters():
            name = char_data["name"]
            if char_data.get("reference_image_path"):
                img = char_service.load_reference_image(char_data["reference_image_path"])
                if img:
                    char_refs[name] = img
            if char_data.get("embedding_path"):
                emb = char_service.load_embedding(char_data["embedding_path"])
                if emb is not None:
                    char_embeds[name] = emb

        # Generate each shot
        shots = project.get_shots()
        output_dir = settings.output_dir / session_id / "shots"
        output_dir.mkdir(parents=True, exist_ok=True)

        for shot in shots:
            shot_id = str(uuid.uuid4())
            panel_img = img_service.generate_shot(shot, char_refs, char_embeds)
            panel_path = output_dir / f"shot_{shot['shot_number']}_{shot_id}.png"
            panel_img.save(panel_path, "PNG")
            shot["image_path"] = str(panel_path)
            logger.info(f"Generated shot {shot['shot_number']}")

        project.set_shots(shots)
        db.commit()

        return {"status": "ok", "shots_generated": len(shots)}

    except Exception as e:
        logger.error(f"Storyboard generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shots/{shot_number}/regenerate")
async def regenerate_shot(
    shot_number: int,
    action: Optional[str] = Form(None),
    shot_type: Optional[str] = Form(None),
    camera_angle: Optional[str] = Form(None),
    mood: Optional[str] = Form(None),
    response: Response = None,
    db: Session = Depends(get_db),
    session_id: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
):
    """Regenerate a single shot with optional parameter changes."""
    session_id = get_or_create_session(response, session_id)
    project = get_or_create_project(session_id, db)

    shots = project.get_shots()
    shot = next((s for s in shots if s["shot_number"] == shot_number), None)
    if not shot:
        raise HTTPException(status_code=404, detail=f"Shot {shot_number} not found")

    # Update parameters if provided
    if action:
        shot["action"] = action
    if shot_type:
        shot["shot_type"] = shot_type
    if camera_angle:
        shot["camera_angle"] = camera_angle
    if mood:
        shot["mood"] = mood

    try:
        img_service = imagegen.get_image_service()
        char_service = character.get_character_service()

        # Load character data
        char_refs = {}
        char_embeds = {}
        for char_data in project.get_characters():
            name = char_data["name"]
            if char_data.get("reference_image_path"):
                img = char_service.load_reference_image(char_data["reference_image_path"])
                if img:
                    char_refs[name] = img
            if char_data.get("embedding_path"):
                emb = char_service.load_embedding(char_data["embedding_path"])
                if emb is not None:
                    char_embeds[name] = emb

        # Regenerate
        panel_img = img_service.generate_shot(shot, char_refs, char_embeds)
        output_dir = settings.output_dir / session_id / "shots"
        output_dir.mkdir(parents=True, exist_ok=True)
        shot_id = str(uuid.uuid4())
        panel_path = output_dir / f"shot_{shot_number}_{shot_id}.png"
        panel_img.save(panel_path, "PNG")
        shot["image_path"] = str(panel_path)

        project.set_shots(shots)
        db.commit()

        logger.info(f"Regenerated shot {shot_number}")
        return {"status": "ok", "shot": shot}

    except Exception as e:
        logger.error(f"Shot regeneration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shots/{shot_number}/alternatives")
async def get_alternative_angles(
    shot_number: int,
    response: Response = None,
    db: Session = Depends(get_db),
    session_id: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
):
    """Get 1-2 alternative angle/mood suggestions for a shot."""
    session_id = get_or_create_session(response, session_id)
    project = get_or_create_project(session_id, db)

    shots = project.get_shots()
    shot = next((s for s in shots if s["shot_number"] == shot_number), None)
    if not shot:
        raise HTTPException(status_code=404, detail=f"Shot {shot_number} not found")

    try:
        parser_service = parser.get_parser_service()
        suggestions = parser_service.get_alternative_angles(shot, scene_context=project.title or "")
        return {"status": "ok", "suggestions": suggestions}
    except Exception as e:
        logger.warning(f"Could not generate alternatives: {e}")
        return {"status": "ok", "suggestions": []}


# ────────────────────────── Assembly ─────────────────────────────────────────


@router.post("/assemble")
async def assemble_storyboard(
    response: Response,
    db: Session = Depends(get_db),
    session_id: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
):
    """Assemble all panels into a single storyboard sheet."""
    session_id = get_or_create_session(response, session_id)
    project = get_or_create_project(session_id, db)

    shots = project.get_shots()
    if not shots:
        raise HTTPException(status_code=400, detail="No shots to assemble")

    try:
        assembler = assembly.get_assembler()
        sheet_path = assembler.assemble(session_id, project.title or "Storyboard", shots)
        return {"status": "ok", "sheet_path": sheet_path}
    except Exception as e:
        logger.error(f"Assembly failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────── Consistency ──────────────────────────────────────


@router.get("/consistency")
async def evaluate_consistency(
    response: Response,
    db: Session = Depends(get_db),
    session_id: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
):
    """Evaluate character consistency across all panels."""
    session_id = get_or_create_session(response, session_id)
    project = get_or_create_project(session_id, db)

    try:
        char_service = character.get_character_service()
        consist_service = consistency.get_consistency_service()

        # Build character dict with embeddings
        characters = {}
        for char_data in project.get_characters():
            name = char_data["name"]
            if char_data.get("embedding_path"):
                emb = char_service.load_embedding(char_data["embedding_path"])
                if emb is not None:
                    characters[name] = {"embedding": emb}

        results = consist_service.evaluate_storyboard(characters, project.get_shots())
        return {"status": "ok", "consistency": results}

    except Exception as e:
        logger.error(f"Consistency evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ────────────────────────── Export ───────────────────────────────────────────


@router.post("/export/pdf")
async def export_pdf(
    response: Response,
    db: Session = Depends(get_db),
    session_id: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
):
    """Export storyboard as PDF (one panel per page)."""
    session_id = get_or_create_session(response, session_id)
    project = get_or_create_project(session_id, db)

    if not project.get_shots():
        raise HTTPException(status_code=400, detail="No shots to export")

    try:
        export_service = export.get_export_service()
        pdf_path = export_service.export_pdf(session_id, project.title or "Storyboard", project.get_shots())

        # Store export record
        export_id = str(uuid.uuid4())
        db_export = DBExport(
            id=export_id,
            project_id=session_id,
            format="pdf",
            file_path=pdf_path,
        )
        db.add(db_export)
        db.commit()

        return {"status": "ok", "pdf_path": pdf_path, "export_id": export_id}

    except Exception as e:
        logger.error(f"PDF export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export/pptx")
async def export_pptx(
    response: Response,
    db: Session = Depends(get_db),
    session_id: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
):
    """Export storyboard as PowerPoint (four panels per slide)."""
    session_id = get_or_create_session(response, session_id)
    project = get_or_create_project(session_id, db)

    if not project.get_shots():
        raise HTTPException(status_code=400, detail="No shots to export")

    try:
        export_service = export.get_export_service()
        pptx_path = export_service.export_pptx(session_id, project.title or "Storyboard", project.get_shots())

        # Store export record
        export_id = str(uuid.uuid4())
        db_export = DBExport(
            id=export_id,
            project_id=session_id,
            format="pptx",
            file_path=pptx_path,
        )
        db.add(db_export)
        db.commit()

        return {"status": "ok", "pptx_path": pptx_path, "export_id": export_id}

    except Exception as e:
        logger.error(f"PPTX export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/{export_id}/download")
async def download_export(export_id: str, db: Session = Depends(get_db)):
    """Download an exported file."""
    db_export = db.query(DBExport).filter(DBExport.id == export_id).first()
    if not db_export:
        raise HTTPException(status_code=404, detail="Export not found")

    file_path = Path(db_export.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Export file not found")

    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=file_path.name,
    )


# ────────────────────────── Share ────────────────────────────────────────────


@router.post("/share")
async def create_shareable_link(
    response: Response,
    db: Session = Depends(get_db),
    session_id: Optional[str] = Cookie(None, alias=settings.session_cookie_name),
):
    """Create a generic shareable link to the storyboard."""
    session_id = get_or_create_session(response, session_id)
    project = get_or_create_project(session_id, db)

    # Generate simple share URL (no auth, just project ID)
    share_url = f"{settings.host}:{settings.port}/share/{project.id}"
    return {"status": "ok", "share_url": share_url, "project_id": project.id}


@router.get("/share/{project_id}", response_model=ProjectResponse)
async def view_shared_project(project_id: str, db: Session = Depends(get_db)):
    """View a shared project (read-only)."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectResponse(
        id=project.id,
        title=project.title,
        screenplay_text=project.screenplay_text,
        characters=project.get_characters(),
        shots=project.get_shots(),
    )
