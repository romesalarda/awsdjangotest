from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('checkin/<uuid:event_id>/', consumers.EventCheckInConsumer.as_asgi()),
    path('dashboard/', consumers.EventDashboardConsumer.as_asgi()),
]