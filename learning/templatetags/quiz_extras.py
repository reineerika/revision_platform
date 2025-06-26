from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key"""
    if dictionary and key:
        return dictionary.get(str(key))
    return None


@register.filter
def percentage(value, total):
    """Calculate percentage"""
    if total and total > 0:
        return round((value / total) * 100, 1)
    return 0


@register.filter
def duration_format(minutes):
    """Format duration in minutes to human readable format"""
    if not minutes:
        return "0 minutes"
    
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    
    hours = minutes // 60
    remaining_minutes = minutes % 60
    
    if remaining_minutes == 0:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    
    return f"{hours} hour{'s' if hours != 1 else ''} {remaining_minutes} minute{'s' if remaining_minutes != 1 else ''}"


@register.filter
def score_color(score):
    """Return Bootstrap color class based on score"""
    if score >= 90:
        return "success"
    elif score >= 75:
        return "primary"
    elif score >= 60:
        return "warning"
    else:
        return "danger"


@register.filter
def mastery_badge(level):
    """Return Bootstrap badge class for mastery level"""
    badges = {
        'expert': 'bg-success',
        'advanced': 'bg-primary',
        'intermediate': 'bg-warning',
        'beginner': 'bg-secondary',
    }
    return badges.get(level, 'bg-secondary')


@register.simple_tag
def question_type_icon(question_type):
    """Return icon for question type"""
    icons = {
        'multiple_choice': 'fas fa-list-ul',
        'true_false': 'fas fa-check-circle',
        'short_answer': 'fas fa-edit',
        'fill_blank': 'fas fa-fill-drip',
    }
    return icons.get(question_type, 'fas fa-question')


@register.inclusion_tag('learning/partials/progress_bar.html')
def progress_bar(current, total, show_percentage=True):
    """Render a progress bar"""
    percentage = percentage(current, total) if total > 0 else 0
    return {
        'current': current,
        'total': total,
        'percentage': percentage,
        'show_percentage': show_percentage,
    }