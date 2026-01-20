from django.contrib import admin
from .models import GuestRegistration, AdminSettings, Room, Amenity

@admin.register(GuestRegistration)
class GuestRegistrationAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'room_number', 'status', 'created_at')
    list_filter = ('status', 'source', 'created_at')
    search_fields = ('last_name', 'first_name', 'booking_id')

@admin.register(AdminSettings)
class AdminSettingsAdmin(admin.ModelAdmin):
    list_display = ('pin_code', 'updated_at')
    # Prevent deletion or adding new rows to enforce singleton pattern in UI
    def has_add_permission(self, request):
        return not AdminSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('number', 'floor', 'price', 'capacity', 'status')
    list_filter = ('floor', 'status')
    search_fields = ('number',)
    filter_horizontal = ('amenities',)

@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ('name', 'icon')
    search_fields = ('name',)