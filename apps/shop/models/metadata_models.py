from django.db import models
from django.utils.translation import gettext_lazy as _
import uuid

class ProductCategory(models.Model):
    '''
    Model representing a product category.
    '''
    title = models.CharField(_("name of category"))
    description = models.TextField(_("category description"),max_length=400, blank=True, null=True)

    class Meta:
        verbose_name_plural = "Product categories"

    def __str__(self) -> str:
        return self.title

class ProductMaterial(models.Model):
    '''
    Model representing a material that a product can be made of.
    '''
    title = models.CharField(_("name of material"))
    description = models.TextField(_("material description"),max_length=400, blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Product materials"
    
    def __str__(self) -> str:
        return self.title

class ProductImage(models.Model):
    '''
    Model representing an image of a product. Many can be uploaded per product.
    '''
    uuid = models.UUIDField(_("product image uuid"), default=uuid.uuid4, editable=False, primary_key=True)
    image = models.ImageField(upload_to='event-product-images/')

    product = models.ForeignKey("shop.EventProduct", on_delete=models.CASCADE, verbose_name=_("product linked to"), related_name="images")

    def __str__(self) -> str:
        return self.image.name