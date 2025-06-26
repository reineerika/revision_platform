from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

app_name = 'learning'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Document management
    path('documents/', views.document_list, name='document_list'),
    path('documents/upload/', views.document_upload, name='document_upload'),
    path('documents/<int:pk>/', views.document_detail, name='document_detail'),
    path('documents/<int:pk>/delete/', views.document_delete, name='document_delete'),
    path('documents/<int:pk>/reprocess/', views.document_reprocess, name='document_reprocess'),
    path('documents/<int:pk>/text/', views.document_text_view, name='document_text_view'),
    path('documents/bulk-action/', views.bulk_document_action, name='bulk_document_action'),
    
    # Quiz management
    path('quizzes/', views.quiz_list, name='quiz_list'),
    path('quiz/generate/', views.quiz_generate, name='quiz_generate'),
    path('quiz/generate/<int:document_id>/', views.quiz_generate, name='quiz_generate_from_document'),
    path('quiz/<int:pk>/', views.quiz_detail, name='quiz_detail'),
    path('quiz/<int:pk>/take/', views.quiz_take, name='quiz_take'),
    path('quiz/attempt/<int:pk>/', views.quiz_attempt, name='quiz_attempt'),
    path('quiz/attempt/<int:pk>/submit/', views.quiz_submit, name='quiz_submit'),
    path('quiz/result/<int:pk>/', views.quiz_result, name='quiz_result'),
    
    # Analytics
    path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),
    path('analytics/performance/<int:document_id>/', views.performance_detail, name='performance_detail'),
    path('analytics/progress/', views.study_progress, name='study_progress'),
    path('analytics/goals/create/', views.create_study_goal, name='create_study_goal'),
    path('analytics/export/', views.export_analytics, name='export_analytics'),
    
    # AJAX endpoints
    path('ajax/document/<int:pk>/status/', views.ajax_document_status, name='ajax_document_status'),
    path('ajax/quiz/attempt/<int:attempt_pk>/answer/', views.quiz_submit_answer, name='quiz_submit_answer'),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)