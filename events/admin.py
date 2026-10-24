from django.contrib import admin
from .models import EventLog, RejectedEvent

class ReadOnlyAdminMixin:
    """Запрещает любые изменения данных через админ-панель"""
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

@admin.register(EventLog)
class EventLogAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('seq', 'event_type', 'client_id', 'event_time', 'source', 'received_at')
    list_filter = ('event_type', 'source')
    search_fields = ('event_id', 'client_id', 'account_id')
    readonly_fields = ('seq', 'event_id', 'event_type', 'event_time', 'client_id', 'account_id', 'payload', 'source', 'received_at')

@admin.register(RejectedEvent)
class RejectedEventAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('received_at', 'reason', 'topic', 'partition', 'offset')
    search_fields = ('reason', 'raw')
    readonly_fields = ('raw', 'reason', 'topic', 'partition', 'offset', 'received_at')
