from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import MatchViewSet, StatsView, ScrapePredictzView, DataExportImportView, StatsResultsView, \
    StatsAdvancedView, TeamViewSet, ScrapeRangeView, LeagueViewSet, MyPredictionsViewSet, JobStatusView

router = DefaultRouter()
router.register(r'leagues', LeagueViewSet)
router.register(r'matches', MatchViewSet, basename='match')
router.register(r'teams', TeamViewSet, basename='team')
router.register(r'my-predictions', MyPredictionsViewSet, basename='my-predictions')

urlpatterns = [
                  path('stats/', StatsView.as_view(), name='stats'),
                  path('stats/results/', StatsResultsView.as_view(), name='stats-results'),
                  path('stats/advanced/', StatsAdvancedView.as_view(), name='stats-advanced'),
                  path('scrape/', ScrapePredictzView.as_view(), name='scrape'),
                  path('scrape/range/', ScrapeRangeView.as_view(), name='scrape-range'),
                  path('data/', DataExportImportView.as_view(), name='data-export-import'),
                  path('jobs/<uuid:job_id>/status/', JobStatusView.as_view(), name='job-status'),
                  path('data/delete-all/', DataExportImportView.as_view(), name='data-delete-all'),
              ] + router.urls
