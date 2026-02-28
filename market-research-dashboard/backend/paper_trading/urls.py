"""Paper Trading URL configuration."""
from django.urls import path

from .views import (
    EquityCurveView,
    PortfolioDetailView,
    PortfolioListView,
    PositionListView,
    RegimeCurrentView,
    RegimeHistoryView,
    ScorecardView,
    TradeDetailView,
    TradeListView,
)

urlpatterns = [
    path("portfolios/", PortfolioListView.as_view()),
    path("portfolios/<slug:slug>/", PortfolioDetailView.as_view()),
    path("portfolios/<slug:slug>/trades/", TradeListView.as_view()),
    path("portfolios/<slug:slug>/trades/<uuid:trade_id>/", TradeDetailView.as_view()),
    path("portfolios/<slug:slug>/positions/", PositionListView.as_view()),
    path("portfolios/<slug:slug>/equity/", EquityCurveView.as_view()),
    path("portfolios/<slug:slug>/scorecards/", ScorecardView.as_view()),
    # Regime
    path("regime/current/", RegimeCurrentView.as_view()),
    path("regime/history/", RegimeHistoryView.as_view()),
]
