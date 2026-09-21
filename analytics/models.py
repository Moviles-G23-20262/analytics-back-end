import uuid
from django.db import models
from django.contrib.postgres.fields import ArrayField

# ==========================================
# ENUMS
# ==========================================

class MaterialCondition(models.TextChoices):
    NEW = 'NEW', 'New'
    LIKE_NEW = 'LIKE_NEW', 'Like New'
    GOOD = 'GOOD', 'Good'
    FAIR = 'FAIR', 'Fair'

class MaterialStatus(models.TextChoices):
    AVAILABLE = 'AVAILABLE', 'Available'
    RESERVED = 'RESERVED', 'Reserved'
    SOLD = 'SOLD', 'Sold'

class MaterialCategory(models.TextChoices):
    BOOKS = 'BOOKS', 'Books'
    CALCULATORS = 'CALCULATORS', 'Calculators'
    LAB_EQUIPMENT = 'LAB_EQUIPMENT', 'Lab Equipment'
    FURNITURE = 'FURNITURE', 'Furniture'
    OTHER = 'OTHER', 'Other'

class NotificationType(models.TextChoices):
    SMART_MATCH = 'SMART_MATCH', 'Smart Match'
    OTHER = 'OTHER', 'Other'

class AnalyticsEventType(models.TextChoices):
    LISTING_VIEW = 'LISTING_VIEW', 'Listing View'
    SEARCH = 'SEARCH', 'Search'
    CONTACT_SELLER = 'CONTACT_SELLER', 'Contact Seller'
    WISHLIST_ADD = 'WISHLIST_ADD', 'Wishlist Add'
    WISHLIST_REMOVE = 'WISHLIST_REMOVE', 'Wishlist Remove'
    NOTIFICATION_SENT = 'NOTIFICATION_SENT', 'Notification Sent'
    NOTIFICATION_OPENED = 'NOTIFICATION_OPENED', 'Notification Opened'

# ==========================================
# MODELS
# ==========================================

class User(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    password_hash = models.CharField(max_length=255, db_column='passwordHash')
    full_name = models.CharField(max_length=255, db_column='fullName')
    major = models.CharField(max_length=255)
    faculty = models.CharField(max_length=255, null=True, blank=True)
    rating = models.FloatField(default=0)
    created_at = models.DateTimeField(db_column='createdAt')

    class Meta:
        managed = False
        db_table = 'User'


class Material(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField()
    course_code = models.CharField(max_length=255, db_column='courseCode', null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    condition = models.CharField(max_length=50, choices=MaterialCondition.choices, null=True, blank=True)
    status = models.CharField(max_length=50, choices=MaterialStatus.choices, default=MaterialStatus.AVAILABLE)
    edition = models.CharField(max_length=255, null=True, blank=True)
    model_name = models.CharField(max_length=255, db_column='model', null=True, blank=True)
    image_urls = ArrayField(models.CharField(max_length=500), db_column='imageUrls', default=list)
    seller = models.ForeignKey(User, on_delete=models.DO_NOTHING, db_column='sellerId', related_name='materials')
    category = models.CharField(max_length=50, choices=MaterialCategory.choices)
    
    created_at = models.DateTimeField(db_column='createdAt')
    updated_at = models.DateTimeField(db_column='updatedAt')

    class Meta:
        managed = False
        db_table = 'Material'


class ChatRoom(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    material = models.ForeignKey(Material, on_delete=models.DO_NOTHING, db_column='materialId', related_name='chat_rooms')
    buyer = models.ForeignKey(User, on_delete=models.DO_NOTHING, db_column='buyerId', related_name='buyer_chat_rooms')
    seller = models.ForeignKey(User, on_delete=models.DO_NOTHING, db_column='sellerId', related_name='seller_chat_rooms')
    created_at = models.DateTimeField(db_column='createdAt')

    class Meta:
        managed = False
        db_table = 'ChatRoom'


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chat_room = models.ForeignKey(ChatRoom, on_delete=models.DO_NOTHING, db_column='chatRoomId', related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.DO_NOTHING, db_column='senderId', related_name='sent_messages')
    content = models.TextField()
    is_read = models.BooleanField(db_column='isRead', default=False)
    created_at = models.DateTimeField(db_column='createdAt')

    class Meta:
        managed = False
        db_table = 'Message'


class Exchange(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    material = models.OneToOneField(Material, on_delete=models.DO_NOTHING, db_column='materialId', related_name='exchange')
    buyer = models.ForeignKey(User, on_delete=models.DO_NOTHING, db_column='buyerId', related_name='buyer_exchanges')
    seller = models.ForeignKey(User, on_delete=models.DO_NOTHING, db_column='sellerId', related_name='seller_exchanges')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    completed_at = models.DateTimeField(db_column='completedAt')

    class Meta:
        managed = False
        db_table = 'Exchange'


class WishlistItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING, db_column='userId', related_name='wishlist_items')
    material = models.ForeignKey(Material, on_delete=models.DO_NOTHING, db_column='materialId', related_name='wishlisted_by')
    created_at = models.DateTimeField(db_column='createdAt')

    class Meta:
        managed = False
        db_table = 'WishlistItem'


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING, db_column='userId', related_name='notifications')
    material = models.ForeignKey(Material, on_delete=models.DO_NOTHING, db_column='materialId', null=True, blank=True)
    type = models.CharField(max_length=50, choices=NotificationType.choices)
    sent_at = models.DateTimeField(db_column='sentAt')
    opened_at = models.DateTimeField(db_column='openedAt', null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'Notification'


class AnalyticsEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING, db_column='userId', null=True, blank=True, related_name='analytics_events')
    material = models.ForeignKey(Material, on_delete=models.DO_NOTHING, db_column='materialId', null=True, blank=True)
    event_type = models.CharField(max_length=50, choices=AnalyticsEventType.choices, db_column='eventType')
    metadata = models.JSONField(null=True, blank=True)
    occurred_at = models.DateTimeField(db_column='occurredAt')

    class Meta:
        managed = False
        db_table = 'AnalyticsEvent'