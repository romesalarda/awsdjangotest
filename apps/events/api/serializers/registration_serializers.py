from rest_framework import serializers
from apps.events.models import ExtraQuestion, QuestionChoice, QuestionAnswer, ParticipantQuestion
from apps.events.models.event_models import EventParticipant
from django.shortcuts import get_object_or_404

class QuestionChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionChoice
        fields = ["id", "text", "value", "order"]
        read_only_fields = ["id"]


class ExtraQuestionSerializer(serializers.ModelSerializer):
    """
    Serializer for extra questions associated with events with nested choice creation.
    
    Example API object:
    {
        "event": "456e7890-e89b-12d3-a456-426614174001",  // Event UUID
        "question_name": "Dietary Requirements",
        "question_body": "Do you have any dietary requirements or food allergies?",
        "question_type": "MULTICHOICE",
        "required": true,
        "order": 1,
        "choice_data": [
            {
                "text": "Vegetarian",
                "value": "vegetarian",
                "order": 1
            },
            {
                "text": "Vegan",
                "value": "vegan",
                "order": 2
            },
            {
                "text": "Gluten Free",
                "value": "gluten_free",
                "order": 3
            },
            {
                "text": "No Requirements",
                "value": "none",
                "order": 4
            }
        ]
    }
    
    Response includes additional computed fields:
    {
        "id": "123e4567-e89b-12d3-a456-426614174005",
        "question_type_display": "Multiple Choice",
        "choices": [
            {
                "id": "234e5678-e89b-12d3-a456-426614174006",
                "text": "Vegetarian",
                "value": "vegetarian",
                "order": 1
            }
            // ... other choices
        ]
    }
    """
    choices = QuestionChoiceSerializer(many=True, read_only=True)
    question_type_display = serializers.CharField(source="get_question_type_display", read_only=True)
    
    # Write-only field for creating choices
    choice_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text="List of choice dicts to create for this question"
    )

    class Meta:
        model = ExtraQuestion
        fields = [
            "id", "event", "question_name", "question_body",
            "question_type", "question_type_display",
            "required", "order", "choices", "choice_data"
        ]
        read_only_fields = ["id", "question_type_display"]
        
    def create(self, validated_data):
        choice_data = validated_data.pop('choice_data', [])
        
        # Create the question
        question = super().create(validated_data)
        
        # Create choices if this is a choice/multichoice question
        if question.question_type in [ExtraQuestion.QuestionType.CHOICE, ExtraQuestion.QuestionType.MULTICHOICE]:
            for choice_dict in choice_data:
                QuestionChoice.objects.create(
                    question=question,
                    text=choice_dict.get('text', ''),
                    value=choice_dict.get('value', choice_dict.get('text', '')),
                    order=choice_dict.get('order', 0)
                )
        
        return question
    
    def update(self, instance, validated_data):
        choice_data = validated_data.pop('choice_data', None)
        
        # Update the question
        question = super().update(instance, validated_data)
        
        # Handle choices updates (replace existing)
        if choice_data is not None and question.question_type in [ExtraQuestion.QuestionType.CHOICE, ExtraQuestion.QuestionType.MULTICHOICE]:
            # Delete existing choices
            question.choices.all().delete()
            
            # Create new choices
            for choice_dict in choice_data:
                QuestionChoice.objects.create(
                    question=question,
                    text=choice_dict.get('text', ''),
                    value=choice_dict.get('value', choice_dict.get('text', '')),
                    order=choice_dict.get('order', 0)
                )
        
        return question


