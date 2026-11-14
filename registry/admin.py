from django.contrib import admin

from .models import Fight, FightEvent, Job, Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'age', 'rank', 'health', 'key']
    list_filter = ['rank']
    search_fields = ['name']


class FightEventInline(admin.TabularInline):
    model = FightEvent
    extra = 0


@admin.register(Fight)
class FightAdmin(admin.ModelAdmin):
    list_display = ['id', 'batch', 'blue', 'red', 'status', 'winner']
    list_filter = ['status', 'batch']
    inlines = [FightEventInline]


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ['kind', 'batch', 'status', 'attempts', 'updated_at']
    list_filter = ['kind', 'status']
