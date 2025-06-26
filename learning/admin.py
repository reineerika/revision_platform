from django.contrib import admin
from .models import (
    Document, Quiz, Question, QuestionOption, QuizAttempt, 
    UserAnswer, PerformanceMetrics, StudyGoal
)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'document_type', 'uploaded_by', 'word_count', 'is_processed', 'created_at']
    list_filter = ['document_type', 'is_processed', 'created_at']
    search_fields = ['title', 'description', 'uploaded_by__username']
    readonly_fields = ['word_count', 'extracted_text', 'created_at', 'updated_at']
    ordering = ['-created_at']


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 4
    max_num = 6


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 1
    readonly_fields = ['created_at']


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ['title', 'document', 'created_by', 'difficulty', 'total_questions', 'is_active', 'created_at']
    list_filter = ['difficulty', 'is_active', 'created_at']
    search_fields = ['title', 'description', 'document__title']
    readonly_fields = ['total_questions', 'created_at', 'updated_at']
    inlines = [QuestionInline]
    ordering = ['-created_at']


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['quiz', 'question_type', 'question_text_short', 'points', 'order']
    list_filter = ['question_type', 'quiz__difficulty']
    search_fields = ['question_text', 'quiz__title']
    inlines = [QuestionOptionInline]
    ordering = ['quiz', 'order']

    def question_text_short(self, obj):
        return obj.question_text[:50] + "..." if len(obj.question_text) > 50 else obj.question_text
    question_text_short.short_description = 'Question Text'


@admin.register(QuestionOption)
class QuestionOptionAdmin(admin.ModelAdmin):
    list_display = ['question', 'option_text', 'is_correct', 'order']
    list_filter = ['is_correct', 'question__question_type']
    search_fields = ['option_text', 'question__question_text']
    ordering = ['question', 'order']


class UserAnswerInline(admin.TabularInline):
    model = UserAnswer
    extra = 0
    readonly_fields = ['question', 'user_answer', 'is_correct', 'points_earned', 'answered_at']


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ['user', 'quiz', 'status', 'percentage_score', 'time_taken_minutes', 'started_at', 'completed_at']
    list_filter = ['status', 'quiz__difficulty', 'started_at']
    search_fields = ['user__username', 'quiz__title']
    readonly_fields = ['percentage_score', 'started_at']
    inlines = [UserAnswerInline]
    ordering = ['-started_at']

    def percentage_score(self, obj):
        return f"{obj.percentage_score:.1f}%"
    percentage_score.short_description = 'Score %'


@admin.register(UserAnswer)
class UserAnswerAdmin(admin.ModelAdmin):
    list_display = ['attempt', 'question_short', 'is_correct', 'points_earned', 'answered_at']
    list_filter = ['is_correct', 'question__question_type', 'answered_at']
    search_fields = ['attempt__user__username', 'question__question_text']
    readonly_fields = ['answered_at']
    ordering = ['-answered_at']

    def question_short(self, obj):
        return f"Q{obj.question.order}: {obj.question.question_text[:30]}..."
    question_short.short_description = 'Question'


@admin.register(PerformanceMetrics)
class PerformanceMetricsAdmin(admin.ModelAdmin):
    list_display = ['user', 'document', 'total_attempts', 'best_score', 'average_score', 'mastery_level', 'last_attempt_date']
    list_filter = ['mastery_level', 'document__document_type', 'last_attempt_date']
    search_fields = ['user__username', 'document__title']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-last_attempt_date']


@admin.register(StudyGoal)
class StudyGoalAdmin(admin.ModelAdmin):
    list_display = ['user', 'goal_type', 'target_value', 'current_progress', 'progress_percentage', 'is_achieved', 'deadline']
    list_filter = ['goal_type', 'is_achieved', 'deadline']
    search_fields = ['user__username']
    readonly_fields = ['created_at', 'achieved_at']
    ordering = ['-created_at']