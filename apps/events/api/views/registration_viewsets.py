from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from apps.events.models import ExtraQuestion, QuestionChoice, QuestionAnswer, ParticipantQuestion
from apps.events.api.serializers import (
    ExtraQuestionSerializer,
    QuestionChoiceSerializer,
    QuestionAnswerSerializer,
    ParticipantQuestionSerializer
)


class ExtraQuestionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing event registration questions.
    Supports filtering by event ID and ordering by question order.
    """
    queryset = ExtraQuestion.objects.all().order_by("order")
    serializer_class = ExtraQuestionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['event', 'question_type', 'required']
    ordering_fields = ['order', 'question_name']
    ordering = ['order']
    
    def get_queryset(self):
        """
        Optionally filter questions by event.
        """
        queryset = super().get_queryset()
        event_id = self.request.query_params.get('event', None)
        if event_id is not None:
            queryset = queryset.filter(event=event_id)
        return queryset.prefetch_related('choices')


class QuestionChoiceViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing question choices.
    """
    queryset = QuestionChoice.objects.all().order_by("order")
    serializer_class = QuestionChoiceSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['question']
    ordering_fields = ['order', 'text']
    ordering = ['order']


class QuestionAnswerViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing participant answers to registration questions.
    """
    queryset = QuestionAnswer.objects.all().select_related("participant", "question").prefetch_related("selected_choices")
    serializer_class = QuestionAnswerSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['participant', 'question', 'question__event']
    
    def get_queryset(self):
        """
        Filter answers by participant or event.
        """
        queryset = super().get_queryset()
        participant_id = self.request.query_params.get('participant', None)
        event_id = self.request.query_params.get('event', None)
        
        if participant_id is not None:
            queryset = queryset.filter(participant=participant_id)
        if event_id is not None:
            queryset = queryset.filter(question__event=event_id)
            
        return queryset

    
class ParticipantQuestionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing participant questions/inquiries to event organizers.
    """
    queryset = ParticipantQuestion.objects.all().select_related("participant", "event", "answered_by").order_by('-submitted_at')
    serializer_class = ParticipantQuestionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['event', 'participant', 'status', 'questions_type', 'priority']
    ordering_fields = ['submitted_at', 'updated_at', 'priority']
    ordering = ['-submitted_at']
    search_fields = ['question_subject', 'question', 'answer']
    
    def get_queryset(self):
        """
        Filter questions by event or participant.
        """
        queryset = super().get_queryset()
        event_id = self.request.query_params.get('event', None)
        participant_id = self.request.query_params.get('participant', None)
        
        if event_id is not None:
            queryset = queryset.filter(event=event_id)
        if participant_id is not None:
            queryset = queryset.filter(participant=participant_id)
            
        return queryset
