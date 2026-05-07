from django.contrib import admin

from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ["id", "notification_type", "recipient", "backend", "success", "created_at"]
    list_filter = ["notification_type", "backend", "success"]
    search_fields = ["recipient__email", "subject"]
    readonly_fields = ["id", "recipient", "notification_type", "backend", "subject",
                       "success", "related_flag_id", "error_message", "created_at"]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
