from django.contrib import admin
from .models import LogSource, LogEntry, LogPattern, LogAlertRule, LogAlert

admin.site.register(LogSource)
admin.site.register(LogEntry)
admin.site.register(LogPattern)
admin.site.register(LogAlertRule)
admin.site.register(LogAlert)