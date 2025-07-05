import os
import textract
from django.conf import settings
from django.core.files.storage import default_storage
from .models import Document
import logging
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.db.models import Avg, Count, Sum, Q
from django.utils import timezone
from datetime import timedelta, datetime
from collections import defaultdict
import json


logger = logging.getLogger(__name__)


def get_file_type(filename):
    """Determine file type from filename extension"""
    extension = os.path.splitext(filename)[1].lower()
    type_mapping = {
        '.pdf': 'pdf',
        '.docx': 'docx',
        '.txt': 'txt',
        '.pptx': 'pptx',
    }
    return type_mapping.get(extension, 'unknown')


def validate_file_size(file):
    """Validate uploaded file size"""
    max_size = getattr(settings, 'MAX_UPLOAD_SIZE', 50 * 1024 * 1024)  # 50MB default
    if file.size > max_size:
        raise ValueError(f"File size ({file.size} bytes) exceeds maximum allowed size ({max_size} bytes)")
    return True


def validate_file_type(file):
    """Validate uploaded file type"""
    allowed_types = getattr(settings, 'ALLOWED_DOCUMENT_TYPES', [])
    if file.content_type not in allowed_types:
        raise ValueError(f"File type '{file.content_type}' is not allowed")
    return True


def extract_text_from_document(document):
    """Extract text from uploaded document using textract"""
    try:
        # Get the full path to the uploaded file
        file_path = document.file.path
        
        # Extract text using textract
        text = textract.process(file_path).decode('utf-8')
        
        # Clean up the text
        text = clean_extracted_text(text)
        
        # Update document with extracted text
        document.extracted_text = text
        document.word_count = len(text.split())
        document.is_processed = True
        document.processing_error = ""
        document.save()
        
        logger.info(f"Successfully extracted text from document: {document.title}")
        return text
        
    except Exception as e:
        error_msg = f"Error extracting text from {document.title}: {str(e)}"
        logger.error(error_msg)
        
        # Update document with error information
        document.processing_error = error_msg
        document.is_processed = False
        document.save()
        
        raise Exception(error_msg)


def clean_extracted_text(text):
    """Clean and normalize extracted text"""
    if not text:
        return ""
    
    # Remove excessive whitespace
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        if line:  # Skip empty lines
            cleaned_lines.append(line)
    
    # Join lines with single newlines
    cleaned_text = '\n'.join(cleaned_lines)
    
    # Remove excessive spaces
    import re
    cleaned_text = re.sub(r' +', ' ', cleaned_text)
    
    return cleaned_text


def get_document_summary(text, max_length=500):
    """Generate a summary of the document text"""
    if not text:
        return ""
    
    # Simple summary: take first few sentences up to max_length
    sentences = text.split('. ')
    summary = ""
    
    for sentence in sentences:
        if len(summary + sentence) <= max_length:
            summary += sentence + ". "
        else:
            break
    
    return summary.strip()


def calculate_reading_time(word_count):
    """Calculate estimated reading time in minutes (assuming 200 words per minute)"""
    if word_count <= 0:
        return 0
    return max(1, round(word_count / 200))


def get_document_stats(document):
    """Get comprehensive statistics for a document"""
    if not document.extracted_text:
        return {}
    
    text = document.extracted_text
    words = text.split()
    
    stats = {
        'word_count': len(words),
        'character_count': len(text),
        'paragraph_count': len([p for p in text.split('\n\n') if p.strip()]),
        'sentence_count': len([s for s in text.split('.') if s.strip()]),
        'reading_time_minutes': calculate_reading_time(len(words)),
        'average_words_per_sentence': len(words) / max(1, len([s for s in text.split('.') if s.strip()])),
    }
    
    return stats


