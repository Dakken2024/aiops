from django.contrib import admin
from .models import User, SystemConfig, Plugin, Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "plan", "domain", "created_at", "updated_at")
    list_filter = ("plan",)
    search_fields = ("name", "domain")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Plugin)
class PluginAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "is_enabled", "created_at", "updated_at")
    list_filter = ("type", "is_enabled")
    search_fields = ("name", "path")
    list_editable = ("is_enabled",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "type", "path", "is_enabled")}),
        ("配置", {"fields": ("config",)}),
        ("时间信息", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


admin.site.register(User)
admin.site.register(SystemConfig)
