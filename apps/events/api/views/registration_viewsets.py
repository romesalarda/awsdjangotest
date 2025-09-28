from rest_framework import viewsets, permissions
from apps.events.models import ExtraQuestion, QuestionChoice, QuestionAnswer, ParticipantQuestion
from apps.events.api.serializers import (
    ExtraQuestionSerializer,
    QuestionChoiceSerializer,
    QuestionAnswerSerializer,
    ParticipantQuestionSerializer
)


class ExtraQuestionViewSet(viewsets.ModelViewSet):
    queryset = ExtraQuestion.objects.all().order_by("order")
    serializer_class = ExtraQuestionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class QuestionChoiceViewSet(viewsets.ModelViewSet):
    queryset = QuestionChoice.objects.all().order_by("order")
    serializer_class = QuestionChoiceSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class QuestionAnswerViewSet(viewsets.ModelViewSet):
    queryset = QuestionAnswer.objects.all().select_related("participant", "question").prefetch_related("selected_choices")
    serializer_class = QuestionAnswerSerializer
    permission_classes = [permissions.IsAuthenticated]
    
class ParticipantQuestionViewSet(viewsets.ModelViewSet):
    queryset = ParticipantQuestion.objects.filter().order_by("order")
    serializer_class = ParticipantQuestionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