def send_revision_reminder_email(user, lesson_title=None):
    """
    Envoie un email de rappel de révision à l'utilisateur
    
    Args:
        user: L'utilisateur à qui envoyer l'email
        lesson_title: Le titre de la leçon à réviser (optionnel)
    """
    if not user.email:
        return False
    
    subject = "Rappel de révision - Plateforme d'apprentissage"
    
    # Préparer le contenu de l'email
    context = {
        'user': user,
        'lesson_title': lesson_title,
    }
    
    # Rendu du template HTML
    html_message = render_to_string('learning/emails/revision_reminder.html', context)
    
    # Version texte simple
    plain_message = strip_tags(html_message)
    
    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Erreur lors de l'envoi de l'email: {e}")
        return False


def send_daily_revision_reminders():
    """
    Envoie des rappels quotidiens à tous les utilisateurs qui ont un email
    """
    users_with_email = User.objects.filter(email__isnull=False).exclude(email='')
    
    for user in users_with_email:
        send_revision_reminder_email(user)
    
    return len(users_with_email)


class LearningAnalytics:
    """Classe pour analyser les données d'apprentissage de l'utilisateur"""
    
    def __init__(self, user):
        self.user = user
        self.now = timezone.now()
    
    def get_user_dashboard_stats(self):
        """Statistiques principales du dashboard"""
        from .models import Document, QuizAttempt, QuizAPIAttempt
        
        # Documents
        total_documents = Document.objects.filter(uploaded_by=self.user).count()
        processed_documents = Document.objects.filter(uploaded_by=self.user, is_processed=True).count()
        
        # Quiz attempts (standards + API)
        standard_attempts = QuizAttempt.objects.filter(user=self.user, status='completed')
        api_attempts = QuizAPIAttempt.objects.filter(user=self.user, status='completed')
        
        total_attempts = standard_attempts.count() + api_attempts.count()
        recent_attempts = (
            standard_attempts.filter(completed_at__gte=self.now - timedelta(days=7)).count() +
            api_attempts.filter(completed_at__gte=self.now - timedelta(days=7)).count()
        )
        
        # Performance (standards + API)
        standard_scores = list(standard_attempts.values_list('score', flat=True))
        api_scores = list(api_attempts.values_list('score', flat=True))
        
        # Calculer le score moyen
        all_scores = standard_scores + api_scores
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
        
        # Study streak
        try:
            profile = self.user.profile
            study_streak = profile.study_streak
            total_points = profile.total_points
        except:
            study_streak = 0
            total_points = 0
        
        return {
            'total_documents': total_documents,
            'processed_documents': processed_documents,
            'total_attempts': total_attempts,
            'recent_attempts': recent_attempts,
            'avg_score': round(avg_score, 1),
            'study_streak': study_streak,
            'total_points': total_points,
        }
    
    def get_performance_over_time(self, days=30):
        """Performance sur le temps"""
        from .models import QuizAttempt, QuizAPIAttempt
        
        end_date = self.now
        start_date = end_date - timedelta(days=days)
        
        # Combiner les tentatives standards et API
        standard_attempts = QuizAttempt.objects.filter(
            user=self.user,
            status='completed',
            completed_at__range=[start_date, end_date]
        )
        
        api_attempts = QuizAPIAttempt.objects.filter(
            user=self.user,
            status='completed',
            completed_at__range=[start_date, end_date]
        )
        
        # Grouper par jour
        daily_performance = defaultdict(list)
        
        for attempt in standard_attempts:
            date_key = attempt.completed_at.strftime('%Y-%m-%d')
            daily_performance[date_key].append(attempt.score)
        
        for attempt in api_attempts:
            date_key = attempt.completed_at.strftime('%Y-%m-%d')
            daily_performance[date_key].append(attempt.score)
        
        # Calculer la moyenne par jour
        performance_data = []
        for date in daily_performance:
            avg_score = sum(daily_performance[date]) / len(daily_performance[date])
            performance_data.append({
                'date': date,
                'score': round(avg_score, 1),
                'attempts': len(daily_performance[date])
            })
        
        return performance_data
    
    def get_subject_performance(self):
        """Performance par sujet/document"""
        from .models import Document, QuizAttempt
        
        documents = Document.objects.filter(uploaded_by=self.user)
        subject_data = []
        
        for doc in documents:
            attempts = QuizAttempt.objects.filter(
                user=self.user,
                quiz__document=doc,
                status='completed'
            )
            
            if attempts.exists():
                avg_score = attempts.aggregate(avg=Avg('score'))['avg']
                total_attempts = attempts.count()
                subject_data.append({
                    'subject': doc.title,
                    'avg_score': round(avg_score, 1),
                    'attempts': total_attempts,
                    'document_id': doc.id
                })
        
        return subject_data
    
    def get_question_type_analysis(self):
        """Analyse par type de question"""
        from .models import UserAnswer, QuizAttempt
        
        user_answers = UserAnswer.objects.filter(
            attempt__user=self.user,
            attempt__status='completed'
        ).select_related('question')
        
        type_analysis = defaultdict(lambda: {'total': 0, 'correct': 0})
        
        for answer in user_answers:
            q_type = answer.question.question_type
            type_analysis[q_type]['total'] += 1
            if answer.is_correct:
                type_analysis[q_type]['correct'] += 1
        
        # Calculer les pourcentages
        result = []
        for q_type, data in type_analysis.items():
            if data['total'] > 0:
                accuracy = (data['correct'] / data['total']) * 100
                result.append({
                    'type': q_type,
                    'total': data['total'],
                    'correct': data['correct'],
                    'accuracy': round(accuracy, 1)
                })
        
        return result
    
    def get_difficulty_analysis(self):
        """Analyse par niveau de difficulté"""
        from .models import QuizAttempt
        
        attempts = QuizAttempt.objects.filter(
            user=self.user,
            status='completed'
        ).select_related('quiz')
        
        difficulty_data = defaultdict(list)
        
        for attempt in attempts:
            if attempt.quiz.difficulty:
                difficulty_data[attempt.quiz.difficulty].append(attempt.score)
        
        result = []
        for difficulty, scores in difficulty_data.items():
            if scores:
                avg_score = sum(scores) / len(scores)
                result.append({
                    'difficulty': difficulty,
                    'avg_score': round(avg_score, 1),
                    'attempts': len(scores)
                })
        
        return result
    
    def get_study_patterns(self):
        """Analyser les patterns d'étude"""
        from .models import QuizAttempt
        
        # Heures d'étude
        attempts = QuizAttempt.objects.filter(
            user=self.user,
            status='completed'
        )
        
        hour_distribution = defaultdict(int)
        for attempt in attempts:
            hour = attempt.completed_at.hour
            hour_distribution[hour] += 1
        
        # Jours de la semaine
        day_distribution = defaultdict(int)
        for attempt in attempts:
            day = attempt.completed_at.strftime('%A')
            day_distribution[day] += 1
        
        return {
            'hour_distribution': dict(hour_distribution),
            'day_distribution': dict(day_distribution)
        }
    
    def get_improvement_suggestions(self):
        """Suggestions d'amélioration basées sur les données"""
        from .models import QuizAttempt
        
        suggestions = []
        
        # Analyser les performances récentes
        recent_attempts = QuizAttempt.objects.filter(
            user=self.user,
            status='completed',
            completed_at__gte=self.now - timedelta(days=7)
        )
        
        if recent_attempts.count() < 3:
            suggestions.append({
                'type': 'activity',
                'message': 'Essayez de faire plus de quiz cette semaine pour améliorer vos compétences.',
                'priority': 'high'
            })
        
        # Analyser la difficulté
        difficulty_analysis = self.get_difficulty_analysis()
        if difficulty_analysis:
            worst_difficulty = min(difficulty_analysis, key=lambda x: x['avg_score'])
            if worst_difficulty['avg_score'] < 70:
                suggestions.append({
                    'type': 'difficulty',
                    'message': f'Concentrez-vous sur les quiz de niveau {worst_difficulty["difficulty"]} pour améliorer vos scores.',
                    'priority': 'medium'
                })
        
        return suggestions