from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ('username', 'email', 'first_name', 'last_name', 'employee_id', 'employment')
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
        ('Employment info', {'fields': ('employee_id', 'employment')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'is_manager')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
