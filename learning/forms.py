from django import forms
from django.core.exceptions import ValidationError
from .models import Document, Quiz
from .utils import validate_file_size, validate_file_type, get_file_type


class DocumentUploadForm(forms.ModelForm):
    """Form for uploading study documents"""
    
    class Meta:
        model = Document
        fields = ['title', 'description', 'file']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter document title',
                'required': True
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Enter document description (optional)'
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.docx,.txt,.pptx',
                'required': True
            })
        }
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if not file:
            raise ValidationError("Please select a file to upload.")
        
        try:
            # Validate file size
            validate_file_size(file)
            
            # Validate file type
            validate_file_type(file)
            
            return file
            
        except ValueError as e:
            raise ValidationError(str(e))
    
    def save(self, commit=True):
        document = super().save(commit=False)
        
        # Set document type based on file extension
        if document.file:
            document.document_type = get_file_type(document.file.name)
        
        if commit:
            document.save()
        
        return document


class QuizGenerationForm(forms.ModelForm):
    """Form for generating quizzes from documents"""
    
    num_questions = forms.IntegerField(
        min_value=5,
        max_value=50,
        initial=10,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '5',
            'max': '50'
        }),
        help_text="Number of questions to generate (5-50)"
    )
    
    class Meta:
        model = Quiz
        fields = ['title', 'description', 'difficulty', 'time_limit_minutes']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter quiz title',
                'required': True
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter quiz description (optional)'
            }),
            'difficulty': forms.Select(attrs={
                'class': 'form-control'
            }),
            'time_limit_minutes': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '5',
                'max': '180',
                'value': '30'
            })
        }


class DocumentSearchForm(forms.Form):
    """Form for searching documents"""
    
    query = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search documents...',
            'type': 'search'
        })
    )
    
    document_type = forms.ChoiceField(
        choices=[('', 'All Types')] + Document.DOCUMENT_TYPES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    
    sort_by = forms.ChoiceField(
        choices=[
            ('created_at', 'Date Created (Newest)'),
            ('-created_at', 'Date Created (Oldest)'),
            ('title', 'Title (A-Z)'),
            ('-title', 'Title (Z-A)'),
            ('word_count', 'Word Count (Low-High)'),
            ('-word_count', 'Word Count (High-Low)'),
        ],
        initial='created_at',
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )


class BulkDocumentActionForm(forms.Form):
    """Form for bulk actions on documents"""
    
    ACTION_CHOICES = [
        ('delete', 'Delete Selected'),
        ('reprocess', 'Reprocess Text Extraction'),
        ('generate_quiz', 'Generate Quiz from Selected'),
    ]
    
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    
    selected_documents = forms.ModelMultipleChoiceField(
        queryset=Document.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=True
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            self.fields['selected_documents'].queryset = Document.objects.filter(
                uploaded_by=user
            ).order_by('-created_at')

