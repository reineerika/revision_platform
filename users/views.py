# Create your views here.
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.contrib.auth.models import User
from .models import UserProfile


def signup(request):
    """User registration view"""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Create user profile
            UserProfile.objects.create(user=user)
            
            # Log the user in
            login(request, user)
            messages.success(request, 'Account created successfully!')
            return redirect('learning:dashboard')
    else:
        form = UserCreationForm()
    
    return render(request, 'registration/signup.html', {'form': form})


@login_required
def profile(request):
    """User profile view"""
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)
    
    return render(request, 'users/profile.html', {'profile': profile})


@login_required
def edit_profile(request):
    """Edit user profile view"""
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)
    
    if request.method == 'POST':
        # Handle profile update
        bio = request.POST.get('bio', '')
        preferred_difficulty = request.POST.get('preferred_difficulty', 'medium')
        email = request.POST.get('email', '').strip()
        
        # Validate email if provided
        if email:
            from django.core.validators import EmailValidator
            from django.core.exceptions import ValidationError
            try:
                EmailValidator()(email)
                request.user.email = email
                request.user.save()
            except ValidationError:
                messages.error(request, 'Veuillez entrer une adresse email valide.')
                return render(request, 'users/edit_profile.html', {'profile': profile})
        
        profile.bio = bio
        profile.preferred_difficulty = preferred_difficulty
        profile.save()
        
        messages.success(request, 'Profil mis à jour avec succès!')
        return redirect('users:profile')
    
    return render(request, 'users/edit_profile.html', {'profile': profile})