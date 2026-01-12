from management.models import Room, Amenity# 1. Create Standard Amenitiesamenities_list = ['Toothbrush', 'TV', 'Ref', 'Towel', 'Pillow', 'WiFi', 'Aircon']db_amenities = []for name in amenities_list:    obj, created = Amenity.objects.get_or_create(name=name)    db_amenities.append(obj)    if created:
    print(f"Created Amenity: {name}")

# 2. Define Hardcoded Room Data (From views.py)
ROOM_DATA = {
    '1st Floor': [
        {'id': '1A', 'price': 2350},
        {'id': '1B', 'price': 2050},
        {'id': '1C', 'price': 2450},
        {'id': '1D', 'price': 1750},
    ],
    '2nd Floor': [
        {'id': '2A', 'price': 1115},
        {'id': '2B', 'price': 1115},
        {'id': '2C', 'price': 1115},
        {'id': '2D', 'price': 1115},
        {'id': '2E', 'price': 1115},
        {'id': '2F', 'price': 1115},
        {'id': '2G', 'price': 2250},
        {'id': '2H', 'price': 1450},
    ],
    '3rd Floor': [
        {'id': '3A', 'price': 1115},
        {'id': '3B', 'price': 1115},
        {'id': '3C', 'price': 1115},
        {'id': '3D', 'price': 1115},
        {'id': '3E', 'price': 1115},
        {'id': '3F', 'price': 1115},
        {'id': '3G', 'price': 2350},
        {'id': '3H', 'price': 1450},
    ]
}

# 3. Create Rooms and Link Amenities
count = 0
for floor, rooms in ROOM_DATA.items():
    for r in rooms:
        room, created = Room.objects.get_or_create(
            number=r['id'],
            defaults={
                'floor': floor,
                'price': r['price'],
                'capacity': 2 # Default pax
            }
        )
        
        # Link all standard amenities to this room
        room.amenities.set(db_amenities)
        room.save()
        
        action = "Created" if created else "Updated"
        print(f"{action} Room {room.number} ({floor}) - ₱{room.price}")
        count += 1

print(f"\nSuccessfully migrated {count} rooms to the database!")