from django.db import models
from django.core import validators
from django.conf import settings
from django.utils.translation import gettext_lazy as _

import uuid

'''
models that help with creating registration forms to sign up for events
'''

class ExtraQuestion(models.Model):
    '''
    E.g. How are you getting to the venue?
    '''
    class QuestionType(models.TextChoices):
        TEXT = "TEXT", _("Text")
        TEXTAREA = "TEXTAREA", _("Text Area")
        INTEGER = "INTEGER", _("Integer")
        BOOLEAN = "BOOLEAN", _("Yes/No")
        CHOICE = "CHOICE", _("Single Choice")
        MULTICHOICE = "MULTICHOICE", _("Multiple Choice")
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("Event", on_delete=models.CASCADE, related_name="extra_questions")
    question_name = models.CharField(_("name of question"), max_length=255)
    question_body = models.TextField(_("question proper"))
    question_type = models.CharField(_("question type"), max_length=20, choices=QuestionType.choices)
    required = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)  # useful for sorting

    def __str__(self):
        return f"{self.question_name} ({self.get_question_type_display()})"
    
class QuestionChoice(models.Model):
    '''
    E.g. 1. CAR  2. PUBLIC TRANSPORT  3. WALKING, etc
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey("ExtraQuestion", on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=255)
    value = models.CharField(max_length=100, blank=True, null=True)  # useful if you want machine-readable values
    order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.text
    
class QuestionAnswer(models.Model):
    '''
    Response to a question that is asked when a participant registers for an event
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey("EventParticipant", on_delete=models.CASCADE, related_name="event_question_answers")
    question = models.ForeignKey("ExtraQuestion", on_delete=models.CASCADE, related_name="question_answers")
    
    # store response in a flexible way
    answer_text = models.TextField(blank=True, null=True)  
    selected_choices = models.ManyToManyField("QuestionChoice", blank=True)  # for choice/multi-choice answers
    
    class Meta:
        unique_together = ("participant", "question")

    def __str__(self):
        return f"{self.participant} - {self.question.question_name}"
    
class ParticipantQuestion(models.Model):
    '''
    Model that allows for participants to submit Q&A for event organizers
    '''
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participant = models.ForeignKey("EventParticipant", on_delete=models.CASCADE, related_name="participant_questions")
    event = models.ForeignKey("Event", on_delete=models.CASCADE, related_name="participant_questions")
    question_subject = models.CharField(max_length=255)
    question = models.TextField(max_length=1000)
    
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    responded_at = models.DateTimeField(blank=True, null=True)
    
    class StatusChoices(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        ANSWERED = "ANSWERED", _("Answered")
        CLOSED = "CLOSED", _("Closed")
    
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING
    )
    admin_notes = models.TextField(blank=True, null=True, help_text="Internal notes for admins")
    answer = models.TextField(blank=True, null=True, help_text="Answer provided by admin")
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="answered_participant_questions",
        help_text="Admin user who answered the question"
    )
    
    class QuestionType(models.TextChoices):
        GENERAL = "GENERAL", _("General")
        CHANGE_REQUEST = "CHANGE_REQUEST", _("Change request")
        OTHER = "OTHER", _("Other")
    
    questions_type = models.CharField(
        max_length=20,
        choices=QuestionType.choices,
        default=QuestionType.GENERAL
    )
    
    class PriorityChoices(models.TextChoices):
        LOW = "LOW", _("Low")
        MEDIUM = "MEDIUM", _("Medium")
        HIGH = "HIGH", _("High")
    
    priority = models.CharField(
        max_length=20,
        choices=PriorityChoices.choices,
        default=PriorityChoices.MEDIUM,
    )
    def __str__(self):
        return f"Question from {self.participant}: {self.question_subject}"