from django.db import models


class UploadedClip(models.Model):
    r2_key = models.CharField(max_length=500, unique=True, db_index=True)
    video_id = models.CharField(max_length=100, db_index=True)
    channel_id = models.CharField(max_length=100, db_index=True)
    youtube_video_id = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'uploaded_clips'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.r2_key
