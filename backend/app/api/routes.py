from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi import Path as ApiPath

from backend.app.config import get_settings
from backend.app.schemas.coaching import CoachingHelpRequest, CoachingHelpResponse
from backend.app.schemas.players import PlayerSearchResponse, PlayerSummary
from backend.app.schemas.prediction import PredictionRequest, PredictionResponse, TournamentSimulationRequest
from backend.app.services.coaching_service import CoachingServiceError, generate_coaching_help
from backend.app.services.model_store import (
    ModelUnavailableError,
    has_current_model,
    has_tour_model,
    load_current_model,
    load_tour_model,
)
from backend.app.services.prediction_service import predict_match
from backend.app.services.roster_service import get_player_by_id, model_has_tour, search_players, tours_for_player_name
from backend.app.services.security import (
    SecurityValidationError,
    validate_video_signature,
    validate_video_upload_metadata,
)
from backend.app.services.simulation_service import simulate_tournament_draw
from backend.app.services.video_analysis import analyze_pose_video, probe_video

router = APIRouter()
settings = get_settings()


@router.get("/model/version")
def model_version() -> dict:
    atp_loaded = has_tour_model("atp")
    wta_loaded = has_tour_model("wta")
    if atp_loaded or wta_loaded or has_current_model():
        atp_model = load_tour_model("atp") if atp_loaded else load_current_model()
        wta_model = load_tour_model("wta") if wta_loaded else None
        return {
            "model_version": atp_model.version,
            "feature_version": "features-v2-walk-forward",
            "training_status": "real historical artifact loaded",
            "matches_processed": atp_model.matches_processed,
            "generated_at": atp_model.generated_at,
            "tours": {
                "atp": {
                    "loaded": True,
                    "model_version": atp_model.version,
                    "matches_processed": atp_model.matches_processed,
                    "players": len(atp_model.players),
                },
                "wta": {
                    "loaded": wta_model is not None,
                    "model_version": wta_model.version if wta_model else None,
                    "matches_processed": wta_model.matches_processed if wta_model else 0,
                    "players": len(wta_model.players) if wta_model else 0,
                },
            },
        }
    return {
        "model_version": settings.model_version,
        "feature_version": "features-v1",
        "training_status": "no real model artifact loaded",
    }


@router.get("/model/metrics")
def model_metrics() -> dict:
    if has_current_model():
        model = load_current_model()
        return {"status": "ok", **model.metrics}
    return {
        "status": "pending_real_data",
        "accuracy": None,
        "roc_auc": None,
        "log_loss": None,
        "brier_score": None,
        "calibration": [],
    }


@router.get("/health")
def api_health() -> dict:
    atp_loaded = has_tour_model("atp")
    wta_loaded = has_tour_model("wta")
    return {
        "status": "ok",
        "model_loaded": atp_loaded or wta_loaded or has_current_model(),
        "atp_model_loaded": atp_loaded,
        "wta_model_loaded": wta_loaded,
        "model_version": load_tour_model("atp").version if atp_loaded else settings.model_version,
        "api_base": "/api",
        "coaching_help_configured": bool(settings.gemini_api_key),
    }


@router.post("/coaching/help", response_model=CoachingHelpResponse)
async def coaching_help(payload: CoachingHelpRequest) -> CoachingHelpResponse:
    try:
        answer = await asyncio.to_thread(generate_coaching_help, payload.question, payload.context, settings)
    except CoachingServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return CoachingHelpResponse(answer=answer)


@router.get("/players/search", response_model=PlayerSearchResponse)
def players_search(
    q: str = Query(default="", max_length=80),
    tour: str | None = Query(default=None, pattern="^(atp|wta)$"),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
) -> PlayerSearchResponse:
    return PlayerSearchResponse(query=q, results=search_players(q, tour=tour, limit=limit, offset=offset))


