import os
import textract
from django.conf import settings
from django.core.files.storage import default_storage
from .models import Document
import logging

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