from backend.app.schemas.prediction import PredictionRequest
from backend.app.services.prediction_service import predict_match


def test_production_predictions_are_approximately_antisymmetric() -> None:
    cases = [
        ("atp", "Carlos Alcaraz", "Jannik Sinner"),
        ("atp", "Novak Djokovic", "Alexander Zverev"),
        ("wta", "Iga Swiatek", "Coco Gauff"),
        ("wta", "Aryna Sabalenka", "Elena Rybakina"),
    ]
    for tour, first, second in cases:
        forward = predict_match(PredictionRequest(player1=first, player2=second, tour=tour, event="Wimbledon")).player1_win_probability
        reverse = predict_match(PredictionRequest(player1=second, player2=first, tour=tour, event="Wimbledon")).player1_win_probability
        assert abs(forward + reverse - 1.0) <= 0.015
