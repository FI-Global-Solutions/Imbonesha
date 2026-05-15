from django.contrib import admin

from .models import MobileNotification, NotificationLog


@admin.register(MobileNotification)
class MobileNotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "recipient", "notification_type", "is_read", "created_at"]
    list_filter = ["is_read", "notification_type"]
    search_fields = ["recipient__email", "title", "body"]
    readonly_fields = ["id", "recipient", "title", "body", "notification_type",
                       "related_flag", "is_read", "read_at", "created_at"]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


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