class QuestionAnswerSerializer(serializers.ModelSerializer):
    """
    Serializer for participant's answers to extra questions with validation and choice handling.
    
    Example API object for TEXT/TEXTAREA question:
    {
        "participant": "123e4567-e89b-12d3-a456-426614174000",  // EventParticipant UUID
        "question": "234e5678-e89b-12d3-a456-426614174005",   // ExtraQuestion UUID
        "answer_text": "I am allergic to nuts and dairy products"
    }
    
    Example API object for CHOICE question:
    {
        "participant": "123e4567-e89b-12d3-a456-426614174000",
        "question": "345e6789-e89b-12d3-a456-426614174006",
        "selected_choices": ["456e7890-e89b-12d3-a456-426614174007"]  // Single choice ID
    }
    
    Example API object for MULTICHOICE question:
    {
        "participant": "123e4567-e89b-12d3-a456-426614174000",
        "question": "567e8901-e89b-12d3-a456-426614174008",
        "selected_choices": [
            "678e9012-e89b-12d3-a456-426614174009",
            "789e0123-e89b-12d3-a456-426614174010"
        ]
    }
    
    Example API object for BOOLEAN question:
    {
        "participant": "123e4567-e89b-12d3-a456-426614174000",
        "question": "890e1234-e89b-12d3-a456-426614174011",
        "answer_text": "true"  // or "false", "yes", "no"
    }
    
    Response includes additional computed fields:
    {
        "id": "901e2345-e89b-12d3-a456-426614174012",
        "question_text": "Do you have any dietary requirements or food allergies?"
    }
    """
    question = serializers.PrimaryKeyRelatedField(
        queryset=ExtraQuestion.objects.all()
    )
    question_text = serializers.CharField(source="question.question_body", read_only=True)
    answer_text = serializers.CharField(allow_blank=True, required=False)

    selected_choices = serializers.PrimaryKeyRelatedField(
        queryset=QuestionChoice.objects.all(),
        many=True,
        required=False,
        write_only=True
    )
    # selected choices display field as list
    selected_choices_display = serializers.ListSerializer(
        child=serializers.CharField(),
        source="selected_choices",
        read_only=True
    )

    class Meta:
        model = QuestionAnswer
        fields = [
            "id", "participant", "question",
            "answer_text", "selected_choices", "question_text", "selected_choices_display"
        ]
        read_only_fields = ["id", "participant", "question_text"]
        
    def validate(self, data):
        '''
        Ensure answers align with question types and requirements.
        '''
        question = data.get("question")
        answer_text = data.get("answer_text", "").strip()
        selected_choices = data.get("selected_choices", [])

        if question.question_type in [ExtraQuestion.QuestionType.CHOICE, ExtraQuestion.QuestionType.MULTICHOICE]:
            if not selected_choices:
                raise serializers.ValidationError("At least one choice must be selected for choice/multi-choice questions.")
            if question.question_type == ExtraQuestion.QuestionType.CHOICE and len(selected_choices) > 1:
                raise serializers.ValidationError("Only one choice can be selected for single choice questions.")
        else:
            if selected_choices:
                raise serializers.ValidationError("Choices should not be selected for non-choice questions.")

        if question.required:
            if question.question_type in [ExtraQuestion.QuestionType.TEXT, ExtraQuestion.QuestionType.TEXTAREA, ExtraQuestion.QuestionType.INTEGER]:
                if not answer_text:
                    raise serializers.ValidationError("This question is required and must be answered.")
            elif question.question_type == ExtraQuestion.QuestionType.BOOLEAN:
                if answer_text.lower() not in ["true", "false", "yes", "no"]:
                    raise serializers.ValidationError("A valid boolean answer (true/false) is required.")
        
        for choice in selected_choices:
            if choice.question != question:
                raise serializers.ValidationError(f"The choice '{choice}' does not belong to the question '{question}'.")
                
        return data
    
    def create(self, validated_data):
        # Ensure unique constraint is maintained (participant, question)
        participant = validated_data.get('participant')
        question = validated_data.get('question')
        
        # Check if answer already exists and update instead of creating duplicate
        existing_answer = QuestionAnswer.objects.filter(
            participant=participant, 
            question=question
        ).first()
        
        if existing_answer:
            # Update existing answer
            for attr, value in validated_data.items():
                setattr(existing_answer, attr, value)
            existing_answer.save()
            
            # Handle selected_choices for existing answer
            if 'selected_choices' in validated_data:
                existing_answer.selected_choices.set(validated_data['selected_choices'])
                
            return existing_answer
        
        # Create new answer
        selected_choices = validated_data.pop('selected_choices', [])
        answer = super().create(validated_data)
        
        # Set selected choices
        if selected_choices:
            answer.selected_choices.set(selected_choices)
            
        return answer
    
    def update(self, instance, validated_data):
        selected_choices = validated_data.pop('selected_choices', None)
        
        # Update the answer
        answer = super().update(instance, validated_data)
        
        # Update selected choices if provided
        if selected_choices is not None:
            answer.selected_choices.set(selected_choices)
            
        return answer


class ParticipantQuestionSerializer(serializers.ModelSerializer):
    """
    Serializer for participant questions (Q&A system for event organizers).
    
    Example API object:
    {
        "participant": "123e4567-e89b-12d3-a456-426614174000",  // EventParticipant UUID
        "event": "456e7890-e89b-12d3-a456-426614174001",       // Event UUID
        "question_subject": "Change Request",
        "question": "Can I change my dietary preference from vegetarian to vegan?",
        "questions_type": "CHANGE_REQUEST",
        "priority": "MEDIUM"
    }
    
    Response includes additional computed fields:
    {
        "id": "789e0123-e89b-12d3-a456-426614174002",
        "submitted_at": "2024-01-15T10:30:00Z",
        "status": "PENDING",
        "status_display": "Pending",
        "questions_type_display": "Change request",
        "priority_display": "Medium",
        "participant_name": "John Doe",
        "answered_by_name": null
    }
    """
    participant_name = serializers.CharField(source="participant.user.get_full_name", read_only=True)
    answered_by_name = serializers.CharField(source="answered_by.get_full_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    questions_type_display = serializers.CharField(source="get_questions_type_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    participant_pax_id = serializers.CharField(write_only=True)

    class Meta:
        model = ParticipantQuestion
        fields = [
            "id", "participant", "event", "question_subject", "question",
            "submitted_at", "updated_at", "responded_at", "status", "status_display",
            "admin_notes", "answer", "answered_by", "answered_by_name",
            "questions_type", "questions_type_display", "priority", "priority_display",
            "participant_name", "participant_pax_id"
        ]
        read_only_fields = [
            "id", "submitted_at", "updated_at", "participant_name", 
            "answered_by_name", "status_display", "questions_type_display", "priority_display", "participant"
        ]
        
    def validate(self, data):
        """
        Ensure required fields are present and valid.
        """
        # if not data.get('question_subject', '').strip():
        #     raise serializers.ValidationError("Question subject is required.")
        
        # if not data.get('question', '').strip():
        #     raise serializers.ValidationError("Question body is required.")
            
        return data
    
    def create(self, validated_data):
        participant = get_object_or_404(EventParticipant, event_pax_id=validated_data.pop("participant_pax_id", None))
        validated_data["participant_id"] = participant.pk
        obj = super().create(validated_data)
        return obj