from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
import json


class Document(models.Model):
    """Model for uploaded study documents"""
    DOCUMENT_TYPES = [
        ('pdf', 'PDF'),
        ('docx', 'Word Document'),
        ('txt', 'Text File'),
        ('pptx', 'PowerPoint'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='documents/')
    document_type = models.CharField(max_length=10, choices=DOCUMENT_TYPES)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    extracted_text = models.TextField(blank=True)
    word_count = models.IntegerField(default=0)
    is_processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']


class Quiz(models.Model):
    """Model for generated quizzes"""
    DIFFICULTY_LEVELS = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='quizzes')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_quizzes')
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_LEVELS, default='medium')
    time_limit_minutes = models.IntegerField(default=30)
    is_active = models.BooleanField(default=True)
    total_questions = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']


class Question(models.Model):
    """Model for quiz questions"""
    QUESTION_TYPES = [
        ('multiple_choice', 'Multiple Choice'),
        ('true_false', 'True/False'),
        ('short_answer', 'Short Answer'),
        ('fill_blank', 'Fill in the Blank'),
    ]
    
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    correct_answer = models.TextField()
    explanation = models.TextField(blank=True)
    points = models.IntegerField(default=1)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Q{self.order}: {self.question_text[:50]}..."

    class Meta:
        ordering = ['order']


class QuestionOption(models.Model):
    """Model for multiple choice question options"""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    option_text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.option_text} ({'Correct' if self.is_correct else 'Incorrect'})"

    class Meta:
        ordering = ['order']


class QuizAttempt(models.Model):
    """Model for user quiz attempts"""
    STATUS_CHOICES = [
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quiz_attempts')
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')
    score = models.FloatField(default=0.0)
    total_points = models.IntegerField(default=0)
    earned_points = models.IntegerField(default=0)
    time_taken_minutes = models.IntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.quiz.title} ({self.status})"

    @property
    def percentage_score(self):
        if self.total_points > 0:
            return (self.earned_points / self.total_points) * 100
        return 0

    class Meta:
        ordering = ['-started_at']


class UserAnswer(models.Model):
    """Model for user answers to questions"""
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    user_answer = models.TextField()
    is_correct = models.BooleanField(default=False)
    points_earned = models.IntegerField(default=0)
    time_taken_seconds = models.IntegerField(default=0)
    answered_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.attempt.user.username} - Q{self.question.order}"

    class Meta:
        unique_together = ['attempt', 'question']


class PerformanceMetrics(models.Model):
    """Model for tracking user performance metrics"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='performance_metrics')
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='performance_metrics')
    total_attempts = models.IntegerField(default=0)
    best_score = models.FloatField(default=0.0)
    average_score = models.FloatField(default=0.0)
    total_time_minutes = models.IntegerField(default=0)
    mastery_level = models.CharField(
        max_length=20,
        choices=[
            ('beginner', 'Beginner'),
            ('intermediate', 'Intermediate'),
            ('advanced', 'Advanced'),
            ('expert', 'Expert'),
        ],
        default='beginner'
    )
    last_attempt_date = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.document.title} ({self.mastery_level})"

    class Meta:
        unique_together = ['user', 'document']


class StudyGoal(models.Model):
    """Model for user study goals"""
    GOAL_TYPES = [
        ('daily_questions', 'Daily Questions'),
        ('weekly_quizzes', 'Weekly Quizzes'),
        ('score_target', 'Score Target'),
        ('streak_target', 'Streak Target'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='study_goals')
    goal_type = models.CharField(max_length=20, choices=GOAL_TYPES)
    target_value = models.IntegerField()
    current_progress = models.IntegerField(default=0)
    deadline = models.DateField(blank=True, null=True)
    is_achieved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    achieved_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_goal_type_display()}: {self.target_value}"

    @property
    def progress_percentage(self):
        if self.target_value > 0:
            return min((self.current_progress / self.target_value) * 100, 100)
        return 0

    class Meta:
        ordering = ['-created_at']


class QuizAPIResult(models.Model):
    document = models.ForeignKey('Document', on_delete=models.CASCADE, related_name='api_quizzes')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='api_quizzes')
    title = models.CharField(max_length=255, blank=True)
    api_response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    time_limit_minutes = models.PositiveIntegerField(default=30)
    difficulty = models.CharField(max_length=50, default='easy')
    num_questions = models.PositiveIntegerField(default=6)

    def __str__(self):
        return f"{self.title} - {self.user.username}"


class QuizAPIAttempt(models.Model):
    """Model for user attempts on API-generated quizzes"""
    STATUS_CHOICES = [
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_quiz_attempts')
    quiz_api = models.ForeignKey(QuizAPIResult, on_delete=models.CASCADE, related_name='attempts')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')
    score = models.FloatField(default=0.0)
    total_questions = models.IntegerField(default=0)
    correct_answers = models.IntegerField(default=0)
    time_taken_minutes = models.IntegerField(default=0)
    answers = models.JSONField(default=dict)  # Stocker les réponses utilisateur
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.quiz_api.title} ({self.status})"

    @property
    def percentage_score(self):
        if self.total_questions > 0:
            return (self.correct_answers / self.total_questions) * 100
        return 0

    class Meta:
        ordering = ['-started_at']