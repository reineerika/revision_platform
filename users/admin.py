# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile, StudySession


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)


@admin.register(StudySession)
class StudySessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'date', 'duration_minutes', 'questions_answered', 'correct_answers', 'points_earned']
    list_filter = ['date', 'user']
    search_fields = ['user__username']
    readonly_fields = ['created_at']
    ordering = ['-date']


# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
