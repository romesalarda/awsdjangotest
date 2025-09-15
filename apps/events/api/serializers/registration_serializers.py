from rest_framework import serializers
from apps.events.models import ExtraQuestion, QuestionChoice, QuestionAnswer


class QuestionChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionChoice
        fields = ["id", "text", "value", "order"]
        read_only_fields = ["id"]


class ExtraQuestionSerializer(serializers.ModelSerializer):
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
    question = ExtraQuestionSerializer(read_only=True)
    question_id = serializers.PrimaryKeyRelatedField(
        queryset=ExtraQuestion.objects.all(),
        source="question",
        write_only=True
    )
    selected_choices = serializers.PrimaryKeyRelatedField(
        queryset=QuestionChoice.objects.all(),
        many=True,
        required=False
    )

    class Meta:
        model = QuestionAnswer
        fields = [
            "id", "participant", "question", "question_id",
            "answer_text", "selected_choices"
        ]
        read_only_fields = ["id"]
