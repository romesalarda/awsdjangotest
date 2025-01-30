from django.db import models
from django.contrib.auth import get_user_model

class Profile(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)  # Optional title for the image
    profile_picture = models.ImageField(upload_to='images/')  # Stores images in MEDIA_ROOT/images/
    uploaded_at = models.DateTimeField(auto_now_add=True)  # Automatically set the upload timestamp
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)

    def __str__(self):
        return self.name or f"Profile {self.id}"    