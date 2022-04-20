from django.contrib import admin

from .models import DownloadLog

class DownloadLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'resource_id', 'resource_name', 'package_id', 'package_name', 'requested_file_format', 'ip_address', 'host', 'remote_host', 'server_name']

    search_fields = list_display
    ordering = ['timestamp']

admin.site.register(DownloadLog, DownloadLogAdmin)
