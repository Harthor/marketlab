from django.urls import include, path

urlpatterns = [
    path('api/', include('api.urls')),
    path('api/paper/', include('paper_trading.urls')),
]
