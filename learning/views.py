from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q, Avg, Max, Sum
from django.db import models
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils import timezone
from datetime import timedelta
from collections import defaultdict
import json
import threading
from typing import Tuple
import requests
import os
import environ
import PyPDF2

from .models import Document, Quiz, Question, QuizAttempt, UserAnswer, PerformanceMetrics, QuizAPIResult
from .forms import DocumentUploadForm, QuizGenerationForm, DocumentSearchForm, BulkDocumentActionForm
from .utils import extract_text_from_document, get_document_stats, send_revision_reminder_email

# Charger les variables d'environnement
env = environ.Env()
environ.Env.read_env()

def generate_test_quiz_data(doc_text, difficulty, num_questions):
    """Génère des données de quiz de test pour diagnostiquer les problèmes"""
    import random
    
    # Questions QCM de test
    qcm_questions = [
        {
            "q": "Quelle est la principale fonction de ce document ?",
            "a": "Informer le lecteur",
            "b": "Divertir le lecteur", 
            "c": "Vendre un produit",
            "R": "a"
        },
        {
            "q": "Combien de sections principales contient ce document ?",
            "a": "2 sections",
            "b": "3 sections", 
            "c": "4 sections",
            "R": "b"
        },
        {
            "q": "Quel est le niveau de difficulté recommandé pour ce contenu ?",
            "a": "Débutant",
            "b": "Intermédiaire",
            "c": "Avancé",
            "R": "b"
        }
    ]
    
    # Questions vrai/faux de test
    vrai_faux_questions = [
        {
            "q": "Ce document contient des informations techniques détaillées.",
            "R": True
        },
        {
            "q": "Le document est organisé en chapitres numérotés.",
            "R": False
        },
        {
            "q": "Les exemples fournis facilitent la compréhension.",
            "R": True
        }
    ]
    
    return {
        "qcm": qcm_questions[:min(3, num_questions // 2)],
        "vrai_faux": vrai_faux_questions[:min(3, num_questions // 2)]
    }


@login_required
def document_list(request):
    """Display list of user's documents with search and filtering"""
    form = DocumentSearchForm(request.GET)
    documents = Document.objects.filter(uploaded_by=request.user)
    
    if form.is_valid():
        query = form.cleaned_data.get('query')
        document_type = form.cleaned_data.get('document_type')
        sort_by = form.cleaned_data.get('sort_by') or '-created_at'
        
        if query:
            documents = documents.filter(
                Q(title__icontains=query) |
                Q(description__icontains=query) |
                Q(extracted_text__icontains=query)
            )
        
        if document_type:
            documents = documents.filter(document_type=document_type)
        
        documents = documents.order_by(sort_by)
    else:
        documents = documents.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(documents, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'documents': page_obj,
        'search_form': form,
        'total_documents': documents.count(),
    }
    
    return render(request, 'learning/document_list.html', context)


@login_required
def document_upload(request):
    """Handle document upload"""
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.uploaded_by = request.user
            document.save()
            
            # Process document in background
            def process_document():
                try:
                    extract_text_from_document(document)
                    messages.success(request, f'Document "{document.title}" uploaded and processed successfully!')
                except Exception as e:
                    messages.error(request, f'Document uploaded but processing failed: {str(e)}')
            
            # Start processing in a separate thread
            thread = threading.Thread(target=process_document)
            thread.daemon = True
            thread.start()
            
            messages.info(request, f'Document "{document.title}" uploaded successfully. Processing in background...')
            return redirect('learning:document_detail', pk=document.pk)
    else:
        form = DocumentUploadForm()
    
    return render(request, 'learning/document_upload.html', {'form': form})


@login_required
def document_detail(request, pk):
    """Display document details and statistics"""
    document = get_object_or_404(Document, pk=pk, uploaded_by=request.user)
    
    # Get document statistics
    stats = get_document_stats(document) if document.is_processed else {}
    
    # Get related quizzes
    quizzes = document.quizzes.filter(is_active=True).order_by('-created_at')
    
    # Get user's performance on this document
    try:
        performance = PerformanceMetrics.objects.get(user=request.user, document=document)
    except PerformanceMetrics.DoesNotExist:
        performance = None
    
    context = {
        'document': document,
        'stats': stats,
        'quizzes': quizzes,
        'performance': performance,
    }
    
    return render(request, 'learning/document_detail.html', context)


@login_required
@require_POST
def document_reprocess(request, pk):
    """Reprocess document text extraction"""
    document = get_object_or_404(Document, pk=pk, uploaded_by=request.user)
    
    try:
        extract_text_from_document(document)
        messages.success(request, f'Document "{document.title}" reprocessed successfully!')
    except Exception as e:
        messages.error(request, f'Error reprocessing document: {str(e)}')
    
    return redirect('learning:document_detail', pk=document.pk)


@login_required
def document_delete(request, pk):
    """Delete document"""
    document = get_object_or_404(Document, pk=pk, uploaded_by=request.user)
    
    if request.method == 'POST':
        title = document.title
        document.delete()
        messages.success(request, f'Document "{title}" deleted successfully!')
        return redirect('learning:document_list')
    
    return render(request, 'learning/document_confirm_delete.html', {'document': document})


@login_required
def document_text_view(request, pk):
    """View extracted text from document"""
    document = get_object_or_404(Document, pk=pk, uploaded_by=request.user)
    
    if not document.is_processed:
        messages.warning(request, 'Document has not been processed yet.')
        return redirect('learning:document_detail', pk=document.pk)
    
    return render(request, 'learning/document_text_view.html', {'document': document})


@login_required
@require_POST
def bulk_document_action(request):
    """Handle bulk actions on documents"""
    form = BulkDocumentActionForm(request.POST, user=request.user)
    
    if form.is_valid():
        action = form.cleaned_data['action']
        documents = form.cleaned_data['selected_documents']
        
        if action == 'delete':
            count = documents.count()
            documents.delete()
            messages.success(request, f'{count} documents deleted successfully!')
            
        elif action == 'reprocess':
            count = 0
            for document in documents:
                try:
                    extract_text_from_document(document)
                    count += 1
                except Exception:
                    pass
            messages.success(request, f'{count} documents reprocessed successfully!')
            
        elif action == 'generate_quiz':
            # Redirect to quiz generation with selected documents
            document_ids = [str(doc.id) for doc in documents]
            return redirect(f'/learning/quiz/generate/?documents={",".join(document_ids)}')
    
    return redirect('learning:document_list')


@login_required
def ajax_document_status(request, pk):
    """AJAX endpoint to check document processing status"""
    document = get_object_or_404(Document, pk=pk, uploaded_by=request.user)
    
    data = {
        'is_processed': document.is_processed,
        'processing_error': document.processing_error,
        'word_count': document.word_count,
    }
    
    return JsonResponse(data)


class DocumentListView(LoginRequiredMixin, ListView):
    """Class-based view for document list (alternative implementation)"""
    model = Document
    template_name = 'learning/document_list.html'
    context_object_name = 'documents'
    paginate_by = 10
    
    def get_queryset(self):
        return Document.objects.filter(uploaded_by=self.request.user).order_by('-created_at')


class DocumentDetailView(LoginRequiredMixin, DetailView):
    """Class-based view for document detail (alternative implementation)"""
    model = Document
    template_name = 'learning/document_detail.html'
    context_object_name = 'document'
    
    def get_queryset(self):
        return Document.objects.filter(uploaded_by=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document = self.object
        
        context['stats'] = get_document_stats(document) if document.is_processed else {}
        context['quizzes'] = document.quizzes.filter(is_active=True).order_by('-created_at')
        
        try:
            context['performance'] = PerformanceMetrics.objects.get(
                user=self.request.user, 
                document=document
            )
        except PerformanceMetrics.DoesNotExist:
            context['performance'] = None
        
        return context


# Dashboard view
@login_required
def dashboard(request):
    """Main dashboard showing user's learning progress"""
    user = request.user
    
    # Get user's documents
    documents = Document.objects.filter(uploaded_by=user)
    processed_documents = documents.filter(is_processed=True)
    
    # Get user's quizzes and attempts
    quiz_attempts = QuizAttempt.objects.filter(user=user)
    completed_attempts = quiz_attempts.filter(status='completed')
    
    # Calculate statistics
    stats = {
        'total_documents': documents.count(),
        'processed_documents': processed_documents.count(),
        'total_quizzes': Quiz.objects.filter(document__uploaded_by=user).count(),
        'quiz_attempts': quiz_attempts.count(),
        'completed_quizzes': completed_attempts.count(),
        'average_score': completed_attempts.aggregate(
            avg_score=models.Avg('score')
        )['avg_score'] or 0,
    }
    
    # Recent activity
    recent_documents = documents.order_by('-created_at')[:5]
    recent_attempts = quiz_attempts.order_by('-started_at')[:5]
    
    # Quiz API disponibles
    api_quizzes = QuizAPIResult.objects.filter(user=user).order_by('-created_at')
    context = {
        'stats': stats,
        'recent_documents': recent_documents,
        'recent_attempts': recent_attempts,
        'api_quizzes': api_quizzes,
    }
    
    return render(request, 'learning/dashboard.html', context)




# Quiz Generation Views
from .quiz_generator import QuizGenerator
from .answer_checker import SmartAnswerChecker
from .analytics import LearningAnalytics


@login_required
def quiz_generate(request, document_id=None):
    """Generate quiz from document using external API"""
    if document_id:
        documents = [get_object_or_404(Document, pk=document_id, uploaded_by=request.user)]
    else:
        document_ids = request.GET.get('documents', '').split(',')
        if document_ids and document_ids[0]:
            documents = Document.objects.filter(
                id__in=[int(id) for id in document_ids if id.isdigit()],
                uploaded_by=request.user
            )
        else:
            documents = Document.objects.filter(uploaded_by=request.user)
    
    if request.method == 'POST':
        form = QuizGenerationForm(request.POST)
        if form.is_valid():
            selected_doc_id = request.POST.get('selected_document')
            if selected_doc_id:
                document = get_object_or_404(Document, pk=selected_doc_id, uploaded_by=request.user)
                doc_text = document.extracted_text or ''
                # Si le texte est vide, essayer d'extraire nativement
                if True:
                    file_path = document.file.path
                    if file_path.lower().endswith('.pdf'):
                        try:
                            with open(file_path, 'rb') as f:
                                reader = PyPDF2.PdfReader(f)
                                doc_text = "\n".join(page.extract_text() or '' for page in reader.pages)
                        except Exception as e:
                            doc_text = ''
                    elif file_path.lower().endswith('.txt'):
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                doc_text = f.read()
                        except Exception as e:
                            doc_text = ''
                num_questions = form.cleaned_data.get('num_questions', 6)
                difficulty = form.cleaned_data.get('difficulty', 'easy')
                prompt = (
                    "Génère un QCM et des questions vrai/faux à partir du texte suivant :\n\n"
                    f"<<CONTENU_DU_FICHIER_ICI>>\n\n"
                    "Paramètres :\n"
                    f"- difficulté : {difficulty}\n"
                    f"- nombre total de questions : {num_questions} (50% QCM et 50% vrai/faux)\n\n"
                    "Format de réponse attendu : un objet JSON contenant deux clés :\n"
                    "1. \"qcm\" : tableau de 3 questions à choix multiples. Chaque question doit avoir la structure :\n"
                    "{\n  \"q\": \"texte de la question\",\n  \"a\": \"option A\",\n  \"b\": \"option B\",\n  \"c\": \"option C\",\n  \"R\": \"a\" (ou \"b\" ou \"c\") correspondant à la bonne réponse\n}\n\n"
                    "2. \"vrai_faux\" : tableau de 3 affirmations à évaluer comme vraies ou fausses. Chaque élément doit avoir la structure :\n"
                    "{\n  \"q\": \"affirmation\",\n  \"R\": true ou false\n}\n\n"
                    "IMPORTANT : la réponse doit être strictement dans ce format JSON, sans aucune explication, sans texte en dehors du JSON. Aucun retour à la ligne inutile.\n\n"
                    f"CONTENU DU FICHIER : {doc_text}\n"
                    f"NOMBRE DE QUESTIONS : {num_questions}\n"
                    f"DIFFICULTE : {difficulty}"
                )

                print(prompt)

               # raise Exception("test")
                # Utiliser les variables d'environnement
                try:
                    api_url = env('RAPIDAPI_URL', default='https://chatgpt-42.p.rapidapi.com/chat')
                    api_host = env('RAPIDAPI_HOST', default='chatgpt-42.p.rapidapi.com')
                    api_key = env('RAPIDAPI_KEY')
                except:
                    # Fallback vers la configuration temporaire
                    import config
                    api_url = config.RAPIDAPI_URL
                    api_host = config.RAPIDAPI_HOST
                    api_key = config.RAPIDAPI_KEY
                
                # Vérifier que la clé API est configurée
                if not api_key or api_key == "your_api_key_here":
                    messages.error(request, 'Clé API non configurée. Veuillez configurer RAPIDAPI_KEY dans votre fichier .env ou config.py')
                    return redirect('learning:quiz_generate')
                
                headers = {
                    'Content-Type': 'application/json',
                    'x-rapidapi-host': api_host,
                    'x-rapidapi-key': api_key,
                }
                data = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }
                try:
                    print(f"Envoi de la requête à l'API: {api_url}")
                    print(f"Headers: {headers}")
                    print(f"Data: {data}")
                    
                    response = requests.post(api_url, headers=headers, json=data, timeout=60)
                    print(f"Status code: {response.status_code}")
                    print(f"Response headers: {response.headers}")
                    print(f"Response content: {response.text[:500]}...")  # Afficher les 500 premiers caractères
                    
                    response.raise_for_status()
                    result = response.json()
                    print(f"API result: {result}")
                    
                    if 'choices' not in result or not result['choices']:
                        raise Exception("Réponse API invalide: pas de 'choices' dans la réponse")
                    
                    content = result['choices'][0]['message']['content']
                    print(f"API content: {content}")
                    
                    # Vérifier si le contenu est vide
                    if not content or content.strip() == '':
                        raise Exception("Réponse API vide")
                    
                    import json as pyjson
                    quiz_data = pyjson.loads(content)
                    print(f"Parsed quiz data: {quiz_data}")
                    
                    # Sauvegarder le résultat dans la base de données
                    quiz_api_result = QuizAPIResult.objects.create(
                        document=document,
                        user=request.user,
                        title=form.cleaned_data.get('title', ''),
                        api_response=quiz_data
                    )
                    print(quiz_data)
                    messages.success(request, "Questions générées avec succès !")
                    return redirect('learning:quiz_api_take', quiz_id=quiz_api_result.id)
                except requests.exceptions.RequestException as e:
                    messages.warning(request, f'Erreur de connexion à l\'API : {str(e)}. Utilisation des données de test.')
                    quiz_data = generate_test_quiz_data(doc_text, difficulty, num_questions)
                except json.JSONDecodeError as e:
                    messages.warning(request, f'Erreur de décodage JSON de la réponse API : {str(e)}. Utilisation des données de test.')
                    quiz_data = generate_test_quiz_data(doc_text, difficulty, num_questions)
                except KeyError as e:
                    messages.warning(request, f'Structure de réponse API invalide : {str(e)}. Utilisation des données de test.')
                    quiz_data = generate_test_quiz_data(doc_text, difficulty, num_questions)
                except Exception as e:
                    messages.warning(request, f'Erreur lors de la génération via l\'API : {str(e)}. Utilisation des données de test.')
                    quiz_data = generate_test_quiz_data(doc_text, difficulty, num_questions)
                
                # Sauvegarder le résultat dans la base de données
                quiz_api_result = QuizAPIResult.objects.create(
                    document=document,
                    user=request.user,
                    title=form.cleaned_data.get('title', ''),
                    api_response=quiz_data
                )
                print(f"Quiz data saved: {quiz_data}")
                messages.success(request, "Questions générées avec succès !")
                return redirect('learning:quiz_api_take', quiz_id=quiz_api_result.id)
            else:
                messages.error(request, 'Please select a document to generate quiz from.')
    else:
        form = QuizGenerationForm()
        
        # Utiliser la difficulté préférée de l'utilisateur
        try:
            user_profile = request.user.profile
            if user_profile.preferred_difficulty:
                form.fields['difficulty'].initial = user_profile.preferred_difficulty
        except:
            pass  # Si pas de profil, utiliser la valeur par défaut
        
        if len(documents) == 1:
            form.fields['title'].initial = f"Quiz: {documents[0].title}"
    
    context = {
        'form': form,
        'documents': documents,
        'single_document': len(documents) == 1,
    }
    return render(request, 'learning/quiz_generate.html', context)


@login_required
def quiz_list(request):
    """Display list of user's quizzes"""
    quizzes = Quiz.objects.filter(
        document__uploaded_by=request.user
    ).select_related('document').order_by('-created_at')
    
    # Filter by status
    status_filter = request.GET.get('status', 'all')
    if status_filter == 'active':
        quizzes = quizzes.filter(is_active=True)
    elif status_filter == 'inactive':
        quizzes = quizzes.filter(is_active=False)
    
    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        quizzes = quizzes.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(document__title__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(quizzes, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'quizzes': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'total_quizzes': quizzes.count(),
    }
    
    return render(request, 'learning/quiz_list.html', context)


@login_required
def quiz_detail(request, pk):
    """Display quiz details"""
    quiz = get_object_or_404(
        Quiz.objects.select_related('document', 'created_by'),
        pk=pk,
        document__uploaded_by=request.user
    )
    
    # Get user's attempts on this quiz
    user_attempts = QuizAttempt.objects.filter(
        user=request.user,
        quiz=quiz
    ).order_by('-started_at')
    
    # Get quiz statistics
    all_attempts = quiz.attempts.filter(status='completed')
    stats = {
        'total_attempts': all_attempts.count(),
        'average_score': all_attempts.aggregate(avg_score=models.Avg('score'))['avg_score'] or 0,
        'best_score': all_attempts.aggregate(max_score=models.Max('score'))['max_score'] or 0,
        'user_attempts': user_attempts.count(),
        'user_best_score': user_attempts.filter(status='completed').aggregate(
            max_score=models.Max('score')
        )['max_score'] or 0,
    }
    
    context = {
        'quiz': quiz,
        'user_attempts': user_attempts[:5],  # Show last 5 attempts
        'stats': stats,
        'questions': quiz.questions.all().order_by('order'),
    }
    
    return render(request, 'learning/quiz_detail.html', context)


@login_required
def quiz_take(request, pk):
    """Take a quiz"""
    quiz = get_object_or_404(
        Quiz.objects.select_related('document'),
        pk=pk,
        document__uploaded_by=request.user,
        is_active=True
    )
    
    # Check if user has an in-progress attempt
    in_progress_attempt = QuizAttempt.objects.filter(
        user=request.user,
        quiz=quiz,
        status='in_progress'
    ).first()
    
    if in_progress_attempt:
        return redirect('learning:quiz_attempt', pk=in_progress_attempt.pk)
    
    # Create new attempt
    attempt = QuizAttempt.objects.create(
        user=request.user,
        quiz=quiz,
        total_points=sum(q.points for q in quiz.questions.all())
    )
    
    return redirect('learning:quiz_attempt', pk=attempt.pk)


@login_required
def quiz_attempt(request, pk):
    """Display quiz attempt interface"""
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related('quiz', 'quiz__document'),
        pk=pk,
        user=request.user
    )
    
    if attempt.status == 'completed':
        return redirect('learning:quiz_result', pk=attempt.pk)
    
    questions = attempt.quiz.questions.all().order_by('order')
    
    # Get user's existing answers
    existing_answers = {
        answer.question_id: answer.user_answer 
        for answer in attempt.answers.all()
    }
    
    context = {
        'attempt': attempt,
        'questions': questions,
        'existing_answers': existing_answers,
        'time_limit_seconds': attempt.quiz.time_limit_minutes * 60,
    }
    
    return render(request, 'learning/quiz_attempt.html', context)


@login_required
@require_POST
def quiz_submit_answer(request, attempt_pk):
    """Submit answer for a question via AJAX"""
    attempt = get_object_or_404(
        QuizAttempt,
        pk=attempt_pk,
        user=request.user,
        status='in_progress'
    )
    
    try:
        data = json.loads(request.body)
        question_id = data.get('question_id')
        user_answer = data.get('answer', '').strip()
        time_taken = data.get('time_taken', 0)
        
        question = get_object_or_404(Question, pk=question_id, quiz=attempt.quiz)
        
        # Save or update user answer
        answer_obj, created = UserAnswer.objects.get_or_create(
            attempt=attempt,
            question=question,
            defaults={
                'user_answer': user_answer,
                'time_taken_seconds': time_taken
            }
        )
        
        if not created:
            answer_obj.user_answer = user_answer
            answer_obj.time_taken_seconds = time_taken
            answer_obj.save()
        
        # Check if answer is correct and calculate points
        is_correct, points = check_answer_correctness(question, user_answer)
        answer_obj.is_correct = is_correct
        answer_obj.points_earned = points
        answer_obj.save()
        
        return JsonResponse({
            'success': True,
            'is_correct': is_correct,
            'points_earned': points
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def quiz_submit(request, attempt_pk):
    """Submit entire quiz"""
    attempt = get_object_or_404(
        QuizAttempt,
        pk=attempt_pk,
        user=request.user,
        status='in_progress'
    )
    
    # Calculate final score
    total_earned = attempt.answers.aggregate(
        total=models.Sum('points_earned')
    )['total'] or 0
    
    attempt.earned_points = total_earned
    attempt.score = (total_earned / attempt.total_points * 100) if attempt.total_points > 0 else 0
    attempt.status = 'completed'
    attempt.completed_at = timezone.now()
    
    # Calculate time taken
    time_diff = attempt.completed_at - attempt.started_at
    attempt.time_taken_minutes = int(time_diff.total_seconds() / 60)
    
    attempt.save()
    
    # Update performance metrics
    update_performance_metrics(request.user, attempt.quiz.document, attempt)
    
    messages.success(request, f'Quiz completed! Your score: {attempt.score:.1f}%')
    return redirect('learning:quiz_result', pk=attempt.pk)


@login_required
def quiz_result(request, pk):
    """Display quiz results"""
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related('quiz', 'quiz__document'),
        pk=pk,
        user=request.user,
        status='completed'
    )
    
    # Get detailed results
    answers = attempt.answers.select_related('question').order_by('question__order')
    
    context = {
        'attempt': attempt,
        'answers': answers,
        'percentage_score': attempt.percentage_score,
    }
    
    return render(request, 'learning/quiz_result.html', context)


def check_answer_correctness(question: Question, user_answer: str) -> Tuple[bool, int]:
    """Check if user answer is correct and return points earned"""
    checker = SmartAnswerChecker()
    is_correct, points_earned, feedback = checker.check_answer(question, user_answer)
    return is_correct, points_earned


def update_performance_metrics(user, document, attempt):
    """Update user's performance metrics for a document"""
    metrics, created = PerformanceMetrics.objects.get_or_create(
        user=user,
        document=document,
        defaults={
            'total_attempts': 0,
            'best_score': 0,
            'average_score': 0,
            'total_time_minutes': 0,
        }
    )
    
    # Update metrics
    metrics.total_attempts += 1
    metrics.best_score = max(metrics.best_score, attempt.score)
    metrics.total_time_minutes += attempt.time_taken_minutes
    metrics.last_attempt_date = attempt.completed_at
    
    # Calculate average score
    all_scores = QuizAttempt.objects.filter(
        user=user,
        quiz__document=document,
        status='completed'
    ).values_list('score', flat=True)
    
    if all_scores:
        metrics.average_score = sum(all_scores) / len(all_scores)
    
    # Determine mastery level
    if metrics.average_score >= 90:
        metrics.mastery_level = 'expert'
    elif metrics.average_score >= 75:
        metrics.mastery_level = 'advanced'
    elif metrics.average_score >= 60:
        metrics.mastery_level = 'intermediate'
    else:
        metrics.mastery_level = 'beginner'
    
    metrics.save()
    
    # Update user profile points and streak
    profile = user.profile
    profile.total_points += attempt.earned_points
    
    # Update study session
    from .models import StudySession
    today = timezone.now().date()
    session, created = StudySession.objects.get_or_create(
        user=user,
        date=today,
        defaults={
            'duration_minutes': 0,
            'questions_answered': 0,
            'correct_answers': 0,
            'points_earned': 0,
        }
    )
    
    session.duration_minutes += attempt.time_taken_minutes
    session.questions_answered += attempt.quiz.total_questions
    session.correct_answers += attempt.answers.filter(is_correct=True).count()
    session.points_earned += attempt.earned_points
    session.save()
    
    profile.save()




# Analytics Views

@login_required
def analytics_dashboard(request):
    """Main analytics dashboard"""
    from .analytics import LearningAnalytics
    
    analytics = LearningAnalytics(request.user)
    
    # Get all analytics data
    dashboard_stats = analytics.get_user_dashboard_stats()
    performance_over_time = analytics.get_performance_over_time(days=30)
    subject_performance = analytics.get_subject_performance()
    question_type_analysis = analytics.get_question_type_analysis()
    difficulty_analysis = analytics.get_difficulty_analysis()
    study_patterns = analytics.get_study_patterns()
    improvement_suggestions = analytics.get_improvement_suggestions()
    
    context = {
        'dashboard_stats': dashboard_stats,
        'performance_over_time': json.dumps(performance_over_time),
        'subject_performance': subject_performance,
        'question_type_analysis': question_type_analysis,
        'difficulty_analysis': difficulty_analysis,
        'study_patterns': study_patterns,
        'improvement_suggestions': improvement_suggestions,
    }
    
    return render(request, 'learning/analytics_dashboard.html', context)


@login_required
def performance_detail(request, document_id):
    """Detailed performance analysis for a specific document"""
    document = get_object_or_404(Document, pk=document_id, uploaded_by=request.user)
    
    # Get performance metrics
    try:
        performance = PerformanceMetrics.objects.get(user=request.user, document=document)
    except PerformanceMetrics.DoesNotExist:
        performance = None
    
    # Get quiz attempts for this document
    attempts = QuizAttempt.objects.filter(
        user=request.user,
        quiz__document=document,
        status='completed'
    ).order_by('-completed_at')
    
    # Calculate trends
    attempt_scores = [attempt.score for attempt in attempts]
    if len(attempt_scores) > 1:
        recent_avg = sum(attempt_scores[:3]) / min(3, len(attempt_scores))
        overall_avg = sum(attempt_scores) / len(attempt_scores)
        trend = "improving" if recent_avg > overall_avg else "declining" if recent_avg < overall_avg else "stable"
    else:
        trend = "insufficient_data"
    
    # Question type breakdown for this document
    user_answers = UserAnswer.objects.filter(
        attempt__user=request.user,
        attempt__quiz__document=document,
        attempt__status='completed'
    ).select_related('question')
    
    type_breakdown = defaultdict(lambda: {'total': 0, 'correct': 0})
    for answer in user_answers:
        q_type = answer.question.question_type
        type_breakdown[q_type]['total'] += 1
        if answer.is_correct:
            type_breakdown[q_type]['correct'] += 1
    
    context = {
        'document': document,
        'performance': performance,
        'attempts': attempts[:10],  # Last 10 attempts
        'trend': trend,
        'type_breakdown': dict(type_breakdown),
        'total_attempts': attempts.count(),
    }
    
    return render(request, 'learning/performance_detail.html', context)


@login_required
def study_progress(request):
    """Study progress and goals tracking"""
    from .models import StudyGoal
    from users.models import StudySession
    
    # Get user's study goals
    goals = StudyGoal.objects.filter(user=request.user).order_by('-created_at')
    
    # Get recent study sessions
    recent_sessions = StudySession.objects.filter(
        user=request.user
    ).order_by('-date')[:14]  # Last 2 weeks
    
    # Calculate weekly progress
    weekly_stats = defaultdict(lambda: {'sessions': 0, 'time': 0, 'questions': 0, 'correct': 0})
    for session in recent_sessions:
        week_start = session.date - timedelta(days=session.date.weekday())
        week_key = week_start.strftime('%Y-%m-%d')
        weekly_stats[week_key]['sessions'] += 1
        weekly_stats[week_key]['time'] += session.duration_minutes
        weekly_stats[week_key]['questions'] += session.questions_answered
        weekly_stats[week_key]['correct'] += session.correct_answers
    
    context = {
        'goals': goals,
        'recent_sessions': recent_sessions,
        'weekly_stats': dict(weekly_stats),
    }
    
    return render(request, 'learning/study_progress.html', context)


@login_required  
def create_study_goal(request):
    """Create a new study goal"""
    from .models import StudyGoal
    
    if request.method == 'POST':
        goal_type = request.POST.get('goal_type')
        target_value = int(request.POST.get('target_value', 0))
        deadline = request.POST.get('deadline')
        
        if goal_type and target_value > 0:
            goal = StudyGoal.objects.create(
                user=request.user,
                goal_type=goal_type,
                target_value=target_value,
                deadline=deadline if deadline else None
            )
            messages.success(request, 'Study goal created successfully!')
            return redirect('learning:study_progress')
        else:
            messages.error(request, 'Please provide valid goal details.')
    
    return render(request, 'learning/create_study_goal.html', {
        'goal_types': StudyGoal.GOAL_TYPES
    })


@login_required
def export_analytics(request):
    """Export analytics data as JSON"""
    analytics = LearningAnalytics(request.user)
    
    export_data = {
        'user': request.user.username,
        'export_date': timezone.now().isoformat(),
        'dashboard_stats': analytics.get_user_dashboard_stats(),
        'performance_over_time': analytics.get_performance_over_time(days=90),
        'subject_performance': analytics.get_subject_performance(),
        'question_type_analysis': analytics.get_question_type_analysis(),
        'difficulty_analysis': analytics.get_difficulty_analysis(),
        'study_patterns': analytics.get_study_patterns(),
    }
    
    response = HttpResponse(
        json.dumps(export_data, indent=2, default=str),
        content_type='application/json'
    )
    response['Content-Disposition'] = f'attachment; filename="learning_analytics_{request.user.username}_{timezone.now().strftime("%Y%m%d")}.json"'
    
    return response


@login_required
def quiz_api_take(request, quiz_id):
    """Afficher un quiz généré par l'API et proposer de le lancer ou d'y répondre plus tard."""
    quiz_api = get_object_or_404(QuizAPIResult, pk=quiz_id, user=request.user)
    quiz_data = quiz_api.api_response
    document = quiz_api.document
    title = quiz_api.title or f"Quiz sur {document.title}"
    context = {
        'quiz_api': quiz_api,
        'quiz_data': quiz_data,
        'document': document,
        'title': title,
    }
    return render(request, 'learning/quiz_api_take.html', context)


@login_required
def quiz_api_attempt(request, quiz_id):
    from .models import QuizAPIAttempt
    
    quiz_api = get_object_or_404(QuizAPIResult, pk=quiz_id, user=request.user)
    quiz_data = quiz_api.api_response
    questions = quiz_data.get('qcm', []) + quiz_data.get('vrai_faux', [])
    total_questions = len(questions)
    time_limit = quiz_api.time_limit_minutes * 60  # en secondes

    # Timer : début de session
    if request.GET.get('start') == '1':
        request.session.pop('quiz_start_time', None)
        request.session.pop('quiz_api_progress', None)
        request.session.pop('quiz_api_score', None)
        request.session.pop('quiz_api_answers', None)

    if 'quiz_start_time' not in request.session:
        request.session['quiz_start_time'] = timezone.now().timestamp()
        request.session['quiz_api_progress'] = 0
        request.session['quiz_api_score'] = 0
        request.session['quiz_api_answers'] = []

    elapsed = int(timezone.now().timestamp() - request.session['quiz_start_time'])
    remaining = max(0, time_limit - elapsed)
    current_index = request.session.get('quiz_api_progress', 0)
    score = request.session.get('quiz_api_score', 0)
    answers = request.session.get('quiz_api_answers', [])

    # Si temps écoulé ou toutes questions répondues
    if remaining == 0 or current_index >= total_questions:
        # Créer l'enregistrement de tentative
        attempt = QuizAPIAttempt.objects.create(
            user=request.user,
            quiz_api=quiz_api,
            status='completed',
            score=score,
            total_questions=total_questions,
            correct_answers=score,
            time_taken_minutes=elapsed // 60,
            answers=answers,
            completed_at=timezone.now()
        )
        
        # Nettoyer la session
        request.session.pop('quiz_start_time', None)
        request.session.pop('quiz_api_progress', None)
        request.session.pop('quiz_api_score', None)
        request.session.pop('quiz_api_answers', None)
        
        return render(request, 'learning/quiz_api_result.html', {
            'quiz_api': quiz_api,
            'score': score,
            'total': total_questions,
            'answers': answers,
            'timeout': remaining == 0,
            'attempt': attempt,
        })

    question = questions[current_index]
    feedback = None
    correct = None

    if request.method == 'POST':
        user_answer = request.POST.get('answer')
        # Correction QCM
        if 'R' in question and 'a' in question:
            correct = (user_answer == question['R'])
        # Correction vrai/faux
        elif 'R' in question and isinstance(question['R'], bool):
            correct = (str(user_answer).lower() == str(question['R']).lower())
        else:
            correct = False
        feedback = 'Bonne réponse !' if correct else 'Mauvaise réponse.'
        # Mise à jour score et progression
        if correct:
            score += 1
        answers.append({'q': question.get('q'), 'user': user_answer, 'correct': correct, 'expected': question.get('R')})
        current_index += 1
        # Sauvegarder progression
        request.session['quiz_api_progress'] = current_index
        request.session['quiz_api_score'] = score
        request.session['quiz_api_answers'] = answers
        # Rediriger pour afficher la question suivante (PRG pattern)
        return redirect('learning:quiz_api_attempt', quiz_id=quiz_id)

    return render(request, 'learning/quiz_api_attempt.html', {
        'quiz_api': quiz_api,
        'question': question,
        'index': current_index + 1,
        'total': total_questions,
        'remaining': remaining,
        'score': score,
        'feedback': feedback,
    })


@login_required
def test_email_notification(request):
    """Vue pour tester l'envoi d'emails de rappel"""
    if request.method == 'POST':
        try:
            # Envoyer un email de test à l'utilisateur connecté
            success = send_revision_reminder_email(request.user, "Test de notification")
            
            if success:
                messages.success(request, 'Email de test envoyé avec succès ! Vérifiez votre boîte de réception.')
            else:
                messages.error(request, 'Erreur lors de l\'envoi de l\'email. Vérifiez que vous avez un email valide dans votre profil.')
                
        except Exception as e:
            messages.error(request, f'Erreur : {str(e)}')
    
    return render(request, 'learning/test_email.html')