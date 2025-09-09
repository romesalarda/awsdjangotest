from rest_framework.routers import DefaultRouter
from events.api.views import *

registration_router = DefaultRouter()
registration_router.register(r"extra-questions", ExtraQuestionViewSet)
registration_router.register(r"question-choices", QuestionChoiceViewSet)
registration_router.register(r"question-answers", QuestionAnswerViewSet)

location_router = DefaultRouter()
location_router.register(r'countries', CountryLocationViewSet)
location_router.register(r'clusters', ClusterLocationViewSet)
location_router.register(r'chapters', ChapterLocationViewSet)
location_router.register(r'units', UnitLocationViewSet)
location_router.register(r'areas', AreaLocationViewSet)
location_router.register(r"search-areas", SearchAreaSupportLocationViewSet, basename="searcharea")

event_router = DefaultRouter()

event_router.register(r'events', EventViewSet)
event_router.register(r'event-service-team', EventServiceTeamMemberViewSet)
event_router.register(r'event-roles', EventRoleViewSet)
event_router.register(r'event-participants', EventParticipantViewSet)
event_router.register(r"public-event-resources", PublicEventResourceViewSet)
location_router.register(r"event-venues", EventVenueViewSet, basename="eventvenue")

payment_routers = DefaultRouter()
payment_routers.register(r"event-payment-methods", EventPaymentMethodViewSet)
payment_routers.register(r"event-payment-packages", EventPaymentPackageViewSet)
payment_routers.register(r"event-payments", EventPaymentViewSet)