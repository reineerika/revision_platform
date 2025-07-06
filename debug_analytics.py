#!/usr/bin/env python
import os
import sys
import django
from datetime import datetime, timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'revision_platform.settings')
django.setup()

from django.utils import timezone
from learning.models import QuizAttempt, QuizAPIAttempt, Document
from users.models import User

def debug_analytics():
    """Debug analytics data"""
    print("=== DEBUG ANALYTICS ===")
    print(f"Current time: {timezone.now()}")
    print(f"7 days ago: {timezone.now() - timedelta(days=7)}")
    
    # Get all users
    users = User.objects.all()
    print(f"Total users: {users.count()}")
    
    for user in users:
        print(f"\n--- User: {user.username} ---")
        
        # Check documents
        documents = Document.objects.filter(uploaded_by=user)
        processed_docs = documents.filter(is_processed=True)
        print(f"Documents: {documents.count()} (processed: {processed_docs.count()})")
        
        # Check regular attempts
        regular_attempts = QuizAttempt.objects.filter(user=user)
        completed_regular = regular_attempts.filter(status='completed')
        print(f"Regular attempts: {regular_attempts.count()} (completed: {completed_regular.count()})")
        
        # Check API attempts
        api_attempts = QuizAPIAttempt.objects.filter(user=user)
        completed_api = api_attempts.filter(status='completed')
        print(f"API attempts: {api_attempts.count()} (completed: {completed_api.count()})")
        
        # Check recent attempts (last 7 days)
        last_7_days = timezone.now() - timedelta(days=7)
        recent_regular = regular_attempts.filter(started_at__gte=last_7_days)
        recent_api = api_attempts.filter(started_at__gte=last_7_days)
        
        print(f"Recent regular attempts (7 days): {recent_regular.count()}")
        print(f"Recent API attempts (7 days): {recent_api.count()}")
        
        # Show ALL attempts without date filter
        print(f"ALL regular attempts: {regular_attempts.count()}")
        print(f"ALL API attempts: {api_attempts.count()}")
        
        # Show some recent attempts with dates
        if recent_regular.exists():
            print("Recent regular attempts:")
            for attempt in recent_regular[:3]:
                print(f"  - {attempt.started_at} (status: {attempt.status})")
        
        if recent_api.exists():
            print("Recent API attempts:")
            for attempt in recent_api[:3]:
                print(f"  - {attempt.started_at} (status: {attempt.status})")
        
        # Check if there are any attempts at all
        if regular_attempts.exists():
            print("Sample regular attempts:")
            for attempt in regular_attempts[:3]:
                print(f"  - {attempt.started_at} -> {attempt.completed_at} (status: {attempt.status})")
        
        if api_attempts.exists():
            print("Sample API attempts:")
            for attempt in api_attempts[:3]:
                print(f"  - {attempt.started_at} -> {attempt.completed_at} (status: {attempt.status})")

if __name__ == "__main__":
    debug_analytics() 