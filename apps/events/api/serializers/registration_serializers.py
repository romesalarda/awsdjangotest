from rest_framework import serializers
from apps.events.models import ExtraQuestion, QuestionChoice, QuestionAnswer
from apps.events.models.event_models import EventParticipant

class QuestionChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionChoice
        fields = ["id", "text", "value", "order"]
        read_only_fields = ["id"]


class ExtraQuestionSerializer(serializers.ModelSerializer):
    '''
    Serializer for extra questions associated with events.
    '''
    choices = QuestionChoiceSerializer(many=True, read_only=True)
    question_type_display = serializers.CharField(source="get_question_type_display", read_only=True)

    class Meta:
        model = ExtraQuestion
        fields = [
            "id", "event", "question_name", "question_body",
            "question_type", "question_type_display",
            "required", "order", "choices"
        ]
        read_only_fields = ["id"]


class QuestionAnswerSerializer(serializers.ModelSerializer):
    '''
    Serializer for participant's answers to extra questions.
    '''
    question = serializers.PrimaryKeyRelatedField(
        queryset=ExtraQuestion.objects.all()
    )
    question_text = serializers.CharField(source="question.question_body", read_only=True)
    answer_text = serializers.CharField(allow_blank=True, required=False)

    selected_choices = serializers.PrimaryKeyRelatedField(
        queryset=QuestionChoice.objects.all(),
        many=True,
        required=False
    )

    class Meta:
        model = QuestionAnswer
        fields = [
            "id", "participant", "question",
            "answer_text", "selected_choices", "question_text"
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