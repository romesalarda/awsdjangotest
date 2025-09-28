from rest_framework.routers import DefaultRouter
from apps.events.api.views import *

registration_router = DefaultRouter()
registration_router.register(r"extra-questions", ExtraQuestionViewSet)
registration_router.register(r"question-choices", QuestionChoiceViewSet)
registration_router.register(r"question-answers", QuestionAnswerViewSet)
registration_router.register(r"participant-questions", ParticipantQuestionViewSet)

location_router = DefaultRouter()
location_router.register(r'countries', CountryLocationViewSet)
location_router.register(r'clusters', ClusterLocationViewSet)
location_router.register(r'chapters', ChapterLocationViewSet)
location_router.register(r'units', UnitLocationViewSet)
location_router.register(r'areas', AreaLocationViewSet)
location_router.register(r"search-areas", SearchAreaSupportLocationViewSet, basename="searcharea")

event_router = DefaultRouter()

event_router.register(r'manage', EventViewSet)
event_router.register(r'service-team', EventServiceTeamMemberViewSet)
event_router.register(r'event-roles', EventRoleViewSet)
event_router.register(r'participants', EventParticipantViewSet)
event_router.register(r"resources", PublicEventResourceViewSet)
event_router.register(r"attendances", EventDayAttendanceViewSet)
location_router.register(r"venues", EventVenueViewSet, basename="eventvenue")

payment_routers = DefaultRouter()
payment_routers.register(r"payment-methods", EventPaymentMethodViewSet)
payment_routers.register(r"payment-packages", EventPaymentPackageViewSet)
payment_routers.register(r"payments", EventPaymentViewSet)