@router.get("/players/{player_id}", response_model=PlayerSummary)
def player_profile(player_id: str = ApiPath(..., min_length=2, max_length=120)) -> PlayerSummary:
    player = get_player_by_id(player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found in current local roster.")
    return player


@router.get("/players/{player_id}/ratings")
def player_ratings(player_id: str = ApiPath(..., min_length=2, max_length=120)) -> dict:
    player = get_player_by_id(player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found in current local roster.")
    return {
        "player": player,
        "status": "pending_real_data",
        "ratings": None,
        "note": "Ratings become available after historical matches are imported and chronological Elo snapshots are built.",
    }


@router.get("/players/{player_id}/form")
def player_form(player_id: str = ApiPath(..., min_length=2, max_length=120)) -> dict:
    player = get_player_by_id(player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found in current local roster.")
    return {
        "player": player,
        "status": "pending_real_data",
        "rolling_form": None,
        "note": "Rolling form is intentionally empty until real match rows exist before the query date.",
    }


@router.post("/predict", response_model=PredictionResponse)
def predict(payload: PredictionRequest) -> PredictionResponse:
    started = perf_counter()
    if payload.player1.strip().lower() == payload.player2.strip().lower():
        raise HTTPException(status_code=400, detail="Choose two different players.")
    if payload.tour not in {"atp", "wta"}:
        raise HTTPException(status_code=400, detail="tour must be 'atp' or 'wta'.")
    p1_tours = tours_for_player_name(payload.player1)
    p2_tours = tours_for_player_name(payload.player2)
    if (p1_tours and payload.tour not in p1_tours) or (p2_tours and payload.tour not in p2_tours):
        raise HTTPException(status_code=400, detail="Choose players from the selected tour.")
    if p1_tours and p2_tours and p1_tours.isdisjoint(p2_tours):
        raise HTTPException(status_code=400, detail="Choose players from the same tour.")
    if not model_has_tour(payload.tour):
        raise HTTPException(
            status_code=503,
            detail=f"{payload.tour.upper()} prediction model is not trained yet. Add {payload.tour.upper()} CSVs and rebuild that tour model.",
        )
    if not payload.allow_demo and not has_tour_model(payload.tour):
        raise HTTPException(
            status_code=503,
            detail=f"No real trained {payload.tour.upper()} model artifact is loaded. Place CSVs in work/tennis-data/{payload.tour}/ and run python scripts/train_models.py --tour {payload.tour}.",
        )
    try:
        response = predict_match(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    response.features["prediction_latency_ms"] = round((perf_counter() - started) * 1000, 2)
    return response


@router.get("/head-to-head")
def head_to_head(
    player1: str = Query(..., min_length=2, max_length=80),
    player2: str = Query(..., min_length=2, max_length=80),
) -> dict:
    return {
        "player1": player1,
        "player2": player2,
        "status": "pending_real_data",
        "matches": [],
        "note": "Head-to-head is intentionally empty until historical matches are imported.",
    }


@router.post("/video/validate-upload")
async def validate_video_upload(request: Request, file: UploadFile = File(...)) -> dict:
    started = perf_counter()
    try:
        with TemporaryDirectory(prefix="courtiq-video-") as tmpdir:
            safe, temp_path = await stream_video_upload(file, Path(tmpdir))
            probe = await asyncio.to_thread(probe_video, temp_path, settings)
    except SecurityValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    return {
        "status": "accepted",
        "safe_filename": safe.safe_filename,
        "bytes": safe.size_bytes,
        "content_type": safe.content_type,
        "duration_ms": round((perf_counter() - started) * 1000, 2),
        "request_id": getattr(request.state, "request_id", "untracked"),
        "probe": probe.__dict__,
        "processing_note": "Upload and media structure validated; pose processing remains a bounded local-demo operation.",
    }


@router.post("/video/analyze")
async def analyze_video(request: Request, file: UploadFile = File(...)) -> dict:
    started = perf_counter()
    try:
        with TemporaryDirectory(prefix="courtiq-video-") as tmpdir:
            safe, temp_path = await stream_video_upload(file, Path(tmpdir))
            await asyncio.to_thread(probe_video, temp_path, settings)
            analysis = await asyncio.to_thread(analyze_pose_video, temp_path)
    except SecurityValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Video analysis failed safely. Try a shorter supported clip.") from exc

    return {
        "status": "processed",
        "bytes": safe.size_bytes,
        "content_type": safe.content_type,
        "analysis": analysis,
        "duration_ms": round((perf_counter() - started) * 1000, 2),
        "request_id": getattr(request.state, "request_id", "untracked"),
    }


async def stream_video_upload(file: UploadFile, directory: Path) -> tuple[object, Path]:
    total = 0
    safe_name = None
    temp_path = directory / "pending-upload"
    try:
        with temp_path.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.upload_limit_bytes:
                    raise SecurityValidationError("upload_too_large", "Uploaded video is too large.")
                handle.write(chunk)
        safe_name = validate_video_upload_metadata(
            original_filename=file.filename or "", content_type=file.content_type, size_bytes=total, settings=settings
        )
        final_path = directory / safe_name.safe_filename
        temp_path.replace(final_path)
        validate_video_signature(final_path, safe_name.extension)
        return safe_name, final_path
    finally:
        await file.close()


@router.post("/simulate/tournament")
async def tournament_simulation(payload: TournamentSimulationRequest) -> dict:
    if payload.simulations > settings.max_simulations:
        raise HTTPException(status_code=400, detail=f"simulations must not exceed {settings.max_simulations}")
    try:
        return await asyncio.to_thread(
            simulate_tournament_draw,
            players=payload.players, tour=payload.tour, event=payload.event,
            simulations=payload.simulations, seed=payload.seed,
        )
    except ModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
