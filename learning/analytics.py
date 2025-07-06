from django.db.models import Avg, Count, Sum, Max, Min, Q
from django.utils import timezone
from datetime import datetime, timedelta
from collections import defaultdict
import json

from .models import (
    Document, Quiz, QuizAttempt, UserAnswer, PerformanceMetrics, 
    Question, StudyGoal, QuizAPIAttempt
)
from users.models import StudySession


class LearningAnalytics:
    """Analytics service for learning performance tracking"""
    
    def __init__(self, user):
        self.user = user
    
    def get_user_dashboard_stats(self):
        """Get comprehensive dashboard statistics for user"""
        # Basic counts
        total_documents = Document.objects.filter(uploaded_by=self.user).count()
        total_quizzes = Quiz.objects.filter(document__uploaded_by=self.user).count()
        
        # Include both regular and API attempts
        total_attempts = QuizAttempt.objects.filter(user=self.user).count()
        api_attempts = QuizAPIAttempt.objects.filter(user=self.user).count()
        total_attempts += api_attempts
        
        completed_attempts = QuizAttempt.objects.filter(user=self.user, status='completed').count()
        completed_api_attempts = QuizAPIAttempt.objects.filter(user=self.user, status='completed').count()
        completed_attempts += completed_api_attempts
        
        # Performance metrics - combine both types
        regular_scores = QuizAttempt.objects.filter(
            user=self.user, status='completed'
        ).values_list('score', flat=True)
        
        api_scores = QuizAPIAttempt.objects.filter(
            user=self.user, status='completed'
        ).values_list('score', flat=True)
        
        all_scores = list(regular_scores) + list(api_scores)
        
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
        best_score = max(all_scores) if all_scores else 0
        
        # Recent activity - include both regular and API attempts
        last_7_days = timezone.now() - timedelta(days=7)
        recent_regular_attempts = QuizAttempt.objects.filter(
            user=self.user,
            started_at__gte=last_7_days
        ).count()
        
        recent_api_attempts = QuizAPIAttempt.objects.filter(
            user=self.user,
            started_at__gte=last_7_days
        ).count()
        
        recent_attempts = recent_regular_attempts + recent_api_attempts
        
        # Study streak
        study_streak = self._calculate_study_streak()
        
        # Total study time
        total_time = StudySession.objects.filter(user=self.user).aggregate(
            total=Sum('duration_minutes')
        )['total'] or 0
        
        # Processed documents count
        processed_documents = Document.objects.filter(
            uploaded_by=self.user,
            is_processed=True
        ).count()
        
        return {
            'total_documents': total_documents,
            'processed_documents': processed_documents,
            'total_quizzes': total_quizzes,
            'total_attempts': total_attempts,
            'completed_attempts': completed_attempts,
            'avg_score': round(avg_score, 1),
            'best_score': round(best_score, 1),
            'recent_attempts': recent_attempts,
            'study_streak': study_streak,
            'total_study_time': total_time,
            'completion_rate': round((completed_attempts / total_attempts * 100) if total_attempts > 0 else 0, 1)
        }
    
    def get_performance_over_time(self, days=30):
        """Get performance data over time"""
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Get both regular and API attempts
        regular_attempts = QuizAttempt.objects.filter(
            user=self.user,
            status='completed',
            completed_at__date__gte=start_date,
            completed_at__date__lte=end_date
        )
        
        api_attempts = QuizAPIAttempt.objects.filter(
            user=self.user,
            status='completed',
            completed_at__date__gte=start_date,
            completed_at__date__lte=end_date
        )
        
        # Group by date
        daily_performance = defaultdict(list)
        
        # Process regular attempts
        for attempt in regular_attempts:
            date_str = attempt.completed_at.date().strftime('%Y-%m-%d')
            daily_performance[date_str].append(attempt.score)
        
        # Process API attempts
        for attempt in api_attempts:
            date_str = attempt.completed_at.date().strftime('%Y-%m-%d')
            daily_performance[date_str].append(attempt.score)
        
        # Calculate daily averages
        performance_data = []
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            scores = daily_performance.get(date_str, [])
            avg_score = sum(scores) / len(scores) if scores else None
            
            performance_data.append({
                'date': date_str,
                'average_score': round(avg_score, 1) if avg_score else None,
                'attempts_count': len(scores)
            })
            current_date += timedelta(days=1)
        
        return performance_data
    
    def get_subject_performance(self):
        """Get performance breakdown by document/subject"""
        performance_metrics = PerformanceMetrics.objects.filter(
            user=self.user
        ).select_related('document').order_by('-average_score')
        
        subject_data = []
        for metric in performance_metrics:
            subject_data.append({
                'document_title': metric.document.title,
                'document_id': metric.document.id,
                'total_attempts': metric.total_attempts,
                'best_score': metric.best_score,
                'average_score': metric.average_score,
                'mastery_level': metric.mastery_level,
                'last_attempt': metric.last_attempt_date,
                'total_time': metric.total_time_minutes
            })
        
        return subject_data
    
    def get_question_type_analysis(self):
        """Analyze performance by question type"""
        user_answers = UserAnswer.objects.filter(
            attempt__user=self.user,
            attempt__status='completed'
        ).select_related('question')
        
        type_stats = defaultdict(lambda: {'total': 0, 'correct': 0, 'points_earned': 0, 'max_points': 0})
        
        for answer in user_answers:
            q_type = answer.question.question_type
            type_stats[q_type]['total'] += 1
            if answer.is_correct:
                type_stats[q_type]['correct'] += 1
            type_stats[q_type]['points_earned'] += answer.points_earned
            type_stats[q_type]['max_points'] += answer.question.points
        
        # Calculate percentages
        analysis = []
        for q_type, stats in type_stats.items():
            if stats['total'] > 0:
                accuracy = (stats['correct'] / stats['total']) * 100
                score_percentage = (stats['points_earned'] / stats['max_points']) * 100 if stats['max_points'] > 0 else 0
                
                analysis.append({
                    'question_type': q_type,
                    'display_name': dict(Question.QUESTION_TYPES).get(q_type, q_type),
                    'total_questions': stats['total'],
                    'correct_answers': stats['correct'],
                    'accuracy_percentage': round(accuracy, 1),
                    'score_percentage': round(score_percentage, 1),
                    'points_earned': stats['points_earned'],
                    'max_points': stats['max_points']
                })
        
        return sorted(analysis, key=lambda x: x['accuracy_percentage'], reverse=True)
    
    def get_difficulty_analysis(self):
        """Analyze performance by difficulty level"""
        # Get regular quiz attempts
        regular_attempts = QuizAttempt.objects.filter(
            user=self.user,
            status='completed'
        ).select_related('quiz')
        
        # Get API quiz attempts
        api_attempts = QuizAPIAttempt.objects.filter(
            user=self.user,
            status='completed'
        ).select_related('quiz_api')
        
        difficulty_stats = defaultdict(lambda: {'attempts': 0, 'total_score': 0, 'best_score': 0})
        
        # Process regular attempts
        for attempt in regular_attempts:
            difficulty = attempt.quiz.difficulty
            difficulty_stats[difficulty]['attempts'] += 1
            difficulty_stats[difficulty]['total_score'] += attempt.score
            difficulty_stats[difficulty]['best_score'] = max(
                difficulty_stats[difficulty]['best_score'], 
                attempt.score
            )
        
        # Process API attempts
        for attempt in api_attempts:
            difficulty = attempt.quiz_api.difficulty
            difficulty_stats[difficulty]['attempts'] += 1
            difficulty_stats[difficulty]['total_score'] += attempt.score
            difficulty_stats[difficulty]['best_score'] = max(
                difficulty_stats[difficulty]['best_score'], 
                attempt.score
            )
        
        analysis = []
        for difficulty, stats in difficulty_stats.items():
            if stats['attempts'] > 0:
                avg_score = stats['total_score'] / stats['attempts']
                analysis.append({
                    'difficulty': difficulty,
                    'display_name': dict(Quiz.DIFFICULTY_LEVELS).get(difficulty, difficulty),
                    'attempts': stats['attempts'],
                    'average_score': round(avg_score, 1),
                    'best_score': round(stats['best_score'], 1)
                })
        
        return sorted(analysis, key=lambda x: x['average_score'], reverse=True)
    
    def get_study_patterns(self):
        """Analyze study patterns and habits"""
        sessions = StudySession.objects.filter(user=self.user).order_by('-date')[:30]
        
        # Study frequency
        study_days = len(sessions)
        total_days = 30
        study_frequency = (study_days / total_days) * 100
        
        # Average session duration
        avg_duration = sessions.aggregate(avg=Avg('duration_minutes'))['avg'] or 0
        
        # Best study day of week
        day_stats = defaultdict(lambda: {'sessions': 0, 'total_time': 0})
        for session in sessions:
            day_name = session.date.strftime('%A')
            day_stats[day_name]['sessions'] += 1
            day_stats[day_name]['total_time'] += session.duration_minutes
        
        best_day = max(day_stats.items(), key=lambda x: x[1]['total_time']) if day_stats else None
        
        # Study consistency (streak)
        current_streak = self._calculate_study_streak()
        longest_streak = self._calculate_longest_streak()
        
        return {
            'study_frequency_percentage': round(study_frequency, 1),
            'average_session_duration': round(avg_duration, 1),
            'best_study_day': best_day[0] if best_day else None,
            'current_streak': current_streak,
            'longest_streak': longest_streak,
            'total_study_days': study_days,
            'recent_sessions': [
                {
                    'date': session.date.strftime('%Y-%m-%d'),
                    'duration': session.duration_minutes,
                    'questions_answered': session.questions_answered,
                    'accuracy': round((session.correct_answers / session.questions_answered * 100) if session.questions_answered > 0 else 0, 1)
                }
                for session in sessions[:7]  # Last 7 sessions
            ]
        }
    
    def get_improvement_suggestions(self):
        """Generate personalized improvement suggestions"""
        suggestions = []
        
        # Analyze recent performance
        recent_attempts = QuizAttempt.objects.filter(
            user=self.user,
            status='completed',
            completed_at__gte=timezone.now() - timedelta(days=14)
        )
        
        if recent_attempts.exists():
            avg_recent_score = recent_attempts.aggregate(avg=Avg('score'))['avg']
            
            if avg_recent_score < 60:
                suggestions.append({
                    'type': 'performance',
                    'title': 'Focus on Fundamentals',
                    'description': 'Your recent scores suggest reviewing basic concepts. Consider re-reading documents before taking quizzes.',
                    'action': 'Review documents',
                    'priority': 'high'
                })
            elif avg_recent_score < 80:
                suggestions.append({
                    'type': 'performance',
                    'title': 'Practice More',
                    'description': 'You\'re doing well but have room for improvement. Try taking more practice quizzes.',
                    'action': 'Take more quizzes',
                    'priority': 'medium'
                })
        
        # Analyze question types
        type_analysis = self.get_question_type_analysis()
        if type_analysis:
            weakest_type = min(type_analysis, key=lambda x: x['accuracy_percentage'])
            if weakest_type['accuracy_percentage'] < 70:
                suggestions.append({
                    'type': 'skill',
                    'title': f'Improve {weakest_type["display_name"]} Questions',
                    'description': f'You have {weakest_type["accuracy_percentage"]}% accuracy on {weakest_type["display_name"]} questions.',
                    'action': 'Practice specific question type',
                    'priority': 'medium'
                })
        
        # Study consistency
        study_patterns = self.get_study_patterns()
        if study_patterns['study_frequency_percentage'] < 50:
            suggestions.append({
                'type': 'habit',
                'title': 'Study More Consistently',
                'description': f'You\'ve studied {study_patterns["study_frequency_percentage"]}% of days. Try to study more regularly.',
                'action': 'Set daily study reminders',
                'priority': 'high'
            })
        
        return suggestions
    
    def _calculate_study_streak(self):
        """Calculate current study streak"""
        today = timezone.now().date()
        streak = 0
        current_date = today
        
        while True:
            if StudySession.objects.filter(user=self.user, date=current_date).exists():
                streak += 1
                current_date -= timedelta(days=1)
            else:
                break
        
        return streak
    
    def _calculate_longest_streak(self):
        """Calculate longest study streak"""
        sessions = StudySession.objects.filter(user=self.user).order_by('date')
        
        if not sessions.exists():
            return 0
        
        longest_streak = 0
        current_streak = 1
        previous_date = sessions.first().date
        
        for session in sessions[1:]:
            if session.date == previous_date + timedelta(days=1):
                current_streak += 1
            else:
                longest_streak = max(longest_streak, current_streak)
                current_streak = 1
            previous_date = session.date
        
        return max(longest_streak, current_streak)


class SystemAnalytics:
    """System-wide analytics for administrators"""
    
    @staticmethod
    def get_system_overview():
        """Get system-wide statistics"""
        total_users = Document.objects.values('uploaded_by').distinct().count()
        total_documents = Document.objects.count()
        total_quizzes = Quiz.objects.count()
        total_attempts = QuizAttempt.objects.count()
        
        # Average scores
        avg_system_score = QuizAttempt.objects.filter(
            status='completed'
        ).aggregate(avg=Avg('score'))['avg'] or 0
        
        # Most popular documents
        popular_docs = Document.objects.annotate(
            quiz_count=Count('quizzes')
        ).order_by('-quiz_count')[:5]
        
        return {
            'total_users': total_users,
            'total_documents': total_documents,
            'total_quizzes': total_quizzes,
            'total_attempts': total_attempts,
            'average_score': round(avg_system_score, 1),
            'popular_documents': [
                {
                    'title': doc.title,
                    'quiz_count': doc.quiz_count,
                    'uploaded_by': doc.uploaded_by.username
                }
                for doc in popular_docs
            ]
        }