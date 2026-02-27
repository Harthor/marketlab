from django.urls import path

from .views import DatasetsView, RunDetailView, RunHealthView, RunPlotView, RunTableView, RunsView

urlpatterns = [
    path('datasets', DatasetsView.as_view()),
    path('runs', RunsView.as_view()),
    path('runs/<str:run_id>', RunDetailView.as_view()),
    path('runs/<str:run_id>/health', RunHealthView.as_view()),
    path('runs/<str:run_id>/table', RunTableView.as_view()),
    path('runs/<str:run_id>/plot', RunPlotView.as_view()),
]
