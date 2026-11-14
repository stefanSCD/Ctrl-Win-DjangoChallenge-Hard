from django.urls import path

from . import views

urlpatterns = [
    path('simulate', views.simulate, name='simulate'),
    path('people/import', views.import_people, name='import-people'),
    path('draft', views.draft, name='draft'),
    path('fights/download', views.download_fights, name='download-fights'),
    path('reset', views.reset_health, name='reset-health'),
]
