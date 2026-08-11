from __future__ import annotations

from backend.app.schemas.players import PlayerSummary
from backend.app.services.model_store import ModelUnavailableError, abbreviated_name_candidates, get_player_record, has_tour_model, load_current_model, load_tour_model


CURRENT_ROSTERS = {
    "atp": [
        "Carlos Alcaraz",
        "Jannik Sinner",
        "Novak Djokovic",
        "Alexander Zverev",
        "Taylor Fritz",
        "Ben Shelton",
        "Alex de Minaur",
        "Jack Draper",
        "Daniil Medvedev",
        "Holger Rune",
        "Casper Ruud",
        "Andrey Rublev",
        "Stefanos Tsitsipas",
        "Tommy Paul",
        "Lorenzo Musetti",
    ],
    "wta": [
        "Aryna Sabalenka",
        "Iga Swiatek",
        "Coco Gauff",
        "Elena Rybakina",
        "Jessica Pegula",
        "Jasmine Paolini",
        "Qinwen Zheng",
        "Mirra Andreeva",
        "Naomi Osaka",
        "Madison Keys",
        "Emma Navarro",
        "Elina Svitolina",
        "Daria Kasatkina",
        "Paula Badosa",
        "Ons Jabeur",
    ],
}


def player_id(name: str, tour: str) -> str:
    return f"{tour}:{name.lower().replace(' ', '-')}"


def _summary_from_model_player(player) -> PlayerSummary:
    return PlayerSummary(
        id=player.key.replace("::", ":"),
        name=player.name,
        tour=player.tour,
        ranking=player.ranking,
        ranking_points=player.ranking_points,
        matches=player.matches,
        last_date=player.last_date,
        overall_elo=round(player.overall_elo, 2),
        hard_elo=round(player.surface_elo.get("hard", player.overall_elo), 2),
        clay_elo=round(player.surface_elo.get("clay", player.overall_elo), 2),
        grass_elo=round(player.surface_elo.get("grass", player.overall_elo), 2),
        status="trained",
    )


def _score_match(name: str, query_key: str) -> tuple[int, str]:
    name_key = name.lower()
    if not query_key:
        return (2, name_key)
    if name_key == query_key:
        return (0, name_key)
    if name_key.startswith(query_key):
        return (1, name_key)
    return (2, name_key)


def _matches_query(player_name: str, query_key: str) -> bool:
    if not query_key:
        return True
    name_key = player_name.lower()
    if query_key in name_key:
        return True
    return any(query_key in candidate.lower() or candidate.lower() in name_key for candidate in abbreviated_name_candidates(query_key))


def search_players(query: str, tour: str | None = None, limit: int = 30, offset: int = 0) -> list[PlayerSummary]:
    query_key = query.strip().lower()
    tour_key = tour.lower() if isinstance(tour, str) else None
    if tour_key not in {"atp", "wta"}:
        tour_key = None
    try:
        if tour_key in {"atp", "wta"}:
            models = [load_tour_model(tour_key)]
        else:
            models = []
            for candidate_tour in ("atp", "wta"):
                try:
                    models.append(load_tour_model(candidate_tour))
                except ModelUnavailableError:
                    continue
            if not models:
                models = [load_current_model()]
        rows = [
            _summary_from_model_player(player)
            for model in models
            for player in model.players.values()
            if (tour_key is None or player.tour == tour_key)
            and _matches_query(player.name, query_key)
        ]
        rows.sort(key=lambda item: (_score_match(item.name, query_key), item.ranking or 99999, item.name))
        return rows[offset : offset + limit]
    except ModelUnavailableError:
        pass
    tours = [tour_key] if tour_key in CURRENT_ROSTERS else ["atp", "wta"]
    rows: list[PlayerSummary] = []
    for fallback_tour in tours:
        for name in CURRENT_ROSTERS[fallback_tour]:
            if not query_key or query_key in name.lower():
                rows.append(PlayerSummary(id=player_id(name, fallback_tour), name=name, tour=fallback_tour, status="profile_only"))
    rows.sort(key=lambda item: _score_match(item.name, query_key))
    return rows[offset : offset + limit]


def get_player_by_id(identifier: str) -> PlayerSummary | None:
    try:
        key = identifier.replace(":", "::", 1)
        tour = key.split("::", 1)[0] if "::" in key else ""
        models = [load_tour_model(tour)] if tour in {"atp", "wta"} else [load_current_model()]
        for model in models:
            if key in model.players:
                player = model.players[key]
                return _summary_from_model_player(player)
    except ModelUnavailableError:
        pass
    if ":" not in identifier:
        return None
    tour, slug = identifier.split(":", 1)
    if tour not in CURRENT_ROSTERS:
        return None
    for name in CURRENT_ROSTERS[tour]:
        if player_id(name, tour) == identifier:
            return PlayerSummary(id=identifier, name=name, tour=tour, status="profile_only")
    return None


def tours_for_player_name(name: str) -> set[str]:
    query = name.strip().lower()
    found: set[str] = set()
    try:
        for tour in ("atp", "wta"):
            try:
                model = load_tour_model(tour)
            except ModelUnavailableError:
                continue
            try:
                player = get_player_record(name, tour)
                found.add(player.tour)
                continue
            except ModelUnavailableError:
                pass
            for player in model.players.values():
                if player.name.strip().lower() == query:
                    found.add(player.tour)
    except ModelUnavailableError:
        pass
    for tour, names in CURRENT_ROSTERS.items():
        if any(item.strip().lower() == query for item in names):
            found.add(tour)
    return found


def model_has_tour(tour: str) -> bool:
    return has_tour_model(tour)
