from django.urls import path

from .views import (
    AlertEventDetailView,
    AlertEventDismissView,
    AlertEventsView,
    AlertRuleDetailView,
    AlertRulesView,
    DashboardView,
    DatasetsView,
    DegenWatchlistView,
    HealthView,
    RunDetailView,
    RunHealthView,
    RunPlotView,
    RunsView,
    RunTableView,
    TriggerFetchView,
)

urlpatterns = [
    path('dashboard', DashboardView.as_view()),
    path('health', HealthView.as_view()),
    path('trigger-fetch/', TriggerFetchView.as_view()),
    path('datasets', DatasetsView.as_view()),
    path('runs', RunsView.as_view()),
    path('runs/<str:run_id>', RunDetailView.as_view()),
    path('runs/<str:run_id>/health', RunHealthView.as_view()),
    path('runs/<str:run_id>/table', RunTableView.as_view()),
    path('runs/<str:run_id>/plot', RunPlotView.as_view()),
    # Alert Engine v1
    path('alerts/rules', AlertRulesView.as_view()),
    path('alerts/rules/<str:rule_id>', AlertRuleDetailView.as_view()),
    path('alerts/events', AlertEventsView.as_view()),
    path('alerts/events/<str:event_id>', AlertEventDetailView.as_view()),
    path('alerts/events/<str:event_id>/dismiss', AlertEventDismissView.as_view()),
    # Degen Scanner
    path('degen/watchlist', DegenWatchlistView.as_view()),
]
