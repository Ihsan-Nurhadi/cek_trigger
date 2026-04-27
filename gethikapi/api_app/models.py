from django.db import models
from django.core.exceptions import ValidationError

MAX_SITES = 2
MAX_NOTIFICATIONS = 20


class CameraSite(models.Model):
    name       = models.CharField(max_length=100)
    ip         = models.CharField(max_length=64)
    port       = models.IntegerField(default=80)
    username   = models.CharField(max_length=64)
    password   = models.CharField(max_length=128)
    track_id   = models.CharField(max_length=16, default='1')
    lat        = models.FloatField(default=0.0)
    lng        = models.FloatField(default=0.0)
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def clean(self):
        # Hanya cek saat membuat site baru (bukan update)
        if not self.pk:
            if CameraSite.objects.count() >= MAX_SITES:
                raise ValidationError(
                    f'Maksimal {MAX_SITES} site kamera diperbolehkan.'
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} ({self.ip})'


class MotionNotification(models.Model):
    EVENT_CHOICES = [
        ('motion_start', 'Motion Start'),
        ('motion_stop',  'Motion Stop'),
    ]

    site      = models.ForeignKey(
        CameraSite, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='notifications'
    )
    site_name = models.CharField(max_length=100, default='')
    channel   = models.CharField(max_length=16, default='1')
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    timestamp  = models.DateTimeField(auto_now_add=True)
    is_read    = models.BooleanField(default=False)

    class Meta:
        ordering = ['-timestamp']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Auto-cap: hapus yang terlama jika total > MAX_NOTIFICATIONS
        qs = MotionNotification.objects.order_by('-timestamp')
        ids_to_keep = list(qs.values_list('id', flat=True)[:MAX_NOTIFICATIONS])
        MotionNotification.objects.exclude(id__in=ids_to_keep).delete()

    def __str__(self):
        return f'[{self.event_type}] {self.site_name} ch{self.channel} @ {self.timestamp}'


import os
from django.utils import timezone
from datetime import timedelta

from django.conf import settings

class SnapshotHistory(models.Model):
    TRIGGER_CHOICES = [
        ('CAMERA', 'Camera Motion'),
        ('PIR_1', 'PIR Sensor 1'),
        ('PIR_2', 'PIR Sensor 2'),
        ('PIR_3', 'PIR Sensor 3'),
        ('PIR_4', 'PIR Sensor 4'),
    ]
    
    site = models.ForeignKey(CameraSite, on_delete=models.CASCADE, related_name='snapshots')
    trigger_source = models.CharField(max_length=20, choices=TRIGGER_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    image_path = models.CharField(max_length=255) # We will store the path or URL relative to MEDIA_ROOT
    
    class Meta:
        ordering = ['-timestamp']
        
    def delete(self, *args, **kwargs):
        # Auto-delete file format from disk
        if self.image_path:
            # We assume image_path is relative to MEDIA_ROOT (e.g. "snapshots/filename.jpg")
            media_dir = getattr(settings, 'MEDIA_ROOT', os.path.join(settings.BASE_DIR, 'media'))
            full_path = os.path.join(media_dir, self.image_path)
            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                except Exception as e:
                    pass
        super().delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Hapus data yang lebih tua dari 2 hari
        cutoff_date = timezone.now() - timedelta(days=2)
        old_snapshots = SnapshotHistory.objects.filter(timestamp__lt=cutoff_date)
        for snap in old_snapshots:
            snap.delete() # Trigger file deletion

    def __str__(self):
        return f'{self.trigger_source} @ {self.timestamp}'

