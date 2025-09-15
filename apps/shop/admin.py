from django.contrib import admin
from apps.shop.models.payments import *
from apps.shop.models.metadata_models import *

@admin.register(ProductPaymentMethod)
class ProductPaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("method", "account_name", "is_active", "created_at")
    list_filter = ("method", "is_active")
    search_fields = ("method", "account_name", "account_number", "iban", "swift_bic")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)

@admin.register(ProductPaymentPackage)
class ProductPaymentPackageAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "currency", "is_active", "available_from", "available_until")
    list_filter = ("is_active", "currency")
    search_fields = ("name", "description")
    filter_horizontal = ("products",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)

@admin.register(ProductPayment)
class ProductPaymentAdmin(admin.ModelAdmin):
    list_display = ("user", "cart", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency", "created_at")
    search_fields = ("user__email", "cart__uuid", "stripe_payment_intent")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)
    
@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("title", "description")
    search_fields = ("title", "description")
    ordering = ("title",)

@admin.register(ProductMaterial)
class ProductMaterialAdmin(admin.ModelAdmin):
    list_display = ("title", "description")
    search_fields = ("title", "description")
    ordering = ("title",)

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("uuid", "product", "image")
    search_fields = ("product__title", "image")
    ordering = ("-uuid",)
    
@admin.register(EventProduct)
class EventProductAdmin(admin.ModelAdmin):
    list_display = ("title", "event", "seller", "price", "discount")
    list_filter = ("event", "seller", "categories", "materials")
    search_fields = ("title", "description", "seller__email")
    filter_horizontal = ("categories", "materials")
    ordering = ("title",)

@admin.register(EventCart)
class EventCartAdmin(admin.ModelAdmin):
    list_display = ("uuid", "user", "event", "total", "shipping_cost", "approved", "submitted", "active", "created", "updated")
    list_filter = ("approved", "submitted", "active", "event")
    search_fields = ("user__email", "event__name", "notes", "shipping_address")
    ordering = ("-created",)

@admin.register(EventProductOrder)
class EventProductOrderAdmin(admin.ModelAdmin):
    list_display = ("product", "cart", "quantity", "added", "price_at_purchase", "discount_applied", "status")
    list_filter = ("status", "product", "cart")
    search_fields = ("product__title", "cart__user__email")
    ordering = ("-added",)
    
@admin.register(ProductSize)
class ProductSizeAdmin(admin.ModelAdmin):
    list_display = ("product", "size", "price_modifier")
    list_filter = ("size", "product")
    search_fields = ("product__title",)
    ordering = ("product", "size")