from channels.routing import URLRouter
from django.urls import path
from apps.events import consumers

websocket_urlpatterns = [
    path('ws/events/checkin/<uuid:event_id>/', consumers.EventCheckInConsumer.as_asgi()),
    path('ws/events/dashboard/', consumers.EventDashboardConsumer.as_asgi()),
]